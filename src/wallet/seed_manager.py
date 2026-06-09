"""
Seed-Manager für BIP-39 / BIP-32 HD-Wallet Schlüsselableitung.

BIP-39: Mnemonic Seed Phrase → Seed
BIP-32: Seed → Master Key → Ableitungspfad → Kind-Schlüssel
BIP-44: Standard-Ableitungspfad m/44'/coin_type'/account'/change/index

Doichain-Pfad: m/44'/7'/0'/0/index  (Namecoin coin_type=7)
"""

import hashlib
import hmac
import struct
from typing import Optional

from mnemonic import Mnemonic

from .crypto_utils import (
    hash160,
    pubkey_to_address,
    base58check_encode,
    sha256,
)
from .doichain_network import MAINNET, get_network

# secp256k1 Kurvenparameter
SECP256K1_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
SECP256K1_GEN_POINT = (
    0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
    0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8,
)
SECP256K1_P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F


# ============================================================
# Elliptische Kurven Arithmetik (secp256k1)
# ============================================================

def _modinv(a: int, m: int) -> int:
    """Modulare Inverse mittels erweitertem Euklidischem Algorithmus."""
    if a < 0:
        a = a % m
    g, x, _ = _extended_gcd(a, m)
    if g != 1:
        raise ValueError("Modulare Inverse existiert nicht")
    return x % m


