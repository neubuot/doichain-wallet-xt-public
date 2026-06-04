from src.wallet.electrumx_client import ElectrumXClient

e = ElectrumXClient()
connected = e.connect()
print(f"ElectrumX connected: {connected}")

# Renes Adresse
addr = "NJBLwnsZ9nAZAzcVmf5naefA9CCJYqhQY2"
print(f"\nAdresse: {addr}")
print(f"History: {e.get_history(addr)}")
print(f"Balance: {e.get_balance(addr)}")

# Deine Adresse
addr2 = "MzdZ49LrAHdewnFb1RD8bpw5iocFKj1iMm"
print(f"\nAdresse: {addr2}")
print(f"History: {e.get_history(addr2)}")
print(f"Balance: {e.get_balance(addr2)}")

e.disconnect()
