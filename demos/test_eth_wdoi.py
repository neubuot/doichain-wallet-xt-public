#!/usr/bin/env python3
"""
Test: Ethereum / wDOI Integration
==================================

Testet die Verbindung zum Ethereum-Netzwerk und den wDOI-Token.

Nutzung:
    python demos/test_eth_wdoi.py
    python demos/test_eth_wdoi.py --address 0x...
    python demos/test_eth_wdoi.py --rpc https://custom-rpc.example.com

© 2026 Ottmar Neuburger, WEBanizer AG
"""

import argparse
import sys
from pathlib import Path

# Projektroot
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    parser = argparse.ArgumentParser(description="Ethereum / wDOI Test")
    parser.add_argument("--address", "-a", help="ETH-Adresse zum Abfragen")
    parser.add_argument("--rpc", help="Benutzerdefinierter RPC-URL")
    parser.add_argument("--seed", help="BIP-39 Seed-Phrase zum Testen (Vorsicht!)")
    args = parser.parse_args()

    print("╔══════════════════════════════════════════╗")
    print("║   Ethereum / wDOI – Test                 ║")
    print("╚══════════════════════════════════════════╝")

    # ─── Test 1: Import ───
    print("\n═══ Test 1: Modul-Import ═══")
    try:
        from src.wallet.eth_wallet import EthWallet, validate_eth_address, HAS_WEB3
        from src.wallet.eth_network import ETH_MAINNET, WDOI_CONTRACT, WDOI_DECIMALS
        print(f"  ✅ eth_wallet importiert")
        print(f"  web3 verfügbar:     {'✅' if HAS_WEB3 else '❌'}")
        print(f"  wDOI Contract:      {WDOI_CONTRACT}")
        print(f"  wDOI Dezimalstellen: {WDOI_DECIMALS}")
    except ImportError as e:
        print(f"  ❌ Import-Fehler: {e}")
        print("  Bitte installieren: pip install web3 eth-account")
        return

    if not HAS_WEB3:
        print("\n  ❌ web3 nicht installiert. Bitte: pip install web3 eth-account")
        return

    # ─── Test 2: Adress-Validierung ───
    print("\n═══ Test 2: Adress-Validierung ═══")
    test_addresses = [
        ("0xA2B6c1a7EFB3dFa75E2d9DF1180b02668c06da72", True),
        ("0x0000000000000000000000000000000000000000", True),
        ("0xinvalid", False),
        ("TYJHdvhnssJKtwsfyCNfV1Mvc2PneoNbx6", False),  # Tron-Adresse
    ]
    for addr, expected in test_addresses:
        result = validate_eth_address(addr)
        status = "✅" if result == expected else "❌"
        print(f"  {status} {addr[:20]}... → {'gültig' if result else 'ungültig'}")

    # ─── Test 3: Verbindung ───
    print("\n═══ Test 3: Ethereum-Verbindung ═══")
    wallet = EthWallet(rpc_url=args.rpc)
    connected = wallet.connect()
    if connected:
        print(f"  ✅ Verbunden mit Ethereum")
        print(f"  RPC: {wallet._rpc_url}")
    else:
        print("  ❌ Verbindung fehlgeschlagen")
        print("  Versuche: python demos/test_eth_wdoi.py --rpc https://eth.llamarpc.com")
        return

    # ─── Test 4: Gas-Preise ───
    print("\n═══ Test 4: Gas-Preise ═══")
    try:
        gas = wallet.estimate_gas_price()
        print(f"  Gas-Preis:          {gas['gas_price_gwei']:.2f} Gwei")
        print(f"  ETH-Transfer:       ~{gas['eth_transfer_cost_eth']:.6f} ETH")
        print(f"  ERC-20-Transfer:    ~{gas['erc20_transfer_cost_eth']:.6f} ETH")
        print(f"  ✅ Gas-Preise abgerufen")
    except Exception as e:
        print(f"  ❌ Fehler: {e}")

    # ─── Test 5: wDOI Token-Info ───
    print("\n═══ Test 5: wDOI Token-Info ═══")
    try:
        info = wallet.get_wdoi_info()
        if info:
            print(f"  Name:          {info['name']}")
            print(f"  Symbol:        {info['symbol']}")
            print(f"  Dezimalstellen: {info['decimals']}")
            print(f"  Total Supply:  {info['total_supply']:,.2f}")
            print(f"  Contract:      {info['contract']}")
            print(f"  ✅ wDOI Token-Info abgerufen")
        else:
            print("  ⚠️ Keine Token-Info erhalten")
    except Exception as e:
        print(f"  ❌ Fehler: {e}")

    # ─── Test 6: Balance-Abfrage ───
    if args.address:
        print(f"\n═══ Test 6: Balance für {args.address[:16]}... ═══")
        try:
            eth_bal = wallet.get_eth_balance(args.address)
            wdoi_bal = wallet.get_wdoi_balance(args.address)
            print(f"  ETH-Saldo:   {eth_bal:.6f} ETH")
            print(f"  wDOI-Saldo:  {wdoi_bal:.6f} wDOI")
            print(f"  ✅ Salden abgerufen")
        except Exception as e:
            print(f"  ❌ Fehler: {e}")
    else:
        print("\n═══ Test 6: Balance-Abfrage ═══")
        print("  Übersprungen (keine Adresse angegeben)")
        print("  Verwende: --address 0x... für Saldoabfrage")

    # ─── Test 7: Seed-Ableitung ───
    if args.seed and HAS_WEB3:
        print(f"\n═══ Test 7: ETH-Adressableitung aus Seed ═══")
        try:
            addr = wallet.from_mnemonic(args.seed)
            print(f"  ETH-Adresse: {addr}")
            print(f"  Explorer:    {wallet.get_address_explorer_url()}")

            # Auch alle Balances holen
            balances = wallet.get_all_balances()
            print(f"  ETH-Saldo:   {balances['ETH']:.6f} ETH")
            print(f"  wDOI-Saldo:  {balances['wDOI']:.6f} wDOI")
            print(f"  ✅ Adresse abgeleitet")
        except Exception as e:
            print(f"  ❌ Fehler: {e}")
    elif args.seed:
        print(f"\n═══ Test 7: Seed-Ableitung ═══")
        print("  ❌ web3/eth-account nicht installiert")
    else:
        print(f"\n═══ Test 7: Seed-Ableitung ═══")
        print("  Übersprungen (kein Seed angegeben)")
        print("  Verwende: --seed \"word1 word2 ...\" für Adressableitung")

    print("\n═══ Tests abgeschlossen ═══")


if __name__ == "__main__":
    main()