def _extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    gcd, x1, y1 = _extended_gcd(b % a, a)
    return gcd, y1 - (b // a) * x1, x1


def point_add(p1: Optional[tuple], p2: Optional[tuple]) -> Optional[tuple]:
    """Punkt-Addition auf der secp256k1 Kurve."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1

    x1, y1 = p1
    x2, y2 = p2

    if x1 == x2 and y1 != y2:
        return None  # Punkt im Unendlichen

    if x1 == x2:
        # Punkt-Verdopplung
        lam = (3 * x1 * x1 * _modinv(2 * y1, SECP256K1_P)) % SECP256K1_P
    else:
        lam = ((y2 - y1) * _modinv(x2 - x1, SECP256K1_P)) % SECP256K1_P

    x3 = (lam * lam - x1 - x2) % SECP256K1_P
    y3 = (lam * (x1 - x3) - y1) % SECP256K1_P
    return (x3, y3)


def scalar_multiply(k: int, point: Optional[tuple] = None) -> Optional[tuple]:
    """Skalare Multiplikation auf secp256k1 (Double-and-Add)."""
    if point is None:
        point = SECP256K1_GEN_POINT

    result = None
    addend = point

    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1

    return result


def point_to_compressed_pubkey(point: tuple) -> bytes:
    """Punkt in komprimierten öffentlichen Schlüssel (33 Bytes) umwandeln."""
    x, y = point
    prefix = b"\x02" if y % 2 == 0 else b"\x03"
    return prefix + x.to_bytes(32, "big")


def privkey_to_pubkey(privkey: bytes) -> bytes:
    """Privaten Schlüssel (32 Bytes) in komprimierten öffentlichen Schlüssel umwandeln."""
    k = int.from_bytes(privkey, "big")
    if k == 0 or k >= SECP256K1_ORDER:
        raise ValueError("Ungültiger privater Schlüssel")
    point = scalar_multiply(k)
    return point_to_compressed_pubkey(point)


# ============================================================
# BIP-39: Mnemonic Seed
# ============================================================

class SeedManager:
    """
    Verwaltet BIP-39 Seed-Phrasen und BIP-32 HD-Schlüsselableitung.
    """

    def __init__(self, network: Optional[dict] = None):
        self.network = network or MAINNET
        self.mnemo = Mnemonic("english")
        self._master_key: Optional[bytes] = None
        self._master_chain_code: Optional[bytes] = None
        self._mnemonic: Optional[str] = None

    @staticmethod
    def generate_mnemonic(strength: int = 256) -> str:
        """
        Generiert eine neue BIP-39 Mnemonic Seed-Phrase.
        
        Args:
            strength: Entropie in Bits (128=12 Wörter, 256=24 Wörter)
        
        Returns:
            Seed-Phrase als String
        """
        mnemo = Mnemonic("english")
        return mnemo.generate(strength)

    @staticmethod
    def validate_mnemonic(mnemonic: str) -> bool:
        """Prüft ob eine Mnemonic-Phrase gültig ist."""
        mnemo = Mnemonic("english")
        return mnemo.check(mnemonic)

    def from_mnemonic(self, mnemonic: str, passphrase: str = "") -> "SeedManager":
        """
        Initialisiert den SeedManager mit einer Mnemonic-Phrase.
        
        Args:
            mnemonic: BIP-39 Seed-Phrase
            passphrase: Optionale Passphrase (BIP-39)
        
        Returns:
            self (für Method-Chaining)
        """
        if not self.validate_mnemonic(mnemonic):
            raise ValueError("Ungültige Mnemonic-Phrase")

        self._mnemonic = mnemonic

        # BIP-39: Mnemonic → Seed (512 Bit)
        seed = Mnemonic.to_seed(mnemonic, passphrase)

        # BIP-32: Seed → Master Key
        self._derive_master_key(seed)

        return self

    def _derive_master_key(self, seed: bytes):
        """BIP-32: Seed → Master Private Key + Chain Code."""
        h = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
        self._master_key = h[:32]
        self._master_chain_code = h[32:]

        # Prüfe ob der Schlüssel gültig ist
        k = int.from_bytes(self._master_key, "big")
        if k == 0 or k >= SECP256K1_ORDER:
            raise ValueError("Ungültiger Master-Schlüssel (extrem unwahrscheinlich)")

    def _derive_child(
        self, parent_key: bytes, parent_chain_code: bytes, index: int, hardened: bool = False
    ) -> tuple[bytes, bytes]:
        """
        BIP-32: Ein Kind-Schlüsselpaar ableiten.
        
        Args:
            parent_key: Eltern-Privatschlüssel (32 Bytes)
            parent_chain_code: Eltern-Chain-Code (32 Bytes)
            index: Kind-Index (0-basiert)
            hardened: Ob gehärtete Ableitung verwendet wird
        
        Returns:
            Tuple von (child_key, child_chain_code)
        """
        if hardened:
            index += 0x80000000
            # Gehärtete Ableitung: HMAC-SHA512(chain_code, 0x00 + privkey + index)
            data = b"\x00" + parent_key + struct.pack(">I", index)
        else:
            # Normale Ableitung: HMAC-SHA512(chain_code, pubkey + index)
            parent_pubkey = privkey_to_pubkey(parent_key)
            data = parent_pubkey + struct.pack(">I", index)

        h = hmac.new(parent_chain_code, data, hashlib.sha512).digest()
        il_int = int.from_bytes(h[:32], "big")
        child_key_int = (il_int + int.from_bytes(parent_key, "big")) % SECP256K1_ORDER

        # BIP-32: IL >= n oder ki == 0 → Schlüssel ungültig,
        # der Index muss übersprungen werden (extrem unwahrscheinlich)
        if il_int >= SECP256K1_ORDER or child_key_int == 0:
            raise ValueError("Ungültiger Kind-Schlüssel (extrem unwahrscheinlich)")

        child_key = child_key_int.to_bytes(32, "big")
        child_chain_code = h[32:]

        return child_key, child_chain_code

    def derive_path(self, path: str) -> tuple[bytes, bytes]:
        """
        BIP-32: Schlüssel über einen Pfad ableiten.
        
        Args:
            path: BIP-32 Pfad, z.B. "m/44'/7'/0'/0/0"
        
        Returns:
            Tuple von (private_key, chain_code)
        """
        if self._master_key is None:
            raise RuntimeError("SeedManager nicht initialisiert. Zuerst from_mnemonic() aufrufen.")

        parts = path.strip().split("/")
        if not parts or parts[0] != "m":
            raise ValueError(f"Ungültiger BIP-32 Pfad: {path!r} (muss mit 'm' beginnen)")

        key = self._master_key
        chain_code = self._master_chain_code

        # Pfad "m" alleine → Master-Schlüssel zurückgeben
        for part in parts[1:]:
            hardened = part.endswith("'") or part.endswith("h")
            index_str = part[:-1] if hardened else part
            if not index_str.isdigit():
                raise ValueError(f"Ungültige Pfad-Komponente: {part!r} in {path!r}")
            index = int(index_str)
            if not 0 <= index < 2**31:
                raise ValueError(f"Index außerhalb des gültigen Bereichs (0..2^31-1): {part!r}")
            key, chain_code = self._derive_child(key, chain_code, index, hardened)

        return key, chain_code

    def get_keypair(self, index: int = 0, change: int = 0, account: int = 0) -> dict:
        """
        Gibt ein Schlüsselpaar für den gegebenen Index zurück.
        
        Args:
            index: Adress-Index (0-basiert)
            change: 0=Empfangsadresse, 1=Wechselgeld-Adresse
            account: Konto-Index
        
        Returns:
            Dict mit private_key, public_key, address, path
        """
        coin_type = self.network["bip44_coin_type"]
        path = f"m/44'/{coin_type}'/{account}'/{change}/{index}"
        
        privkey, _ = self.derive_path(path)
        pubkey = privkey_to_pubkey(privkey)
        address = pubkey_to_address(pubkey, self.network["pubkey_hash"])

        return {
            "private_key": privkey,
            "public_key": pubkey,
            "address": address,
            "path": path,
            "index": index,
            "change": change,
        }

    def get_receive_address(self, index: int = 0) -> str:
        """Gibt eine Empfangsadresse zurück."""
        return self.get_keypair(index=index, change=0)["address"]

    def get_change_address(self, index: int = 0) -> str:
        """Gibt eine Wechselgeld-Adresse zurück."""
        return self.get_keypair(index=index, change=1)["address"]

    def get_private_key_wif(self, index: int = 0, change: int = 0) -> str:
        """
        Gibt den privaten Schlüssel im WIF-Format (Wallet Import Format) zurück.
        
        Args:
            index: Adress-Index
            change: 0=Empfang, 1=Wechselgeld
        
        Returns:
            WIF-kodierter privater Schlüssel
        """
        keypair = self.get_keypair(index=index, change=change)
        privkey = keypair["private_key"]
        
        # WIF: version + privkey + 0x01 (compressed) + checksum
        return base58check_encode(
            self.network["wif_prefix"],
            privkey + b"\x01"  # 0x01 = komprimierter öffentlicher Schlüssel
        )

    @property
    def mnemonic(self) -> Optional[str]:
        """Gibt die Mnemonic-Phrase zurück (Vorsicht: sensible Daten!)."""
        return self._mnemonic

    @property
    def is_initialized(self) -> bool:
        """Prüft ob der SeedManager initialisiert ist."""
        return self._master_key is not None
