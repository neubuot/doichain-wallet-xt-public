#!/usr/bin/env python3
"""
Demo: Unified Wallet Manager
==============================

Testet den WalletManager, der DOI + Tron (TRX/USDT) aus
einem einzigen BIP-39 Seed verwaltet.

Nutzung:
    python demos/test_wallet_manager.py                        # Automatische Tests
    python demos/test_wallet_manager.py -i                     # Interaktiv
    python demos/test_wallet_manager.py --restore "seed..."    # Wiederherstellen
    python demos/test_wallet_manager.py --load wallet.dat      # Wallet laden
"""

import argparse
import getpass
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_encryption():
    """Test 1: AES-256-GCM Verschlüsselung."""
    print("\n═══ Test 1: AES-256-GCM Verschlüsselung ═══")
    from src.wallet.wallet_manager import _encrypt, _decrypt

    data = b"Geheime Seed-Phrase mit 24 Woertern"
    password = "MeinSicheresPasswort!"

    enc = _encrypt(data, password)
    dec = _decrypt(enc, password)
    assert dec == data
    print("  ✅ Verschlüsseln → Entschlüsseln OK")

    try:
        _decrypt(enc, "FalschesPasswort")
        assert False
    except ValueError:
        print("  ✅ Falsches Passwort korrekt abgelehnt")

    return True


def test_create_save_load():
    """Test 2: Erstellen, Speichern, Laden."""
    print("\n═══ Test 2: Erstellen → Speichern → Laden ═══")
    from src.wallet.wallet_manager import WalletManager

    password = "TestPasswort2024!"

    # Erstellen
    wm = WalletManager()
    mnemonic = wm.create(password)
    doi_addr = wm.primary_addresses["doi"]
    tron_addr = wm.primary_addresses["tron"]
    print(f"  Erstellt:")
    print(f"    Seed:  {' '.join(mnemonic.split()[:4])}... ({len(mnemonic.split())} Wörter)")
    print(f"    DOI:   {doi_addr}")
    print(f"    Tron:  {tron_addr}")

    # Speichern
    with tempfile.NamedTemporaryFile(suffix=".wallet", delete=False) as f:
        path = f.name
    wm.save(path)
    print(f"  Gespeichert: {path} ({os.path.getsize(path)} Bytes)")

    # Laden
    wm2 = WalletManager()
    addrs = wm2.load(path, password)
    assert addrs["doi"] == doi_addr
    assert addrs["tron"] == tron_addr
    print(f"  Geladen:")
    print(f"    DOI:   {addrs['doi']}  ✅")
    print(f"    Tron:  {addrs['tron']}  ✅")

    # Falsches Passwort
    try:
        WalletManager().load(path, "Falsch")
        assert False
    except ValueError:
        print(f"  ✅ Falsches Passwort abgelehnt")

    wm.close()
    wm2.close()
    os.unlink(path)
    return True


def test_restore():
    """Test 3: Wiederherstellung aus Mnemonic."""
    print("\n═══ Test 3: Wiederherstellung ═══")
    from src.wallet.wallet_manager import WalletManager

    wm1 = WalletManager()
    mnemonic = wm1.create("Passwort1234!")
    addr1 = wm1.primary_addresses.copy()

    wm2 = WalletManager()
    addr2 = wm2.restore(mnemonic, "AnderesPasswort!")

    assert addr2["doi"] == addr1["doi"]
    assert addr2["tron"] == addr1["tron"]
    print(f"  ✅ Gleicher Seed → gleiche Adressen")

    wm1.close()
    wm2.close()
    return True


def test_lock_unlock():
    """Test 4: Lock / Unlock."""
    print("\n═══ Test 4: Lock / Unlock ═══")
    from src.wallet.wallet_manager import WalletManager

    password = "LockTest2024!"

    wm = WalletManager()
    wm.create(password)
    doi_addr = wm.primary_addresses["doi"]

    with tempfile.NamedTemporaryFile(suffix=".wallet", delete=False) as f:
        path = f.name
    wm.save(path)

    wm.lock()
    assert not wm.is_initialized
    print(f"  Gesperrt: initialized={wm.is_initialized}")

    wm.unlock(password)
    assert wm.is_initialized
    assert wm.primary_addresses["doi"] == doi_addr
    print(f"  Entsperrt: DOI={wm.primary_addresses['doi'][:15]}...  ✅")

    wm.close()
    os.unlink(path)
    return True


