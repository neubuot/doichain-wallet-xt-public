"""
Doichain Transaktions-Builder.

Erstellt und signiert P2PKH (Pay-to-Public-Key-Hash) Transaktionen
für die Doichain Blockchain (Bitcoin-Fork UTXO-Modell).

Unterstützt Outputs an:
  - P2PKH  (Legacy, N.../M...)
  - P2SH   (Script-Hash, 3...)
  - P2WPKH (Native SegWit, dc1q... 20 Bytes)
  - P2WSH  (Native SegWit, dc1q... 32 Bytes)
  - P2TR   (Taproot, dc1p... 32 Bytes)

Transaktionsformat: Version 1, Inputs nur P2PKH-signiert.
"""

import math
import struct
import hashlib
from typing import Optional

from .crypto_utils import (
    hash256,
    encode_varint,
    address_to_pubkey_hash,
    address_to_script_pubkey,
    doi_to_satoshi,
    satoshi_to_doi,
)
from .seed_manager import privkey_to_pubkey

# SIGHASH Typen
SIGHASH_ALL = 0x01

# Doichain pubkey_hash Version-Bytes (Mainnet 0x34, Testnet 0x6F).
# Der Signierer implementiert NUR den Legacy-P2PKH-Sighash (kein BIP-143,
# keine Witness-Serialisierung) – andere Input-Typen müssen abgelehnt werden,
# sonst entstehen ungültige Signaturen und festsitzende/verlorene Coins.
P2PKH_VERSION_BYTES = (0x34, 0x6F)


def _assert_p2pkh_utxo(utxo: "UTXO"):
    """
    Stellt sicher, dass der UTXO zu einer P2PKH-Adresse gehört.

    Raises:
        ValueError: Wenn die Adresse kein Doichain-P2PKH ist
            (z.B. P2SH, SegWit/Bech32 oder Fremd-Chain).
    """
    try:
        version, _ = address_to_pubkey_hash(utxo.address)
    except ValueError:
        raise ValueError(
            f"Nur P2PKH-Inputs werden unterstützt "
            f"(Adresse {utxo.address} ist kein Base58-P2PKH)"
        )
    if version not in P2PKH_VERSION_BYTES:
        raise ValueError(
            f"Nur P2PKH-Inputs werden unterstützt "
            f"(Adresse {utxo.address} hat Version-Byte 0x{version:02X})"
        )


class UTXO:
    """Repräsentiert einen unverbrauchten Transaktionsausgang."""

    def __init__(
        self,
        tx_hash: str,
        tx_pos: int,
        value: int,
        address: str,
        height: int = 0,
    ):
        self.tx_hash = tx_hash     # 64 Hex-Zeichen
        self.tx_pos = tx_pos       # Output-Index
        self.value = value         # Wert in Satoshis
        self.address = address     # Zugehörige Adresse
        self.height = height       # Block-Höhe (0 = unbestätigt)

    @property
    def outpoint(self) -> bytes:
        """Serialisierter Outpoint (32 Bytes txid + 4 Bytes index)."""
        # txid in reversed byte order (little-endian)
        txid_bytes = bytes.fromhex(self.tx_hash)[::-1]
        return txid_bytes + struct.pack("<I", self.tx_pos)

    def __repr__(self):
        return f"UTXO({self.tx_hash[:8]}...:{self.tx_pos}, {satoshi_to_doi(self.value)} DOI)"


class TxInput:
    """Ein Transaktionseingang."""

    def __init__(self, utxo: UTXO, private_key: Optional[bytes] = None):
        self.utxo = utxo
        self.private_key = private_key
        self.script_sig = b""  # Wird beim Signieren befüllt
        self.sequence = 0xFFFFFFFF

    def serialize_unsigned(self, script_pubkey: bytes) -> bytes:
        """Serialisiert den Input mit dem scriptPubKey (für Signierung)."""
        return (
            self.utxo.outpoint
            + encode_varint(len(script_pubkey))
            + script_pubkey
            + struct.pack("<I", self.sequence)
        )

    def serialize(self) -> bytes:
        """Serialisiert den Input mit scriptSig."""
        return (
            self.utxo.outpoint
            + encode_varint(len(self.script_sig))
            + self.script_sig
            + struct.pack("<I", self.sequence)
        )


