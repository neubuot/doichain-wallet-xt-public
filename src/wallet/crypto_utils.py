"""
Kryptographische Hilfsfunktionen für Bitcoin-basierte Chains.

Enthält:
- Base58Check Encoding/Decoding
- Bech32/Bech32m Encoding/Decoding (BIP-173/BIP-350, SegWit-Adressen)
- Hash-Funktionen (SHA256, RIPEMD160, Hash160, Hash256)
- ECDSA secp256k1 Operationen
"""

import hashlib
import struct
from typing import Optional, Tuple

# ============================================================
# Hash-Funktionen
# ============================================================

def sha256(data: bytes) -> bytes:
    """Einfacher SHA-256 Hash."""
    return hashlib.sha256(data).digest()


def ripemd160(data: bytes) -> bytes:
    """RIPEMD-160 Hash."""
    h = hashlib.new("ripemd160")
    h.update(data)
    return h.digest()


def hash256(data: bytes) -> bytes:
    """Doppelter SHA-256 (Bitcoin-Standard für Transaktions-Hashes)."""
    return sha256(sha256(data))


def hash160(data: bytes) -> bytes:
    """RIPEMD160(SHA256(data)) - Standard für Bitcoin-Adressen."""
    return ripemd160(sha256(data))


# ============================================================
# Base58 Encoding/Decoding
# ============================================================

BASE58_ALPHABET = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
BASE58_ALPHABET_STR = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(data: bytes) -> str:
    """Base58 Encoding (ohne Checksum)."""
    # Führende Null-Bytes zählen
    leading_zeros = 0
    for byte in data:
        if byte == 0:
            leading_zeros += 1
        else:
            break

    # Bytes als große Ganzzahl interpretieren
    num = int.from_bytes(data, "big")

    # In Base58 umwandeln
    result = []
    while num > 0:
        num, remainder = divmod(num, 58)
        result.append(BASE58_ALPHABET_STR[remainder])

    # Umkehren und führende '1'en hinzufügen
    return "1" * leading_zeros + "".join(reversed(result))


def base58_decode(s: str) -> bytes:
    """Base58 Decoding (ohne Checksum)."""
    num = 0
    for char in s:
        idx = BASE58_ALPHABET_STR.index(char)
        num = num * 58 + idx

    # Führende '1'en zählen
    leading_ones = 0
    for char in s:
        if char == "1":
            leading_ones += 1
        else:
            break

    # In Bytes umwandeln
    if num == 0:
        return b"\x00" * leading_ones

    result = num.to_bytes((num.bit_length() + 7) // 8, "big")
    return b"\x00" * leading_ones + result


def base58check_encode(version: int, payload: bytes) -> str:
    """Base58Check Encoding: Version-Byte + Payload + 4-Byte Checksum."""
    data = bytes([version]) + payload
    checksum = hash256(data)[:4]
    return base58_encode(data + checksum)


def base58check_decode(address: str) -> tuple[int, bytes]:
    """
    Base58Check Decoding.
    
    Returns:
        Tuple von (version_byte, payload_bytes)
    
    Raises:
        ValueError: Bei ungültiger Checksum
    """
    data = base58_decode(address)
    
    # Mindestens 1 Version-Byte + 4 Checksum-Bytes
    if len(data) < 5:
        raise ValueError(f"Base58Check-Daten zu kurz: {len(data)} Bytes")
    
    payload_with_version = data[:-4]
    checksum = data[-4:]
    
    # Checksum verifizieren
    expected_checksum = hash256(payload_with_version)[:4]
    if checksum != expected_checksum:
        raise ValueError(
            f"Ungültige Base58Check-Checksum: "
            f"erwartet {expected_checksum.hex()}, erhalten {checksum.hex()}"
        )
    
    version = payload_with_version[0]
    payload = payload_with_version[1:]
    
    return version, payload


# ============================================================
# Adress-Funktionen
# ============================================================

# Bekannte Doichain Base58Check Version-Bytes (Mainnet, Testnet).
# Andere Version-Bytes (z.B. Bitcoin 0x00/0x05) werden NICHT akzeptiert,
# sonst könnten Coins an Fremd-Chain-Adressen gesendet (verloren) werden.
DOI_P2PKH_VERSIONS = (0x34, 0x6F)   # pubkey_hash: Mainnet "N"/"M", Testnet "m"/"n"
DOI_P2SH_VERSIONS = (0x0D, 0xC4)    # script_hash: Mainnet, Testnet


def pubkey_to_address(pubkey: bytes, version: int = 0x34) -> str:
    """
    Öffentlichen Schlüssel (komprimiert, 33 Bytes) in eine Base58Check-Adresse umwandeln.
    
    Args:
        pubkey: Komprimierter öffentlicher Schlüssel (33 Bytes)
        version: Version-Byte (0x34 für Doichain Mainnet)
    
    Returns:
        Base58Check-kodierte Adresse
    """
    pubkey_hash = hash160(pubkey)
    return base58check_encode(version, pubkey_hash)


def address_to_pubkey_hash(address: str) -> tuple[int, bytes]:
    """
    Adresse in Version-Byte und Public-Key-Hash dekodieren.
    
    Returns:
        Tuple von (version_byte, 20-byte pubkey_hash)
    """
    version, payload = base58check_decode(address)
    if len(payload) != 20:
        raise ValueError(f"Ungültige Payload-Länge: {len(payload)}, erwartet 20")
    return version, payload


def _looks_like_bech32(address: str) -> bool:
    """
    Heuristik: Hat die Adresse Bech32-Form?

    Kriterien (BIP-173): einheitliche Schreibweise, Separator "1" mit
    mindestens 6 Checksum-Zeichen dahinter, Datenanteil nur aus dem
    Bech32-Charset, Gesamtlänge <= 90.
    """
    if address.lower() != address and address.upper() != address:
        return False  # Gemischte Schreibweise → kein gültiges Bech32
    addr = address.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr) or len(addr) > 90:
        return False
    return all(c in BECH32_CHARSET for c in addr[pos + 1:])


