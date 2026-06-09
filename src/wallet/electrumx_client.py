"""
ElectrumX JSON-RPC Client für Doichain.

Kommuniziert über SSL/TCP mit ElectrumX-Servern für:
- UTXO-Abfragen
- Transaktions-Broadcast
- Blockchain-Header
- Adress-Saldo

Sicherheits-Updates (v0.9.5):
  * TLS: Standardmäßig strikte CA- und Hostname-Validierung. Optionales
    Certificate-Pinning per SHA-256 Fingerprint. Klartext-CERT_NONE ist
    nur noch über expliziten Opt-out (ssl_strict=False) erreichbar – und
    wird bei jedem Verbindungsaufbau geloggt.
  * Scripthash unterstützt jetzt ALLE Adresstypen (P2PKH, P2SH, P2WPKH,
    P2WSH, P2TR) via crypto_utils.address_to_script_pubkey().
  * Saubere Puffer-basierte Empfangslogik (auch für große Antworten und
    nachfolgende Notifications).
  * Auto-Reconnect bei Verbindungsabbruch während eines Aufrufs.
"""

import hashlib
import json
import socket
import ssl
import sys
import threading
import time
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
        self._recv_buffer = b""
        self._current_server: Optional[dict] = None
        # Thread-Sicherheit: GUI ruft aus mehreren Threads auf. RLock, damit
        # _call() → _reconnect() → connect() im selben Thread nicht deadlockt.
        self._lock = threading.RLock()
        # Guard gegen Endlos-Rekursion connect → _call → _reconnect → connect.
        self._connecting = False
        # Letzter per Notification empfangener Blockchain-Tip
        # (blockchain.headers.subscribe), siehe _call().
        self._cached_tip: Optional[dict] = None

        # Server aus Netzwerk-Config oder Parameter
        if host and port:
            self.servers = [{"host": host, "port": port, "protocol": "ssl"}]
        else:
            self.servers = self.network.get("electrum_servers", [])

    # ========================================================
    # SSL-Kontext (gehärtet)
    # ========================================================

    @staticmethod
    def _normalize_fingerprint(fp: str) -> str:
        """Normalisiert einen SHA-256 Fingerprint (lowercase, ohne ':' / Leerzeichen)."""
        return fp.lower().replace(":", "").replace(" ", "")

    def _pinned_fingerprints_for_host(self, host: Optional[str]) -> set:
        """
        Gibt die gepinnten Fingerprints für einen bestimmten Host zurück.

        Bevorzugtes Format (per-Host, verhindert dass das Zertifikat von
        Server A für Server B akzeptiert wird):
            "ssl_pinned_fingerprints": {
                "white-snail-54.doi.works": ["ab12cd34..."],
                "itchy-jellyfish-89.doi.works": ["ef56..."],
            }

        Fallback (Legacy, klar dokumentiert): Eine flache Liste von
        Fingerprints. Diese gilt – wie bisher – für ALLE Hosts, da im
        Altformat keine Host-Zuordnung möglich ist. Neue Einträge sollten
        immer das Dict-Format verwenden.
        """
        pinned = self.network.get("ssl_pinned_fingerprints") or {}
        if isinstance(pinned, dict):
            # Per-Host Allowlist: nur die Fingerprints DIESES Hosts zählen.
            return {self._normalize_fingerprint(fp) for fp in (pinned.get(host) or [])}
        # Legacy-Fallback: flache Liste gilt für alle konfigurierten Hosts.
        return {self._normalize_fingerprint(fp) for fp in pinned}

    def _build_ssl_context(self, host: Optional[str] = None) -> ssl.SSLContext:
        """
        Baut einen SSL-Kontext entsprechend der Netzwerk-Konfiguration.

        Priorität:
          1. Gepinnte Fingerprints für den Host  → Pinning (Hostname-Check aus,
             CA-Check aus, dafür nach connect() Fingerprint-Vergleich).
          2. ssl_strict = True (Default)        → CA + Hostname strikt.
          3. ssl_strict = False                 → Validierung aus (UNSICHER).
        """
        pinned = self._pinned_fingerprints_for_host(host)
        strict = self.network.get("ssl_strict", True)

        ctx = ssl.create_default_context()

        if pinned:
            # Pinning übernimmt die Identitätsprüfung. CA-Chain darf ungültig sein
            # (self-signed), wir prüfen hinterher den Fingerprint.
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx

        if strict:
            # Strikte Validierung mit System-CAs (oder certifi, je nach Python-Build).
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED
            return ctx

        # Expliziter Opt-out: Validierung deaktiviert. Mit Warnhinweis.
        print(
            "⚠️  WARNUNG: TLS-Validierung deaktiviert (ssl_strict=False). "
            "Verbindung ist anfällig für Man-in-the-Middle-Angriffe.",
            file=sys.stderr,
        )
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _verify_pinned_fingerprint(
        self, ssl_socket: ssl.SSLSocket, host: Optional[str] = None
    ) -> bool:
        """
        Vergleicht den SHA-256 Fingerprint des Server-Zertifikats gegen die
        per-Host-Allowlist in network['ssl_pinned_fingerprints'].
        """
        pinned = self._pinned_fingerprints_for_host(host)
        if not pinned:
            return True  # Pinning für diesen Host nicht aktiv

        der_cert = ssl_socket.getpeercert(binary_form=True)
        if not der_cert:
            return False
        actual = hashlib.sha256(der_cert).hexdigest()
        return actual in pinned

    # ========================================================
    # Verbindung
    # ========================================================

    # TCP-Keepalive-Parameter. Default-OS-Werte (Windows: 2 Stunden Idle)
    # sind für ein interaktives Wallet zu lang. Mit diesen Werten erkennt
    # das Wallet eine tote Verbindung typischerweise binnen ca. 45 Sekunden
    # und der Auto-Reconnect in _call() greift transparent.
    KEEPALIVE_IDLE_SEC = 30      # Sekunden Idle vor erstem Probe
    KEEPALIVE_INTERVAL_SEC = 5   # Sekunden zwischen Probes
    KEEPALIVE_PROBES = 3         # Anzahl Probes ohne Antwort, bevor Verbindung tot ist

    @classmethod
    def _setup_keepalive(cls, sock: socket.socket) -> None:
        """
        Aktiviert TCP-Keepalive auf einem rohen TCP-Socket – plattformsicher.

        Muss aufgerufen werden BEVOR der Socket per SSL gewrappt wird. Schlägt
        eine plattformspezifische Option fehl, wird sie still übersprungen
        (auf alten Linux-Kerneln, restriktiven Sandboxes etc.).
        """
        # Basis-Option: funktioniert überall.
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except (OSError, AttributeError):
            return

        idle = cls.KEEPALIVE_IDLE_SEC
        intv = cls.KEEPALIVE_INTERVAL_SEC

        # Windows: SIO_KEEPALIVE_VALS akzeptiert Millisekunden.
        if hasattr(socket, "SIO_KEEPALIVE_VALS"):
            try:
                sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, idle * 1000, intv * 1000))
                return
            except (OSError, AttributeError):
                pass

        # Linux: TCP_KEEPIDLE / KEEPINTVL / KEEPCNT
        try:
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, idle)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, intv)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, cls.KEEPALIVE_PROBES)
        except (OSError, AttributeError):
            pass

        # macOS: TCP_KEEPALIVE (Sekunden Idle vor Probe)
        if hasattr(socket, "TCP_KEEPALIVE"):
            try:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, idle)
            except (OSError, AttributeError):
                pass

    def connect(self) -> bool:
        """
        Verbindet zum ersten erreichbaren ElectrumX-Server.

        Returns:
            True bei erfolgreicher Verbindung.
        """
        with self._lock:
            last_error: Optional[Exception] = None
            # Guard: Während des Handshakes darf _call() KEINEN Reconnect
            # auslösen, sonst entsteht Endlos-Rekursion
            # connect → _call → _reconnect → connect.
            self._connecting = True
            try:
                for server in self.servers:
                    try:
                        self._cleanup()
                        host = server["host"]
                        port = server["port"]

                        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        self._socket.settimeout(self.timeout)
                        # Tote/Idle-Verbindungen schnell erkennen (NAT-Timeouts etc.).
                        self._setup_keepalive(self._socket)

                        ctx = self._build_ssl_context(host)
                        if self._socket is None:
                            raise ConnectionError(
                                f"create_connection({host}:{port}) lieferte None"
                            )
                        self._ssl_socket = ctx.wrap_socket(self._socket, server_hostname=host)
                        self._ssl_socket.connect((host, port))

                        # Pinning prüfen, falls für diesen Host aktiv
                        if not self._verify_pinned_fingerprint(self._ssl_socket, host):
                            self._cleanup()
                            last_error = ssl.SSLError(
                                f"Certificate-Pinning fehlgeschlagen für {host}: "
                                f"Fingerprint nicht in ssl_pinned_fingerprints."
                            )
                            continue

                        self._connected = True
                        self._current_server = server
                        self._recv_buffer = b""

                        # Server-Version handshake – _retry=False, damit ein
                        # Fehlschlag hier keinen Reconnect (und damit erneutes
                        # connect()) auslöst.
                        result = self._call(
                            "server.version", ["doichain-wallet", "1.4"], _retry=False
                        )
                        if result:
                            return True

                    # RuntimeError (RPC-Fehlerantwort) und ValueError (inkl.
                    # json.JSONDecodeError) müssen ebenfalls zum Failover auf den
                    # nächsten Server führen, statt connect() abzubrechen.
                    except (socket.error, ssl.SSLError, OSError,
                            ConnectionRefusedError, ConnectionError,
                            RuntimeError, json.JSONDecodeError, ValueError) as e:
                        last_error = e
                        self._cleanup()
                        continue

                if last_error is not None:
                    print(f"⚠️  Kein ElectrumX-Server erreichbar. Letzter Fehler: {last_error}",
                          file=sys.stderr)
                # Keinen halb offenen Zustand zurücklassen.
                self._cleanup()
                return False
            finally:
                self._connecting = False

    def disconnect(self):
        """Verbindung trennen."""
        with self._lock:
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
        self._recv_buffer = b""

    def _reconnect(self) -> bool:
        """Versucht, die Verbindung wiederherzustellen."""
        with self._lock:
            if self._connecting:
                # Wir befinden uns bereits in connect() (Handshake) –
                # kein verschachtelter Reconnect (Endlos-Rekursions-Schutz).
                return False
            self._cleanup()
            return self.connect()

    # ========================================================
    # RPC
    # ========================================================

    # Obergrenze für den Empfangspuffer. Eine Zeile ohne '\n' jenseits dieser
    # Grenze ist entweder ein fehlerhafter/bösartiger Server oder ein
    # Protokollfehler – Verbindung wird zurückgesetzt.
    MAX_RECV_BUFFER = 16 * 1024 * 1024  # 16 MB

    def _call(self, method: str, params: list = None, _retry: bool = True) -> any:
        """
        JSON-RPC Aufruf an den ElectrumX-Server.

        Thread-sicher: Der komplette Sende-/Empfangszyklus läuft unter
        self._lock (RLock), damit GUI-Threads sich Request-IDs, Puffer und
        Socket nicht gegenseitig zerschießen.

        Antworten werden anhand der JSON-RPC 'id' dem Request zugeordnet.
        Asynchrone Server-Notifications (z.B. blockchain.headers.subscribe
        nach get_tip()) sowie veraltete Antworten werden NICHT als Ergebnis
        fehlinterpretiert, sondern verarbeitet (Tip-Cache) bzw. verworfen.

        Args:
            method: RPC-Methode (z.B. "blockchain.scripthash.get_balance").
            params: Parameter-Liste.
            _retry: intern – bei Verbindungsabbruch genau einmal neu verbinden.

        Returns:
            Ergebnis des Aufrufs.

        Raises:
            ConnectionError: Bei Verbindungsproblemen, die auch nach Reconnect bestehen.
            RuntimeError: Bei RPC-Fehlern vom Server.
        """
        with self._lock:
            if not self._ssl_socket:
                raise ConnectionError("Nicht verbunden. Zuerst connect() aufrufen.")

            self._request_id += 1
            request_id = self._request_id
            request = {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params or [],
            }
            msg = (json.dumps(request) + "\n").encode("utf-8")

            try:
                self._ssl_socket.sendall(msg)
                response = self._recv_response(request_id)
            except (socket.error, ssl.SSLError, ConnectionError, OSError) as e:
                # Einmaliger Reconnect-Versuch (in connect() unterdrückt
                # _reconnect() sich selbst, siehe self._connecting).
                if _retry and self._reconnect():
                    return self._call(method, params, _retry=False)
                raise ConnectionError(f"Verbindung verloren: {e}") from e

            if "error" in response and response["error"]:
                raise RuntimeError(f"ElectrumX Fehler: {response['error']}")

            return response.get("result")

    def _recv_response(self, request_id: int) -> dict:
        """
        Liest Zeilen vom Server, bis die Antwort mit der passenden JSON-RPC
        'id' eintrifft (Timeout: self.timeout).

        Zeilen ohne 'id' bzw. mit fremder 'id' sind asynchrone Notifications
        (z.B. blockchain.headers.subscribe) oder veraltete Antworten:
          - Header-Notifications aktualisieren den Tip-Cache (self._cached_tip),
          - alles andere wird verworfen.
        """
        deadline = time.monotonic() + self.timeout

        while True:
            if time.monotonic() > deadline:
                raise socket.timeout(
                    f"Timeout: keine Antwort mit id={request_id} "
                    f"innerhalb von {self.timeout}s"
                )

            line = self._recv_line()
            try:
                message = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                # Protokollfehler – Verbindung gilt als kaputt, damit der
                # Reconnect-Pfad in _call() greifen kann.
                raise ConnectionError(f"Ungültige JSON-Zeile vom Server: {e}") from e

            if not isinstance(message, dict):
                continue  # Unbrauchbare Zeile verwerfen

            msg_id = message.get("id")
            if msg_id == request_id:
                return message  # Unsere Antwort

            if msg_id is None:
                # Notification (keine 'id'): Header-Notifications cachen,
                # alles andere verwerfen.
                if message.get("method") == "blockchain.headers.subscribe":
                    n_params = message.get("params") or []
                    if n_params:
                        self._cached_tip = n_params[0]
                continue

            # Fremde/veraltete 'id' (stale Antwort) – verwerfen und weiterlesen.
            continue

    def _recv_line(self) -> bytes:
        """
        Liest eine vollständige, mit '\\n' terminierte JSON-Zeile aus dem
        Socket. Restliche bereits empfangene Bytes werden gepuffert und beim
        nächsten Aufruf zuerst verarbeitet (wichtig für asynchrone
        Server-Notifications und große Antworten).

        Der Puffer ist auf MAX_RECV_BUFFER begrenzt: Läuft er ohne Newline
        voll, wird die Verbindung zurückgesetzt und ConnectionError geworfen.
        """
        while b"\n" not in self._recv_buffer:
            if len(self._recv_buffer) > self.MAX_RECV_BUFFER:
                size = len(self._recv_buffer)
                # Verbindung zurücksetzen – der Puffer ist nicht mehr vertrauenswürdig.
                self._cleanup()
                raise ConnectionError(
                    f"Empfangspuffer-Limit überschritten "
                    f"({size} > {self.MAX_RECV_BUFFER} Bytes ohne Newline)"
                )
            chunk = self._ssl_socket.recv(65536)
            if not chunk:
                raise ConnectionError("Verbindung geschlossen (recv 0 bytes)")
            self._recv_buffer += chunk

        line, _, self._recv_buffer = self._recv_buffer.partition(b"\n")
        return line

    # ========================================================
    # Electrum Scripthash – jetzt für ALLE Adresstypen
    # ========================================================

    @staticmethod
    def address_to_scripthash(address: str, bech32_hrp: str = "dc") -> str:
        """
        Konvertiert eine Doichain-Adresse in einen Electrum-Scripthash.

        Unterstützte Adresstypen (delegiert an crypto_utils.address_to_script_pubkey):
          - P2PKH   (Legacy, N.../M...)
          - P2SH    (z.B. 3...)
          - P2WPKH  (Native SegWit, dc1q..., 20 Bytes)
          - P2WSH   (Native SegWit, dc1q..., 32 Bytes)
          - P2TR    (Taproot, dc1p..., 32 Bytes)

        Electrum-Scripthash = SHA256(scriptPubKey) in reversed Byte-Reihenfolge.

        Args:
            address: Doichain-Adresse (beliebiger unterstützter Typ).
            bech32_hrp: Bech32 Human-Readable Part (Default: "dc" für Doichain).

        Returns:
            Hex-String des Scripthashes (64 Zeichen).
        """
        from .crypto_utils import address_to_script_pubkey

        script = address_to_script_pubkey(address, bech32_hrp=bech32_hrp)
        h = hashlib.sha256(script).digest()
        return h[::-1].hex()

    def _scripthash(self, address: str) -> str:
        """Komfort: nutzt den HRP aus self.network."""
        return self.address_to_scripthash(
            address, bech32_hrp=self.network.get("bech32_hrp", "dc")
        )

    # ========================================================
    # Öffentliche API-Methoden
    # ========================================================

    def get_balance(self, address: str) -> dict:
        """
        Gibt den Saldo einer Adresse zurück.

        Returns:
            Dict mit 'confirmed' und 'unconfirmed' (in Satoshis).
        """
        result = self._call("blockchain.scripthash.get_balance", [self._scripthash(address)])
        return {
            "confirmed": result.get("confirmed", 0),
            "unconfirmed": result.get("unconfirmed", 0),
            "total": result.get("confirmed", 0) + result.get("unconfirmed", 0),
        }

    def get_utxos(self, address: str) -> list:
        """
        Gibt die unverbrauchten Transaktionsausgaben (UTXOs) einer Adresse zurück.
        """
        return self._call("blockchain.scripthash.listunspent", [self._scripthash(address)])

    def get_history(self, address: str) -> list:
        """Gibt die Transaktionshistorie einer Adresse zurück."""
        return self._call("blockchain.scripthash.get_history", [self._scripthash(address)])

    def get_transaction(self, tx_hash: str, verbose: bool = True) -> dict:
        """
        Gibt eine Transaktion als Hex oder als Verbose-Dict zurück.
        """
        return self._call("blockchain.transaction.get", [tx_hash, verbose])

    def get_raw_transaction(self, tx_hash: str) -> str:
        """Gibt die rohe Transaktion als Hex-String zurück."""
        return self._call("blockchain.transaction.get", [tx_hash, False])

    def broadcast_transaction(self, raw_tx_hex: str) -> str:
        """
        Sendet eine signierte Transaktion an das Netzwerk.

        Returns:
            Transaktions-Hash bei Erfolg.

        Raises:
            RuntimeError: Bei Ablehnung durch den Server.
        """
        return self._call("blockchain.transaction.broadcast", [raw_tx_hex])

    def get_block_header(self, height: int) -> dict:
        """Gibt den Block-Header für eine bestimmte Höhe zurück."""
        return self._call("blockchain.block.header", [height])

    def get_tip(self) -> dict:
        """Gibt den aktuellen Blockchain-Tip (neuester Block) zurück."""
        result = self._call("blockchain.headers.subscribe", [])
        if result:
            self._cached_tip = result
        return result

    def get_fee_estimate(self, target_blocks: int = 6) -> Optional[float]:
        """
        Schätzt die Transaktionsgebühr (DOI/kB).
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

    @property
    def current_server(self) -> Optional[dict]:
        """Aktiver Server (Host/Port-Dict), falls verbunden."""
        return self._current_server
