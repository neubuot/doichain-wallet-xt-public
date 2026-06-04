#!/usr/bin/env python3
"""
Doichain Wallet XT – Interaktives Wallet
==========================================

Vollständiges Multi-Chain Wallet (DOI + TRX + USDT).
Erstellen, Wiederherstellen, Saldo abfragen und Überweisungen tätigen.

Nutzung:
    python wallet_app.py              # Neues Wallet oder bestehendes laden
    python wallet_app.py --load wallet.dat
"""

import argparse
import getpass
import os
import sys
from pathlib import Path

# Projektroot zum Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent))

from src.wallet.wallet_manager import WalletManager
from src.wallet.tron_crypto import validate_tron_address, sun_to_trx, raw_to_usdt
from src.wallet.crypto_utils import validate_address as validate_doi_address
from src.exchange.xt_client import XTClient


def load_config_data():
    """Lädt die gesamte Konfiguration."""
    try:
        from src.utils.config import load_config
        return load_config()
    except Exception:
        return {}


def load_tron_api_key():
    """Lädt den TronGrid API-Key aus config.yaml."""
    config = load_config_data()
    return config.get("tron", {}).get("api_key", "")


def create_xt_client():
    """Erstellt den XT.com Client aus config.yaml."""
    config = load_config_data()
    xt_conf = config.get("xt_com", {})
    return XTClient(
        api_key=xt_conf.get("api_key", ""),
        api_secret=xt_conf.get("api_secret", ""),
        symbol=xt_conf.get("symbol", "doi_usdt"),
    )


def clear():
    os.system('cls' if os.name == 'nt' else 'clear')


