#!/usr/bin/env python3
"""
Phase 0 – PoC: Tron Netzwerk-Test (USDT TRC-20 + TRX)
=======================================================

Testet folgende Funktionen:
1. Verbindung zum Tron-Netzwerk (TronGrid)
2. Neues Tron-Wallet erstellen (BIP-44 kompatibel)
3. TRX-Saldo einer Adresse abfragen
4. USDT (TRC-20) Saldo abfragen
5. Tron Energie- und Bandbreite-Infos
6. BIP-39 Seed → Tron-Adresse Ableitung

Nutzung:
    python poc/test_tron.py                          # Alle Tests
    python poc/test_tron.py --address <TRON-Adresse>  # Saldo einer bestimmten Adresse
"""

import argparse
import json
import sys
from pathlib import Path

import requests
from rich.console import Console
from rich.table import Table

# Projektroot zum Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.config import load_config

console = Console()

# Tron Mainnet
TRONGRID_URL = "https://api.trongrid.io"

# USDT TRC-20 Contract (Mainnet)
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# Nile Testnet (für Entwicklung)
TRONGRID_TESTNET_URL = "https://nile.trongrid.io"
USDT_CONTRACT_TESTNET = "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj"


# ──────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────

def tron_api_get(endpoint: str, base_url: str = TRONGRID_URL, api_key: str = None) -> dict:
    """GET-Request an TronGrid API."""
    url = f"{base_url}{endpoint}"
    headers = {"Accept": "application/json"}
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key
    
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]❌ Tron API-Fehler: {e}[/red]")
        return None


