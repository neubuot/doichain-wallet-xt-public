#!/usr/bin/env python3
"""
Phase 0 – PoC: XT.com API Verbindungstest
==========================================

Testet folgende Funktionen:
1. Öffentliche API: DOI/USDT Orderbuch abrufen
2. Öffentliche API: DOI/USDT Ticker (aktueller Preis)
3. Öffentliche API: DOI Einzahlungs-/Auszahlungsinfos
4. Private API: Kontosaldo abrufen (benötigt API-Key)
5. Preisberechnung: VWAP für eine bestimmte DOI-Menge

Nutzung:
    python poc/test_xt_api.py                    # Nur öffentliche Tests
    python poc/test_xt_api.py --with-private      # Inkl. private API (benötigt config.yaml)
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import requests
from rich.console import Console
from rich.table import Table

# Projektroot zum Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.config import load_config, validate_xt_config

console = Console()

# XT.com API Basis-URLs
BASE_URL = "https://sapi.xt.com"
SYMBOL = "doi_usdt"


# ──────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────

def xt_public_get(endpoint: str, params: dict = None) -> dict:
    """Öffentlicher GET-Request an XT.com API."""
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]❌ API-Fehler: {e}[/red]")
        return None


def xt_private_get(endpoint: str, api_key: str, api_secret: str, params: dict = None) -> dict:
    """
    Authentifizierter GET-Request an XT.com API.
    Signatur nach XT.com v4 Dokumentation.
    """
    timestamp = str(int(time.time() * 1000))
    
    # Query-String sortiert aufbauen
    if params:
        sorted_params = sorted(params.items())
        query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
    else:
        query_string = ""
    
    # Signatur erstellen
    # Format: timestamp + method + path + query_string
    path = endpoint
    sign_payload = f"{timestamp}#GET#{path}"
    if query_string:
        sign_payload += f"#{query_string}"
    
    signature = hmac.new(
        api_secret.encode("utf-8"),
        sign_payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    
    headers = {
        "xt-validate-appkey": api_key,
        "xt-validate-timestamp": timestamp,
        "xt-validate-signature": signature,
        "xt-validate-algorithms": "HmacSHA256",
    }
    
    url = f"{BASE_URL}{endpoint}"
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]❌ API-Fehler: {e}[/red]")
        if hasattr(e, 'response') and e.response is not None:
            console.print(f"[red]   Response: {e.response.text}[/red]")
        return None


# ──────────────────────────────────────────────
# Test 1: Orderbuch
# ──────────────────────────────────────────────

def test_orderbook():
    """Ruft das DOI/USDT Orderbuch ab."""
    console.print("\n[bold cyan]═══ Test 1: DOI/USDT Orderbuch ═══[/bold cyan]")
    
    data = xt_public_get("/v4/public/depth", {"symbol": SYMBOL, "limit": 10})
    
    if not data or data.get("rc") != 0:
        console.print(f"[red]❌ Orderbuch konnte nicht abgerufen werden: {data}[/red]")
        return None
    
    result = data.get("result", {})
    asks = result.get("asks", [])  # Verkaufsangebote (aufsteigend)
    bids = result.get("bids", [])  # Kaufangebote (absteigend)
    
    # Tabelle: Asks (Verkaufsangebote)
    table = Table(title="Orderbuch DOI/USDT")
    table.add_column("Seite", style="bold")
    table.add_column("Preis (USDT)", justify="right")
    table.add_column("Menge (DOI)", justify="right")
    table.add_column("Gesamt (USDT)", justify="right")
    
    for ask in asks[:5]:
        price, qty = float(ask[0]), float(ask[1])
        table.add_row("ASK (Verkauf)", f"{price:.6f}", f"{qty:.2f}", f"{price * qty:.4f}")
    
    table.add_row("─────", "─────────", "─────────", "─────────")
    
    for bid in bids[:5]:
        price, qty = float(bid[0]), float(bid[1])
        table.add_row("BID (Kauf)", f"{price:.6f}", f"{qty:.2f}", f"{price * qty:.4f}")
    
    console.print(table)
    
    if asks and bids:
        best_ask = float(asks[0][0])
        best_bid = float(bids[0][0])
        spread = best_ask - best_bid
        spread_pct = (spread / best_ask) * 100
        console.print(f"  Best Ask: {best_ask:.6f} USDT")
        console.print(f"  Best Bid: {best_bid:.6f} USDT")
        console.print(f"  Spread:   {spread:.6f} USDT ({spread_pct:.2f}%)")
    
    console.print("[green]✅ Orderbuch erfolgreich abgerufen[/green]")
    return result


# ──────────────────────────────────────────────
# Test 2: Ticker (aktueller Preis)
# ──────────────────────────────────────────────

def test_ticker():
    """Ruft den aktuellen DOI/USDT Ticker ab."""
    console.print("\n[bold cyan]═══ Test 2: DOI/USDT Ticker ═══[/bold cyan]")
    
    data = xt_public_get("/v4/public/ticker/price", {"symbol": SYMBOL})
    
    if not data or data.get("rc") != 0:
        console.print(f"[red]❌ Ticker konnte nicht abgerufen werden: {data}[/red]")
        return None
    
    result = data.get("result", {})
    if isinstance(result, list):
        result = result[0] if result else {}
    
    price = result.get("p", "N/A")
    console.print(f"  Aktueller DOI-Preis: {price} USDT")
    console.print("[green]✅ Ticker erfolgreich abgerufen[/green]")
    return result


# ──────────────────────────────────────────────
# Test 3: Währungsinfos (Deposit/Withdrawal)
# ──────────────────────────────────────────────

def test_currency_info():
    """Ruft DOI und USDT Einzahlungs-/Auszahlungsinfos ab."""
    console.print("\n[bold cyan]═══ Test 3: Währungsinfos (DOI & USDT) ═══[/bold cyan]")
    
    data = xt_public_get("/v4/public/wallet/support/currency")
    
    if not data or data.get("rc") != 0:
        console.print(f"[red]❌ Währungsinfos konnten nicht abgerufen werden[/red]")
        return None
    
    currencies = data.get("result", [])
    
    for target in ["doi", "usdt"]:
        info = next((c for c in currencies if c.get("currency", "").lower() == target), None)
        
        if info:
            console.print(f"\n  [bold]{target.upper()}:[/bold]")
            for chain_info in info.get("supportChains", []):
                chain = chain_info.get("chain", "?")
                dep_enabled = chain_info.get("depositEnabled", False)
                wd_enabled = chain_info.get("withdrawEnabled", False)
                wd_fee = chain_info.get("withdrawFeeAmount", "?")
                wd_min = chain_info.get("withdrawMinAmount", "?")
                console.print(f"    Chain: {chain}")
                console.print(f"    Deposit:    {'✅ Aktiv' if dep_enabled else '❌ Inaktiv'}")
                console.print(f"    Withdrawal: {'✅ Aktiv' if wd_enabled else '❌ Inaktiv'}")
                console.print(f"    Withdrawal-Gebühr: {wd_fee}")
                console.print(f"    Withdrawal-Minimum: {wd_min}")
        else:
            console.print(f"  [yellow]⚠️  {target.upper()} nicht in Währungsliste gefunden[/yellow]")
    
    console.print("\n[green]✅ Währungsinfos erfolgreich abgerufen[/green]")
    return currencies


# ──────────────────────────────────────────────
# Test 4: Kontosaldo (Private API)
# ──────────────────────────────────────────────

def test_balance(api_key: str, api_secret: str):
    """Ruft den Kontosaldo über die private API ab."""
    console.print("\n[bold cyan]═══ Test 4: Kontosaldo (Private API) ═══[/bold cyan]")
    
    data = xt_private_get("/v4/balances", api_key, api_secret)
    
    if not data:
        console.print("[red]❌ Saldo konnte nicht abgerufen werden[/red]")
        return None
    
    if data.get("rc") != 0:
        console.print(f"[red]❌ API-Fehler: {data.get('mc', 'Unbekannter Fehler')}[/red]")
        console.print("[yellow]   Mögliche Ursachen:[/yellow]")
        console.print("   - API-Key hat keine Lese-Berechtigung")
        console.print("   - Signatur-Format stimmt nicht (XT.com Doku prüfen)")
        console.print("   - IP nicht in Whitelist")
        return None
    
    assets = data.get("result", [])
    
    table = Table(title="Kontosaldo auf XT.com")
    table.add_column("Asset", style="bold")
    table.add_column("Verfügbar", justify="right")
    table.add_column("Gesperrt", justify="right")
    
    relevant = ["doi", "usdt", "trx"]
    found_any = False
    
    for asset in assets:
        currency = asset.get("currency", "").lower()
        if currency in relevant:
            available = asset.get("available", "0")
            frozen = asset.get("frozen", "0")
            table.add_row(currency.upper(), available, frozen)
            found_any = True
    
    if found_any:
        console.print(table)
    else:
        console.print("  [yellow]Keine DOI/USDT/TRX Bestände auf XT.com gefunden.[/yellow]")
    
    console.print("[green]✅ Saldo erfolgreich abgerufen[/green]")
    return assets


# ──────────────────────────────────────────────
# Test 5: VWAP-Preisberechnung
# ──────────────────────────────────────────────

def test_vwap_calculation(target_amount_doi: float = 100.0):
    """
    Berechnet den volumengewichteten Durchschnittspreis (VWAP) 
    für eine bestimmte DOI-Menge basierend auf dem Orderbuch.
    """
    console.print(f"\n[bold cyan]═══ Test 5: VWAP-Berechnung für {target_amount_doi} DOI ═══[/bold cyan]")
    
    data = xt_public_get("/v4/public/depth", {"symbol": SYMBOL, "limit": 50})
    
    if not data or data.get("rc") != 0:
        console.print("[red]❌ Orderbuch für VWAP nicht verfügbar[/red]")
        return None
    
    result = data.get("result", {})
    asks = result.get("asks", [])
    
    if not asks:
        console.print("[red]❌ Keine Verkaufsangebote im Orderbuch[/red]")
        return None
    
    # VWAP berechnen: Durch Asks iterieren bis Zielmenge erreicht
    total_cost = 0.0
    total_filled = 0.0
    fills = []
    
    for ask in asks:
        price = float(ask[0])
        available_qty = float(ask[1])
        remaining = target_amount_doi - total_filled
        
        if remaining <= 0:
            break
        
        fill_qty = min(available_qty, remaining)
        fill_cost = fill_qty * price
        
        fills.append({
            "price": price,
            "qty": fill_qty,
            "cost": fill_cost,
        })
        
        total_cost += fill_cost
        total_filled += fill_qty
    
    if total_filled < target_amount_doi:
        console.print(f"[yellow]⚠️  Nicht genug Liquidität! Nur {total_filled:.2f} / {target_amount_doi:.2f} DOI verfügbar[/yellow]")
    
    if total_filled > 0:
        vwap = total_cost / total_filled
        limit_price = vwap * 1.05  # + 5% Aufschlag
        
        table = Table(title=f"Kauf-Simulation: {target_amount_doi} DOI")
        table.add_column("Preis (USDT)", justify="right")
        table.add_column("Menge (DOI)", justify="right")
        table.add_column("Kosten (USDT)", justify="right")
        
        for fill in fills:
            table.add_row(
                f"{fill['price']:.6f}",
                f"{fill['qty']:.2f}",
                f"{fill['cost']:.4f}",
            )
        
        table.add_row("─────────", "─────────", "─────────")
        table.add_row(f"VWAP: {vwap:.6f}", f"{total_filled:.2f}", f"{total_cost:.4f}")
        console.print(table)
        
        console.print(f"\n  VWAP (Durchschnittspreis):  {vwap:.6f} USDT/DOI")
        console.print(f"  Limit-Preis (+5%):          {limit_price:.6f} USDT/DOI")
        console.print(f"  Gesamtkosten:               {total_cost:.4f} USDT")
        console.print(f"  Gesamtkosten mit Limit:     {total_filled * limit_price:.4f} USDT (max.)")
        
        console.print("\n[green]✅ VWAP-Berechnung abgeschlossen[/green]")
        
        return {
            "vwap": vwap,
            "limit_price": limit_price,
            "total_cost": total_cost,
            "total_filled": total_filled,
            "fills": fills,
        }
    
    return None


# ──────────────────────────────────────────────
# Hauptprogramm
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="XT.com API Proof of Concept")
    parser.add_argument("--with-private", action="store_true", 
                       help="Private API Tests einschließen (benötigt config.yaml)")
    parser.add_argument("--doi-amount", type=float, default=100.0,
                       help="DOI-Menge für VWAP-Berechnung (Standard: 100)")
    args = parser.parse_args()
    
    console.print("[bold]╔══════════════════════════════════════════╗[/bold]")
    console.print("[bold]║   XT.com API – Proof of Concept         ║[/bold]")
    console.print("[bold]║   Trading-Paar: DOI/USDT                ║[/bold]")
    console.print("[bold]╚══════════════════════════════════════════╝[/bold]")
    
    # Öffentliche Tests (kein API-Key nötig)
    console.print("\n[bold white]── Öffentliche API-Tests ──[/bold white]")
    
    test_ticker()
    test_orderbook()
    test_currency_info()
    test_vwap_calculation(args.doi_amount)
    
    # Private Tests (API-Key nötig)
    if args.with_private:
        console.print("\n[bold white]── Private API-Tests ──[/bold white]")
        
        try:
            config = load_config()
            if validate_xt_config(config):
                xt = config["xt_com"]
                test_balance(xt["api_key"], xt["api_secret"])
            else:
                console.print("[yellow]⚠️  Private Tests übersprungen – API-Keys nicht konfiguriert[/yellow]")
        except FileNotFoundError as e:
            console.print(f"[yellow]⚠️  {e}[/yellow]")
    else:
        console.print("\n[dim]Private API-Tests übersprungen. Nutze --with-private zum Aktivieren.[/dim]")
    
    console.print("\n[bold green]═══ PoC abgeschlossen ═══[/bold green]")


if __name__ == "__main__":
    main()
