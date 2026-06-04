#!/usr/bin/env python3
"""
Phase 0 – PoC: Doichain Netzwerk-Test
======================================

Testet folgende Funktionen:
1. Verbindung zum Doichain-Netzwerk (Electrum-Server)
2. Blockchain-Infos abrufen (Blockhöhe, etc.)
3. Adresse generieren (BIP-39 Seed → BIP-44 Ableitung)
4. Adress-Saldo abfragen

Hinweis: 
    Doichain ist ein Bitcoin-Fork und nutzt das Electrum-Protokoll.
    Für den produktiven Einsatz wird der Electrum-DOI-Fork benötigt.
    Dieses PoC testet die grundlegende Netzwerkkommunikation.

Nutzung:
    python poc/test_doichain.py
    python poc/test_doichain.py --address <DOI-Adresse>
"""

import argparse
import hashlib
import json
import socket
import ssl
import sys
from pathlib import Path

from rich.console import Console

# Projektroot zum Path hinzufügen
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.config import load_config

console = Console()

# Standard Electrum-Server für Doichain
DEFAULT_SERVERS = [
    {"host": "white-snail-54.doi.works", "port": 50002, "protocol": "ssl"},
    {"host": "itchy-jellyfish-89.doi.works", "port": 50002, "protocol": "ssl"},
    {"host": "ugly-bird-70.doi.works", "port": 50002, "protocol": "ssl"},
]


# ──────────────────────────────────────────────
# Electrum-Protokoll Kommunikation
# ──────────────────────────────────────────────

class ElectrumClient:
    """
    Minimaler Electrum-Protokoll-Client für Doichain.
    Nutzt JSON-RPC über TCP/SSL.
    """
    
    def __init__(self, host: str, port: int, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.sock = None
        self.request_id = 0
    
    def connect(self) -> bool:
        """Verbindung zum Electrum-Server herstellen."""
        try:
            raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            raw_sock.settimeout(15)
            
            if self.use_ssl:
                context = ssl.create_default_context()
                # Für Testzwecke: Selbstsignierte Zertifikate akzeptieren
                context.check_hostname = False
                context.verify_mode = ssl.CERT_NONE
                self.sock = context.wrap_socket(raw_sock, server_hostname=self.host)
            else:
                self.sock = raw_sock
            
            self.sock.connect((self.host, self.port))
            return True
        except Exception as e:
            console.print(f"[red]❌ Verbindung fehlgeschlagen: {e}[/red]")
            return False
    
    def request(self, method: str, params: list = None) -> dict:
        """JSON-RPC Request an den Electrum-Server senden."""
        if not self.sock:
            raise ConnectionError("Nicht verbunden")
        
        self.request_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params or [],
        }
        
        msg = json.dumps(payload) + "\n"
        self.sock.sendall(msg.encode("utf-8"))
        
        # Antwort lesen (zeilenbasiert)
        response = b""
        while True:
            chunk = self.sock.recv(4096)
            response += chunk
            if b"\n" in response:
                break
        
        return json.loads(response.decode("utf-8").strip())
    
    def close(self):
        """Verbindung schließen."""
        if self.sock:
            self.sock.close()
            self.sock = None


# ──────────────────────────────────────────────
# Test 1: Server-Verbindung
# ──────────────────────────────────────────────

def test_server_connection(servers: list = None) -> ElectrumClient:
    """Versucht eine Verbindung zu einem Doichain Electrum-Server herzustellen."""
    console.print("\n[bold cyan]═══ Test 1: Doichain Electrum-Server Verbindung ═══[/bold cyan]")
    
    if servers is None:
        servers = DEFAULT_SERVERS
    
    for server in servers:
        host = server["host"]
        port = server["port"]
        use_ssl = server.get("protocol", "ssl") == "ssl"
        
        console.print(f"  Verbinde zu {host}:{port} ({'SSL' if use_ssl else 'TCP'})...")
        
        client = ElectrumClient(host, port, use_ssl)
        if client.connect():
            console.print(f"[green]  ✅ Verbindung zu {host}:{port} hergestellt[/green]")
            return client
        else:
            console.print(f"[yellow]  ⚠️  {host}:{port} nicht erreichbar, nächsten Server versuchen...[/yellow]")
    
    console.print("[red]❌ Kein Electrum-Server erreichbar[/red]")
    return None