def validate_address(address: str, expected_version=None,
                     bech32_hrp: Optional[str] = None) -> bool:
    """
    Prüft ob eine Adresse gültig ist (Legacy Base58Check ODER Bech32 SegWit).

    Args:
        address: Die zu prüfende Adresse
        expected_version: Erwartetes Version-Byte (int) oder mehrere erlaubte
            Version-Bytes (Tuple/Liste/Set) für Base58Check. Ohne Angabe werden
            NUR die bekannten Doichain-Versionen akzeptiert – Adressen fremder
            Chains (z.B. Bitcoin 0x00) werden abgelehnt.
        bech32_hrp: Bech32 Human-Readable Prefix (z.B. "dc" für Doichain).
            Bech32-Adressen werden über den Präfix "<hrp>1" erkannt –
            der HRP wird NICHT aus der Adresse selbst geraten.

    Returns:
        True wenn die Adresse gültig (und netzwerkkonform) ist
    """
    if not address:
        return False

    # Bech32/SegWit: ausschließlich über den bekannten HRP-Präfix erkennen
    if bech32_hrp and address.lower().startswith(bech32_hrp.lower() + "1"):
        witver, _ = bech32_decode_segwit(bech32_hrp.lower(), address)
        return witver is not None

    # Sieht die Adresse generell wie Bech32 aus (Separator "1" + gültiger
    # Charset), NICHT auf Base58 zurückfallen: entweder falscher/unbekannter
    # HRP (Fremd-Chain, z.B. bc1...) oder defekte SegWit-Adresse.
    if _looks_like_bech32(address):
        return False

    # Base58Check (Legacy P2PKH / P2SH)
    try:
        version, payload = base58check_decode(address)
    except (ValueError, IndexError):
        return False
    if len(payload) != 20:
        return False

    if expected_version is None:
        # Ohne explizite Vorgabe: nur bekannte Doichain-Versionen,
        # KEINE beliebigen Version-Bytes (Fremd-Chain-Schutz).
        allowed = set(DOI_P2PKH_VERSIONS) | set(DOI_P2SH_VERSIONS)
    elif isinstance(expected_version, int):
        allowed = {expected_version}
    else:
        allowed = set(expected_version)
    return version in allowed


# ============================================================
# Bech32 / Bech32m Encoding (BIP-173 / BIP-350)
# Referenzimplementierung: github.com/sipa/bech32
# ============================================================

BECH32_CHARSET = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
BECH32_CONST = 1          # Bech32 (SegWit v0)
BECH32M_CONST = 0x2bc830a3  # Bech32m (SegWit v1+, Taproot)