def tron_api_post(endpoint: str, data: dict, base_url: str = TRONGRID_URL, api_key: str = None) -> dict:
    """POST-Request an TronGrid API."""
    url = f"{base_url}{endpoint}"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key
    
    try:
        resp = requests.post(url, json=data, headers=headers, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        console.print(f"[red]❌ Tron API-Fehler: {e}[/red]")
        return None


# ──────────────────────────────────────────────
# Test 1: Netzwerk-Verbindung
# ──────────────────────────────────────────────

def test_tron_connection():
    """Testet die Verbindung zum Tron-Netzwerk."""
    console.print("\n[bold cyan]═══ Test 1: Tron Netzwerk-Verbindung ═══[/bold cyan]")
    
    # Aktuellen Block abrufen
    data = tron_api_post("/wallet/getnowblock", {})
    
    if not data:
        console.print("[red]❌ Tron-Netzwerk nicht erreichbar[/red]")
        return False
    
    block_header = data.get("block_header", {}).get("raw_data", {})
    block_number = block_header.get("number", "N/A")
    timestamp = block_header.get("timestamp", 0)
    
    # Timestamp in lesbare Zeit umwandeln
    from datetime import datetime
    block_time = datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S") if timestamp else "N/A"
    
    console.print(f"  Aktuelle Blockhöhe: {block_number}")
    console.print(f"  Block-Zeitstempel:  {block_time}")
    console.print(f"  Transaktionen:      {len(data.get('transactions', []))}")
    
    # Node-Info
    node_info = tron_api_get("/wallet/getnodeinfo")
    if node_info:
        console.print(f"  Node-Version:       {node_info.get('configNodeInfo', {}).get('codeVersion', 'N/A')}")
    
    console.print("[green]✅ Verbindung zum Tron-Netzwerk hergestellt[/green]")
    return True


# ──────────────────────────────────────────────
# Test 2: Wallet erstellen (TronPy)
# ──────────────────────────────────────────────

def test_create_wallet():
    """Erstellt ein neues Tron-Wallet mit TronPy."""
    console.print("\n[bold cyan]═══ Test 2: Tron-Wallet erstellen (TronPy) ═══[/bold cyan]")
    
    try:
        from tronpy.keys import PrivateKey
        
        # Neuen Private Key generieren
        priv_key = PrivateKey.random()
        address = priv_key.public_key.to_base58check_address()
        
        console.print(f"  Adresse:     {address}")
        console.print(f"  Public Key:  {priv_key.public_key.hex()[:40]}...")
        console.print(f"  Private Key: {priv_key.hex()[:10]}... [dim](gekürzt aus Sicherheitsgründen)[/dim]")
        console.print("")
        console.print("  [yellow]⚠️  Dies ist nur eine Demo! Dieser Key wird NICHT gespeichert.[/yellow]")
        
        console.print("[green]✅ Tron-Wallet erfolgreich erstellt[/green]")
        return address
        
    except ImportError:
        console.print("[yellow]  ⚠️  'tronpy' nicht installiert. Bitte: pip install tronpy[/yellow]")
        return None


# ──────────────────────────────────────────────
# Test 3: TRX-Saldo abfragen
# ──────────────────────────────────────────────

def test_trx_balance(address: str):
    """Fragt den TRX-Saldo einer Adresse ab."""
    console.print(f"\n[bold cyan]═══ Test 3: TRX-Saldo für {address[:12]}... ═══[/bold cyan]")
    
    data = tron_api_post("/wallet/getaccount", {"address": address, "visible": True})
    
    if not data:
        console.print("[yellow]  Konto existiert möglicherweise noch nicht (0 TRX, nie aktiviert).[/yellow]")
        return 0
    
    if "balance" not in data and "address" not in data:
        console.print("  [yellow]Konto nicht auf der Blockchain gefunden (noch nicht aktiviert).[/yellow]")
        console.print("  [dim]Hinweis: Tron-Konten werden erst bei der ersten eingehenden Transaktion aktiviert.[/dim]")
        return 0
    
    balance_sun = data.get("balance", 0)  # In SUN (1 TRX = 1,000,000 SUN)
    balance_trx = balance_sun / 1_000_000
    
    console.print(f"  TRX-Saldo:   {balance_trx:.6f} TRX")
    console.print(f"  TRX (SUN):   {balance_sun}")
    
    # Bandbreite und Energie
    net_usage = data.get("net_usage", 0)
    energy_usage = data.get("account_resource", {}).get("energy_usage", 0)
    console.print(f"  Bandbreite:  {net_usage}")
    console.print(f"  Energie:     {energy_usage}")
    
    console.print("[green]✅ TRX-Saldo abgerufen[/green]")
    return balance_trx


# ──────────────────────────────────────────────
# Test 4: USDT (TRC-20) Saldo abfragen
# ──────────────────────────────────────────────

def test_usdt_balance(address: str):
    """Fragt den USDT TRC-20 Saldo einer Adresse ab."""
    console.print(f"\n[bold cyan]═══ Test 4: USDT (TRC-20) Saldo für {address[:12]}... ═══[/bold cyan]")
    
    # TRC-20 Balance über TronGrid API
    data = tron_api_get(f"/v1/accounts/{address}")
    
    if not data or not data.get("data"):
        console.print("  [yellow]Konto nicht gefunden oder keine Token-Bestände.[/yellow]")
        return 0
    
    account_data = data["data"][0] if data.get("data") else {}
    trc20_balances = account_data.get("trc20", [])
    
    usdt_balance = 0
    for token in trc20_balances:
        if USDT_CONTRACT in token:
            # USDT hat 6 Dezimalstellen
            raw_balance = int(token[USDT_CONTRACT])
            usdt_balance = raw_balance / 1_000_000
            break
    
    console.print(f"  USDT-Saldo:  {usdt_balance:.6f} USDT")
    
    # Alle TRC-20 Token anzeigen
    if trc20_balances:
        console.print(f"  [dim]Gefundene TRC-20 Token: {len(trc20_balances)}[/dim]")
    
    console.print("[green]✅ USDT-Saldo abgerufen[/green]")
    return usdt_balance


# ──────────────────────────────────────────────
# Test 5: Energie- und Bandbreite-Kosten
# ──────────────────────────────────────────────

def test_energy_costs():
    """Ermittelt aktuelle Tron Energie- und Bandbreite-Kosten."""
    console.print("\n[bold cyan]═══ Test 5: Tron Energie & Bandbreite ═══[/bold cyan]")
    
    # Chain-Parameter abrufen
    data = tron_api_get("/wallet/getchainparameters")
    
    if not data:
        console.print("[red]❌ Chain-Parameter nicht abrufbar[/red]")
        return None
    
    params = data.get("chainParameter", [])
    
    # Relevante Parameter extrahieren
    relevant_params = {
        "getEnergyFee": "Energie-Preis (SUN/Energie)",
        "getTransactionFee": "Bandbreite-Preis (SUN/Byte)",
        "getCreateAccountFee": "Konto-Erstellungsgebühr (SUN)",
        "getCreateNewAccountFeeInSystemContract": "Konto-Erstellung Systemvertrag",
    }
    
    table = Table(title="Tron Netzwerk-Kosten")
    table.add_column("Parameter", style="bold")
    table.add_column("Wert", justify="right")
    table.add_column("Beschreibung")
    
    for param in params:
        key = param.get("key", "")
        if key in relevant_params:
            value = param.get("value", "N/A")
            table.add_row(key, str(value), relevant_params[key])
    
    console.print(table)
    
    # Geschätzte Kosten für USDT-Transfer
    console.print("\n  [bold]Geschätzte Kosten für einen USDT TRC-20 Transfer:[/bold]")
    console.print("  Energie benötigt:  ~65.000 Energy")
    console.print("  Bei aktuellem Preis: ~6,5 TRX (~0,50 – 1,50 USD)")
    console.print("  [dim]Hinweis: Mit gestaktem TRX kann Energy kostenlos generiert werden.[/dim]")
    
    console.print("[green]✅ Netzwerk-Kosten ermittelt[/green]")
    return params


# ──────────────────────────────────────────────
# Test 6: BIP-39 Seed → Tron-Adresse
# ──────────────────────────────────────────────

def test_seed_to_tron_address():
    """Demonstriert die Ableitung einer Tron-Adresse aus einem BIP-39 Seed."""
    console.print("\n[bold cyan]═══ Test 6: BIP-39 Seed → Tron-Adresse (Demo) ═══[/bold cyan]")
    
    try:
        from mnemonic import Mnemonic
        from bip_utils import (
            Bip39SeedGenerator, Bip44, Bip44Coins, Bip44Changes
        )
        
        # Demo-Seed generieren
        mnemo = Mnemonic("english")
        seed_phrase = mnemo.generate(256)
        
        console.print(f"  Seed Phrase: {seed_phrase[:40]}... [dim](gekürzt)[/dim]")
        
        # BIP-39 Seed → BIP-44 Ableitung für Tron
        seed_bytes = Bip39SeedGenerator(seed_phrase).Generate()
        
        # m/44'/195'/0'/0/0 (Tron BIP-44 Pfad)
        bip44_ctx = Bip44.FromSeed(seed_bytes, Bip44Coins.TRON)
        account = bip44_ctx.Purpose().Coin().Account(0)
        change = account.Change(Bip44Changes.CHAIN_EXT)
        address_0 = change.AddressIndex(0)
        
        tron_address = address_0.PublicKey().ToAddress()
        private_key = address_0.PrivateKey().Raw().ToHex()
        
        console.print(f"  Ableitungspfad: m/44'/195'/0'/0/0")
        console.print(f"  Tron-Adresse:   {tron_address}")
        console.print(f"  Private Key:    {private_key[:10]}... [dim](gekürzt)[/dim]")
        console.print("")
        console.print("  [yellow]⚠️  Demo! Dieser Seed wird NICHT gespeichert.[/yellow]")
        
        # Auch zweite Adresse zeigen (für HD-Wallet)
        address_1 = change.AddressIndex(1)
        tron_address_1 = address_1.PublicKey().ToAddress()
        console.print(f"\n  Zweite Adresse (Index 1): {tron_address_1}")
        console.print("  [dim]→ HD-Wallet: Beliebig viele Adressen aus einem Seed ableitbar.[/dim]")
        
        console.print("[green]✅ Seed → Tron-Adresse Ableitung erfolgreich[/green]")
        return tron_address
        
    except ImportError as e:
        console.print(f"[yellow]  ⚠️  Fehlende Pakete: {e}[/yellow]")
        console.print("  [dim]Bitte installiere: pip install mnemonic bip-utils[/dim]")
        return None


# ──────────────────────────────────────────────
# Hauptprogramm
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Tron Netzwerk Proof of Concept")
    parser.add_argument("--address", type=str, default=None,
                       help="Tron-Adresse für Saldoabfrage (z.B. TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t)")
    parser.add_argument("--testnet", action="store_true",
                       help="Nile Testnet statt Mainnet verwenden")
    args = parser.parse_args()
    
    console.print("[bold]╔══════════════════════════════════════════╗[/bold]")
    console.print("[bold]║   Tron Netzwerk – Proof of Concept      ║[/bold]")
    console.print("[bold]║   USDT (TRC-20) + TRX                   ║[/bold]")
    console.print("[bold]╚══════════════════════════════════════════╝[/bold]")
    
    if args.testnet:
        global TRONGRID_URL, USDT_CONTRACT
        TRONGRID_URL = TRONGRID_TESTNET_URL
        USDT_CONTRACT = USDT_CONTRACT_TESTNET
        console.print("[yellow]  Verwende Nile Testnet[/yellow]")
    
    # Test 1: Netzwerk-Verbindung
    connected = test_tron_connection()
    
    if not connected:
        console.print("\n[red]Weitere Tests abgebrochen (keine Verbindung).[/red]")
        return
    
    # Test 2: Wallet erstellen
    demo_address = test_create_wallet()
    
    # Test 3 & 4: Saldo abfragen
    # Verwende angegebene Adresse oder eine bekannte Adresse mit Guthaben
    query_address = args.address
    if not query_address:
        # Verwende die USDT-Contract-Adresse als Demo (hat definitiv Aktivität)
        query_address = USDT_CONTRACT
        console.print(f"\n  [dim]Keine Adresse angegeben, verwende USDT-Contract als Demo: {query_address}[/dim]")
    
    test_trx_balance(query_address)
    test_usdt_balance(query_address)
    
    # Test 5: Energie-Kosten
    test_energy_costs()
    
    # Test 6: Seed → Tron-Adresse
    test_seed_to_tron_address()
    
    console.print("\n[bold green]═══ PoC abgeschlossen ═══[/bold green]")


if __name__ == "__main__":
    main()
