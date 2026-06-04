"""
Unified Wallet Manager

Verwaltet DOI- und Tron-Wallets aus einer einzigen BIP-39 Seed-Phrase.
Bietet ein einheitliches Interface für alle Chains und speichert den
Wallet-Zustand verschlüsselt (AES-256-GCM) auf der Festplatte.

Wallet-Datei Format (.wallet):
    {
        "version": 1,
        "created": "ISO-8601",
        "encrypted_seed": base64(AES-256-GCM(mnemonic)),
        "salt": base64(32 bytes),
        "nonce": base64(12 bytes),
        "tag": base64(16 bytes),
        "kdf": "scrypt",
        "kdf_params": {"n": 2^20, "r": 8, "p": 1},
        "settings": { ... }
    }

Verwendung:
    # Neues Wallet erstellen
    wm = WalletManager()
    mnemonic = wm.create("mein-sicheres-passwort")
    wm.save("wallet.dat")

    # Wallet laden
    wm = WalletManager()
    wm.load("wallet.dat", "mein-sicheres-passwort")

    # Unified Interface
    balances = wm.get_all_balances()
    wm.send("DOI", "NAddr...", 10.0)
    wm.send("USDT", "TAddr...", 50.0)
"""

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt
from mnemonic import Mnemonic

from .doi_wallet import DoiWallet
from .tron_wallet import TronWallet
from .tron_network import TRON_MAINNET, TRON_NILE_TESTNET
from .doichain_network import MAINNET as DOI_MAINNET, TESTNET as DOI_TESTNET

# Ethereum / wDOI (optional – nur wenn web3 installiert)
try:
    from .eth_wallet import EthWallet, validate_eth_address
    from .eth_network import ETH_MAINNET
    HAS_ETH = True
except ImportError:
    HAS_ETH = False
    EthWallet = None

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Konstanten
# ──────────────────────────────────────────────

WALLET_FILE_VERSION = 1
DEFAULT_KDF_PARAMS = {
    "n": 2**20,  # CPU/Memory-Kosten (ca. 1 GB RAM, ~1s auf moderner HW)
    "r": 8,
    "p": 1,
    "key_len": 32,  # 256 Bit
}

# Unterstützte Chains
SUPPORTED_CHAINS = ("DOI", "TRX", "USDT", "ETH", "wDOI")


# ──────────────────────────────────────────────
# Verschlüsselung
# ──────────────────────────────────────────────

def _derive_key(password: str, salt: bytes, params: dict = None) -> bytes:
    """
    Leitet einen Verschlüsselungskey aus einem Passwort ab (scrypt KDF).

    Args:
        password: Benutzer-Passwort
        salt: 32-Byte Salt
        params: scrypt-Parameter (n, r, p, key_len)

    Returns:
        32-Byte Verschlüsselungskey
    """
    p = params or DEFAULT_KDF_PARAMS
    return scrypt(
        password.encode("utf-8"),
        salt,
        key_len=p["key_len"],
        N=p["n"],
        r=p["r"],
        p=p["p"],
    )