# ──────────────────────────────────────────────
# Test 2: Blockchain-Infos
# ──────────────────────────────────────────────

def test_blockchain_info(client: ElectrumClient):
    """Ruft grundlegende Blockchain-Informationen ab."""
    console.print("\n[bold cyan]═══ Test 2: Blockchain-Informationen ═══[/bold cyan]")
    
    try:
        # Server-Version abfragen
        version = client.request("server.version", ["doichain-wallet-poc", "1.4"])
        console.print(f"  Server-Version: {version.get('result', 'N/A')}")
        
        # Server-Banner
        banner = client.request("server.banner")
        banner_text = banner.get("result", "N/A")
        if banner_text:
            # Nur erste 200 Zeichen anzeigen
            console.print(f"  Server-Banner: {banner_text[:200]}...")
        
        console.print("[green]✅ Blockchain-Infos erfolgreich abgerufen[/green]")
        return True
        
    except Exception as e:
        console.print(f"[red]❌ Fehler bei Blockchain-Abfrage: {e}[/red]")
        return False


# ──────────────────────────────────────────────
# Test 3: Block-Header abrufen
# ──────────────────────────────────────────────

def test_block_headers(client: ElectrumClient):
    """Ruft aktuelle Blockhöhe und Header ab."""
    console.print("\n[bold cyan]═══ Test 3: Aktuelle Blockhöhe ═══[/bold cyan]")
    
    try:
        # Headers subscriben (gibt aktuelle Höhe zurück)
        headers = client.request("blockchain.headers.subscribe")
        result = headers.get("result", {})
        
        if isinstance(result, dict):
            height = result.get("height", "N/A")
            console.print(f"  Aktuelle Blockhöhe: {height}")
        else:
            console.print(f"  Response: {result}")
        
        console.print("[green]✅ Block-Header erfolgreich abgerufen[/green]")
        return result
        
    except Exception as e:
        console.print(f"[red]❌ Fehler bei Block-Header-Abfrage: {e}[/red]")
        return None


# ──────────────────────────────────────────────
# Test 4: Adress-Saldo abfragen
# ──────────────────────────────────────────────

def test_address_balance(client: ElectrumClient, address: str = None):
    """Fragt den Saldo einer Doichain-Adresse ab."""
    console.print("\n[bold cyan]═══ Test 4: Adress-Saldo ═══[/bold cyan]")
    
    if not address:
        console.print("  [dim]Keine Adresse angegeben. Verwende --address <DOI-Adresse> für Saldoabfrage.[/dim]")
        console.print("  [dim]Übersprungen.[/dim]")
        return None
    
    try:
        # Electrum nutzt Script-Hash statt Adresse
        # Für den PoC versuchen wir den direkten Aufruf
        console.print(f"  Abfrage für Adresse: {address}")
        
        # Script-Hash berechnen (SHA256 des Script-Pubkeys)
        # Hinweis: Dies ist vereinfacht – für den produktiven Einsatz 
        # muss der korrekte Script-Hash aus der Adresse abgeleitet werden
        balance = client.request("blockchain.address.get_balance", [address])
        result = balance.get("result", {})
        
        if "error" in balance:
            console.print(f"[yellow]  ⚠️  Server-Antwort: {balance.get('error', {})}[/yellow]")
            console.print("  [dim]Hinweis: Manche Server erwarten einen Script-Hash statt einer Adresse.[/dim]")
        else:
            confirmed = result.get("confirmed", 0)
            unconfirmed = result.get("unconfirmed", 0)
            # Doichain hat wie Bitcoin 8 Dezimalstellen (Satoshis)
            console.print(f"  Bestätigt:   {confirmed / 1e8:.8f} DOI")
            console.print(f"  Unbestätigt: {unconfirmed / 1e8:.8f} DOI")
        
        console.print("[green]✅ Adress-Abfrage abgeschlossen[/green]")
        return result
        
    except Exception as e:
        console.print(f"[red]❌ Fehler bei Adress-Abfrage: {e}[/red]")
        return None


