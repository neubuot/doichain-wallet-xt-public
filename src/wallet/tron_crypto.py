"""
Tron Kryptographie-Utilities

Tron-spezifische Kryptofunktionen:
- Adressgenerierung: secp256k1 Public Key → Keccak-256 → Base58Check (0x41 Prefix)
- Transaktionssignierung: ECDSA mit secp256k1
- Adressvalidierung: Base58Check + Hex-Adressen (41...)

Tron BIP-44 Pfad: m/44'/195'/0'/0/x
"""

import hashlib
import struct
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Tuple

from Crypto.Hash import keccak


# ──────────────────────────────────────────────
# Konstanten
# ──────────────────────────────────────────────

TRON_ADDRESS_PREFIX = 0x41  # Mainnet (alle Adressen beginnen mit "T")
TRON_ADDRESS_PREFIX_TESTNET = 0xA0  # Testnet

# Base58 Alphabet (gleich wie Bitcoin)
BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# ──────────────────────────────────────────────
# Hash-Funktionen
# ──────────────────────────────────────────────

def keccak256(data: bytes) -> bytes:
    """Keccak-256 Hash (NICHT SHA3-256!)."""
    k = keccak.new(digest_bits=256)
    k.update(data)
    return k.digest()


def sha256(data: bytes) -> bytes:
    """SHA-256 Hash."""
    return hashlib.sha256(data).digest()


def double_sha256(data: bytes) -> bytes:
    """Doppelter SHA-256 Hash (für Base58Check Checksum)."""
    return sha256(sha256(data))


# ──────────────────────────────────────────────
# Base58Check Encoding/Decoding
# ──────────────────────────────────────────────

def base58_encode(data: bytes) -> str:
    """Base58-Encoding (ohne Checksum)."""
    num = int.from_bytes(data, "big")
    result = []
    while num > 0:
        num, remainder = divmod(num, 58)
        result.append(BASE58_ALPHABET[remainder])
    # Führende Null-Bytes als '1' kodieren
    for byte in data:
        if byte == 0:
            result.append("1")
        else:
            break
    return "".join(reversed(result))


def base58_decode(s: str) -> bytes:
    """Base58-Decoding (ohne Checksum)."""
    num = 0
    for char in s:
        num = num * 58 + BASE58_ALPHABET.index(char)
    # Länge berechnen
    byte_length = (num.bit_length() + 7) // 8
    result = num.to_bytes(byte_length, "big") if byte_length > 0 else b""
    # Führende '1' als Null-Bytes
    leading_ones = len(s) - len(s.lstrip("1"))
    return b"\x00" * leading_ones + result


def base58check_encode(payload: bytes) -> str:
    """Base58Check-Encoding (mit 4-Byte Checksum)."""
    checksum = double_sha256(payload)[:4]
    return base58_encode(payload + checksum)


def base58check_decode(address: str) -> Optional[bytes]:
    """
    Base58Check-Decoding mit Checksum-Verifizierung.
    
    Returns:
        Payload-Bytes (ohne Checksum) oder None bei Fehler
    """
    try:
        data = base58_decode(address)
        if len(data) < 5:
            return None
        payload, checksum = data[:-4], data[-4:]
        if double_sha256(payload)[:4] != checksum:
            return None
        return payload
    except (ValueError, IndexError):
        return None


# ──────────────────────────────────────────────
# Tron-Adressgenerierung
# ──────────────────────────────────────────────