def header():
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║   🔗 Doichain Wallet XT                     ║")
    print("  ║   DOI · TRX · USDT (TRC-20)                 ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()


def get_password(prompt="  Passwort: ", confirm=False):
    """Passwort sicher abfragen."""
    while True:
        pw = getpass.getpass(prompt)
        if len(pw) < 8:
            print("  ⚠️  Passwort muss mindestens 8 Zeichen lang sein!")
            continue
        if confirm:
            pw2 = getpass.getpass("  Passwort bestätigen: ")
            if pw != pw2:
                print("  ⚠️  Passwörter stimmen nicht überein!")
                continue
        return pw


def _auto_connect_doi(wm):
    """Verbindet DOI-Wallet automatisch mit ElectrumX."""
    print("  Verbinde DOI mit ElectrumX...", end=" ", flush=True)
    try:
        ok = wm.connect_doi()
        if ok:
            print("✅")
        else:
            print("⚠️ fehlgeschlagen (Option 7 zum Wiederholen)")
    except Exception as e:
        print(f"⚠️ {e}")


def startup(wallet_path=None):
    """Wallet erstellen, wiederherstellen oder laden."""
    header()
    api_key = load_tron_api_key()
    wm = WalletManager(tron_api_key=api_key)

    if wallet_path and Path(wallet_path).exists():
        print(f"  Wallet-Datei gefunden: {wallet_path}")
        pw = getpass.getpass("  Passwort: ")
        try:
            wm.load(wallet_path, pw)
            print(f"  ✅ Wallet geladen!")
            _auto_connect_doi(wm)
            return wm
        except ValueError as e:
            print(f"  ❌ {e}")
            return None

    # Menü: Neu / Wiederherstellen / Laden
    print("  Was möchtest du tun?")
    print()
    print("  1. Neues Wallet erstellen")
    print("  2. Wallet aus Seed-Phrase wiederherstellen")
    print("  3. Wallet-Datei laden")
    print("  0. Beenden")
    print()

    choice = input("  Auswahl: ").strip()

    if choice == "1":
        print()
        pw = get_password("  Neues Passwort (min. 8 Zeichen): ", confirm=True)
        mnemonic = wm.create(pw)
        print()
        print("  ╔══════════════════════════════════════════════╗")
        print("  ║  ⚠️  SEED-PHRASE – SICHER AUFBEWAHREN!       ║")
        print("  ╠══════════════════════════════════════════════╣")
        words = mnemonic.split()
        for i in range(0, len(words), 4):
            line = "  ║  "
            for j in range(4):
                if i + j < len(words):
                    line += f"{i+j+1:2d}. {words[i+j]:<14s}"
            line = line.ljust(48) + "║"
            print(line)
        print("  ╠══════════════════════════════════════════════╣")
        print("  ║  Ohne diese Phrase ist dein Wallet für       ║")
        print("  ║  immer verloren! Schreibe sie auf Papier!    ║")
        print("  ╚══════════════════════════════════════════════╝")
        print()
        input("  Drücke ENTER wenn du die Phrase notiert hast...")

        # Automatisch speichern
        default_path = "wallet.dat"
        save_path = input(f"  Wallet speichern als [{default_path}]: ").strip() or default_path
        wm.save(save_path)
        print(f"  ✅ Wallet gespeichert: {save_path}")
        _auto_connect_doi(wm)
        return wm

    elif choice == "2":
        print()
        mnemonic = input("  Seed-Phrase eingeben: ").strip()
        pw = get_password("  Neues Passwort (min. 8 Zeichen): ", confirm=True)
        try:
            wm.restore(mnemonic, pw)
            save_path = input("  Wallet speichern als [wallet.dat]: ").strip() or "wallet.dat"
            wm.save(save_path)
            print(f"  ✅ Wallet wiederhergestellt und gespeichert!")
            _auto_connect_doi(wm)
            return wm
        except ValueError as e:
            print(f"  ❌ {e}")
            return None

    elif choice == "3":
        path = input("  Dateipfad: ").strip()
        if not Path(path).exists():
            print(f"  ❌ Datei nicht gefunden: {path}")
            return None
        pw = getpass.getpass("  Passwort: ")
        try:
            wm.load(path, pw)
            print(f"  ✅ Wallet geladen!")
            _auto_connect_doi(wm)
            return wm
        except ValueError as e:
            print(f"  ❌ {e}")
            return None

    return None


def show_balances(wm):
    """Alle Salden anzeigen."""
    print()
    print("  ┌─ Salden ─────────────────────────────────────┐")

    # DOI
    try:
        doi_bal = wm.doi.get_balance()
        conf = doi_bal.get("confirmed_doi", 0)
        unconf = doi_bal.get("unconfirmed_doi", 0)
        print(f"  │  DOI:   {conf:>14.8f} DOI", end="")
        if unconf:
            print(f" (+{unconf:.8f} unbestätigt)", end="")
        print()
    except Exception:
        print(f"  │  DOI:   ⚠️  Nicht verbunden (Option 7)")

    # TRX
    try:
        trx = wm.tron.get_trx_balance()
        print(f"  │  TRX:   {trx:>14.6f} TRX")
    except Exception as e:
        print(f"  │  TRX:   ⚠️  Fehler: {e}")

    # USDT
    try:
        usdt = wm.tron.get_usdt_balance()
        print(f"  │  USDT:  {usdt:>14.6f} USDT")
    except Exception as e:
        print(f"  │  USDT:  ⚠️  Fehler: {e}")

    print("  └──────────────────────────────────────────────┘")


def show_addresses(wm):
    """Alle Adressen anzeigen."""
    print()
    print("  ── DOI Empfangsadressen ──")
    for i, addr in enumerate(wm.doi.get_receive_addresses()):
        marker = " ◀ primär" if i == 0 else ""
        print(f"    [{i}] {addr}{marker}")

    print()
    print("  ── Tron Adressen ──")
    for i, addr in enumerate(wm.tron.get_all_addresses()):
        marker = " ◀ primär" if i == 0 else ""
        print(f"    [{i}] {addr}{marker}")


def send_doi(wm):
    """DOI senden."""
    print()
    print("  ── DOI senden ──")

    # Prüfen ob verbunden
    if wm.doi.electrum is None:
        print("  ⚠️  DOI-Wallet nicht verbunden!")
        print("  Zuerst mit Option 7 verbinden.")
        return

    to_addr = input("  Empfänger-Adresse: ").strip()
    if not validate_doi_address(to_addr, bech32_hrp="dc"):
        print("  ❌ Ungültige DOI-Adresse!")
        return

    try:
        amount = float(input("  Betrag (DOI): ").strip())
    except ValueError:
        print("  ❌ Ungültiger Betrag!")
        return

    if amount <= 0:
        print("  ❌ Betrag muss positiv sein!")
        return

    # Bestätigung
    print()
    print(f"  Sende: {amount:.8f} DOI")
    print(f"  An:    {to_addr}")
    confirm = input("  Bestätigen? (ja/nein): ").strip().lower()

    if confirm not in ("ja", "j", "yes", "y"):
        print("  Abgebrochen.")
        return

    try:
        result = wm.send("DOI", to_addr, amount)
        tx_id = result.get("txid", "N/A")
        print(f"\n  ✅ Transaktion gesendet!")
        print(f"  TX-ID: {tx_id}")
    except Exception as e:
        print(f"\n  ❌ Fehler: {e}")


def send_trx(wm):
    """TRX senden."""
    print()
    print("  ── TRX senden ──")

    to_addr = input("  Empfänger-Adresse (T...): ").strip()
    if not validate_tron_address(to_addr):
        print("  ❌ Ungültige Tron-Adresse!")
        return

    try:
        amount = float(input("  Betrag (TRX): ").strip())
    except ValueError:
        print("  ❌ Ungültiger Betrag!")
        return

    if amount <= 0:
        print("  ❌ Betrag muss positiv sein!")
        return

    # Aktueller Saldo
    balance = wm.tron.get_trx_balance()
    print(f"\n  Aktueller Saldo: {balance:,.6f} TRX")
    print(f"  Sende:           {amount:,.6f} TRX")
    print(f"  An:              {to_addr}")

    if amount > balance:
        print(f"  ❌ Unzureichender Saldo!")
        return

    confirm = input("  Bestätigen? (ja/nein): ").strip().lower()
    if confirm not in ("ja", "j", "yes", "y"):
        print("  Abgebrochen.")
        return

    try:
        result = wm.send("TRX", to_addr, amount)
        tx_id = result.get("txID", "N/A")
        if result and "error" not in result:
            print(f"\n  ✅ Transaktion gesendet!")
            print(f"  TX-ID: {tx_id}")
            print(f"  https://tronscan.org/#/transaction/{tx_id}")
        else:
            print(f"\n  ❌ Fehler: {result.get('error', 'Unbekannt')}")
    except Exception as e:
        print(f"\n  ❌ Fehler: {e}")


def send_usdt(wm):
    """USDT (TRC-20) senden."""
    print()
    print("  ── USDT (TRC-20) senden ──")
    print("  ℹ️  Für USDT-Transfers werden ~5-15 TRX als Gas benötigt!")

    to_addr = input("  Empfänger-Adresse (T...): ").strip()
    if not validate_tron_address(to_addr):
        print("  ❌ Ungültige Tron-Adresse!")
        return

    try:
        amount = float(input("  Betrag (USDT): ").strip())
    except ValueError:
        print("  ❌ Ungültiger Betrag!")
        return

    if amount <= 0:
        print("  ❌ Betrag muss positiv sein!")
        return

    # Salden prüfen
    usdt_balance = wm.tron.get_usdt_balance()
    trx_balance = wm.tron.get_trx_balance()

    print(f"\n  USDT-Saldo:  {usdt_balance:,.6f} USDT")
    print(f"  TRX für Gas: {trx_balance:,.6f} TRX")
    print(f"  Sende:       {amount:,.6f} USDT")
    print(f"  An:          {to_addr}")

    if amount > usdt_balance:
        print(f"  ❌ Unzureichender USDT-Saldo!")
        return

    if trx_balance < 5:
        print(f"  ❌ Mindestens 5 TRX für Gas nötig! (aktuell: {trx_balance:.6f})")
        return

    confirm = input("  Bestätigen? (ja/nein): ").strip().lower()
    if confirm not in ("ja", "j", "yes", "y"):
        print("  Abgebrochen.")
        return

    try:
        result = wm.send("USDT", to_addr, amount)
        tx_id = result.get("txID", "N/A")
        if result and "error" not in result:
            print(f"\n  ✅ USDT-Transaktion gesendet!")
            print(f"  TX-ID: {tx_id}")
            print(f"  https://tronscan.org/#/transaction/{tx_id}")
        else:
            print(f"\n  ❌ Fehler: {result.get('error', 'Unbekannt')}")
    except Exception as e:
        print(f"\n  ❌ Fehler: {e}")


def query_external(wm):
    """Externe Adresse abfragen."""
    print()
    addr = input("  Adresse eingeben: ").strip()

    if validate_tron_address(addr):
        print(f"\n  Tron-Adresse erkannt: {addr}")
        try:
            trx_sun = wm.tron.client.get_trx_balance(addr)
            usdt_raw = wm.tron.client.get_usdt_balance(addr)
            print(f"  TRX:  {sun_to_trx(trx_sun):,.6f}")
            print(f"  USDT: {raw_to_usdt(usdt_raw):,.6f}")
        except Exception as e:
            print(f"  ❌ {e}")

    elif validate_doi_address(addr, bech32_hrp="dc"):
        print(f"\n  DOI-Adresse erkannt: {addr}")
        if wm.doi.electrum:
            try:
                bal = wm.doi.get_address_balance(addr)
                print(f"  DOI: {bal}")
            except Exception as e:
                print(f"  ❌ {e}")
        else:
            print("  ⚠️  DOI nicht verbunden (Option 7)")
    else:
        print("  ❌ Adresse nicht erkannt (weder DOI noch Tron)")


def connect_doi(wm):
    """DOI ElectrumX-Verbindung herstellen."""
    print()
    print("  Verbinde mit Doichain ElectrumX...", end=" ", flush=True)
    try:
        ok = wm.connect_doi()
        if ok:
            print("✅")
        else:
            print("❌ Verbindung fehlgeschlagen")
    except Exception as e:
        print(f"❌ {e}")


# ──────────────────────────────────────────────
# XT.com Exchange Funktionen
# ──────────────────────────────────────────────

def show_doi_price(xt):
    """DOI/USDT Marktdaten anzeigen."""
    print()
    try:
        t = xt.get_ticker()
        t24 = xt.get_ticker_24h()
        ob = xt.get_orderbook(limit=5)

        print(f"  ┌─ DOI/USDT Markt ────────────────────────────┐")
        print(f"  │  Preis:     {t['price']:>12.6f} USDT           │")
        print(f"  │  24h Hoch:  {t24['high']:>12.6f}               │")
        print(f"  │  24h Tief:  {t24['low']:>12.6f}               │")
        print(f"  │  24h Vol:   {t24['volume']:>12,.0f} DOI            │")
        print(f"  │  24h Änd:   {t24['change_pct']:>+11.2f}%               │")
        print(f"  │  Spread:    {ob['spread']:>12.6f} ({ob['spread_pct']:.2f}%)      │")
        print(f"  └──────────────────────────────────────────────┘")

        print(f"\n  Orderbuch (Top 5):")
        print(f"  {'ASK (Verkauf)':>15s}  {'Preis':>10s}  {'Menge':>10s}  {'Gesamt':>10s}")
        for a in ob["asks"][:5]:
            print(f"  {'':>15s}  {a['price']:>10.6f}  {a['quantity']:>10.2f}  {a['price']*a['quantity']:>10.4f}")
        print(f"  {'─'*50}")
        for b in ob["bids"][:5]:
            print(f"  {'':>15s}  {b['price']:>10.6f}  {b['quantity']:>10.2f}  {b['price']*b['quantity']:>10.4f}")

    except Exception as e:
        print(f"  ❌ {e}")


def show_vwap(xt):
    """VWAP-Berechnung für eine bestimmte Menge."""
    print()
    try:
        side = input("  Kaufen oder Verkaufen? (k/v): ").strip().lower()
        side = "BUY" if side in ("k", "buy", "kaufen") else "SELL"

        amount = float(input("  Menge (DOI): ").strip())

        vwap = xt.calculate_vwap(amount, side)

        action = "Kauf" if side == "BUY" else "Verkauf"
        print(f"\n  {action}-Simulation für {amount:,.0f} DOI:")
        print(f"  VWAP:        {vwap['vwap']:.6f} USDT/DOI")
        print(f"  Gesamtkosten:{vwap['total_cost']:>10.4f} USDT")
        print(f"  Slippage:    {vwap['slippage_pct']:.3f}%")
        print(f"  Gefüllt:     {vwap['filled']:,.0f} / {vwap['requested']:,.0f} DOI")

        if not vwap["fully_filled"]:
            print(f"  ⚠️  Nicht genug Liquidität im Orderbuch!")

    except ValueError:
        print("  ❌ Ungültige Eingabe")
    except Exception as e:
        print(f"  ❌ {e}")


def show_exchange_balance(xt):
    """XT.com Kontosalden anzeigen."""
    print()
    if not xt.has_credentials:
        print("  ⚠️  Kein XT.com API-Key konfiguriert!")
        print("  Trage api_key und api_secret in config/config.yaml ein.")
        return

    try:
        balances = xt.get_balances()
        if balances:
            print(f"  ┌─ XT.com Kontosaldo ──────────────────────────┐")
            for b in balances:
                print(f"  │  {b['currency']:<6s}  {b['available']:>14.6f} verfügbar", end="")
                if b['frozen'] > 0:
                    print(f"  ({b['frozen']:.6f} gesperrt)", end="")
                print()
            print(f"  └──────────────────────────────────────────────┘")
        else:
            print("  Keine Bestände auf XT.com")
    except Exception as e:
        print(f"  ❌ {e}")


def place_order(xt):
    """Order auf XT.com erstellen."""
    print()
    if not xt.has_credentials:
        print("  ⚠️  Kein XT.com API-Key konfiguriert!")
        return

    try:
        # Aktuellen Preis anzeigen
        t = xt.get_ticker()
        print(f"  Aktueller DOI-Preis: {t['price']:.6f} USDT")
        print()

        side = input("  Kaufen oder Verkaufen? (k/v): ").strip().lower()
        side = "BUY" if side in ("k", "buy", "kaufen") else "SELL"

        order_type = input("  Order-Typ (limit/market) [limit]: ").strip().lower() or "limit"

        if order_type == "limit":
            price = float(input("  Limit-Preis (USDT): ").strip())
            quantity = float(input("  Menge (DOI): ").strip())
            total = price * quantity

            action = "Kaufe" if side == "BUY" else "Verkaufe"
            print(f"\n  {action} {quantity:,.2f} DOI @ {price:.6f} USDT")
            print(f"  Gesamtwert: {total:,.4f} USDT")

            confirm = input("  Bestätigen? (ja/nein): ").strip().lower()
            if confirm not in ("ja", "j", "yes", "y"):
                print("  Abgebrochen.")
                return

            result = xt.place_limit_order(side, price, quantity)
            print(f"\n  ✅ Limit-Order erstellt!")
            print(f"  Order-ID: {result['order_id']}")

        elif order_type == "market":
            if side == "BUY":
                usdt_amount = float(input("  USDT-Betrag: ").strip())
                print(f"\n  Kaufe DOI für {usdt_amount:,.2f} USDT (Market)")
                confirm = input("  Bestätigen? (ja/nein): ").strip().lower()
                if confirm not in ("ja", "j", "yes", "y"):
                    print("  Abgebrochen.")
                    return
                result = xt.place_market_order(side, quote_quantity=usdt_amount)
            else:
                quantity = float(input("  Menge (DOI): ").strip())
                print(f"\n  Verkaufe {quantity:,.2f} DOI (Market)")
                confirm = input("  Bestätigen? (ja/nein): ").strip().lower()
                if confirm not in ("ja", "j", "yes", "y"):
                    print("  Abgebrochen.")
                    return
                result = xt.place_market_order(side, quantity=quantity)

            print(f"\n  ✅ Market-Order erstellt!")
            print(f"  Order-ID: {result['order_id']}")
        else:
            print("  ❌ Ungültiger Order-Typ")

    except ValueError as e:
        print(f"  ❌ {e}")
    except Exception as e:
        print(f"  ❌ {e}")


def show_open_orders(xt):
    """Offene Orders anzeigen."""
    print()
    if not xt.has_credentials:
        print("  ⚠️  Kein XT.com API-Key konfiguriert!")
        return

    try:
        orders = xt.get_open_orders()
        if orders:
            print(f"  Offene Orders:")
            for o in orders:
                filled_pct = (o['filled'] / o['quantity'] * 100) if o['quantity'] else 0
                print(f"    {o['order_id']}  {o['side']:<4s}  {o['quantity']:>10.2f} DOI"
                      f" @ {o['price']:.6f}  ({filled_pct:.0f}% gefüllt)  {o['status']}")
        else:
            print("  Keine offenen Orders.")
    except Exception as e:
        print(f"  ❌ {e}")


def cancel_order_menu(xt):
    """Order stornieren."""
    print()
    if not xt.has_credentials:
        print("  ⚠️  Kein XT.com API-Key konfiguriert!")
        return

    try:
        orders = xt.get_open_orders()
        if not orders:
            print("  Keine offenen Orders zum Stornieren.")
            return

        print(f"  Offene Orders:")
        for i, o in enumerate(orders):
            print(f"    [{i+1}] {o['side']:<4s}  {o['quantity']:>10.2f} DOI"
                  f" @ {o['price']:.6f}  ID: {o['order_id']}")

        print(f"    [a] Alle stornieren")
        choice = input("\n  Stornieren: ").strip().lower()

        if choice == "a":
            xt.cancel_all_orders()
            print("  ✅ Alle Orders storniert!")
        else:
            idx = int(choice) - 1
            if 0 <= idx < len(orders):
                xt.cancel_order(orders[idx]["order_id"])
                print(f"  ✅ Order {orders[idx]['order_id']} storniert!")
            else:
                print("  ❌ Ungültige Auswahl")

    except Exception as e:
        print(f"  ❌ {e}")


def show_currency_info(xt):
    """Deposit/Withdrawal Status anzeigen."""
    print()
    try:
        for cur in ["doi", "usdt"]:
            info = xt.get_currency_info(cur)
            if info:
                print(f"  {info['currency']}:")
                for c in info["chains"]:
                    dep = "✅" if c["deposit"] else "❌"
                    wd = "✅" if c["withdraw"] else "❌"
                    print(f"    {c['chain']:<20s}  Deposit: {dep}  Withdraw: {wd}", end="")
                    if c["withdraw"]:
                        print(f"  (Gebühr: {c['withdraw_fee']}, Min: {c['withdraw_min']})", end="")
                    print()
                print()
    except Exception as e:
        print(f"  ❌ {e}")


def exchange_menu(xt):
    """XT.com Exchange Untermenü."""
    while True:
        print()
        auth_status = "🔑 API verbunden" if xt.has_credentials else "🔓 Nur öffentliche Daten"
        print(f"  ┌─ XT.com Exchange ({auth_status}) ──────┐")
        print(f"  │  a. 📊 DOI/USDT Preis & Orderbuch     │")
        print(f"  │  b. 📐 VWAP-Berechnung                │")
        print(f"  │  c. 💰 XT.com Kontosaldo              │")
        print(f"  │  d. 📝 Order erstellen                 │")
        print(f"  │  e. 📋 Offene Orders                   │")
        print(f"  │  f. ❌ Order stornieren                │")
        print(f"  │  g. 🔄 Deposit/Withdrawal Status       │")
        print(f"  │  0. ← Zurück                           │")
        print(f"  └──────────────────────────────────────────┘")

        try:
            choice = input("\n  Auswahl: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "0":
            break
        elif choice == "a":
            show_doi_price(xt)
        elif choice == "b":
            show_vwap(xt)
        elif choice == "c":
            show_exchange_balance(xt)
        elif choice == "d":
            place_order(xt)
        elif choice == "e":
            show_open_orders(xt)
        elif choice == "f":
            cancel_order_menu(xt)
        elif choice == "g":
            show_currency_info(xt)
        else:
            print("  Ungültige Auswahl.")


def main_menu(wm, xt):
    """Hauptmenü."""
    while True:
        print()
        print("  ┌──────────────────────────────────────────────┐")
        print(f"  │  DOI:  {wm.primary_addresses.get('doi', 'N/A'):<37s} │")
        print(f"  │  Tron: {wm.primary_addresses.get('tron', 'N/A'):<37s} │")
        print("  ├──────────────────────────────────────────────┤")
        print("  │  1. 💰 Salden anzeigen                      │")
        print("  │  2. 📋 Alle Adressen                        │")
        print("  │  3. 📤 DOI senden                           │")
        print("  │  4. 📤 TRX senden                           │")
        print("  │  5. 📤 USDT senden                          │")
        print("  │  6. 🔍 Externe Adresse abfragen             │")
        print("  │  7. 🔌 DOI verbinden (ElectrumX)            │")
        print("  │  8. 💾 Wallet speichern                     │")
        print("  │  9. ℹ️  Wallet-Info                          │")
        print("  │  x. 📈 XT.com Exchange                      │")
        print("  │  0. 🚪 Beenden                              │")
        print("  └──────────────────────────────────────────────┘")

        try:
            choice = input("\n  Auswahl: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if choice == "0":
            break
        elif choice == "1":
            show_balances(wm)
        elif choice == "2":
            show_addresses(wm)
        elif choice == "3":
            send_doi(wm)
        elif choice == "4":
            send_trx(wm)
        elif choice == "5":
            send_usdt(wm)
        elif choice == "6":
            query_external(wm)
        elif choice == "7":
            connect_doi(wm)
        elif choice == "8":
            try:
                default = wm.wallet_path or "wallet.dat"
                path = input(f"  Speichern als [{default}]: ").strip() or default
                wm.save(path)
                print(f"  ✅ Gespeichert: {path}")
            except Exception as e:
                print(f"  ❌ {e}")
        elif choice == "9":
            print()
            info = wm.info()
            for k, v in info.items():
                print(f"    {k}: {v}")
            status = wm.check_connections()
            print(f"    doi_connected: {status.get('doi', False)}")
            print(f"    tron_connected: {status.get('tron', False)}")
        elif choice == "x":
            exchange_menu(xt)
        else:
            print("  Ungültige Auswahl.")


def main():
    parser = argparse.ArgumentParser(description="Doichain Wallet XT")
    parser.add_argument("--load", type=str, help="Wallet-Datei laden")
    args = parser.parse_args()

    clear()

    # Auto-detect wallet.dat
    load_path = args.load
    if not load_path and Path("wallet.dat").exists():
        load_path = "wallet.dat"

    wm = startup(wallet_path=load_path)
    if wm is None:
        print("\n  Beende.")
        return

    # XT.com Client erstellen
    xt = create_xt_client()

    try:
        main_menu(wm, xt)
    finally:
        wm.close()
        print("\n  Wallet geschlossen. Auf Wiedersehen! 👋")


if __name__ == "__main__":
    main()