def test_password_change():
    """Test 5: Passwort ändern."""
    print("\n═══ Test 5: Passwort ändern ═══")
    from src.wallet.wallet_manager import WalletManager

    wm = WalletManager()
    wm.create("AltesPasswort1!")
    doi_addr = wm.primary_addresses["doi"]

    with tempfile.NamedTemporaryFile(suffix=".wallet", delete=False) as f:
        path = f.name
    wm.save(path)

    wm.change_password("AltesPasswort1!", "NeuesPasswort2!")

    # Mit neuem Passwort laden
    wm2 = WalletManager()
    addrs = wm2.load(path, "NeuesPasswort2!")
    assert addrs["doi"] == doi_addr
    print(f"  ✅ Passwort geändert und verifiziert")

    wm.close()
    wm2.close()
    os.unlink(path)
    return True


def test_live_balances():
    """Test 6: Live Saldo-Abfrage."""
    print("\n═══ Test 6: Live Saldo-Abfrage ═══")
    from src.wallet.wallet_manager import WalletManager

    wm = WalletManager()
    wm.create("BalanceTest2024!")

    balances = wm.get_all_balances()

    doi = balances.get("doi", {})
    if "error" in doi:
        print(f"  DOI:  ⚠️ nicht verbunden (ElectrumX connect() nötig)")
    else:
        print(f"  DOI:  {doi.get('confirmed', 0)} DOI")

    print(f"  TRX:  {balances.get('trx', 0):.6f} TRX")
    print(f"  USDT: {balances.get('usdt', 0):.6f} USDT")

    # Netzwerk-Status
    status = wm.check_connections()
    print(f"  Tron-Netzwerk: {'✅' if status.get('tron') else '❌'}")

    wm.close()
    return True