class TxOutput:
    """Ein Transaktionsausgang."""

    def __init__(self, value: int, address: str, bech32_hrp: str = "dc"):
        """
        Args:
            value: Wert in Satoshis
            address: Empfängeradresse (Legacy P2PKH, P2SH, oder SegWit Bech32)
            bech32_hrp: Bech32 Human-Readable Part (default: "dc" für Doichain)
        """
        self.value = value
        self.address = address
        self.bech32_hrp = bech32_hrp

    @property
    def script_pubkey(self) -> bytes:
        """Erstellt den scriptPubKey für die Adresse (P2PKH, P2SH, P2WPKH, P2WSH, P2TR)."""
        return address_to_script_pubkey(self.address, self.bech32_hrp)

    def serialize(self) -> bytes:
        """Serialisiert den Output."""
        # Wert muss in ein unsigniertes 64-Bit-Feld passen; negative Werte
        # würden mit "<q" stillschweigend als riesige Beträge serialisiert.
        if self.value < 0 or self.value > 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"Ungültiger Output-Wert: {self.value}")
        script = self.script_pubkey
        return struct.pack("<Q", self.value) + encode_varint(len(script)) + script


def make_p2pkh_script(address: str, bech32_hrp: str = "dc") -> bytes:
    """Erstellt ein scriptPubKey für eine Adresse (P2PKH, P2SH, oder SegWit)."""
    return address_to_script_pubkey(address, bech32_hrp)


class Transaction:
    """
    Doichain-Transaktion (P2PKH).
    
    Erstellt, signiert und serialisiert Transaktionen im Bitcoin-Format.
    """

    def __init__(self, version: int = 1, locktime: int = 0):
        self.version = version
        self.locktime = locktime
        self.inputs: list[TxInput] = []
        self.outputs: list[TxOutput] = []

    def add_input(self, utxo: UTXO, private_key: bytes) -> "Transaction":
        """
        Fügt einen Input hinzu.

        Args:
            utxo: Der zu verbrauchende UTXO (muss P2PKH sein)
            private_key: Der zugehörige private Schlüssel

        Raises:
            ValueError: Wenn der UTXO kein P2PKH-Input ist (der Signierer
                unterstützt kein BIP-143/SegWit).
        """
        _assert_p2pkh_utxo(utxo)
        self.inputs.append(TxInput(utxo, private_key))
        return self

    def add_output(self, address: str, value: int) -> "Transaction":
        """
        Fügt einen Output hinzu.
        
        Args:
            address: Empfängeradresse
            value: Wert in Satoshis
        """
        if value < 0:
            raise ValueError(f"Ungültiger Output-Wert: {value}")
        self.outputs.append(TxOutput(value, address))
        return self

    def _serialize_for_signing(self, input_index: int) -> bytes:
        """
        Serialisiert die Transaktion für die Signierung eines bestimmten Inputs.
        
        Für SIGHASH_ALL: Alle Outputs bleiben, alle Inputs außer dem
        aktuellen bekommen ein leeres scriptSig.
        """
        parts = []

        # Version
        parts.append(struct.pack("<I", self.version))

        # Inputs
        parts.append(encode_varint(len(self.inputs)))
        for i, inp in enumerate(self.inputs):
            if i == input_index:
                # Aktueller Input: scriptPubKey des UTXO einfügen
                script_pubkey = make_p2pkh_script(inp.utxo.address)
                parts.append(inp.serialize_unsigned(script_pubkey))
            else:
                # Andere Inputs: leeres Script
                parts.append(inp.utxo.outpoint)
                parts.append(encode_varint(0))
                parts.append(struct.pack("<I", inp.sequence))

        # Outputs
        parts.append(encode_varint(len(self.outputs)))
        for out in self.outputs:
            parts.append(out.serialize())

        # Locktime
        parts.append(struct.pack("<I", self.locktime))

        # SIGHASH_ALL
        parts.append(struct.pack("<I", SIGHASH_ALL))

        return b"".join(parts)

    def _sign_input(self, input_index: int) -> bytes:
        """
        Signiert einen einzelnen Input und gibt das scriptSig zurück.
        
        Returns:
            scriptSig bytes (DER-Signatur + SIGHASH + komprimierter PubKey)
        """
        inp = self.inputs[input_index]
        if inp.private_key is None:
            raise ValueError(f"Kein privater Schlüssel für Input {input_index}")

        # 1. Transaktion für Signierung serialisieren
        tx_for_signing = self._serialize_for_signing(input_index)

        # 2. Doppelter SHA-256 Hash
        sighash = hash256(tx_for_signing)

        # 3. ECDSA-Signatur erstellen (DER-Format)
        signature_der = _ecdsa_sign(inp.private_key, sighash)

        # 4. SIGHASH-Byte anhängen
        signature = signature_der + bytes([SIGHASH_ALL])

        # 5. Öffentlichen Schlüssel ableiten
        pubkey = privkey_to_pubkey(inp.private_key)

        # 6. scriptSig erstellen: <sig_len> <signature> <pubkey_len> <pubkey>
        script_sig = (
            bytes([len(signature)]) + signature
            + bytes([len(pubkey)]) + pubkey
        )

        return script_sig

    def sign(self) -> "Transaction":
        """
        Signiert alle Inputs der Transaktion.
        
        Returns:
            self (für Method-Chaining)
        """
        for i in range(len(self.inputs)):
            self.inputs[i].script_sig = self._sign_input(i)
        return self

    def serialize(self) -> bytes:
        """
        Serialisiert die signierte Transaktion.
        
        Returns:
            Rohe Transaktions-Bytes
        """
        parts = []

        # Version
        parts.append(struct.pack("<I", self.version))

        # Inputs
        parts.append(encode_varint(len(self.inputs)))
        for inp in self.inputs:
            parts.append(inp.serialize())

        # Outputs
        parts.append(encode_varint(len(self.outputs)))
        for out in self.outputs:
            parts.append(out.serialize())

        # Locktime
        parts.append(struct.pack("<I", self.locktime))

        return b"".join(parts)

    def serialize_hex(self) -> str:
        """Gibt die signierte Transaktion als Hex-String zurück."""
        return self.serialize().hex()

    @property
    def txid(self) -> str:
        """Berechnet die Transaktions-ID (reversed double SHA-256)."""
        return hash256(self.serialize())[::-1].hex()

    @property
    def total_input(self) -> int:
        """Gesamter Input-Wert in Satoshis."""
        return sum(inp.utxo.value for inp in self.inputs)

    @property
    def total_output(self) -> int:
        """Gesamter Output-Wert in Satoshis."""
        return sum(out.value for out in self.outputs)

    @property
    def fee(self) -> int:
        """Transaktionsgebühr in Satoshis."""
        return self.total_input - self.total_output

    @property
    def size(self) -> int:
        """Transaktionsgröße in Bytes (signiert exakt, sonst minimal geschätzt)."""
        # Basis ist immer die REALE Serialisierung (korrekte Output-Größen,
        # VarInts etc.). Für jeden noch unsignierten Input fehlt lediglich
        # das P2PKH-scriptSig (~107 Bytes: Sig + SIGHASH + PubKey), das wird
        # aufaddiert statt die gesamte Transaktion pauschal zu schätzen.
        unsigned_inputs = sum(1 for inp in self.inputs if inp.script_sig == b"")
        return len(self.serialize()) + unsigned_inputs * 107

    def __repr__(self):
        return (
            f"Transaction(inputs={len(self.inputs)}, outputs={len(self.outputs)}, "
            f"fee={self.fee} sat)"
        )


