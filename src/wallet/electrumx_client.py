"""
ElectrumX JSON-RPC Client für Doichain.

Kommuniziert über SSL/TCP mit ElectrumX-Servern für:
- UTXO-Abfragen
- Transaktions-Broadcast
- Blockchain-Header
- Adress-Saldo
"""

import json
import socket
import ssl
import time
import hashlib
from typing import Optional

from .doichain_network import MAINNET


class ElectrumXClient:
    """
    JSON-RPC Client für ElectrumX-Server (Doichain).
    
    Verwendet das Electrum-Protokoll v1.4 über SSL.
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        network: Optional[dict] = None,
        timeout: int = 10,
    ):
        self.network = network or MAINNET
        self.timeout = timeout
        self._socket: Optional[socket.socket] = None
        self._ssl_socket: Optional[ssl.SSLSocket] = None
        self._request_id = 0
        self._connected = False

        # Server aus Netzwerk-Config oder Parameter
        if host and port:
            self.servers = [{"host": host, "port": port, "protocol": "ssl"}]
        else:
            self.servers = self.network.get("electrum_servers", [])

    def connect(self) -> bool:
        """
        Verbindet zum ersten erreichbaren ElectrumX-Server.
        
        Returns:
            True bei erfolgreicher Verbindung
        """
        for server in self.servers:
            try:
                host = server["host"]
                port = server["port"]
                
                # TCP Socket
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self.timeout)

                # SSL Kontext (self-signed Zertifikate akzeptieren)
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                self._ssl_socket = ctx.wrap_socket(self._socket, server_hostname=host)
                self._ssl_socket.connect((host, port))
                self._connected = True

                # Server-Version handshake
                result = self._call("server.version", ["doichain-wallet", "1.4"])
                if result:
                    return True

            except (socket.error, ssl.SSLError, OSError, ConnectionRefusedError) as e:
                self._cleanup()
                continue

        return False

    def disconnect(self):
        """Verbindung trennen."""
        self._cleanup()

    def _cleanup(self):
        """Räumt Socket-Ressourcen auf."""
        try:
            if self._ssl_socket:
                self._ssl_socket.close()
        except Exception:
            pass
        try:
            if self._socket:
                self._socket.close()
        except Exception:
            pass
        self._ssl_socket = None
        self._socket = None
        self._connected = False

    def _call(self, method: str, params: list = None) -> any:
        """
        JSON-RPC Aufruf an den ElectrumX-Server.
        
        Args:
            method: RPC-Methode (z.B. "blockchain.scripthash.get_balance")
            params: Parameter-Liste
        
        Returns:
            Ergebnis des Aufrufs
        
        Raises:
            ConnectionError: Bei Verbindungsproblemen
            RuntimeError: Bei RPC-Fehlern
        """
        if not self._ssl_socket:
            raise ConnectionError("Nicht verbunden. Zuerst connect() aufrufen.")

        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self._request_id,
            "method": method,
            "params": params or [],
        }

        # Request senden
        msg = json.dumps(request) + "\n"
        self._ssl_socket.sendall(msg.encode("utf-8"))

        # Response empfangen
        response_data = b""
        while True:
            chunk = self._ssl_socket.recv(4096)
            if not chunk:
                raise ConnectionError("Verbindung geschlossen")
            response_data += chunk
            if b"\n" in response_data:
                break

        # Erste Zeile parsen (eine Antwort pro Zeile)
        line = response_data.split(b"\n")[0]
        response = json.loads(line.decode("utf-8"))

        if "error" in response and response["error"]:
            raise RuntimeError(
                f"ElectrumX Fehler: {response['error']}"
            )

        return response.get("result")

    # ========================================================
    # Electrum Scripthash
    # ========================================================

    @staticmethod
    def address_to_scripthash(address: str) -> str:
        """
        Konvertiert eine Doichain-Adresse in einen Electrum-Scripthash.
        
        Electrum verwendet den SHA256-Hash des P2PKH-ScriptPubKey
        in reversed Byte-Reihenfolge als Identifier.
        
        Args:
            address: Doichain Base58Check-Adresse
        
        Returns:
            Hex-String des Scripthash
        """
        from .crypto_utils import base58check_decode

        version, pubkey_hash = base58check_decode(address)

        # P2PKH ScriptPubKey: OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG
        script = bytes([0x76, 0xA9, 0x14]) + pubkey_hash + bytes([0x88, 0xAC])

        # SHA256 und Byte-Reihenfolge umkehren
        h = hashlib.sha256(script).digest()
        return h[::-1].hex()

    # ========================================================
    # Öffentliche API-Methoden
    # ========================================================

    def get_balance(self, address: str) -> dict:
        """
        Gibt den Saldo einer Adresse zurück.
        
        Args:
            address: Doichain-Adresse
        
        Returns:
            Dict mit 'confirmed' und 'unconfirmed' (in Satoshis)
        """
        scripthash = self.address_to_scripthash(address)
        result = self._call("blockchain.scripthash.get_balance", [scripthash])
        return {
            "confirmed": result.get("confirmed", 0),
            "unconfirmed": result.get("unconfirmed", 0),
            "total": result.get("confirmed", 0) + result.get("unconfirmed", 0),
        }

    def get_utxos(self, address: str) -> list:
        """
        Gibt die unverbrauchten Transaktionsausgaben (UTXOs) einer Adresse zurück.
        
        Args:
            address: Doichain-Adresse
        
        Returns:
            Liste von UTXOs: [{"tx_hash": ..., "tx_pos": ..., "value": ..., "height": ...}, ...]
        """
        scripthash = self.address_to_scripthash(address)
        return self._call("blockchain.scripthash.listunspent", [scripthash])

    def get_history(self, address: str) -> list:
        """
        Gibt die Transaktionshistorie einer Adresse zurück.
        
        Returns:
            Liste: [{"tx_hash": ..., "height": ...}, ...]
        """
        scripthash = self.address_to_scripthash(address)
        return self._call("blockchain.scripthash.get_history", [scripthash])

    def get_transaction(self, tx_hash: str, verbose: bool = True) -> dict:
        """
        Gibt eine Transaktion als Hex oder als Verbose-Dict zurück.
        
        Args:
            tx_hash: Transaktions-Hash (64 Hex-Zeichen)
            verbose: True für detaillierte Infos, False für Raw-Hex
        """
        return self._call("blockchain.transaction.get", [tx_hash, verbose])

    def get_raw_transaction(self, tx_hash: str) -> str:
        """Gibt die rohe Transaktion als Hex-String zurück."""
        return self._call("blockchain.transaction.get", [tx_hash, False])

    def broadcast_transaction(self, raw_tx_hex: str) -> str:
        """
        Sendet eine signierte Transaktion an das Netzwerk.
        
        Args:
            raw_tx_hex: Signierte Transaktion als Hex-String
        
        Returns:
            Transaktions-Hash bei Erfolg
        
        Raises:
            RuntimeError: Bei Ablehnung durch den Server
        """
        return self._call("blockchain.transaction.broadcast", [raw_tx_hex])

    def get_block_header(self, height: int) -> dict:
        """Gibt den Block-Header für eine bestimmte Höhe zurück."""
        return self._call("blockchain.block.header", [height])

    def get_tip(self) -> dict:
        """Gibt den aktuellen Blockchain-Tip (neuester Block) zurück."""
        return self._call("blockchain.headers.subscribe", [])

    def get_fee_estimate(self, target_blocks: int = 6) -> Optional[float]:
        """
        Schätzt die Transaktionsgebühr (DOI/kB).
        
        Args:
            target_blocks: Gewünschte Bestätigungszeit in Blöcken
        
        Returns:
            Geschätzte Gebühr in DOI/kB, oder None
        """
        try:
            result = self._call("blockchain.estimatefee", [target_blocks])
            if result and result > 0:
                return result
        except Exception:
            pass
        return None

    def server_version(self) -> list:
        """Gibt die Server-Version zurück."""
        return self._call("server.version", ["doichain-wallet", "1.4"])

    def ping(self) -> bool:
        """Prüft ob der Server erreichbar ist."""
        try:
            self._call("server.ping")
            return True
        except Exception:
            return False

    # ========================================================
    # Context Manager
    # ========================================================

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    @property
    def is_connected(self) -> bool:
        return self._connected
