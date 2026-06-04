#!/usr/bin/env python3
"""
Phase 1b – Demo: Tron Wallet (TRX + USDT TRC-20)
===================================================

Testet:
  1. Kryptografie (Keccak-256, Adressgenerierung, Validierung)
  2. BIP-44 Seed-Ableitung (m/44'/195'/0'/0/x)
  3. TronGrid API-Verbindung
  4. TRX-Saldo abfragen
  5. USDT TRC-20 Saldo abfragen
  6. Wallet-Erstellung und -Wiederherstellung
  7. Interaktiver Modus

Nutzung:
    python demos/test_tron_wallet.py                        # Automatische Tests
    python demos/test_tron_wallet.py --address <TRON-ADDR>  # Saldo abfragen
    python demos/test_tron_wallet.py --restore "<MNEMONIC>" # Wallet wiederherstellen
"""

import argparse
import sys
from pathlib import Path

# Projektroot zum Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_crypto():
    """Test 1: Kryptografie-Grundlagen."""
    print("\n═══ Test 1: Kryptografie ═══")
    
    from src.wallet.tron_crypto import (
        keccak256, pubkey_to_tron_address, validate_tron_address,
        tron_address_to_hex, hex_to_tron_address, _decompress_pubkey,
        base58check_encode, base58check_decode,
    )
    
    # Keccak-256
    h = keccak256(b"")
    expected = "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"
    assert h.hex() == expected, f"Keccak-256 falsch: {h.hex()}"
    print("  ✅ Keccak-256 korrekt")
    
    # Public Key → Adresse
    from ecdsa import SigningKey, SECP256k1
    test_privkey = bytes(31) + b"\x01"  # Privkey = 1
    sk = SigningKey.from_string(test_privkey, curve=SECP256k1)
    vk = sk.get_verifying_key()
    pubkey = b"\x04" + vk.to_string()
    
    addr = pubkey_to_tron_address(pubkey)
    assert addr.startswith("T"), f"Adresse beginnt nicht mit T: {addr}"
    print(f"  ✅ PubKey → Adresse: {addr}")
    
    # Komprimierter Key → gleiche Adresse
    y_int = int.from_bytes(vk.to_string()[32:], "big")
    prefix = b"\x02" if y_int % 2 == 0 else b"\x03"
    compressed = prefix + vk.to_string()[:32]
    addr2 = pubkey_to_tron_address(compressed)
    assert addr == addr2, "Komprimiert ≠ Unkomprimiert!"
    print("  ✅ Komprimierter PubKey → gleiche Adresse")
    
    # Validierung
    assert validate_tron_address(addr)
    assert validate_tron_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")  # USDT Contract
    assert not validate_tron_address("INVALID")
    assert not validate_tron_address("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")  # Bitcoin
    print("  ✅ Adress-Validierung korrekt")
    
    # Hex-Roundtrip
    hex_addr = tron_address_to_hex(addr)
    assert hex_addr.startswith("41")
    addr_back = hex_to_tron_address(hex_addr)
    assert addr_back == addr
    print(f"  ✅ Hex-Roundtrip: {hex_addr[:10]}... → {addr}")
    
    return True


def test_bip44_derivation():
    """Test 2: BIP-44 Seed → Tron-Adressen."""
    print("\n═══ Test 2: BIP-44 Seed-Ableitung ═══")
    
    from src.wallet.tron_crypto import derive_tron_address_from_seed, validate_tron_address
    from mnemonic import Mnemonic
    
    mnemo = Mnemonic("english")
    mnemonic = mnemo.generate(256)
    seed = mnemo.to_seed(mnemonic, passphrase="")
    
    print(f"  Mnemonic: {' '.join(mnemonic.split()[:4])}... ({len(mnemonic.split())} Wörter)")
    print(f"  BIP-44 Pfad: m/44'/195'/0'/0/x")
    print()
    
    for i in range(3):
        addr, privkey, pubkey = derive_tron_address_from_seed(seed, account=0, index=i)
        assert validate_tron_address(addr)
        print(f"  Index {i}: {addr}")
    
    # Determinismus
    a1, _, _ = derive_tron_address_from_seed(seed, account=0, index=0)
    a2, _, _ = derive_tron_address_from_seed(seed, account=0, index=0)
    assert a1 == a2
    print("  ✅ Deterministisch: gleicher Seed → gleiche Adressen")
    
    return True