def interactive_mode(mnemonic: str = None, wallet_path: str = None):
    """Interaktiver Wallet-Manager Modus."""
    from src.wallet.wallet_manager import WalletManager

    wm = WalletManager()

    if wallet_path:
        password = getpass.getpass("  Wallet-Passwort: ")
        try:
            wm.load(wallet_path, password)
            print(f"  ✅ Wallet geladen: {wallet_path}")
        except ValueError as e:
            print(f"  ❌ {e}")
            return
    elif mnemonic:
        password = getpass.getpass("  Neues Passwort (min. 8 Zeichen): ")
        wm.restore(mnemonic, password)
        print(f"  ✅ Wallet wiederhergestellt")
    else:
        password = getpass.getpass("  Neues Passwort (min. 8 Zeichen): ")
        seed = wm.create(password)
        print(f"\n  ⚠️  SEED-PHRASE SICHER AUFBEWAHREN:")
        print(f"  {seed}")
        print(f"\n  Ohne diese Phrase ist das Wallet NICHT wiederherstellbar!")

    print(f"\n  DOI-Adresse:  {wm.primary_addresses.get('doi', 'N/A')}")
    print(f"  Tron-Adresse: {wm.primary_addresses.get('tron', 'N/A')}")

    while True:
        print("\n  ┌──────────────────────────────────────┐")
        print("  │  Unified Wallet Manager              │")
        print("  ├──────────────────────────────────────┤")
        print("  │  1. Salden abfragen (alle Chains)    │")
        print("  │  2. Alle Adressen anzeigen           │")
        print("  │  3. Wallet-Info                      │")
        print("  │  4. Netzwerk-Status                  │")
        print("  │  5. Wallet speichern                 │")
        print("  │  6. DOI verbinden (ElectrumX)        │")
        print("  │  7. Passwort ändern                  │")
        print("  │  0. Beenden                          │")
        print("  └──────────────────────────────────────┘")

        try:
            choice = input("\n  Auswahl: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "0":
            break

        elif choice == "1":
            print("\n  Salden werden abgefragt...")
            balances = wm.get_all_balances()
            doi = balances.get("doi", {})
            if "error" in doi:
                print(f"    DOI:  ⚠️ {doi['error']}")
            else:
                conf = doi.get("confirmed", 0)
                unconf = doi.get("unconfirmed", 0)
                print(f"    DOI:  {conf} (bestätigt) + {unconf} (unbestätigt)")
            print(f"    TRX:  {balances.get('trx', 0):,.6f}")
            print(f"    USDT: {balances.get('usdt', 0):,.6f}")

        elif choice == "2":
            all_addr = wm.get_all_addresses()
            print("\n  DOI Receive:")
            for i, a in enumerate(all_addr.get("doi", {}).get("receive", [])):
                print(f"    [{i}] {a}")
            print(f"\n  DOI Change:")
            for i, a in enumerate(all_addr.get("doi", {}).get("change", [])):
                print(f"    [{i}] {a}")
            print(f"\n  Tron:")
            for i, a in enumerate(all_addr.get("tron", [])):
                print(f"    [{i}] {a}  (m/44'/195'/0'/0/{i})")

        elif choice == "3":
            info = wm.info()
            print()
            for k, v in info.items():
                print(f"    {k}: {v}")

        elif choice == "4":
            status = wm.check_connections()
            print()
            for chain, ok in status.items():
                print(f"    {chain}: {'✅ verbunden' if ok else '❌ nicht verbunden'}")

        elif choice == "5":
            try:
                default_path = wm.wallet_path or "wallet.dat"
                path = input(f"    Dateipfad [{default_path}]: ").strip() or default_path
                saved = wm.save(path)
                print(f"    ✅ Gespeichert: {saved}")
            except Exception as e:
                print(f"    ❌ {e}")

        elif choice == "6":
            try:
                connected = wm.connect_doi()
                print(f"    {'✅ Verbunden' if connected else '❌ Verbindung fehlgeschlagen'}")
            except Exception as e:
                print(f"    ❌ {e}")

        elif choice == "7":
            try:
                old_pw = getpass.getpass("    Aktuelles Passwort: ")
                new_pw = getpass.getpass("    Neues Passwort: ")
                wm.change_password(old_pw, new_pw)
                print("    ✅ Passwort geändert")
            except Exception as e:
                print(f"    ❌ {e}")

    wm.close()
    print("\n  Wallet geschlossen.")


def main():
    parser = argparse.ArgumentParser(description="Unified Wallet Manager Demo")
    parser.add_argument("--restore", type=str, help="Seed-Phrase zum Wiederherstellen")
    parser.add_argument("--load", type=str, help="Wallet-Datei laden")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interaktiver Modus")
    parser.add_argument("--tests-only", action="store_true", help="Nur automatische Tests")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║   Unified Wallet Manager (DOI + Tron)    ║")
    print("╚══════════════════════════════════════════╝")

    if args.interactive or args.restore or args.load:
        interactive_mode(mnemonic=args.restore, wallet_path=args.load)
        return

    # Automatische Tests
    results = []
    tests = [
        ("AES-256-GCM Verschlüsselung", test_encryption),
        ("Erstellen → Speichern → Laden", test_create_save_load),
        ("Wiederherstellung", test_restore),
        ("Lock / Unlock", test_lock_unlock),
        ("Passwort ändern", test_password_change),
        ("Live Saldo-Abfrage", test_live_balances),
    ]

    for name, test_fn in tests:
        try:
            results.append((name, test_fn()))
        except Exception as e:
            print(f"  ❌ {e}")
            results.append((name, False))

    # Zusammenfassung
    print("\n═══════════════════════════════════════")
    print("  Ergebnis:")
    all_passed = True
    for name, passed in results:
        print(f"    {'✅' if passed else '❌'} {name}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n  🎉 Alle Tests bestanden!")

    if not args.tests_only:
        print("\n  Interaktiv:       python demos/test_wallet_manager.py -i")
        print("  Wiederherstellen: python demos/test_wallet_manager.py --restore \"seed...\"")
        print("  Wallet laden:     python demos/test_wallet_manager.py --load wallet.dat")


if __name__ == "__main__":
    main()