# ============================================================
# ECDSA Signierung (secp256k1, RFC 6979)
# ============================================================

from .seed_manager import SECP256K1_ORDER, scalar_multiply


def _ecdsa_sign(private_key: bytes, message_hash: bytes) -> bytes:
    """
    ECDSA-Signatur mit deterministic k (RFC 6979).
    
    Args:
        private_key: 32-Byte privater Schlüssel
        message_hash: 32-Byte Hash der zu signierenden Nachricht
    
    Returns:
        DER-kodierte Signatur
    """
    d = int.from_bytes(private_key, "big")
    z = int.from_bytes(message_hash, "big")
    n = SECP256K1_ORDER

    # RFC 6979 deterministic k
    k = _rfc6979_k(private_key, message_hash)

    # r = (k * G).x mod n
    point = scalar_multiply(k)
    r = point[0] % n
    if r == 0:
        raise ValueError("Signatur fehlgeschlagen: r == 0")

    # s = k^(-1) * (z + r*d) mod n
    from .seed_manager import _modinv
    k_inv = _modinv(k, n)
    s = (k_inv * (z + r * d)) % n
    if s == 0:
        raise ValueError("Signatur fehlgeschlagen: s == 0")

    # Low-S Normalisierung (BIP-62)
    if s > n // 2:
        s = n - s

    return _der_encode_signature(r, s)


