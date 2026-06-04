#!/usr/bin/env python3
"""
Phase 1a – Doichain Wallet Demo & Test

Interaktives Skript zum Testen aller Wallet-Funktionen:
1. Wallet erstellen (neue Seed-Phrase)
2. Wallet wiederherstellen (aus Seed)
3. Adressen generieren
4. Saldo abfragen
5. UTXOs anzeigen
6. Transaktion erstellen (Dry-Run)
7. Transaktion senden

Verwendung:
    python demos/test_doi_wallet.py
    python demos/test_doi_wallet.py --host white-snail-54.doi.works
    python demos/test_doi_wallet.py --restore "word1 word2 ... word24"
"""

import sys
import os
import argparse

# Projekt-Root zum Pfad hinzufügen
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

from src.wallet import (
    DoiWallet,
    SeedManager,
    validate_address,
    satoshi_to_doi,
    doi_to_satoshi,
    MAINNET,
)

console = Console()


def print_header():
    console.print(Panel(
        "[bold cyan]Doichain Wallet – Phase 1a Demo[/bold cyan]\n"
        "DOI On-Chain Wallet (SPV via ElectrumX)",
        border_style="cyan",
    ))


def test_crypto_basics():
    """Test 1: Kryptographische Grundfunktionen."""
    console.print("\n[bold]═══ Test 1: Krypto-Grundfunktionen ═══[/bold]")

    from src.wallet.crypto_utils import (
        sha256, hash160, hash256,
        base58check_encode, base58check_decode,
        pubkey_to_address,
    )

    # SHA-256 Test (bekannter Vektor)
    test_hash = sha256(b"hello").hex()
    expected = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    assert test_hash == expected, f"SHA-256 fehlgeschlagen: {test_hash}"
    console.print("  ✅ SHA-256")

    # Base58Check Round-Trip
    original = b"\x00" * 20  # 20 Null-Bytes
    encoded = base58check_encode(0x34, original)
    version, decoded = base58check_decode(encoded)
    assert version == 0x34 and decoded == original, "Base58Check Round-Trip fehlgeschlagen"
    console.print(f"  ✅ Base58Check (Beispiel-Adresse: {encoded})")

    # Hash160
    h = hash160(b"test")
    assert len(h) == 20, f"Hash160 falsche Länge: {len(h)}"
    console.print("  ✅ Hash160 (RIPEMD160(SHA256))")

    console.print("[green]✅ Krypto-Tests bestanden[/green]")


def test_seed_and_keys():
    """Test 2: Seed-Generierung und Schlüsselableitung."""
    console.print("\n[bold]═══ Test 2: Seed & Schlüsselableitung ═══[/bold]")

    sm = SeedManager()

    # Mnemonic generieren
    mnemonic = SeedManager.generate_mnemonic(256)
    words = mnemonic.split()
    console.print(f"  Seed-Phrase generiert: {words[0]} {words[1]} {words[2]} ... ({len(words)} Wörter)")
    assert len(words) == 24, f"Falsche Wortanzahl: {len(words)}"
    console.print("  ✅ 24-Wort Mnemonic")

    # Validierung
    assert SeedManager.validate_mnemonic(mnemonic), "Mnemonic-Validierung fehlgeschlagen"
    console.print("  ✅ Mnemonic-Validierung")

    # Schlüsselableitung
    sm.from_mnemonic(mnemonic)

    # Erste 3 Empfangsadressen
    table = Table(title="Abgeleitete Doichain-Adressen")
    table.add_column("Pfad", style="dim")
    table.add_column("Adresse", style="cyan")
    table.add_column("PubKey (hex, gekürzt)", style="dim")

    for i in range(3):
        kp = sm.get_keypair(index=i, change=0)
        table.add_row(
            kp["path"],
            kp["address"],
            kp["public_key"].hex()[:20] + "...",
        )

    console.print(table)

    # Prüfe Adress-Format (muss mit M oder N beginnen)
    addr = sm.get_receive_address(0)
    assert addr[0] in ("M", "N"), f"Unerwartetes Adress-Prefix: {addr[0]}"
    console.print(f"  ✅ Adress-Prefix: '{addr[0]}' (erwartet: M oder N)")

    # WIF Export
    wif = sm.get_private_key_wif(0)
    console.print(f"  WIF Private Key: {wif[:8]}...{wif[-4:]}")
    console.print("  ✅ WIF-Export")

    # Determinismus prüfen (gleicher Seed → gleiche Adressen)
    sm2 = SeedManager()
    sm2.from_mnemonic(mnemonic)
    assert sm.get_receive_address(0) == sm2.get_receive_address(0), "Determinismus-Fehler!"
    console.print("  ✅ Deterministische Ableitung (gleicher Seed → gleiche Adressen)")

    console.print("[green]✅ Seed & Key Tests bestanden[/green]")
    return mnemonic


