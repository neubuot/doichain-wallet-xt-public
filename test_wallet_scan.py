from src.wallet.wallet_manager import WalletManager
import getpass

pw = getpass.getpass("Wallet-Passwort: ")
wm = WalletManager()
wm.load("wallet.dat", pw)

doi = wm.doi
print(f"Known addresses: {len(doi._known_addresses)}")
for addr, info in doi._known_addresses.items():
    print(f"  {addr} (index={info['index']}, change={info['change']})")

print(f"\nVerbinde...")
wm.connect_doi()
print(f"Nach discover: {len(doi._known_addresses)} Adressen")
for addr, info in doi._known_addresses.items():
    print(f"  {addr} (index={info['index']}, change={info['change']})")

bal = doi.get_balance(force_refresh=True)
print(f"\nBalance: {bal}")
print(f"DOI: {bal['total_doi']}")