def _rfc6979_k(private_key: bytes, message_hash: bytes) -> int:
    """RFC 6979 deterministic k generation für secp256k1."""
    n = SECP256K1_ORDER
    q_len = 32  # Byte-Länge der Ordnung

    # Schritt a: h1 = Hash(message) - bereits erledigt
    h1 = message_hash

    # Schritt b: V = 0x01 * 32
    v = b"\x01" * 32

    # Schritt c: K = 0x00 * 32
    k = b"\x00" * 32

    # Schritt d: K = HMAC(K, V || 0x00 || privkey || h1)
    k = hmac_sha256(k, v + b"\x00" + private_key + h1)

    # Schritt e: V = HMAC(K, V)
    v = hmac_sha256(k, v)

    # Schritt f: K = HMAC(K, V || 0x01 || privkey || h1)
    k = hmac_sha256(k, v + b"\x01" + private_key + h1)

    # Schritt g: V = HMAC(K, V)
    v = hmac_sha256(k, v)

    # Schritt h: Wiederhole bis gültiges k gefunden
    while True:
        v = hmac_sha256(k, v)
        candidate = int.from_bytes(v, "big")

        if 1 <= candidate < n:
            return candidate

        k = hmac_sha256(k, v + b"\x00")
        v = hmac_sha256(k, v)


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    """HMAC-SHA256."""
    import hmac as hmac_mod
    return hmac_mod.new(key, data, hashlib.sha256).digest()


def _der_encode_signature(r: int, s: int) -> bytes:
    """DER-Kodierung einer ECDSA-Signatur."""
    r_bytes = _int_to_der_bytes(r)
    s_bytes = _int_to_der_bytes(s)

    # 0x02 <len_r> <r> 0x02 <len_s> <s>
    r_part = b"\x02" + bytes([len(r_bytes)]) + r_bytes
    s_part = b"\x02" + bytes([len(s_bytes)]) + s_bytes

    # 0x30 <total_len> <r_part> <s_part>
    payload = r_part + s_part
    return b"\x30" + bytes([len(payload)]) + payload


def _int_to_der_bytes(n: int) -> bytes:
    """Integer in DER-kompatible Bytes umwandeln."""
    b = n.to_bytes(32, "big").lstrip(b"\x00")
    if not b:
        b = b"\x00"
    # DER: Wenn höchstes Bit gesetzt, 0x00 voranstellen
    if b[0] & 0x80:
        b = b"\x00" + b
    return b


# ============================================================
# Hilfsfunktionen für Transaktionserstellung
# ============================================================

def _estimate_tx_size(n_inputs: int, n_outputs: int) -> int:
    """
    Schätzt die Größe einer P2PKH-Transaktion in Bytes.

    P2PKH-Input: ~148 Bytes, Output: ~34 Bytes, Overhead: ~10 Bytes.
    """
    return 10 + n_inputs * 148 + n_outputs * 34


def select_utxos(utxos: list[UTXO], target_value: int, fee_per_byte: int = 5) -> tuple[list[UTXO], int]:
    """
    Wählt UTXOs für eine Transaktion aus (einfacher Greedy-Algorithmus).

    Strategie: Sortiert nach Wert (größte zuerst), nimmt UTXOs
    bis der Zielwert + geschätzte Gebühren erreicht ist. Geprüft wird
    konsistent zuerst die 2-Output-Variante (Empfänger + Wechselgeld);
    reicht es dafür nicht, aber für die 1-Output-Variante (kein
    Wechselgeld, Rest geht als Gebühr), wird diese akzeptiert.

    Hinweis: Die zurückgegebene Gebühr ist nur eine Vorab-Schätzung –
    build_transaction() passt sie iterativ an die real signierte Größe an.

    Args:
        utxos: Verfügbare UTXOs
        target_value: Zu sendender Betrag in Satoshis
        fee_per_byte: Gebühr pro Byte in Satoshis

    Returns:
        Tuple von (ausgewählte_utxos, geschätzte_gebühr)

    Raises:
        ValueError: Wenn nicht genügend Guthaben vorhanden
    """
    sorted_utxos = sorted(utxos, key=lambda u: u.value, reverse=True)

    selected = []
    total = 0

    for utxo in sorted_utxos:
        selected.append(utxo)
        total += utxo.value

        # 2 Outputs: Empfänger + Wechselgeld
        fee_with_change = _estimate_tx_size(len(selected), 2) * fee_per_byte
        if total >= target_value + fee_with_change:
            return selected, fee_with_change

        # 1 Output: Betrag passt (fast) exakt, kein Wechselgeld-Output
        fee_without_change = _estimate_tx_size(len(selected), 1) * fee_per_byte
        if total >= target_value + fee_without_change:
            return selected, fee_without_change

    # Auch mit allen UTXOs reicht es nicht
    total_available = sum(u.value for u in utxos)
    estimated_fee = _estimate_tx_size(max(len(sorted_utxos), 1), 1) * fee_per_byte
    raise ValueError(
        f"Nicht genügend Guthaben: "
        f"verfügbar {satoshi_to_doi(total_available)} DOI, "
        f"benötigt {satoshi_to_doi(target_value + estimated_fee)} DOI "
        f"(inkl. ~{satoshi_to_doi(estimated_fee)} DOI Gebühren)"
    )