def test_trongrid_connection():
    """Test 3: TronGrid API-Verbindung."""
    print("\n═══ Test 3: TronGrid API-Verbindung ═══")
    
    from src.wallet.tron_network import TronClient
    
    client = TronClient()
    
    # Blockhöhe
    height = client.get_block_height()
    if height is None:
        print("  ❌ Keine Verbindung zum Tron-Netzwerk")
        return False
    
    print(f"  Aktuelle Blockhöhe: {height:,}")
    print(f"  API-Endpunkt: {client.base_url}")
    print("  ✅ Verbindung hergestellt")
    
    client.close()
    return True


def test_trx_balance(address: str = None):
    """Test 4: TRX-Saldo abfragen."""
    print("\n═══ Test 4: TRX-Saldo ═══")
    
    from src.wallet.tron_network import TronClient
    from src.wallet.tron_crypto import sun_to_trx
    
    # Bekannte Adresse mit Aktivität (USDT Contract)
    test_addr = address or "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    client = TronClient()
    
    balance_sun = client.get_trx_balance(test_addr)
    balance_trx = sun_to_trx(balance_sun)
    
    print(f"  Adresse:  {test_addr}")
    print(f"  TRX-Saldo: {balance_trx:,.6f} TRX ({balance_sun:,} SUN)")
    
    # Ressourcen
    resources = client.get_account_resources(test_addr)
    if resources:
        bw_free = resources.get("freeNetLimit", 0)
        bw_used = resources.get("freeNetUsed", 0)
        energy = resources.get("EnergyLimit", 0)
        print(f"  Bandbreite: {bw_used}/{bw_free} (frei)")
        print(f"  Energie:    {energy}")
    
    print("  ✅ TRX-Saldo abgerufen")
    
    client.close()
    return balance_trx


def test_usdt_balance(address: str = None):
    """Test 5: USDT TRC-20 Saldo."""
    print("\n═══ Test 5: USDT (TRC-20) Saldo ═══")
    
    from src.wallet.tron_network import TronClient
    from src.wallet.tron_crypto import raw_to_usdt
    
    # Adresse die wahrscheinlich USDT hat
    test_addr = address or "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    client = TronClient()
    
    usdt_raw = client.get_usdt_balance(test_addr)
    usdt = raw_to_usdt(usdt_raw)
    
    print(f"  Adresse:    {test_addr}")
    print(f"  USDT-Saldo: {usdt:,.6f} USDT (raw: {usdt_raw:,})")
    print(f"  Contract:   {client.network['usdt_contract']}")
    print("  ✅ USDT-Saldo abgerufen")
    
    client.close()
    return usdt


def test_wallet_creation():
    """Test 6: Wallet erstellen und wiederherstellen."""
    print("\n═══ Test 6: Wallet erstellen & wiederherstellen ═══")
    
    from src.wallet.tron_wallet import TronWallet
    
    # Neues Wallet erstellen
    wallet = TronWallet()
    mnemonic = wallet.create()
    
    primary = wallet.primary_address
    all_addrs = wallet.get_all_addresses()
    
    print(f"  Mnemonic: {' '.join(mnemonic.split()[:4])}... ({len(mnemonic.split())} Wörter)")
    print(f"  Primäre Adresse: {primary}")
    print(f"  Adressen abgeleitet: {len(all_addrs)}")
    
    for i, addr in enumerate(all_addrs):
        print(f"    [{i}] {addr}")
    
    # Wallet wiederherstellen
    wallet2 = TronWallet()
    wallet2.restore(mnemonic)
    
    assert wallet2.primary_address == primary, "Wiederherstellung fehlgeschlagen!"
    print()
    print(f"  Wiederhergestellt: {wallet2.primary_address}")
    print("  ✅ Gleiche Adresse nach Wiederherstellung")
    
    # Saldo abfragen (wird 0 sein für neues Wallet)
    try:
        balance = wallet.get_total_balance()
        print(f"  TRX-Saldo:  {balance['trx']:.6f} TRX")
        print(f"  USDT-Saldo: {balance['usdt']:.6f} USDT")
        print("  ✅ Saldo-Abfrage funktioniert")
    except Exception as e:
        print(f"  ⚠️  Saldo-Abfrage: {e}")
    
    wallet.close()
    wallet2.close()
    return True


