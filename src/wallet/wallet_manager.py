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
import hmac
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
STATE_FILE_SUFFIX = ".state.json"   # State-Datei neben wallet.dat
DEFAULT_KDF_PARAMS = {
    "n": 2**20,  # CPU/Memory-Kosten (ca. 1 GB RAM, ~1s auf moderner HW)
    "r": 8,
    "p": 1,
    "key_len": 32,  # 256 Bit
}

# Obergrenzen für KDF-Parameter aus Wallet-Dateien.
# Verhindert DoS durch manipulierte Dateien mit absurd hohen Kosten.
KDF_MAX_N = 2**22
KDF_MAX_R = 32
KDF_MAX_P = 16

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


def _sanitize_kdf_params(params: Optional[dict]) -> dict:
    """
    Validiert KDF-Parameter aus einer Wallet-Datei.

    Obergrenzen verhindern Denial-of-Service durch manipulierte Dateien
    mit absurd hohen scrypt-Kosten.

    Args:
        params: kdf_params aus der Wallet-Datei (oder None)

    Returns:
        Bereinigte Parameter (n, r, p, key_len)

    Raises:
        ValueError: Bei ungültigen oder zu teuren Parametern
    """
    if not params:
        return dict(DEFAULT_KDF_PARAMS)

    try:
        n = int(params.get("n", DEFAULT_KDF_PARAMS["n"]))
        r = int(params.get("r", DEFAULT_KDF_PARAMS["r"]))
        p = int(params.get("p", DEFAULT_KDF_PARAMS["p"]))
        key_len = int(params.get("key_len", DEFAULT_KDF_PARAMS["key_len"]))
    except (TypeError, ValueError):
        raise ValueError("Ungültige KDF-Parameter in der Wallet-Datei")

    if not (1 < n <= KDF_MAX_N) or (n & (n - 1)) != 0:
        raise ValueError(f"Ungültiger KDF-Parameter n={n} (max. {KDF_MAX_N}, Zweierpotenz)")
    if not (1 <= r <= KDF_MAX_R):
        raise ValueError(f"Ungültiger KDF-Parameter r={r} (max. {KDF_MAX_R})")
    if not (1 <= p <= KDF_MAX_P):
        raise ValueError(f"Ungültiger KDF-Parameter p={p} (max. {KDF_MAX_P})")
    if key_len != 32:
        raise ValueError(f"Ungültige KDF-Schlüssellänge: {key_len} (erwartet: 32)")

    return {"n": n, "r": r, "p": p, "key_len": key_len}


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