def _encrypt(data: bytes, password: str) -> dict:
    """
    Verschlüsselt Daten mit AES-256-GCM.

    Returns:
        Dict mit salt, nonce, ciphertext, tag (alle base64-kodiert)
    """
    salt = os.urandom(32)
    key = _derive_key(password, salt)

    cipher = AES.new(key, AES.MODE_GCM, nonce=os.urandom(12))
    ciphertext, tag = cipher.encrypt_and_digest(data)

    return {
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(cipher.nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
        "tag": base64.b64encode(tag).decode(),
    }


def _decrypt(enc: dict, password: str) -> bytes:
    """
    Entschlüsselt AES-256-GCM-verschlüsselte Daten.

    Args:
        enc: Dict mit salt, nonce, ciphertext, tag
        password: Benutzer-Passwort

    Returns:
        Entschlüsselte Daten

    Raises:
        ValueError: Bei falschem Passwort oder beschädigten Daten
    """
    salt = base64.b64decode(enc["salt"])
    nonce = base64.b64decode(enc["nonce"])
    ciphertext = base64.b64decode(enc["ciphertext"])
    tag = base64.b64decode(enc["tag"])

    key = _derive_key(password, salt)

    try:
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext
    except (ValueError, KeyError):
        raise ValueError("Falsches Passwort oder beschädigte Wallet-Datei")


# ──────────────────────────────────────────────
# Wallet Manager
# ──────────────────────────────────────────────

class WalletManager:
    """
    Einheitlicher Wallet-Manager für DOI + Tron (TRX/USDT) + Ethereum (ETH/wDOI).

    Verwaltet alle Chains aus einer einzigen BIP-39 Seed-Phrase
    und speichert den Zustand verschlüsselt auf der Festplatte.
    """

    def __init__(self, tron_api_key: str = ""):
        """
        Initialisiert den Wallet-Manager.

        Args:
            tron_api_key: Optionaler TronGrid API-Key
        """
        self._mnemonic: Optional[str] = None
        self._password: Optional[str] = None
        self._wallet_path: Optional[Path] = None
        self._settings: dict = {
            "doi_network": "mainnet",
            "tron_network": "mainnet",
            "created": None,
            "last_accessed": None,
        }

        # Sub-Wallets (erst nach create/load/restore initialisiert)
        self.doi: Optional[DoiWallet] = None
        self.tron: Optional[TronWallet] = None
        self.eth: Optional[EthWallet] = None

        self._tron_api_key = tron_api_key

    # ──────────────────────────────────────────
    # Erstellen / Wiederherstellen / Laden
    # ──────────────────────────────────────────

    def create(self, password: str, strength: int = 256, passphrase: str = "") -> str:
        """
        Erstellt ein neues Wallet mit zufälliger Seed-Phrase.

        Args:
            password: Passwort für die Wallet-Datei
            strength: Seed-Stärke (256 = 24 Wörter, 128 = 12 Wörter)
            passphrase: Optionale BIP-39 Passphrase

        Returns:
            Mnemonic Seed-Phrase (SICHER AUFBEWAHREN!)
        """
        if len(password) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen lang sein")

        mnemo = Mnemonic("english")
        self._mnemonic = mnemo.generate(strength)
        self._password = password
        self._settings["created"] = datetime.now(timezone.utc).isoformat()

        # Sub-Wallets initialisieren
        self._init_wallets(passphrase)

        logger.info("Neues Wallet erstellt")
        return self._mnemonic

    def restore(self, mnemonic: str, password: str, passphrase: str = "") -> dict:
        """
        Stellt ein Wallet aus einer Seed-Phrase wieder her.

        Args:
            mnemonic: BIP-39 Seed-Phrase (12 oder 24 Wörter)
            password: Passwort für die Wallet-Datei
            passphrase: Optionale BIP-39 Passphrase

        Returns:
            Dict mit primären Adressen {doi, tron}
        """
        if len(password) < 8:
            raise ValueError("Passwort muss mindestens 8 Zeichen lang sein")

        mnemo = Mnemonic("english")
        if not mnemo.check(mnemonic):
            raise ValueError("Ungültige Seed-Phrase!")

        self._mnemonic = mnemonic.strip()
        self._password = password
        self._settings["created"] = datetime.now(timezone.utc).isoformat()

        # Sub-Wallets initialisieren
        self._init_wallets(passphrase)

        logger.info("Wallet wiederhergestellt")
        return self.primary_addresses

    def _init_wallets(self, passphrase: str = ""):
        """Initialisiert alle Sub-Wallets aus dem Mnemonic."""
        if not self._mnemonic:
            raise RuntimeError("Kein Mnemonic vorhanden")

        # DOI Wallet
        self.doi = DoiWallet()
        self.doi.restore(self._mnemonic, passphrase)

        # Tron Wallet
        self.tron = TronWallet(api_key=self._tron_api_key)
        self.tron.restore(self._mnemonic, passphrase)

        # Ethereum / wDOI Wallet
        if HAS_ETH:
            try:
                self.eth = EthWallet()
                self.eth.from_mnemonic(self._mnemonic)
                self.eth.connect()
                logger.info(f"ETH-Wallet initialisiert: {self.eth.address}")
            except Exception as e:
                logger.warning(f"ETH-Wallet Fehler: {e}")
                self.eth = None
        else:
            logger.info("ETH-Support nicht verfügbar (web3 nicht installiert)")

    # ──────────────────────────────────────────
    # Speichern / Laden
    # ──────────────────────────────────────────

    def save(self, path: str = None) -> str:
        """
        Speichert das Wallet verschlüsselt auf der Festplatte.

        Args:
            path: Dateipfad (default: letzter Pfad oder "wallet.dat")

        Returns:
            Gespeicherter Dateipfad
        """
        if not self._mnemonic or not self._password:
            raise RuntimeError("Wallet nicht initialisiert oder kein Passwort gesetzt")

        filepath = Path(path) if path else (self._wallet_path or Path("wallet.dat"))

        # Mnemonic verschlüsseln
        encrypted = _encrypt(self._mnemonic.encode("utf-8"), self._password)

        # Wallet-Datei zusammenbauen
        wallet_data = {
            "version": WALLET_FILE_VERSION,
            "encrypted_seed": encrypted["ciphertext"],
            "salt": encrypted["salt"],
            "nonce": encrypted["nonce"],
            "tag": encrypted["tag"],
            "kdf": "scrypt",
            "kdf_params": {
                "n": DEFAULT_KDF_PARAMS["n"],
                "r": DEFAULT_KDF_PARAMS["r"],
                "p": DEFAULT_KDF_PARAMS["p"],
            },
            "settings": self._settings,
        }

        # Atomar schreiben (erst temp, dann umbenennen)
        temp_path = filepath.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(wallet_data, f, indent=2)

        temp_path.replace(filepath)
        self._wallet_path = filepath

        logger.info(f"Wallet gespeichert: {filepath}")
        return str(filepath)

    def load(self, path: str, password: str) -> dict:
        """
        Lädt ein verschlüsseltes Wallet von der Festplatte.

        Args:
            path: Dateipfad
            password: Passwort zum Entschlüsseln

        Returns:
            Dict mit primären Adressen {doi, tron}

        Raises:
            FileNotFoundError: Datei nicht gefunden
            ValueError: Falsches Passwort
        """
        filepath = Path(path)
        if not filepath.exists():
            raise FileNotFoundError(f"Wallet-Datei nicht gefunden: {filepath}")

        with open(filepath, "r") as f:
            wallet_data = json.load(f)

        # Version prüfen
        version = wallet_data.get("version", 0)
        if version != WALLET_FILE_VERSION:
            raise ValueError(f"Inkompatible Wallet-Version: {version} (erwartet: {WALLET_FILE_VERSION})")

        # Entschlüsseln
        enc = {
            "salt": wallet_data["salt"],
            "nonce": wallet_data["nonce"],
            "ciphertext": wallet_data["encrypted_seed"],
            "tag": wallet_data["tag"],
        }

        try:
            plaintext = _decrypt(enc, password)
            self._mnemonic = plaintext.decode("utf-8")
        except ValueError:
            raise ValueError("Falsches Passwort!")

        self._password = password
        self._wallet_path = filepath
        self._settings = wallet_data.get("settings", self._settings)
        self._settings["last_accessed"] = datetime.now(timezone.utc).isoformat()

        # Sub-Wallets initialisieren
        self._init_wallets()

        logger.info(f"Wallet geladen: {filepath}")
        return self.primary_addresses

    def change_password(self, old_password: str, new_password: str) -> bool:
        """
        Ändert das Wallet-Passwort.

        Args:
            old_password: Aktuelles Passwort
            new_password: Neues Passwort

        Returns:
            True bei Erfolg
        """
        if old_password != self._password:
            raise ValueError("Aktuelles Passwort ist falsch")
        if len(new_password) < 8:
            raise ValueError("Neues Passwort muss mindestens 8 Zeichen lang sein")

        self._password = new_password

        # Wallet neu speichern wenn bereits gespeichert
        if self._wallet_path:
            self.save()

        logger.info("Passwort geändert")
        return True

    # ──────────────────────────────────────────
    # Adressen
    # ──────────────────────────────────────────

    @property
    def primary_addresses(self) -> dict:
        """Gibt die primären Adressen aller Chains zurück."""
        result = {}
        if self.doi and self.doi.seed_manager.is_initialized:
            result["doi"] = self.doi.seed_manager.get_receive_address(0)
        if self.tron and self.tron.is_initialized:
            result["tron"] = self.tron.primary_address
        if self.eth and self.eth.address:
            result["eth"] = self.eth.address
        return result

    @property
    def is_initialized(self) -> bool:
        """Prüft ob das Wallet initialisiert ist."""
        return self._mnemonic is not None

    @property
    def is_saved(self) -> bool:
        """Prüft ob das Wallet auf der Festplatte gespeichert ist."""
        return self._wallet_path is not None and self._wallet_path.exists()

    @property
    def wallet_path(self) -> Optional[str]:
        """Gibt den Wallet-Dateipfad zurück."""
        return str(self._wallet_path) if self._wallet_path else None

    def get_all_addresses(self) -> dict:
        """
        Gibt alle Adressen aller Chains zurück.

        Returns:
            {
                "doi": {"receive": [...], "change": [...]},
                "tron": [...]
            }
        """
        result = {}
        if self.doi:
            result["doi"] = {
                "receive": self.doi.get_receive_addresses(),
                "change": self.doi.get_change_addresses(),
            }
        if self.tron:
            result["tron"] = self.tron.get_all_addresses()
        if self.eth and self.eth.address:
            result["eth"] = [self.eth.address]
        return result

    # ──────────────────────────────────────────
    # Salden
    # ──────────────────────────────────────────

    def get_all_balances(self) -> dict:
        """
        Gibt die Salden aller Chains zurück.

        Returns:
            {
                "doi": {"confirmed": float, "unconfirmed": float},
                "trx": float,
                "usdt": float,
            }
        """
        result = {}

        if self.doi:
            try:
                doi_bal = self.doi.get_balance()
                result["doi"] = doi_bal
            except Exception as e:
                logger.warning(f"DOI-Saldo-Fehler: {e}")
                result["doi"] = {"confirmed": 0, "unconfirmed": 0, "error": str(e)}

        if self.tron:
            try:
                result["trx"] = self.tron.get_trx_balance()
            except Exception as e:
                logger.warning(f"TRX-Saldo-Fehler: {e}")
                result["trx"] = 0

            try:
                result["usdt"] = self.tron.get_usdt_balance()
            except Exception as e:
                logger.warning(f"USDT-Saldo-Fehler: {e}")
                result["usdt"] = 0

        if self.eth:
            try:
                result["eth"] = self.eth.get_eth_balance()
            except Exception as e:
                logger.warning(f"ETH-Saldo-Fehler: {e}")
                result["eth"] = 0

            try:
                result["wdoi"] = self.eth.get_wdoi_balance()
            except Exception as e:
                logger.warning(f"wDOI-Saldo-Fehler: {e}")
                result["wdoi"] = 0

        return result

    def get_balance(self, chain: str) -> Any:
        """
        Gibt den Saldo einer bestimmten Chain zurück.

        Args:
            chain: "DOI", "TRX" oder "USDT"

        Returns:
            Saldo (Format abhängig von Chain)
        """
        chain = chain.upper()

        if chain == "DOI":
            if not self.doi:
                raise RuntimeError("DOI-Wallet nicht initialisiert")
            return self.doi.get_balance()

        elif chain == "TRX":
            if not self.tron:
                raise RuntimeError("Tron-Wallet nicht initialisiert")
            return self.tron.get_trx_balance()

        elif chain == "USDT":
            if not self.tron:
                raise RuntimeError("Tron-Wallet nicht initialisiert")
            return self.tron.get_usdt_balance()

        elif chain == "ETH":
            if not self.eth:
                raise RuntimeError("ETH-Wallet nicht initialisiert")
            return self.eth.get_eth_balance()

        elif chain == "WDOI":
            if not self.eth:
                raise RuntimeError("ETH-Wallet nicht initialisiert")
            return self.eth.get_wdoi_balance()

        else:
            raise ValueError(f"Unbekannte Chain: {chain} (unterstützt: {SUPPORTED_CHAINS})")

    # ──────────────────────────────────────────
    # Senden
    # ──────────────────────────────────────────

    def send(self, chain: str, to_address: str, amount: float, **kwargs) -> dict:
        """
        Sendet Coins/Token an eine Adresse.

        Args:
            chain: "DOI", "TRX" oder "USDT"
            to_address: Empfänger-Adresse
            amount: Betrag
            **kwargs: Chain-spezifische Parameter
                - DOI: fee_rate (Sat/Byte)
                - USDT: fee_limit_trx (max TRX für Gas)

        Returns:
            Ergebnis mit txID
        """
        chain = chain.upper()

        if chain == "DOI":
            if not self.doi:
                raise RuntimeError("DOI-Wallet nicht initialisiert")
            fee_rate = kwargs.get("fee_rate", 10)
            return self.doi.send(to_address, amount, fee_per_byte=fee_rate)

        elif chain == "TRX":
            if not self.tron:
                raise RuntimeError("Tron-Wallet nicht initialisiert")
            return self.tron.send_trx(to_address, amount)

        elif chain == "USDT":
            if not self.tron:
                raise RuntimeError("Tron-Wallet nicht initialisiert")
            fee_limit = kwargs.get("fee_limit_trx", 100.0)
            return self.tron.send_usdt(to_address, amount, fee_limit_trx=fee_limit)

        elif chain == "ETH":
            if not self.eth:
                raise RuntimeError("ETH-Wallet nicht initialisiert")
            tx_hash = self.eth.send_eth(to_address, amount)
            return {"txid": tx_hash, "explorer": self.eth.get_explorer_url(tx_hash)}

        elif chain == "WDOI":
            if not self.eth:
                raise RuntimeError("ETH-Wallet nicht initialisiert")
            tx_hash = self.eth.send_wdoi(to_address, amount)
            return {"txid": tx_hash, "explorer": self.eth.get_explorer_url(tx_hash)}

        else:
            raise ValueError(f"Unbekannte Chain: {chain} (unterstützt: {SUPPORTED_CHAINS})")

    # ──────────────────────────────────────────
    # Transaktions-History
    # ──────────────────────────────────────────

    def get_history(self, chain: str = None, limit: int = 20) -> dict:
        """
        Gibt die Transaktions-History zurück.

        Args:
            chain: "DOI", "TRX", "USDT", "ETH", "wDOI" oder None für alle
            limit: Maximale Anzahl pro Chain

        Returns:
            Dict mit History pro Chain
        """
        result = {}

        if chain is None or chain.upper() == "DOI":
            if self.doi:
                try:
                    result["doi"] = self.doi.get_history()
                except Exception as e:
                    result["doi"] = {"error": str(e)}

        if chain is None or chain.upper() == "TRX":
            if self.tron:
                try:
                    result["trx"] = self.tron.get_history(limit=limit)
                except Exception as e:
                    result["trx"] = {"error": str(e)}

        if chain is None or chain.upper() == "USDT":
            if self.tron:
                try:
                    result["usdt"] = self.tron.get_usdt_history(limit=limit)
                except Exception as e:
                    result["usdt"] = {"error": str(e)}

        if chain is None or chain.upper() == "ETH":
            if self.eth:
                try:
                    result["eth"] = self.eth.get_eth_history(limit=limit)
                except Exception as e:
                    result["eth"] = {"error": str(e)}

        if chain is None or chain.upper() == "WDOI":
            if self.eth:
                try:
                    result["wdoi"] = self.eth.get_wdoi_history(limit=limit)
                except Exception as e:
                    result["wdoi"] = {"error": str(e)}

        return result

    # ──────────────────────────────────────────
    # Netzwerk-Status
    # ──────────────────────────────────────────

    def connect_doi(self, host: str = None, port: int = None) -> bool:
        """Verbindet das DOI-Wallet mit einem ElectrumX-Server."""
        if not self.doi:
            raise RuntimeError("DOI-Wallet nicht initialisiert")
        return self.doi.connect(host, port)

    def check_connections(self) -> dict:
        """
        Prüft die Verbindung zu allen Netzwerken.

        Returns:
            {"doi": bool, "tron": bool}
        """
        result = {}

        if self.doi:
            try:
                result["doi"] = self.doi.electrumx is not None
            except Exception:
                result["doi"] = False

        if self.tron:
            try:
                result["tron"] = self.tron.check_connection()
            except Exception:
                result["tron"] = False

        if self.eth:
            try:
                result["eth"] = self.eth.is_connected
            except Exception:
                result["eth"] = False

        return result

    # ──────────────────────────────────────────
    # Wallet-Info
    # ──────────────────────────────────────────

    def info(self) -> dict:
        """Gibt eine Übersicht über den Wallet-Zustand zurück."""
        addresses = self.primary_addresses
        return {
            "initialized": self.is_initialized,
            "saved": self.is_saved,
            "wallet_path": self.wallet_path,
            "created": self._settings.get("created"),
            "addresses": addresses,
            "seed_words": len(self._mnemonic.split()) if self._mnemonic else 0,
            "doi_addresses": len(self.doi.get_all_addresses()) if self.doi else 0,
            "tron_addresses": len(self.tron.get_all_addresses()) if self.tron else 0,
            "eth_address": self.eth.address if self.eth else None,
            "eth_available": HAS_ETH,
        }

    # ──────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────

    def close(self):
        """Schließt alle Verbindungen und überschreibt sensible Daten."""
        if self.doi:
            try:
                self.doi.disconnect()
            except Exception:
                pass

        if self.tron:
            self.tron.close()

        # Sensible Daten überschreiben
        if self._mnemonic:
            self._mnemonic = "x" * len(self._mnemonic)
        self._mnemonic = None
        self._password = None

        self.doi = None
        self.tron = None
        self.eth = None

        logger.info("Wallet-Manager geschlossen")

    def lock(self):
        """
        Sperrt das Wallet (entfernt Seed aus dem Speicher).
        Das Wallet muss mit unlock() wieder entsperrt werden.
        """
        if not self._wallet_path:
            raise RuntimeError("Wallet muss zuerst gespeichert werden, bevor es gesperrt werden kann")

        # Sensible Daten entfernen
        if self._mnemonic:
            self._mnemonic = "x" * len(self._mnemonic)
        self._mnemonic = None

        # Sub-Wallets schließen
        if self.tron:
            self.tron.close()
        self.tron = None
        self.doi = None
        self.eth = None

        logger.info("Wallet gesperrt")

    def unlock(self, password: str):
        """
        Entsperrt ein gesperrtes Wallet.

        Args:
            password: Wallet-Passwort
        """
        if not self._wallet_path:
            raise RuntimeError("Kein Wallet-Pfad bekannt")
        self.load(str(self._wallet_path), password)
        logger.info("Wallet entsperrt")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def __repr__(self):
        status = "initialized" if self.is_initialized else "not initialized"
        saved = f", saved={self.wallet_path}" if self.is_saved else ""
        return f"WalletManager({status}{saved})"
