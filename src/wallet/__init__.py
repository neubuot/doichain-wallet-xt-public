"""
Doichain Wallet Paket.

Hauptkomponenten:
- WalletManager: Einheitlicher Manager für DOI + Tron (TRX/USDT)
- DoiWallet: Vollständiges SPV-Wallet für Doichain
- TronWallet: HD-Wallet für Tron (TRX + USDT TRC-20)
- SeedManager: BIP-39/BIP-32 Schlüsselableitung
- ElectrumXClient: ElectrumX Server-Verbindung
- Transaction: Transaktionserstellung und -signierung
"""

from .wallet_manager import WalletManager
from .doi_wallet import DoiWallet
from .tron_wallet import TronWallet
from .seed_manager import SeedManager
from .electrumx_client import ElectrumXClient
from .transaction import Transaction, UTXO, build_transaction
from .doichain_network import MAINNET, TESTNET, get_network
from .tron_network import TRON_MAINNET, TRON_NILE_TESTNET, TronClient
from .crypto_utils import (
    validate_address,
    pubkey_to_address,
    satoshi_to_doi,
    doi_to_satoshi,
)

__all__ = [
    "WalletManager",
    "DoiWallet",
    "TronWallet",
    "SeedManager",
    "ElectrumXClient",
    "TronClient",
    "Transaction",
    "UTXO",
    "build_transaction",
    "MAINNET",
    "TESTNET",
    "get_network",
    "TRON_MAINNET",
    "TRON_NILE_TESTNET",
    "validate_address",
    "pubkey_to_address",
    "satoshi_to_doi",
    "doi_to_satoshi",
]