def _decrypt(enc: dict, password: str, kdf_params: dict = None) -> bytes:
    """
    Entschlüsselt AES-256-GCM-verschlüsselte Daten.

    Args:
        enc: Dict mit salt, nonce, ciphertext, tag
        password: Benutzer-Passwort
        kdf_params: KDF-Parameter aus der Wallet-Datei
                    (default: DEFAULT_KDF_PARAMS; werden vor Verwendung
                    mit Obergrenzen validiert, siehe _sanitize_kdf_params)

    Returns:
        Entschlüsselte Daten

    Raises:
        ValueError: Bei falschem Passwort oder beschädigten Daten
    """
    salt = base64.b64decode(enc["salt"])
    nonce = base64.b64decode(enc["nonce"])
    ciphertext = base64.b64decode(enc["ciphertext"])
    tag = base64.b64decode(enc["tag"])

    key = _derive_key(password, salt, _sanitize_kdf_params(kdf_params))

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

        # Netzwerke aus den gespeicherten Settings auflösen
        # (z.B. nach load() einer Testnet-Wallet-Datei)
        doi_net_name = str(self._settings.get("doi_network", "mainnet")).lower()
        doi_network = DOI_TESTNET if doi_net_name in ("testnet", "test") else DOI_MAINNET

        tron_net_name = str(self._settings.get("tron_network", "mainnet")).lower()
        tron_network = (
            TRON_NILE_TESTNET if tron_net_name in ("testnet", "test", "nile") else TRON_MAINNET
        )

        # DOI Wallet
        self.doi = DoiWallet(network=doi_network)
        self.doi.restore(self._mnemonic, passphrase)

        # Tron Wallet
        self.tron = TronWallet(network=tron_network, api_key=self._tron_api_key)
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

        # Nicht-sensibler Adress-Fingerprint (erste DOI-Empfangsadresse).
        # Erlaubt beim Laden die Erkennung einer falschen/fehlenden
        # BIP-39-Passphrase, ohne Geheimnisse preiszugeben.
        fingerprint = None
        if self.doi and self.doi.seed_manager.is_initialized:
            try:
                fingerprint = self.doi.seed_manager.get_receive_address(0)
            except Exception as e:
                logger.warning(f"Adress-Fingerprint konnte nicht abgeleitet werden: {e}")

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
            "address_fingerprint": fingerprint,
            "settings": self._settings,
        }

        # Atomar schreiben (erst temp, dann umbenennen).
        # Suffix anhängen statt ersetzen, damit z.B. a.dat und a.json
        # nicht beide auf a.tmp kollidieren.
        temp_path = filepath.with_suffix(filepath.suffix + ".tmp")
        # Restriktive Dateirechte (0o600) direkt beim Anlegen setzen.
        # Unter Windows ist der Modus weitgehend wirkungslos – unkritisch.
        fd = os.open(str(temp_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(wallet_data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

        temp_path.replace(filepath)
        self._wallet_path = filepath

        # State-Datei (Indizes, Discovery-Marker) parallel schreiben.
        # Fehler hier sind nicht fatal – die Wallet-Datei selbst ist sicher.
        try:
            self.save_state()
        except Exception as e:
            logger.warning(f"State-Datei konnte nicht geschrieben werden: {e}")

        logger.info(f"Wallet gespeichert: {filepath}")
        return str(filepath)

    def load(self, path: str, password: str, passphrase: str = "") -> dict:
        """
        Lädt ein verschlüsseltes Wallet von der Festplatte.

        Args:
            path: Dateipfad
            password: Passwort zum Entschlüsseln
            passphrase: Optionale BIP-39 Passphrase (muss mit der beim
                        Erstellen/Wiederherstellen verwendeten übereinstimmen)

        Returns:
            Dict mit primären Adressen {doi, tron}

        Raises:
            FileNotFoundError: Datei nicht gefunden
            ValueError: Falsches Passwort oder falsche Passphrase
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

        # KDF-Parameter aus der Datei validieren (Obergrenzen gegen DoS,
        # siehe _sanitize_kdf_params) – VOR dem Entschlüsseln, damit
        # ein Parameter-Fehler nicht als "Falsches Passwort" maskiert wird
        kdf_params = _sanitize_kdf_params(wallet_data.get("kdf_params"))

        # Entschlüsseln
        enc = {
            "salt": wallet_data["salt"],
            "nonce": wallet_data["nonce"],
            "ciphertext": wallet_data["encrypted_seed"],
            "tag": wallet_data["tag"],
        }

        try:
            plaintext = _decrypt(enc, password, kdf_params)
            self._mnemonic = plaintext.decode("utf-8")
        except ValueError:
            raise ValueError("Falsches Passwort!")

        self._password = password
        self._wallet_path = filepath
        self._settings = wallet_data.get("settings", self._settings)
        self._settings["last_accessed"] = datetime.now(timezone.utc).isoformat()

        # Sub-Wallets initialisieren (mit BIP-39 Passphrase)
        self._init_wallets(passphrase)

        # Adress-Fingerprint prüfen: erkennt eine falsche/fehlende
        # BIP-39 Passphrase, statt stillschweigend leere Wallets zu zeigen.
        fingerprint = wallet_data.get("address_fingerprint")
        if fingerprint and self.doi and self.doi.seed_manager.is_initialized:
            derived = self.doi.seed_manager.get_receive_address(0)
            if derived != fingerprint:
                # Sensible Daten wieder entfernen
                self._mnemonic = None
                self._password = None
                self.doi = None
                self.tron = None
                self.eth = None
                raise ValueError(
                    "Passphrase oder Wallet-Daten stimmen nicht überein – "
                    "bitte BIP-39 Passphrase prüfen"
                )

        # State-Datei lesen, falls vorhanden, und in DOI-Wallet einspielen.
        # Bei Fehlern oder fehlender Datei: kein Problem, beim nächsten
        # connect() läuft die Discovery und schreibt die State-Datei neu.
        try:
            state = self._load_state_file()
            if state and self.doi:
                self.doi.set_state(state.get("doi", {}))
        except Exception as e:
            logger.warning(f"State-Datei konnte nicht gelesen werden: {e}")

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

    def verify_password(self, password: str) -> bool:
        """
        Prüft ein Passwort gegen das geladene Wallet, ohne Geheimnisse
        preiszugeben.

        Bevorzugt wird der Schlüssel mit Salt/KDF-Parametern aus der
        gespeicherten Wallet-Datei neu abgeleitet und eine Entschlüsselung
        versucht (scrypt-Kosten sind hier akzeptabel). Ist das Wallet noch
        nicht gespeichert (direkt nach create()/restore()), wird das
        Passwort zeitkonstant (hmac.compare_digest) mit dem im Speicher
        gehaltenen Passwort verglichen.

        Args:
            password: Zu prüfendes Passwort

        Returns:
            True wenn das Passwort korrekt ist, sonst False
            (auch wenn kein Wallet geladen ist)
        """
        if not isinstance(password, str):
            return False

        # Bevorzugt: gegen die gespeicherte Wallet-Datei prüfen
        if self._wallet_path and self._wallet_path.exists():
            try:
                with open(self._wallet_path, "r") as f:
                    wallet_data = json.load(f)
                enc = {
                    "salt": wallet_data["salt"],
                    "nonce": wallet_data["nonce"],
                    "ciphertext": wallet_data["encrypted_seed"],
                    "tag": wallet_data["tag"],
                }
                _decrypt(enc, password, wallet_data.get("kdf_params"))
                return True
            except Exception:
                return False

        # Fallback: Wallet existiert nur im Speicher (vor dem ersten save())
        if self._password is None:
            return False
        return hmac.compare_digest(
            password.encode("utf-8"), self._password.encode("utf-8")
        )

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
            result = self.doi.send(to_address, amount, fee_per_byte=fee_rate)
            # Indizes nach Send persistieren (Best Effort).
            try:
                self.save_state()
            except Exception as e:
                logger.warning(f"State-Persistenz nach DOI-Send fehlgeschlagen: {e}")
            return result

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
                result["doi"] = self.doi.electrum is not None
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
    # State-Persistenz (separate .state.json neben wallet.dat)
    # ──────────────────────────────────────────

    @property
    def _state_path(self) -> Optional[Path]:
        """Pfad zur State-Datei. None wenn das Wallet nicht gespeichert ist."""
        if not self._wallet_path:
            return None
        return self._wallet_path.with_suffix(self._wallet_path.suffix + STATE_FILE_SUFFIX)

    def save_state(self) -> Optional[str]:
        """
        Schreibt nur die State-Datei (Indizes etc.).

        Wird automatisch nach save() und nach jedem DOI-send() aufgerufen –
        kann aber auch manuell ausgelöst werden, z.B. aus einem
        Diagnose-Button im GUI.
        """
        state_path = self._state_path
        if not state_path:
            return None

        payload: dict = {
            "version": 1,
            "wallet": self._wallet_path.name if self._wallet_path else None,
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        if self.doi:
            try:
                payload["doi"] = self.doi.get_state()
            except Exception as e:
                logger.warning(f"DoiWallet.get_state() fehlgeschlagen: {e}")

        # Atomar schreiben, mit restriktiven Dateirechten (0o600).
        # Unter Windows ist der Modus weitgehend wirkungslos – unkritisch.
        tmp = state_path.with_suffix(state_path.suffix + ".tmp")
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(state_path)
        return str(state_path)

    def _load_state_file(self) -> Optional[dict]:
        """Liest die State-Datei, falls vorhanden. Sonst None."""
        state_path = self._state_path
        if not state_path or not state_path.exists():
            return None
        with open(state_path, "r") as f:
            return json.load(f)

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

        # Sensible Daten entfernen (siehe Hinweis in lock(): Python-Strings
        # sind unveränderlich, echtes Memory-Wiping ist hier nicht möglich)
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

        # Sensible Daten entfernen.
        # Hinweis: Python-Strings sind unveränderlich – das Überschreiben
        # erzeugt nur ein neues Objekt und löscht den alten Mnemonic NICHT
        # zuverlässig aus dem Speicher. Es entfernt lediglich die Referenz;
        # echtes Memory-Wiping ist in reinem Python nicht möglich.
        if self._mnemonic:
            self._mnemonic = "x" * len(self._mnemonic)
        self._mnemonic = None
        self._password = None

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