def test_electrum_connection(host: str, port: int):
    """Test 3: ElectrumX-Verbindung."""
    console.print(f"\n[bold]═══ Test 3: ElectrumX-Verbindung ({host}:{port}) ═══[/bold]")

    from src.wallet.electrumx_client import ElectrumXClient

    client = ElectrumXClient(host=host, port=port)

    if not client.connect():
        console.print("[red]❌ Verbindung fehlgeschlagen![/red]")
        return None

    console.print(f"  ✅ Verbunden mit {host}:{port}")

    # Blockchain-Tip
    try:
        tip = client.get_tip()
        console.print(f"  Blockhöhe: {tip.get('height', 'unbekannt')}")
    except Exception as e:
        console.print(f"  ⚠️  Tip-Abfrage: {e}")

    # Fee-Schätzung
    fee = client.get_fee_estimate(6)
    if fee:
        console.print(f"  Geschätzte Gebühr (6 Blöcke): {fee} DOI/kB")
    else:
        console.print("  ⚠️  Fee-Schätzung nicht verfügbar (verwende Standard)")

    client.disconnect()
    console.print("[green]✅ ElectrumX-Tests bestanden[/green]")
    return True


def test_wallet_full(host: str, port: int, mnemonic: str = None, test_address: str = None):
    """Test 4: Vollständiger Wallet-Test."""
    console.print(f"\n[bold]═══ Test 4: Wallet-Gesamttest ═══[/bold]")

    wallet = DoiWallet()

    # Wallet erstellen oder wiederherstellen
    if mnemonic:
        console.print("  Wallet wird aus Seed wiederhergestellt...")
        wallet.restore(mnemonic)
    else:
        console.print("  Neues Wallet wird erstellt...")
        mnemonic = wallet.create()
        console.print(f"  Seed: {' '.join(mnemonic.split()[:3])} ... (Demo)")

    # Verbinden
    console.print(f"  Verbinde zu {host}:{port}...")
    if not wallet.connect(host=host, port=port):
        console.print("[red]❌ Verbindung fehlgeschlagen![/red]")
        return

    console.print("  ✅ Verbunden")

    # Wallet-Info
    info = wallet.info()
    console.print(f"  Netzwerk: {info['network']}")
    console.print(f"  Adressen: {info['receive_addresses']} Empfang, {info['change_addresses']} Wechselgeld")

    # Empfangsadressen anzeigen
    table = Table(title="Empfangsadressen")
    table.add_column("#", style="dim")
    table.add_column("Adresse", style="cyan")

    for i, addr in enumerate(wallet.get_receive_addresses()[:5]):
        table.add_row(str(i), addr)

    console.print(table)

    # Saldo abfragen
    console.print("\n  Saldo wird abgefragt...")
    try:
        balance = wallet.get_balance()
        console.print(
            f"  💰 Saldo: {balance['confirmed_doi']:.8f} DOI (bestätigt)"
        )
        if balance['unconfirmed'] > 0:
            console.print(
                f"          {balance['unconfirmed_doi']:.8f} DOI (unbestätigt)"
            )
    except Exception as e:
        console.print(f"  ⚠️  Saldo-Abfrage: {e}")

    # UTXOs
    try:
        utxos = wallet.get_utxos()
        if utxos:
            table = Table(title=f"UTXOs ({len(utxos)} gefunden)")
            table.add_column("TX Hash", style="dim")
            table.add_column("Index")
            table.add_column("Wert (DOI)", justify="right", style="green")
            table.add_column("Höhe", justify="right")

            for utxo in utxos[:10]:
                table.add_row(
                    utxo.tx_hash[:16] + "...",
                    str(utxo.tx_pos),
                    f"{satoshi_to_doi(utxo.value):.8f}",
                    str(utxo.height),
                )
            console.print(table)
        else:
            console.print("  Keine UTXOs gefunden (Wallet leer)")
    except Exception as e:
        console.print(f"  ⚠️  UTXO-Abfrage: {e}")

    # Externe Adresse testen
    if test_address:
        console.print(f"\n  Externe Adresse abfragen: {test_address[:20]}...")
        try:
            bal = wallet.electrum.get_balance(
                wallet.electrum.address_to_scripthash(test_address)
                if False else test_address
            )
            # Use the public method
            from src.wallet.electrumx_client import ElectrumXClient
            scripthash = ElectrumXClient.address_to_scripthash(test_address)
            bal = wallet.electrum._call("blockchain.scripthash.get_balance", [scripthash])
            console.print(f"  Saldo: {satoshi_to_doi(bal.get('confirmed', 0)):.8f} DOI")
        except Exception as e:
            console.print(f"  ⚠️  Fehler: {e}")

    # Transaktionshistorie
    console.print("\n  Transaktionshistorie wird geladen...")
    try:
        history = wallet.get_history()
        if history:
            console.print(f"  {len(history)} Transaktionen gefunden")
            for tx in history[:5]:
                console.print(f"    Block {tx['height']}: {tx['tx_hash'][:16]}...")
        else:
            console.print("  Keine Transaktionen gefunden")
    except Exception as e:
        console.print(f"  ⚠️  Historie: {e}")

    wallet.disconnect()
    console.print("\n[green]✅ Wallet-Gesamttest abgeschlossen[/green]")


