from src.wallet.electrumx_client import ElectrumXClient

e = ElectrumXClient()
connected = e.connect()
print(f"ElectrumX connected: {connected}")

# Beispiel-Adresse 1 (Platzhalter – durch eigene Adresse ersetzen)
addr = "N_BEISPIEL_ADRESSE_1_HIER_EINSETZEN"
print(f"\nAdresse: {addr}")
print(f"History: {e.get_history(addr)}")
print(f"Balance: {e.get_balance(addr)}")

# Beispiel-Adresse 2 (Platzhalter – durch eigene Adresse ersetzen)
addr2 = "N_BEISPIEL_ADRESSE_2_HIER_EINSETZEN"
print(f"\nAdresse: {addr2}")
print(f"History: {e.get_history(addr2)}")
print(f"Balance: {e.get_balance(addr2)}")

e.disconnect()