def pubkey_to_tron_address(pubkey: bytes, prefix: int = TRON_ADDRESS_PREFIX) -> str:
    """
    Konvertiert einen secp256k1 Public Key in eine Tron-Adresse.
    
    Algorithmus:
        1. Public Key (unkomprimiert, 65 Bytes mit 04-Prefix)
        2. Keccak-256(PubKey[1:]) → 32 Bytes
        3. Letzte 20 Bytes = Address-Bytes
        4. 0x41 + Address-Bytes → 21 Bytes
        5. Base58Check-Encoding → "T..."
    
    Args:
        pubkey: Öffentlicher Schlüssel (33 Bytes komprimiert oder 65 Bytes unkomprimiert)
        prefix: Adress-Prefix (0x41 = Mainnet, 0xA0 = Testnet)
    
    Returns:
        Tron-Adresse im Base58Check-Format (z.B. "TJCnKsPa7y5okkXvQAidZBzqx3QyQ6sxMW")
    """
    # Komprimierten Key in unkomprimierten konvertieren
    if len(pubkey) == 33:
        pubkey = _decompress_pubkey(pubkey)
    
    if len(pubkey) != 65 or pubkey[0] != 0x04:
        raise ValueError(f"Ungültiger Public Key: erwartet 65 Bytes (04+x+y), bekam {len(pubkey)} Bytes")
    
    # Keccak-256 Hash (ohne 04-Prefix)
    key_hash = keccak256(pubkey[1:])
    
    # Letzte 20 Bytes = Adress-Bytes
    address_bytes = key_hash[-20:]
    
    # Prefix + Adress-Bytes
    payload = bytes([prefix]) + address_bytes
    
    # Base58Check
    return base58check_encode(payload)


def tron_address_to_hex(address: str) -> Optional[str]:
    """
    Konvertiert eine Base58Check Tron-Adresse in Hex-Format (41...).
    
    Args:
        address: Base58Check Tron-Adresse (z.B. "TJCn...")
    
    Returns:
        Hex-String (z.B. "41...") oder None bei Fehler
    """
    payload = base58check_decode(address)
    if payload is None or len(payload) != 21:
        return None
    return payload.hex()


def hex_to_tron_address(hex_address: str) -> Optional[str]:
    """
    Konvertiert eine Hex-Adresse (41...) in Base58Check-Format.
    
    Args:
        hex_address: Hex-String (z.B. "41..." oder "0x41...")
    
    Returns:
        Base58Check Tron-Adresse (z.B. "TJCn...")
    """
    hex_address = hex_address.lower().replace("0x", "")
    try:
        payload = bytes.fromhex(hex_address)
        if len(payload) != 21 or payload[0] != TRON_ADDRESS_PREFIX:
            return None
        return base58check_encode(payload)
    except ValueError:
        return None


def validate_tron_address(address: str) -> bool:
    """
    Validiert eine Tron-Adresse (Base58Check oder Hex).
    
    Args:
        address: Tron-Adresse
    
    Returns:
        True wenn gültig
    """
    if not address:
        return False
    
    # Hex-Adresse (41...)
    if address.startswith("41") and len(address) == 42:
        try:
            bytes.fromhex(address)
            return True
        except ValueError:
            return False
    
    # Base58Check-Adresse (T...)
    if not address.startswith("T"):
        return False
    
    payload = base58check_decode(address)
    if payload is None:
        return False
    
    return len(payload) == 21 and payload[0] == TRON_ADDRESS_PREFIX


# ──────────────────────────────────────────────
# Public Key Decompression
# ──────────────────────────────────────────────