def interactive_mode(mnemonic: str = None, address: str = None):
    """Interaktiver Wallet-Modus."""
    from src.wallet.tron_wallet import TronWallet
    from src.wallet.tron_crypto import validate_tron_address
    
    wallet = TronWallet()
    
    if mnemonic:
        print(f"\n  Stelle Wallet wieder her...")
        wallet.restore(mnemonic)
    elif address:
        # Nur Saldo-Abfrage ohne Wallet
        print(f"\n═══ Saldo-Abfrage: {address} ═══")
        balance = wallet.client.get_trx_balance(address)
        usdt = wallet.client.get_usdt_balance(address)
        from src.wallet.tron_crypto import sun_to_trx, raw_to_usdt
        print(f"  TRX:  {sun_to_trx(balance):,.6f}")
        print(f"  USDT: {raw_to_usdt(usdt):,.6f}")
        wallet.close()
        return
    else:
        print(f"\n  Erstelle neues Wallet...")
        mnemonic = wallet.create()
        print(f"\n  ⚠️  SEED-PHRASE SICHER AUFBEWAHREN:")
        print(f"  {mnemonic}")
    
    print(f"\n  Primäre Adresse: {wallet.primary_address}")
    
    while True:
        print("\n  ┌─────────────────────────────────┐")
        print("  │  Tron Wallet – Interaktiv       │")
        print("  ├─────────────────────────────────┤")
        print("  │  1. Alle Adressen anzeigen      │")
        print("  │  2. TRX-Saldo                   │")
        print("  │  3. USDT-Saldo                  │")
        print("  │  4. Gesamt-Saldo (alle Adressen)│")
        print("  │  5. Ressourcen (Bandbreite/En.)  │")
        print("  │  6. Externe Adresse abfragen    │")
        print("  │  7. Blockhöhe                   │")
        print("  │  8. Wallet-Info                 │")
        print("  │  0. Beenden                     │")
        print("  └─────────────────────────────────┘")
        
        try:
            choice = input("\n  Auswahl: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        
        if choice == "0":
            break
        
        elif choice == "1":
            print()
            for i, addr in enumerate(wallet.get_all_addresses()):
                print(f"    [{i}] {addr}  (m/44'/195'/0'/0/{i})")
        
        elif choice == "2":
            balance = wallet.get_trx_balance()
            print(f"\n    TRX-Saldo: {balance:,.6f} TRX")
        
        elif choice == "3":
            usdt = wallet.get_usdt_balance()
            print(f"\n    USDT-Saldo: {usdt:,.6f} USDT")
        
        elif choice == "4":
            print()
            total_trx = 0
            total_usdt = 0
            for bal in wallet.get_all_balances():
                print(f"    [{bal['index']}] {bal['address']}")
                print(f"        TRX: {bal['trx']:,.6f}  |  USDT: {bal['usdt']:,.6f}")
                total_trx += bal['trx']
                total_usdt += bal['usdt']
            print(f"\n    Gesamt: {total_trx:,.6f} TRX | {total_usdt:,.6f} USDT")
        
        elif choice == "5":
            res = wallet.get_resources()
            if res:
                print(f"\n    Bandbreite frei:    {res['bandwidth_free']}")
                print(f"    Bandbreite genutzt: {res['bandwidth_used']}")
                print(f"    Energie-Limit:      {res['energy_limit']}")
                print(f"    Energie genutzt:    {res['energy_used']}")
            else:
                print("\n    Account nicht aktiviert (keine Ressourcen)")
        
        elif choice == "6":
            try:
                ext_addr = input("    Tron-Adresse: ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if validate_tron_address(ext_addr):
                bal = wallet.get_total_balance(ext_addr)
                print(f"\n    TRX:  {bal['trx']:,.6f}")
                print(f"    USDT: {bal['usdt']:,.6f}")
            else:
                print("    ❌ Ungültige Tron-Adresse")
        
        elif choice == "7":
            height = wallet.get_block_height()
            print(f"\n    Blockhöhe: {height:,}" if height else "\n    ❌ Fehler")
        
        elif choice == "8":
            print(f"\n    {wallet}")
            print(f"    Netzwerk:  {wallet.network['name']}")
            print(f"    Adressen:  {len(wallet.get_all_addresses())}")
            print(f"    API:       {wallet.client.base_url}")
    
    wallet.close()
    print("\n  Wallet geschlossen.")


def main():
    parser = argparse.ArgumentParser(description="Tron Wallet Demo & Tests")
    parser.add_argument("--address", type=str, help="Tron-Adresse für Saldo-Abfrage")
    parser.add_argument("--restore", type=str, help="Seed-Phrase zum Wiederherstellen")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interaktiver Modus")
    parser.add_argument("--tests-only", action="store_true", help="Nur automatische Tests")
    args = parser.parse_args()
    
    print("╔══════════════════════════════════════════╗")
    print("║   Phase 1b: Tron Wallet (TRX + USDT)    ║")
    print("╚══════════════════════════════════════════╝")
    
    if args.interactive or args.restore:
        interactive_mode(mnemonic=args.restore, address=args.address)
        return
    
    if args.address:
        interactive_mode(address=args.address)
        return
    
    # Automatische Tests
    results = []
    
    # Test 1: Kryptografie
    try:
        results.append(("Kryptografie", test_crypto()))
    except Exception as e:
        print(f"  ❌ {e}")
        results.append(("Kryptografie", False))
    
    # Test 2: BIP-44 Ableitung
    try:
        results.append(("BIP-44 Ableitung", test_bip44_derivation()))
    except Exception as e:
        print(f"  ❌ {e}")
        results.append(("BIP-44 Ableitung", False))
    
    # Test 3: TronGrid Verbindung
    try:
        connected = test_trongrid_connection()
        results.append(("TronGrid Verbindung", connected))
    except Exception as e:
        print(f"  ❌ {e}")
        results.append(("TronGrid Verbindung", False))
        connected = False
    
    if connected:
        # Test 4: TRX-Saldo
        try:
            test_trx_balance(args.address)
            results.append(("TRX-Saldo", True))
        except Exception as e:
            print(f"  ❌ {e}")
            results.append(("TRX-Saldo", False))
        
        # Test 5: USDT-Saldo
        try:
            test_usdt_balance(args.address)
            results.append(("USDT-Saldo", True))
        except Exception as e:
            print(f"  ❌ {e}")
            results.append(("USDT-Saldo", False))
        
        # Test 6: Wallet
        try:
            results.append(("Wallet erstellen", test_wallet_creation()))
        except Exception as e:
            print(f"  ❌ {e}")
            results.append(("Wallet erstellen", False))
    
    # Zusammenfassung
    print("\n═══════════════════════════════════════")
    print("  Ergebnis:")
    all_passed = True
    for name, passed in results:
        icon = "✅" if passed else "❌"
        print(f"    {icon} {name}")
        if not passed:
            all_passed = False
    
    if all_passed:
        print("\n  🎉 Alle Tests bestanden!")
    else:
        print("\n  ⚠️  Einige Tests fehlgeschlagen")
    
    if not args.tests_only:
        print("\n  Interaktiver Modus: python demos/test_tron_wallet.py -i")
        print("  Wallet wiederherstellen: python demos/test_tron_wallet.py --restore \"seed phrase\"")


if __name__ == "__main__":
    main()