def build_transaction(
    utxos: list[UTXO],
    recipient: str,
    amount_satoshi: int,
    change_address: str,
    keypairs: dict[str, bytes],
    fee_per_byte: int = 5,
    dust_threshold: int = 546,
) -> Transaction:
    """
    Erstellt eine vollständig signierte Transaktion.
    
    Args:
        utxos: Verfügbare UTXOs
        recipient: Empfängeradresse
        amount_satoshi: Zu sendender Betrag in Satoshis
        change_address: Wechselgeld-Adresse
        keypairs: Dict von {adresse: private_key_bytes}
        fee_per_byte: Gebühr pro Byte
        dust_threshold: Minimum-Output (darunter kein Wechselgeld)
    
    Returns:
        Signierte Transaction

    Raises:
        ValueError: Bei unzureichendem Guthaben, fehlendem privaten
            Schlüssel oder Nicht-P2PKH-Inputs.

    Hinweis:
        Die Gebühr wird iterativ an die REAL signierte Größe angepasst:
        bauen + signieren, Größe messen, required_fee = ceil(size × fee_per_byte),
        Wechselgeld neu berechnen und bei Abweichung neu bauen/signieren
        (konvergiert praktisch immer in 1-2 Durchläufen, max. 3 Nachbesserungen).
    """
    # 1. Initiale UTXO-Auswahl mit grober Gebühren-Schätzung
    selected_list, fee = select_utxos(utxos, amount_satoshi, fee_per_byte)
    selected = list(selected_list)
    # Restliche UTXOs (größte zuerst), falls die reale Gebühr mehr Inputs erfordert
    remaining = [u for u in sorted(utxos, key=lambda u: u.value, reverse=True)
                 if u not in selected]

    def _insufficient(needed: int) -> ValueError:
        total_available = sum(u.value for u in utxos)
        return ValueError(
            f"Nicht genügend Guthaben: "
            f"verfügbar {satoshi_to_doi(total_available)} DOI, "
            f"benötigt {satoshi_to_doi(needed)} DOI (inkl. Gebühren)"
        )

    tx: Optional[Transaction] = None
    for _ in range(1 + 3):  # initialer Bau + max. 3 Nachbesserungen
        # 2. Wechselgeld berechnen; bei Bedarf weitere UTXOs nachziehen
        total_input = sum(u.value for u in selected)
        change = total_input - amount_satoshi - fee
        while change < 0:
            if not remaining:
                raise _insufficient(amount_satoshi + fee)
            extra = remaining.pop(0)
            selected.append(extra)
            total_input += extra.value
            # Jeder zusätzliche P2PKH-Input vergrößert die Transaktion (~148 B)
            fee += 148 * fee_per_byte
            change = total_input - amount_satoshi - fee

        # 3. Transaktion erstellen
        tx = Transaction()

        # Inputs hinzufügen (nur P2PKH – add_input prüft das)
        for utxo in selected:
            privkey = keypairs.get(utxo.address)
            if privkey is None:
                raise ValueError(f"Kein privater Schlüssel für Adresse: {utxo.address}")
            tx.add_input(utxo, privkey)

        # Empfänger-Output
        tx.add_output(recipient, amount_satoshi)

        # Wechselgeld-Output (nur wenn über Dust-Threshold).
        # Dust-Regel: 0 < change <= dust_threshold geht als zusätzliche
        # Gebühr an die Miner. change ist hier garantiert >= 0 (s.o.).
        if change > dust_threshold:
            tx.add_output(change_address, change)

        # 4. Signieren und Gebühr gegen die REALE signierte Größe prüfen
        tx.sign()
        required_fee = math.ceil(tx.size * fee_per_byte)
        if tx.fee >= required_fee:
            return tx

        # Gebühr war zu niedrig geschätzt → mit korrigierter Gebühr neu bauen
        fee = required_fee

    # Nach max. Iterationen: letzter Stand weicht höchstens um wenige
    # Satoshi (DER-Signatur-Längen-Jitter von ±1 Byte pro Input) ab.
    return tx