def interactive_mode(host: str, port: int):
    """Interaktiver Wallet-Modus."""
    console.print(Panel(
        "[bold yellow]Interaktiver Modus[/bold yellow]\n"
        "Du kannst das Wallet live testen.",
        border_style="yellow",
    ))

    wallet = DoiWallet()

    # Wallet erstellen oder wiederherstellen
    choice = Prompt.ask(
        "Wallet erstellen oder wiederherstellen?",
        choices=["neu", "restore"],
        default="neu",
    )

    if choice == "restore":
        mnemonic = Prompt.ask("Seed-Phrase eingeben (24 Wörter)")
        try:
            wallet.restore(mnemonic)
            console.print("[green]✅ Wallet wiederhergestellt[/green]")
        except ValueError as e:
            console.print(f"[red]❌ Fehler: {e}[/red]")
            return
    else:
        mnemonic = wallet.create()
        console.print(Panel(
            f"[bold red]⚠️  SEED-PHRASE SICHER AUFBEWAHREN! ⚠️[/bold red]\n\n"
            f"[yellow]{mnemonic}[/yellow]\n\n"
            "Dies ist der einzige Weg, dein Wallet wiederherzustellen!",
            title="Neue Seed-Phrase",
            border_style="red",
        ))

    # Verbinden
    console.print(f"\nVerbinde zu {host}:{port}...")
    if not wallet.connect(host=host, port=port):
        console.print("[red]❌ Verbindung fehlgeschlagen![/red]")
        return

    console.print("[green]✅ Verbunden[/green]")

    # Hauptschleife
    while True:
        console.print("\n[bold]Optionen:[/bold]")
        console.print("  [1] Empfangsadresse anzeigen")
        console.print("  [2] Saldo abfragen")
        console.print("  [3] UTXOs anzeigen")
        console.print("  [4] Transaktion erstellen (Dry-Run)")
        console.print("  [5] Transaktion senden")
        console.print("  [6] Transaktionshistorie")
        console.print("  [7] Adress-Scan (Gap-Limit)")
        console.print("  [8] Wallet-Info")
        console.print("  [0] Beenden")

        choice = Prompt.ask("Auswahl", choices=["0","1","2","3","4","5","6","7","8"], default="2")

        try:
            if choice == "0":
                break
            elif choice == "1":
                addr = wallet.get_new_receive_address()
                console.print(f"\n  📬 Neue Empfangsadresse:\n  [bold cyan]{addr}[/bold cyan]")
            elif choice == "2":
                balance = wallet.get_balance(force_refresh=True)
                console.print(f"\n  💰 Bestätigt:   {balance['confirmed_doi']:.8f} DOI")
                console.print(f"     Unbestätigt: {balance['unconfirmed_doi']:.8f} DOI")
                console.print(f"     Gesamt:      {balance['total_doi']:.8f} DOI")
            elif choice == "3":
                utxos = wallet.get_utxos(force_refresh=True)
                if utxos:
                    for u in utxos:
                        console.print(f"  {u.tx_hash[:16]}...: {satoshi_to_doi(u.value):.8f} DOI")
                else:
                    console.print("  Keine UTXOs")
            elif choice == "4":
                recipient = Prompt.ask("Empfängeradresse")
                amount = float(Prompt.ask("Betrag (DOI)"))
                result = wallet.send(recipient, amount, dry_run=True)
                console.print(f"\n  [yellow]DRY-RUN:[/yellow]")
                console.print(f"  Empfänger: {result['recipient']}")
                console.print(f"  Betrag:    {result['amount_doi']:.8f} DOI")
                console.print(f"  Gebühr:    {result['fee_doi']:.8f} DOI")
                console.print(f"  Größe:     {result['size_bytes']} Bytes")
                console.print(f"  Inputs:    {result['inputs']}")
                console.print(f"  TX Hex:    {result['hex'][:60]}...")
            elif choice == "5":
                recipient = Prompt.ask("Empfängeradresse")
                amount = float(Prompt.ask("Betrag (DOI)"))
                if Confirm.ask(f"Wirklich {amount} DOI an {recipient[:20]}... senden?"):
                    result = wallet.send(recipient, amount, dry_run=False)
                    if result["status"] == "broadcast":
                        console.print(f"\n  [green]✅ {result['message']}[/green]")
                    else:
                        console.print(f"\n  [red]❌ {result['message']}[/red]")
            elif choice == "6":
                history = wallet.get_history()
                for tx in history[:10]:
                    console.print(f"  Block {tx['height']}: {tx['tx_hash'][:24]}...")
                if not history:
                    console.print("  Keine Transaktionen")
            elif choice == "7":
                console.print("  Scanne Adressen...")
                found = wallet.scan_addresses()
                console.print(f"  {found} Adressen mit Transaktionen gefunden")
            elif choice == "8":
                info = wallet.info()
                for k, v in info.items():
                    console.print(f"  {k}: {v}")
        except Exception as e:
            console.print(f"[red]  Fehler: {e}[/red]")

    wallet.disconnect()
    console.print("Wallet geschlossen. Auf Wiedersehen!")


