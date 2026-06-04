"""
Tron Wallet – TRX + USDT (TRC-20)

Vollständiges HD-Wallet für das Tron-Netzwerk:
- BIP-39 Seed → BIP-44 Schlüsselableitung (m/44'/195'/0'/0/x)
- TRX-Saldo und Transfers
- USDT TRC-20 Saldo und Transfers
- Transaktions-History
- Lokale Signierung (Private Keys verlassen nie das Gerät)

Verwendet die gleiche BIP-39 Seed-Phrase wie das DOI-Wallet
(verschiedene BIP-44 Ableitungspfade).
"""

import logging
from typing import Dict, List, Optional, Tuple

from mnemonic import Mnemonic

from .tron_crypto import (
    derive_tron_address_from_seed,
    validate_tron_address,
    sun_to_trx,
    trx_to_sun,
    raw_to_usdt,
    usdt_to_raw,
    tron_address_to_hex,
)
from .tron_network import (
    TronClient,
    TRON_MAINNET,
    TRON_NILE_TESTNET,
)

logger = logging.getLogger(__name__)


class TronWallet:
    """
    HD-Wallet für Tron (TRX + USDT TRC-20).
    
    Verwendung:
        # Neues Wallet erstellen
        wallet = TronWallet()
        mnemonic = wallet.create()
        
        # Bestehendes Wallet wiederherstellen
        wallet = TronWallet()
        wallet.restore("abandon ability able ... zone zoo")
        
        # Saldo abfragen
        balance = wallet.get_trx_balance()
        usdt = wallet.get_usdt_balance()
        
        # TRX senden
        result = wallet.send_trx("TDestAddr...", 10.0)
        
        # USDT senden
        result = wallet.send_usdt("TDestAddr...", 100.0)
    """
    
    def __init__(self, network: dict = None, api_key: str = ""):
        """
        Initialisiert das Tron-Wallet.
        
        Args:
            network: Netzwerk-Parameter (default: TRON_MAINNET)
            api_key: TronGrid API-Key (optional, für höhere Rate-Limits)
        """
        self.network = network or TRON_MAINNET
        self.client = TronClient(self.network, api_key)
        
        # Wallet-State
        self._seed: Optional[bytes] = None
        self._mnemonic: Optional[str] = None
        self._addresses: Dict[int, dict] = {}  # index → {address, privkey, pubkey}
        self._address_count = 5  # Standard: 5 Adressen vorableiten
    
    # ──────────────────────────────────────────
    # Wallet erstellen / wiederherstellen
    # ──────────────────────────────────────────
    
    def create(self, strength: int = 256, passphrase: str = "") -> str:
        """
        Erstellt ein neues Wallet mit zufälliger Seed-Phrase.
        
        Args:
            strength: Seed-Stärke in Bits (256 = 24 Wörter, 128 = 12 Wörter)
            passphrase: Optionale BIP-39 Passphrase
        
        Returns:
            Mnemonic Seed-Phrase (SICHER AUFBEWAHREN!)
        """
        mnemo = Mnemonic("english")
        self._mnemonic = mnemo.generate(strength)
        self._seed = mnemo.to_seed(self._mnemonic, passphrase)
        
        # Adressen vorableiten
        self._derive_addresses()
        
        logger.info(f"Neues Tron-Wallet erstellt: {self.primary_address}")
        return self._mnemonic
    
    def restore(self, mnemonic: str, passphrase: str = "") -> str:
        """
        Stellt ein Wallet aus einer Seed-Phrase wieder her.
        
        Args:
            mnemonic: BIP-39 Seed-Phrase (12 oder 24 Wörter)
            passphrase: Optionale BIP-39 Passphrase
        
        Returns:
            Primäre Tron-Adresse
        """
        mnemo = Mnemonic("english")
        if not mnemo.check(mnemonic):
            raise ValueError("Ungültige Seed-Phrase!")
        
        self._mnemonic = mnemonic.strip()
        self._seed = mnemo.to_seed(self._mnemonic, passphrase)
        
        # Adressen vorableiten
        self._derive_addresses()
        
        logger.info(f"Tron-Wallet wiederhergestellt: {self.primary_address}")
        return self.primary_address
    
    def restore_from_seed(self, seed: bytes) -> str:
        """
        Stellt ein Wallet direkt aus einem BIP-39 Seed wieder her.
        
        Args:
            seed: 64-Byte BIP-39 Seed
        
        Returns:
            Primäre Tron-Adresse
        """
        if len(seed) != 64:
            raise ValueError(f"Ungültige Seed-Länge: {len(seed)} (erwartet: 64)")
        
        self._seed = seed
        self._mnemonic = None
        
        self._derive_addresses()
        
        logger.info(f"Tron-Wallet aus Seed wiederhergestellt: {self.primary_address}")
        return self.primary_address
    
    def _derive_addresses(self, count: int = None):
        """Leitet Adressen aus dem Seed ab."""
        if self._seed is None:
            raise RuntimeError("Wallet nicht initialisiert")
        
        count = count or self._address_count
        for i in range(count):
            if i not in self._addresses:
                address, privkey, pubkey = derive_tron_address_from_seed(
                    self._seed, account=0, index=i
                )
                self._addresses[i] = {
                    "address": address,
                    "privkey": privkey,
                    "pubkey": pubkey,
                    "index": i,
                    "path": f"m/44'/195'/0'/0/{i}",
                }
    
    # ──────────────────────────────────────────
    # Adressen
    # ──────────────────────────────────────────
    
    @property
    def primary_address(self) -> Optional[str]:
        """Gibt die primäre Tron-Adresse zurück (Index 0)."""
        if 0 in self._addresses:
            return self._addresses[0]["address"]
        return None
    
    @property
    def is_initialized(self) -> bool:
        """Prüft ob das Wallet initialisiert ist."""
        return self._seed is not None
    
    def get_address(self, index: int = 0) -> str:
        """
        Gibt eine Tron-Adresse für den gegebenen Index zurück.
        
        Args:
            index: Adress-Index (default: 0)
        
        Returns:
            Tron-Adresse
        """
        if index not in self._addresses:
            self._derive_addresses(index + 1)
        return self._addresses[index]["address"]
    
    def get_all_addresses(self) -> List[str]:
        """Gibt alle abgeleiteten Adressen zurück."""
        return [info["address"] for info in sorted(self._addresses.values(), key=lambda x: x["index"])]
    
    def _get_privkey(self, address: str) -> Optional[bytes]:
        """Gibt den Private Key für eine Adresse zurück."""
        for info in self._addresses.values():
            if info["address"] == address:
                return info["privkey"]
        return None
    
    # ──────────────────────────────────────────
    # Saldo-Abfragen
    # ──────────────────────────────────────────
    
    def get_trx_balance(self, address: str = None) -> float:
        """
        Gibt den TRX-Saldo in TRX zurück.
        
        Args:
            address: Tron-Adresse (default: primäre Adresse)
        
        Returns:
            Saldo in TRX
        """
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        
        sun = self.client.get_trx_balance(addr)
        return sun_to_trx(sun)
    
    def get_trx_balance_sun(self, address: str = None) -> int:
        """Gibt den TRX-Saldo in SUN zurück."""
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        return self.client.get_trx_balance(addr)
    
    def get_usdt_balance(self, address: str = None) -> float:
        """
        Gibt den USDT-Saldo zurück.
        
        Args:
            address: Tron-Adresse (default: primäre Adresse)
        
        Returns:
            Saldo in USDT
        """
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        
        raw = self.client.get_usdt_balance(addr)
        return raw_to_usdt(raw)
    
    def get_total_balance(self, address: str = None) -> dict:
        """
        Gibt alle Salden einer Adresse zurück.
        
        Returns:
            Dict mit {trx, trx_sun, usdt, usdt_raw, address}
        """
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        
        trx_sun = self.client.get_trx_balance(addr)
        usdt_raw = self.client.get_usdt_balance(addr)
        
        return {
            "address": addr,
            "trx": sun_to_trx(trx_sun),
            "trx_sun": trx_sun,
            "usdt": raw_to_usdt(usdt_raw),
            "usdt_raw": usdt_raw,
        }
    
    def get_all_balances(self) -> List[dict]:
        """Gibt die Salden aller Adressen zurück."""
        results = []
        for info in sorted(self._addresses.values(), key=lambda x: x["index"]):
            balance = self.get_total_balance(info["address"])
            balance["index"] = info["index"]
            balance["path"] = info["path"]
            results.append(balance)
        return results
    
    def get_resources(self, address: str = None) -> Optional[dict]:
        """
        Gibt Ressourcen-Informationen zurück (Bandbreite, Energie).
        
        Returns:
            Dict mit Bandbreite und Energie-Informationen
        """
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        
        resources = self.client.get_account_resources(addr)
        if not resources:
            return None
        
        return {
            "bandwidth_free": resources.get("freeNetLimit", 0),
            "bandwidth_used": resources.get("freeNetUsed", 0),
            "bandwidth_staked": resources.get("NetLimit", 0),
            "energy_limit": resources.get("EnergyLimit", 0),
            "energy_used": resources.get("EnergyUsed", 0),
        }
    
    # ──────────────────────────────────────────
    # TRX senden
    # ──────────────────────────────────────────
    
    def send_trx(
        self,
        to_address: str,
        amount_trx: float,
        from_address: str = None,
    ) -> dict:
        """
        Sendet TRX an eine Adresse.
        
        Args:
            to_address: Empfänger-Adresse
            amount_trx: Betrag in TRX
            from_address: Absender-Adresse (default: primäre Adresse)
        
        Returns:
            Ergebnis mit txID
        
        Raises:
            ValueError: Bei ungültiger Adresse oder unzureichendem Saldo
            RuntimeError: Wenn Wallet nicht initialisiert
        """
        from_addr = from_address or self.primary_address
        if not from_addr:
            raise RuntimeError("Wallet nicht initialisiert")
        
        # Validierung
        if not validate_tron_address(to_address):
            raise ValueError(f"Ungültige Empfänger-Adresse: {to_address}")
        
        if amount_trx <= 0:
            raise ValueError(f"Ungültiger Betrag: {amount_trx} TRX")
        
        amount_sun = trx_to_sun(amount_trx)
        
        # Saldo prüfen
        balance_sun = self.client.get_trx_balance(from_addr)
        if balance_sun < amount_sun:
            raise ValueError(
                f"Unzureichender Saldo: {sun_to_trx(balance_sun):.6f} TRX "
                f"(benötigt: {amount_trx:.6f} TRX)"
            )
        
        # Private Key finden
        privkey = self._get_privkey(from_addr)
        if not privkey:
            raise ValueError(f"Kein Private Key für Adresse: {from_addr}")
        
        # Transaktion erstellen
        unsigned_tx = self.client.create_trx_transfer(from_addr, to_address, amount_sun)
        if not unsigned_tx:
            raise RuntimeError("Konnte Transaktion nicht erstellen")
        
        # Signieren und senden
        result = self.client.sign_and_broadcast(unsigned_tx, privkey)
        
        if result and "error" not in result:
            logger.info(f"TRX gesendet: {amount_trx} TRX → {to_address}")
        
        return result
    
    # ──────────────────────────────────────────
    # USDT senden
    # ──────────────────────────────────────────
    
    def send_usdt(
        self,
        to_address: str,
        amount_usdt: float,
        from_address: str = None,
        fee_limit_trx: float = 100.0,
    ) -> dict:
        """
        Sendet USDT (TRC-20) an eine Adresse.
        
        WICHTIG: Für TRC-20 Transfers werden TRX als Gas benötigt!
        Typisch: 5–15 TRX pro USDT-Transfer.
        
        Args:
            to_address: Empfänger-Adresse
            amount_usdt: Betrag in USDT
            from_address: Absender-Adresse (default: primäre Adresse)
            fee_limit_trx: Maximale Fee in TRX (default: 100)
        
        Returns:
            Ergebnis mit txID
        """
        from_addr = from_address or self.primary_address
        if not from_addr:
            raise RuntimeError("Wallet nicht initialisiert")
        
        # Validierung
        if not validate_tron_address(to_address):
            raise ValueError(f"Ungültige Empfänger-Adresse: {to_address}")
        
        if amount_usdt <= 0:
            raise ValueError(f"Ungültiger Betrag: {amount_usdt} USDT")
        
        amount_raw = usdt_to_raw(amount_usdt)
        
        # USDT-Saldo prüfen
        usdt_balance_raw = self.client.get_usdt_balance(from_addr)
        if usdt_balance_raw < amount_raw:
            raise ValueError(
                f"Unzureichender USDT-Saldo: {raw_to_usdt(usdt_balance_raw):.6f} USDT "
                f"(benötigt: {amount_usdt:.6f} USDT)"
            )
        
        # TRX-Saldo für Gas prüfen
        trx_balance = self.client.get_trx_balance(from_addr)
        min_trx_for_gas = trx_to_sun(5.0)  # Mindestens 5 TRX für Gas
        if trx_balance < min_trx_for_gas:
            raise ValueError(
                f"Unzureichender TRX-Saldo für Gas: {sun_to_trx(trx_balance):.6f} TRX "
                f"(mindestens ~5 TRX nötig für TRC-20 Transfer)"
            )
        
        # Private Key finden
        privkey = self._get_privkey(from_addr)
        if not privkey:
            raise ValueError(f"Kein Private Key für Adresse: {from_addr}")
        
        # Transaktion erstellen
        fee_limit_sun = trx_to_sun(fee_limit_trx)
        unsigned_tx = self.client.create_trc20_transfer(
            from_addr, to_address, amount_raw, fee_limit=fee_limit_sun
        )
        if not unsigned_tx:
            raise RuntimeError("Konnte USDT-Transaktion nicht erstellen")
        
        # Signieren und senden
        result = self.client.sign_and_broadcast(unsigned_tx, privkey)
        
        if result and "error" not in result:
            logger.info(f"USDT gesendet: {amount_usdt} USDT → {to_address}")
        
        return result
    
    # ──────────────────────────────────────────
    # Transaktions-History
    # ──────────────────────────────────────────
    
    def get_history(self, address: str = None, limit: int = 20) -> List[dict]:
        """Gibt die TRX-Transaktions-History zurück."""
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        return self.client.get_transactions(addr, limit)
    
    def get_usdt_history(self, address: str = None, limit: int = 20) -> List[dict]:
        """Gibt die USDT-Transaktions-History zurück."""
        addr = address or self.primary_address
        if not addr:
            raise RuntimeError("Wallet nicht initialisiert")
        return self.client.get_trc20_transactions(addr, limit=limit)
    
    # ──────────────────────────────────────────
    # Netzwerk-Status
    # ──────────────────────────────────────────
    
    def check_connection(self) -> bool:
        """Prüft die Verbindung zum Tron-Netzwerk."""
        return self.client.is_connected()
    
    def get_block_height(self) -> Optional[int]:
        """Gibt die aktuelle Blockhöhe zurück."""
        return self.client.get_block_height()
    
    # ──────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────
    
    def close(self):
        """Schließt Verbindungen und löscht sensible Daten."""
        self.client.close()
        # Sensible Daten überschreiben
        if self._seed:
            self._seed = b"\x00" * len(self._seed)
        self._seed = None
        self._mnemonic = None
        for info in self._addresses.values():
            if info.get("privkey"):
                info["privkey"] = b"\x00" * len(info["privkey"])
        self._addresses.clear()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
    
    def __repr__(self):
        status = "initialized" if self.is_initialized else "not initialized"
        addr = self.primary_address or "N/A"
        return f"TronWallet({status}, address={addr}, network={self.network['name']})"