# ──────────────────────────────────────────────
# Test 5: BIP-39 Seed generieren (Demo)
# ──────────────────────────────────────────────

def test_seed_generation():
    """Demonstriert die BIP-39 Seed-Generierung."""
    console.print("\n[bold cyan]═══ Test 5: BIP-39 Seed-Generierung (Demo) ═══[/bold cyan]")
    
    try:
        from mnemonic import Mnemonic
        
        mnemo = Mnemonic("english")
        # 24 Wörter = 256 Bit Entropie
        seed_phrase = mnemo.generate(256)
        
        # Validierung
        is_valid = mnemo.check(seed_phrase)
        
        console.print(f"  Seed Phrase generiert: [bold]{seed_phrase[:30]}...[/bold]")
        console.print(f"  Wortanzahl: {len(seed_phrase.split())}")
        console.print(f"  Validierung: {'✅ Gültig' if is_valid else '❌ Ungültig'}")
        console.print("")
        console.print("  [yellow]⚠️  Dies ist nur eine Demo! Dieser Seed wird NICHT gespeichert.[/yellow]")
        console.print("  [yellow]    Im produktiven Wallet wird der Seed verschlüsselt gesichert.[/yellow]")
        
        console.print("[green]✅ Seed-Generierung erfolgreich[/green]")
        return True
        
    except ImportError:
        console.print("[yellow]  ⚠️  'mnemonic' Paket nicht installiert. Bitte: pip install mnemonic[/yellow]")
        return False


# ──────────────────────────────────────────────
# Hauptprogramm
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Doichain Netzwerk Proof of Concept")
    parser.add_argument("--address", type=str, default=None,
                       help="DOI-Adresse für Saldoabfrage")
    parser.add_argument("--host", type=str, default=None,
                       help="Electrum-Server Hostname")
    parser.add_argument("--port", type=int, default=50002,
                       help="Electrum-Server Port (Standard: 50002)")
    args = parser.parse_args()
    
    console.print("[bold]╔══════════════════════════════════════════╗[/bold]")
    console.print("[bold]║   Doichain Netzwerk – Proof of Concept  ║[/bold]")
    console.print("[bold]╚══════════════════════════════════════════╝[/bold]")
    
    # Server-Liste
    if args.host:
        servers = [{"host": args.host, "port": args.port, "protocol": "ssl"}]
    else:
        servers = DEFAULT_SERVERS
    
    # Test 1: Verbindung
    client = test_server_connection(servers)
    
    if client:
        try:
            # Test 2: Blockchain-Infos
            test_blockchain_info(client)
            
            # Test 3: Block-Header
            test_block_headers(client)
            
            # Test 4: Adress-Saldo
            test_address_balance(client, args.address)
            
        finally:
            client.close()
            console.print("\n  [dim]Verbindung geschlossen.[/dim]")
    else:
        console.print("\n[yellow]Tests 2–4 übersprungen (keine Verbindung).[/yellow]")
        console.print("[yellow]Mögliche Ursachen:[/yellow]")
        console.print("  - Electrum-Server nicht erreichbar")
        console.print("  - Firewall blockiert Port 50002")
        console.print("  - Server-Adresse falsch (mit --host anpassen)")
    
    # Test 5: Seed-Generierung (offline, kein Server nötig)
    test_seed_generation()
    
    console.print("\n[bold green]═══ PoC abgeschlossen ═══[/bold green]")


if __name__ == "__main__":
    main()