def _decompress_pubkey(compressed: bytes) -> bytes:
    """
    Dekomprimiert einen secp256k1 Public Key (33 → 65 Bytes).
    
    Verwendet die secp256k1-Kurvengleichung: y² = x³ + 7 (mod p)
    """
    if len(compressed) != 33 or compressed[0] not in (0x02, 0x03):
        raise ValueError("Ungültiger komprimierter Public Key")
    
    # secp256k1 Parameter
    p = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
    
    x = int.from_bytes(compressed[1:], "big")
    
    # y² = x³ + 7 (mod p)
    y_squared = (pow(x, 3, p) + 7) % p
    
    # Modulare Quadratwurzel (p ≡ 3 mod 4)
    y = pow(y_squared, (p + 1) // 4, p)
    
    # Parität prüfen (02 = gerade, 03 = ungerade)
    if (y % 2) != (compressed[0] - 0x02):
        y = p - y
    
    return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


# ──────────────────────────────────────────────
# Transaktions-Signierung
# ──────────────────────────────────────────────

def sign_transaction(tx_hash: bytes, private_key: bytes) -> bytes:
    """
    Signiert einen Transaktions-Hash mit ECDSA (secp256k1).
    
    Tron verwendet den gleichen ECDSA-Algorithmus wie Bitcoin/Ethereum,
    aber die Signatur wird als 65-Byte recoverable Signature zurückgegeben:
    r (32 Bytes) + s (32 Bytes) + v (1 Byte, Recovery-ID)
    
    Args:
        tx_hash: 32-Byte SHA-256 Hash der Transaktion (txID)
        private_key: 32-Byte Private Key
    
    Returns:
        65-Byte Signatur (r + s + v)
    """
    from ecdsa import SigningKey, SECP256k1
    from ecdsa.util import sigencode_string

    sk = SigningKey.from_string(private_key, curve=SECP256k1)

    # Deterministisch signieren (RFC 6979) – kein zufälliges k,
    # damit schwache Zufallsquellen den Private Key nicht gefährden
    signature = sk.sign_digest_deterministic(
        tx_hash,
        hashfunc=hashlib.sha256,
        sigencode=sigencode_string,
    )

    # r und s extrahieren (je 32 Bytes)
    r = int.from_bytes(signature[:32], "big")
    s = int.from_bytes(signature[32:], "big")

    # Low-S-Normalisierung (Schutz vor Signatur-Malleability):
    # Bei s > n/2 wird s = n - s gesetzt; die Recovery-ID wird unten
    # anhand der normalisierten Signatur neu bestimmt.
    n = SECP256k1.order
    if s > n // 2:
        s = n - s

    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")

    # Recovery ID berechnen
    vk = sk.get_verifying_key()
    pubkey = b"\x04" + vk.to_string()

    recovery_id = _find_recovery_id(tx_hash, r, s, pubkey)

    return signature + bytes([recovery_id])


def _find_recovery_id(msg_hash: bytes, r: int, s: int, pubkey: bytes) -> int:
    """
    Findet die Recovery-ID (0 oder 1) für eine ECDSA-Signatur.

    Raises:
        RuntimeError: Wenn keine Recovery-ID den Public Key reproduziert
                      (eine falsche ID würde zu einer ungültigen Signatur
                      und damit potenziell zu Geldverlust führen).
    """
    from ecdsa import SECP256k1, VerifyingKey
    from ecdsa.util import sigdecode_string

    recovered_keys = VerifyingKey.from_public_key_recovery_with_digest(
        signature=r.to_bytes(32, "big") + s.to_bytes(32, "big"),
        digest=msg_hash,
        curve=SECP256k1,
        hashfunc=hashlib.sha256,
        sigdecode=sigdecode_string
    )
    for i, key in enumerate(recovered_keys):
        if b"\x04" + key.to_string() == pubkey:
            return i

    raise RuntimeError(
        "Keine gültige Recovery-ID gefunden – Signatur passt nicht zum Public Key"
    )


# ──────────────────────────────────────────────
# BIP-44 Adressableitung
# ──────────────────────────────────────────────

def derive_tron_address_from_seed(
    seed: bytes,
    account: int = 0,
    index: int = 0,
    prefix: int = TRON_ADDRESS_PREFIX
) -> Tuple[str, bytes, bytes]:
    """
    Leitet eine Tron-Adresse aus einem BIP-39 Seed ab.
    
    Pfad: m/44'/195'/account'/0/index
    
    Args:
        seed: BIP-39 Seed (64 Bytes)
        account: BIP-44 Account-Index
        index: Adress-Index
        prefix: Adress-Prefix (0x41 = Mainnet)
    
    Returns:
        Tuple: (tron_address, private_key_bytes, public_key_bytes)
    """
    # BIP-32 Master-Key ableiten
    import hmac
    master_secret = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    master_key = master_secret[:32]
    master_chain = master_secret[32:]
    
    # BIP-44 Pfad: m/44'/195'/account'/0/index
    path = [
        44 + 0x80000000,      # 44' (Purpose)
        195 + 0x80000000,     # 195' (Tron Coin-Type)
        account + 0x80000000, # account' 
        0,                    # 0 (External chain)
        index,                # Adress-Index
    ]
    
    key = master_key
    chain = master_chain
    
    for child_index in path:
        key, chain = _ckd_priv(key, chain, child_index)
    
    # Public Key generieren (unkomprimiert)
    from ecdsa import SigningKey, SECP256k1
    sk = SigningKey.from_string(key, curve=SECP256k1)
    vk = sk.get_verifying_key()
    pubkey_uncompressed = b"\x04" + vk.to_string()  # 65 Bytes
    
    # Tron-Adresse generieren
    address = pubkey_to_tron_address(pubkey_uncompressed, prefix)
    
    return address, key, pubkey_uncompressed


def _ckd_priv(key: bytes, chain: bytes, index: int) -> Tuple[bytes, bytes]:
    """
    Child Key Derivation (Private) – BIP-32.
    
    Identisch mit der Implementierung in seed_manager.py,
    hier dupliziert um zirkuläre Imports zu vermeiden.
    """
    import hmac
    
    if index >= 0x80000000:
        # Hardened: HMAC-SHA512(chain, 0x00 + key + index)
        data = b"\x00" + key + struct.pack(">I", index)
    else:
        # Normal: HMAC-SHA512(chain, pubkey + index)
        from ecdsa import SigningKey, SECP256k1
        sk = SigningKey.from_string(key, curve=SECP256k1)
        vk = sk.get_verifying_key()
        # Komprimierter Public Key
        pubkey = vk.to_string()
        x = pubkey[:32]
        y = int.from_bytes(pubkey[32:], "big")
        prefix = b"\x02" if y % 2 == 0 else b"\x03"
        compressed = prefix + x
        data = compressed + struct.pack(">I", index)
    
    I = hmac.new(chain, data, hashlib.sha512).digest()
    IL, IR = I[:32], I[32:]

    # Neuer Key = (IL + key) mod n
    n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
    il_int = int.from_bytes(IL, "big")
    child_int = (il_int + int.from_bytes(key, "big")) % n

    # BIP-32 Gültigkeitsprüfung: IL >= n oder Child-Key == 0 ist ungültig
    # (laut BIP-32 müsste dann der nächste Index verwendet werden)
    if il_int >= n or child_int == 0:
        raise ValueError(
            f"Ungültiger BIP-32 Child-Key bei Index {index} – "
            f"bitte nächsten Index verwenden"
        )

    child_key = child_int.to_bytes(32, "big")

    return child_key, IR


# ──────────────────────────────────────────────
# Utility: SUN ↔ TRX Konvertierung
# ──────────────────────────────────────────────

def sun_to_trx(sun: int) -> float:
    """Konvertiert SUN in TRX (1 TRX = 1.000.000 SUN)."""
    return sun / 1_000_000


def trx_to_sun(trx: float) -> int:
    """
    Konvertiert TRX in SUN.

    Verwendet Decimal mit kaufmännischer Rundung, um Float-Abschneidefehler
    zu vermeiden (z.B. int(19.99 * 1e6) == 19989999).
    """
    return int((Decimal(str(trx)) * 1_000_000).to_integral_value(rounding=ROUND_HALF_UP))


def raw_to_usdt(raw: int) -> float:
    """Konvertiert Raw-USDT in USDT (6 Dezimalstellen)."""
    return raw / 1_000_000


def usdt_to_raw(usdt: float) -> int:
    """
    Konvertiert USDT in Raw-Wert.

    Verwendet Decimal mit kaufmännischer Rundung, um Float-Abschneidefehler
    zu vermeiden.
    """
    return int((Decimal(str(usdt)) * 1_000_000).to_integral_value(rounding=ROUND_HALF_UP))
