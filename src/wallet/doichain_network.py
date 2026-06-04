"""
Doichain Netzwerk-Parameter

Doichain ist ein Namecoin-Fork (Bitcoin-basiert) und verwendet
die gleichen Adress-Version-Bytes wie Namecoin.

Unterstützte Adressformate:
  - Legacy P2PKH:          N.../M... (Base58Check, pubkey_hash=0x34)
  - P2SH (inkl. P2SH-P2WPKH): Script-Hash-Adressen (Base58Check, script_hash=0x0D)
  - Native SegWit P2WPKH:  dc1q... (Bech32, 20-Byte Witness-Programm)
  - Native SegWit P2WSH:   dc1q... (Bech32, 32-Byte Witness-Programm)

Referenz: doichain-core/src/kernel/chainparams.cpp
          electrum-doi/electrum/constants.py (SEGWIT_HRP = "dc")
"""

# === Mainnet Parameter ===
MAINNET = {
    "name": "doichain-mainnet",

    # Base58Check Version-Bytes
    "pubkey_hash": 0x34,      # 52 dezimal → Adressen beginnen mit "N" oder "M"
    "script_hash": 0x0D,      # 13 dezimal → P2SH-Adressen beginnen mit "3" (wie Bitcoin)
    "wif_prefix": 0xB4,       # 180 dezimal → WIF Private Keys beginnen mit "T" oder "7"

    # Bech32 (SegWit) – Human-Readable Prefix
    # Doichain verwendet SEGWIT_HRP = "dc" (Quelle: electrum-doi/electrum/constants.py)
    # Native SegWit-Adressen beginnen mit "dc1q..." (v0) bzw. "dc1p..." (v1/Taproot)
    "bech32_hrp": "dc",

    # BIP-32 Extended Key Version-Bytes (wie Namecoin/Bitcoin)
    "bip32_public": 0x0488B21E,   # xpub...
    "bip32_private": 0x0488ADE4,  # xprv...

    # BIP-44 Ableitungspfad
    # Doichain hat keinen offiziellen SLIP-44 Coin-Type.
    # Namecoin verwendet coin_type=7.
    "bip44_coin_type": 7,     # Namecoin coin type als Fallback
    "bip44_path": "m/44'/7'/0'",

    # Netzwerk
    "message_prefix": "\x18Doichain Signed Message:\n",
    "default_port": 8338,

    # ElectrumX Server
    "electrum_servers": [
        {"host": "white-snail-54.doi.works", "port": 50002, "protocol": "ssl"},
        {"host": "itchy-jellyfish-89.doi.works", "port": 50002, "protocol": "ssl"},
        {"host": "ugly-bird-70.doi.works", "port": 50002, "protocol": "ssl"},
    ],

    # ── TLS-Sicherheit für ElectrumX-Verbindung ────────────────────────
    # ssl_strict:
    #   True  (Default) – strikte CA-Validierung + Hostname-Check.
    #                     Empfohlen, falls die Server gültige CA-Zertifikate haben.
    #   False           – Validierung deaktiviert (UNSICHER, MITM möglich).
    #                     Nur, wenn die Server self-signed Zertifikate verwenden
    #                     UND keine Fingerprints gepflegt werden.
    #
    # ssl_pinned_fingerprints:
    #   Liste von SHA-256 Fingerprints des erwarteten Server-Zertifikats
    #   (DER-codiert), als Hex-String ohne Doppelpunkte, lowercase.
    #   Bei nicht-leerer Liste wird Pinning erzwungen und ssl_strict ignoriert.
    #   Beispiel:
    #     "ssl_pinned_fingerprints": [
    #         "ab12cd34...",  # white-snail-54.doi.works
    #         "ef56gh78...",  # itchy-jellyfish-89.doi.works
    #     ]
    "ssl_strict": True,
    "ssl_pinned_fingerprints": [],

    # Transaktionsparameter
    "coin_name": "DOI",
    "satoshis_per_coin": 100_000_000,  # 1 DOI = 10^8 Satoshis (wie Bitcoin)
    "min_relay_fee": 1000,             # Minimum Fee in Satoshis
    "dust_threshold": 546,             # Minimum Output in Satoshis
}

# === Testnet Parameter ===
TESTNET = {
    "name": "doichain-testnet",
    "pubkey_hash": 0x6F,      # 111 dezimal → Adressen beginnen mit "m" oder "n"
    "script_hash": 0xC4,      # 196 dezimal
    "wif_prefix": 0xEF,       # 239 dezimal
    "bech32_hrp": "tn",       # Testnet Bech32 HRP (wie Namecoin testnet)
    "bip32_public": 0x043587CF,
    "bip32_private": 0x04358394,
    "bip44_coin_type": 1,     # Testnet coin type
    "bip44_path": "m/44'/1'/0'",
    "message_prefix": "\x18Doichain Signed Message:\n",
    "default_port": 18338,
    "electrum_servers": [],
    "ssl_strict": True,
    "ssl_pinned_fingerprints": [],
    "coin_name": "tDOI",
    "satoshis_per_coin": 100_000_000,
    "min_relay_fee": 1000,
    "dust_threshold": 546,
}

# Standard-Netzwerk
ACTIVE_NETWORK = MAINNET


def get_network(name: str = "mainnet") -> dict:
    """Gibt die Netzwerk-Parameter zurück."""
    if name.lower() in ("mainnet", "main", "doichain"):
        return MAINNET
    elif name.lower() in ("testnet", "test"):
        return TESTNET
    else:
        raise ValueError(f"Unbekanntes Netzwerk: {name}")
