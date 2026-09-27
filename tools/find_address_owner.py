"""
Prueft, ob Doichain-Adressen zu einer Wallet-Datei (DOI-Wallet-iX) gehoeren.

Durchsucht den Standardpfad des Wallets (m/44'/7'/0'/{0,1}/i) und zusaetzlich
alternative Ableitungen (andere Coin-Types, Accounts), falls die Adresse von
einer anderen Wallet-Software oder -Version aus demselben Seed erzeugt wurde.

Das Passwort wird am Terminal verdeckt abgefragt und nur lokal fuer die
Entschluesselung benutzt. Nichts wird uebertragen.

Aufruf (im Repo-Ordner, mit dem venv):
    venv\\Scripts\\python tools\\find_address_owner.py "C:\\Pfad\\wallet-2.dat" NGbJiAAautYLi57zk7D66e9kLtau5ZHJUC N4aGCKf7V9HTDD8JG6CQKMj8TjxVi29HmG

Optionen:  --max 300        Indizes je Kette (Standard 300)
           --passphrase     Wallet wurde mit BIP-39-Passphrase angelegt
           --quick          nur den Standardpfad pruefen
"""

import argparse
import getpass
import os
import sys
import warnings

warnings.simplefilter("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.wallet.wallet_manager import WalletManager  # noqa: E402
from src.wallet.seed_manager import SeedManager  # noqa: E402

COIN_TYPES = (7, 22, 7070, 0, 1)
ACCOUNTS = (0, 1, 2)


def scan(sm: SeedManager, targets: set, coin_types, accounts, max_idx: int):
    found = {}
    for coin in coin_types:
        for acc in accounts:
            for change in (0, 1):
                for idx in range(max_idx):
                    path = f"m/44'/{coin}'/{acc}'/{change}/{idx}"
                    try:
                        a = sm.derive_address(path) if hasattr(sm, "derive_address") else None
                    except Exception:
                        a = None
                    if a is None:
                        # Fallback ueber get_keypair mit temporaer gesetztem Coin-Type
                        orig = sm.network.get("bip44_coin_type")
                        sm.network["bip44_coin_type"] = coin
                        try:
                            a = sm.get_keypair(index=idx, change=change, account=acc)["address"]
                        finally:
                            sm.network["bip44_coin_type"] = orig
                    if a in targets and a not in found:
                        found[a] = path
                        if len(found) == len(targets):
                            return found
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("wallet_file")
    ap.add_argument("address", nargs="+")
    ap.add_argument("--max", type=int, default=300)
    ap.add_argument("--passphrase", action="store_true")
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()

    password = getpass.getpass(f"Passwort fuer {os.path.basename(args.wallet_file)}: ")
    passphrase = getpass.getpass("BIP-39-Passphrase: ") if args.passphrase else ""

    wm = WalletManager()
    try:
        wm.load(args.wallet_file, password, passphrase)
    except Exception as e:
        print(f"Wallet konnte nicht geladen werden: {e}")
        return 1

    sm = wm.doi.seed_manager
    targets = set(args.address)
    print(f"Wallet: {args.wallet_file}")
    print(f"Erste Empfangsadresse (m/44'/7'/0'/0/0): {sm.get_receive_address(0)}")

    print(f"Standardpfad m/44'/7'/0'/... bis Index {args.max} ...")
    found = scan(sm, targets, (7,), (0,), args.max)
    if len(found) < len(targets) and not args.quick:
        print("Alternative Pfade (Coin-Types 22, 7070, 0, 1 und Accounts 1, 2) ...")
        found.update(scan(sm, targets - set(found), COIN_TYPES, ACCOUNTS, args.max))

    for a in args.address:
        if a in found:
            print(f"  {a}: JA, Pfad {found[a]}")
        else:
            print(f"  {a}: nein (nicht gefunden)")
    wm.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