def _bech32_polymod(values: list) -> int:
    """Berechnet das BCH Polynom-Modulus für Bech32."""
    generators = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for value in values:
        top = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ value
        for i in range(5):
            chk ^= generators[i] if ((top >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list:
    """Expandiert den HRP für die Checksum-Berechnung."""
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_verify_checksum(hrp: str, data: list) -> Optional[int]:
    """
    Verifiziert die Bech32-Checksum.
    
    Returns:
        BECH32_CONST (1) für Bech32, BECH32M_CONST für Bech32m, oder None
    """
    check = _bech32_polymod(_bech32_hrp_expand(hrp) + data)
    if check == BECH32_CONST:
        return BECH32_CONST
    elif check == BECH32M_CONST:
        return BECH32M_CONST
    return None


def _bech32_create_checksum(hrp: str, data: list, spec: int = BECH32_CONST) -> list:
    """Berechnet die Bech32/Bech32m Checksum."""
    values = _bech32_hrp_expand(hrp) + data
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ spec
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def bech32_encode(hrp: str, data: list, spec: int = BECH32_CONST) -> str:
    """
    Bech32/Bech32m Encoding.
    
    Args:
        hrp: Human-Readable Part (z.B. "dc")
        data: Liste von 5-Bit Werten
        spec: BECH32_CONST oder BECH32M_CONST
    
    Returns:
        Bech32-kodierter String
    """
    combined = data + _bech32_create_checksum(hrp, data, spec)
    return hrp + "1" + "".join([BECH32_CHARSET[d] for d in combined])


def bech32_decode(bech: str) -> Tuple[Optional[str], Optional[list], Optional[int]]:
    """
    Bech32/Bech32m Decoding.
    
    Returns:
        Tuple von (hrp, data, spec) oder (None, None, None) bei Fehler
    """
    if any(ord(x) < 33 or ord(x) > 126 for x in bech):
        return (None, None, None)
    if bech.lower() != bech and bech.upper() != bech:
        return (None, None, None)
    bech = bech.lower()
    
    pos = bech.rfind("1")
    if pos < 1 or pos + 7 > len(bech) or len(bech) > 90:
        return (None, None, None)
    
    if not all(x in BECH32_CHARSET for x in bech[pos + 1:]):
        return (None, None, None)
    
    hrp = bech[:pos]
    data = [BECH32_CHARSET.find(x) for x in bech[pos + 1:]]
    
    spec = _bech32_verify_checksum(hrp, data)
    if spec is None:
        return (None, None, None)
    
    return (hrp, data[:-6], spec)


def _convertbits(data: list, frombits: int, tobits: int, pad: bool = True) -> Optional[list]:
    """Konvertiert zwischen Bit-Breiten (z.B. 8-Bit → 5-Bit)."""
    acc = 0
    bits = 0
    ret = []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


# ============================================================
# SegWit-Adress-Funktionen
# ============================================================

def bech32_encode_segwit(hrp: str, witver: int, witprog: bytes) -> str:
    """
    Kodiert eine native SegWit-Adresse (P2WPKH, P2WSH, P2TR).
    
    Args:
        hrp: Human-Readable Part (z.B. "dc" für Doichain)
        witver: Witness-Version (0 für P2WPKH/P2WSH, 1 für Taproot)
        witprog: Witness-Programm (20 Bytes für P2WPKH, 32 für P2WSH/P2TR)
    
    Returns:
        Bech32-kodierte SegWit-Adresse
    """
    spec = BECH32_CONST if witver == 0 else BECH32M_CONST
    data5 = _convertbits(list(witprog), 8, 5)
    return bech32_encode(hrp, [witver] + data5, spec)


def bech32_decode_segwit(hrp: str, addr: str) -> Tuple[Optional[int], Optional[bytes]]:
    """
    Dekodiert eine native SegWit-Adresse.
    
    Args:
        hrp: Erwarteter Human-Readable Part (z.B. "dc")
        addr: Bech32/Bech32m-kodierte Adresse
    
    Returns:
        Tuple von (witness_version, witness_program) oder (None, None)
    """
    hrpgot, data, spec = bech32_decode(addr)
    if hrpgot != hrp:
        return (None, None)
    if data is None or len(data) == 0:
        return (None, None)
    
    decoded = _convertbits(data[1:], 5, 8, False)
    if decoded is None or len(decoded) < 2 or len(decoded) > 40:
        return (None, None)
    
    # Witness-Version 0..16
    if data[0] > 16:
        return (None, None)
    
    # v0: nur 20 Bytes (P2WPKH) oder 32 Bytes (P2WSH)
    if data[0] == 0 and len(decoded) != 20 and len(decoded) != 32:
        return (None, None)
    
    # v0 → Bech32, v1+ → Bech32m
    if data[0] == 0 and spec != BECH32_CONST:
        return (None, None)
    if data[0] != 0 and spec != BECH32M_CONST:
        return (None, None)
    
    return (data[0], bytes(decoded))


def pubkey_to_segwit_address(pubkey: bytes, hrp: str = "dc") -> str:
    """
    Öffentlichen Schlüssel in eine native SegWit P2WPKH-Adresse (dc1q...) umwandeln.
    
    Args:
        pubkey: Komprimierter öffentlicher Schlüssel (33 Bytes)
        hrp: Bech32 Human-Readable Part (default: "dc")
    
    Returns:
        Bech32-kodierte P2WPKH-Adresse
    """
    pubkey_hash = hash160(pubkey)
    return bech32_encode_segwit(hrp, 0, pubkey_hash)


# ============================================================
# Universelle Adress → scriptPubKey Konvertierung
# ============================================================

def address_to_script_pubkey(
    address: str,
    bech32_hrp: str = "dc",
    p2pkh_versions: tuple = DOI_P2PKH_VERSIONS,
    p2sh_versions: tuple = DOI_P2SH_VERSIONS,
) -> bytes:
    """
    Konvertiert eine Adresse (Legacy ODER SegWit) in den entsprechenden scriptPubKey.

    Unterstützt:
      - P2PKH (Legacy, z.B. N... / M...)  → OP_DUP OP_HASH160 <20> OP_EQUALVERIFY OP_CHECKSIG
      - P2SH  (z.B. 3...)                 → OP_HASH160 <20> OP_EQUAL
      - P2WPKH (Native SegWit, dc1q..., 20 Bytes) → OP_0 <20>
      - P2WSH  (Native SegWit, dc1q..., 32 Bytes) → OP_0 <32>
      - P2TR   (Taproot, dc1p..., 32 Bytes)       → OP_1 <32>

    Args:
        address: Jede gültige Doichain-Adresse
        bech32_hrp: Bech32 Human-Readable Part
        p2pkh_versions: Erlaubte pubkey_hash Version-Bytes
            (default: Doichain 0x34 Mainnet / 0x6F Testnet)
        p2sh_versions: Erlaubte script_hash Version-Bytes
            (default: Doichain 0x0D Mainnet / 0xC4 Testnet)

    Returns:
        scriptPubKey als Bytes

    Raises:
        ValueError: Bei ungültiger Adresse oder unbekanntem Version-Byte
            (z.B. Bitcoin-Adressen werden NICHT stillschweigend akzeptiert)
    """
    # Versuche zuerst Bech32/SegWit
    witver, witprog = bech32_decode_segwit(bech32_hrp, address)
    if witver is not None:
        # SegWit: OP_N <len> <witness_program>
        if witver == 0:
            op_ver = 0x00  # OP_0
        else:
            op_ver = 0x50 + witver  # OP_1..OP_16
        return bytes([op_ver, len(witprog)]) + witprog

    # Base58Check (Legacy P2PKH oder P2SH)
    try:
        version, payload = base58check_decode(address)
    except ValueError as e:
        raise ValueError(f"Ungültige Adresse '{address}': {e}")

    if len(payload) != 20:
        raise ValueError(f"Ungültige Payload-Länge: {len(payload)}")

    # P2PKH: pubkey_hash Version-Byte (0x34 Mainnet, 0x6F Testnet)
    if version in p2pkh_versions:
        # OP_DUP OP_HASH160 <20 bytes> OP_EQUALVERIFY OP_CHECKSIG
        return bytes([0x76, 0xA9, 0x14]) + payload + bytes([0x88, 0xAC])

    # P2SH: script_hash Version-Byte (0x0D Mainnet, 0xC4 Testnet)
    elif version in p2sh_versions:
        # OP_HASH160 <20 bytes> OP_EQUAL
        return bytes([0xA9, 0x14]) + payload + bytes([0x87])

    else:
        # Unbekanntes Version-Byte → ablehnen statt raten. Eine als P2PKH
        # interpretierte Fremd-Chain-Adresse (z.B. Bitcoin 0x00) würde
        # sonst zu unwiederbringlich verlorenen Coins führen.
        raise ValueError(
            f"Unbekanntes Adress-Version-Byte 0x{version:02X} für '{address}' – "
            f"Adresse gehört nicht zum Doichain-Netzwerk"
        )


# ============================================================
# Satoshi-Konvertierung
# ============================================================

def doi_to_satoshi(doi: float) -> int:
    """DOI in Satoshis umrechnen (vermeidet Fließkomma-Fehler)."""
    return int(round(doi * 100_000_000))


def satoshi_to_doi(satoshi: int) -> float:
    """Satoshis in DOI umrechnen."""
    return satoshi / 100_000_000


# ============================================================
# Kompakter Größen-Encoder (Bitcoin VarInt)
# ============================================================

def encode_varint(n: int) -> bytes:
    """Bitcoin VarInt Encoding."""
    if n < 0xFD:
        return struct.pack("<B", n)
    elif n <= 0xFFFF:
        return b"\xfd" + struct.pack("<H", n)
    elif n <= 0xFFFFFFFF:
        return b"\xfe" + struct.pack("<I", n)
    else:
        return b"\xff" + struct.pack("<Q", n)


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    """
    Bitcoin VarInt Decoding.
    
    Returns:
        Tuple von (wert, neue_offset_position)
    """
    first_byte = data[offset]
    if first_byte < 0xFD:
        return first_byte, offset + 1
    elif first_byte == 0xFD:
        return struct.unpack("<H", data[offset + 1:offset + 3])[0], offset + 3
    elif first_byte == 0xFE:
        return struct.unpack("<I", data[offset + 1:offset + 5])[0], offset + 5
    else:
        return struct.unpack("<Q", data[offset + 1:offset + 9])[0], offset + 9