def main():
    parser = argparse.ArgumentParser(description="Doichain Wallet Demo")
    parser.add_argument("--host", default="white-snail-54.doi.works", help="ElectrumX Server")
    parser.add_argument("--port", type=int, default=50002, help="ElectrumX Port")
    parser.add_argument("--restore", type=str, help="Seed-Phrase zum Wiederherstellen")
    parser.add_argument("--address", type=str, help="Externe Adresse zum Testen")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interaktiver Modus")
    parser.add_argument("--test-only", action="store_true", help="Nur automatische Tests")
    args = parser.parse_args()

    print_header()

    if args.interactive:
        interactive_mode(args.host, args.port)
        return

    # Automatische Tests
    console.print("[bold]Phase 1a – Automatische Tests[/bold]\n")

    # Test 1: Krypto
    test_crypto_basics()

    # Test 2: Seed & Keys
    mnemonic = test_seed_and_keys()

    # Test 3: ElectrumX
    electrum_ok = test_electrum_connection(args.host, args.port)

    # Test 4: Wallet Gesamt
    if electrum_ok:
        test_wallet_full(
            args.host,
            args.port,
            mnemonic=args.restore,
            test_address=args.address,
        )

    console.print(Panel(
        "[bold green]Phase 1a – Tests abgeschlossen![/bold green]\n\n"
        "Nächste Schritte:\n"
        "  • Wallet mit eigenem Seed wiederherstellen: --restore 'wort1 wort2 ...'\n"
        "  • Externe Adresse testen: --address 'N...'\n"
        "  • Interaktiver Modus: --interactive",
        border_style="green",
    ))


if __name__ == "__main__":
    main()
