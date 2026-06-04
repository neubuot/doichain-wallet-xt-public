"""
Ethereum Netzwerk-Konfiguration
================================

Definiert die Netzwerk-Parameter für Ethereum Mainnet und Testnets.
Enthält auch die wDOI Token-Konfiguration.

© 2026 Ottmar Neuburger, WEBanizer AG
"""

# ──────────────────────────────────────────────
# wDOI Token
# ──────────────────────────────────────────────

WDOI_CONTRACT = "0xA2B6c1a7EFB3dFa75E2d9DF1180b02668c06da72"
WDOI_DECIMALS = 18
WDOI_SYMBOL = "wDOI"

# Standard ERC-20 ABI (nur die Funktionen die wir brauchen)
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "name",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_to", "type": "address"},
            {"name": "_value", "type": "uint256"},
        ],
        "name": "transfer",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"},
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function",
    },
]


# ──────────────────────────────────────────────
# Netzwerk-Definitionen
# ──────────────────────────────────────────────

ETH_MAINNET = {
    "name": "Ethereum Mainnet",
    "chain_id": 1,
    "rpc_urls": [
        "https://eth.llamarpc.com",
        "https://rpc.ankr.com/eth",
        "https://ethereum-rpc.publicnode.com",
        "https://1rpc.io/eth",
    ],
    "explorer": "https://etherscan.io",
    "wdoi_contract": WDOI_CONTRACT,
    "wdoi_decimals": WDOI_DECIMALS,
    "wdoi_symbol": WDOI_SYMBOL,
    "erc20_abi": ERC20_ABI,
    "bip44_coin_type": 60,  # ETH = 60
}

ETH_SEPOLIA = {
    "name": "Ethereum Sepolia Testnet",
    "chain_id": 11155111,
    "rpc_urls": [
        "https://rpc.sepolia.org",
        "https://rpc2.sepolia.org",
        "https://ethereum-sepolia-rpc.publicnode.com",
    ],
    "explorer": "https://sepolia.etherscan.io",
    "wdoi_contract": None,  # Kein wDOI auf Testnet
    "wdoi_decimals": WDOI_DECIMALS,
    "wdoi_symbol": WDOI_SYMBOL,
    "erc20_abi": ERC20_ABI,
    "bip44_coin_type": 60,
}
