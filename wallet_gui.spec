# -*- mode: python ; coding: utf-8 -*-
"""
DOI-Wallet-iX v0.9 – PyInstaller Build-Konfiguration
======================================================

Build:  pyinstaller wallet_gui.spec --clean --noconfirm
Output: dist/DOI-Wallet-iX.exe

© 2026 Ottmar Neuburger, WEBanizer AG – MIT License
"""

import os
import sys

block_cipher = None
PROJECT_ROOT = os.path.abspath('.')

# ── Daten die eingebunden werden müssen ──
datas = []

# CustomTkinter (Themes, JSON-Dateien, Assets)
import customtkinter
ctk_path = os.path.dirname(customtkinter.__file__)
datas.append((ctk_path, 'customtkinter'))

# Beispiel-Config einbinden (falls vorhanden).
# WICHTIG: NIEMALS die echte config.yaml bundeln – sie enthaelt API-Keys/Secrets!
example_config = os.path.join(PROJECT_ROOT, 'config', 'config.example.yaml')
if os.path.exists(example_config):
    datas.append((example_config, 'config'))

# certifi CA-Zertifikate
import certifi
datas.append((certifi.where(), 'certifi'))

# Mnemonic BIP-39 Wortlisten – die Library laedt sie relativ zu
# os.path.dirname(mnemonic.__file__)/wordlist/<sprache>.txt, im Frozen-Build
# also aus sys._MEIPASS/mnemonic/wordlist. Das Bundling hier genuegt;
# der fruehere Runtime-Hook (rthook_mnemonic.py) setzte ein nicht
# existierendes Attribut (Mnemonic.WORDLIST_DIR) und war ein No-op.
import mnemonic as _mn
import os as _os
_mnpath = _os.path.join(_os.path.dirname(_mn.__file__), 'wordlist')
datas.append((_mnpath, 'mnemonic/wordlist'))

# eth_account braucht seine eigene BIP-39-Wortliste
# (eth_account/hdaccount/wordlist/english.txt) fuer Account.from_mnemonic().
# Ohne sie schlaegt die ETH-Wallet-Initialisierung im Frozen-Build fehl.
from PyInstaller.utils.hooks import collect_data_files, collect_submodules
datas += collect_data_files('eth_account')
datas += collect_data_files('eth_utils')
datas += collect_data_files('eth_typing')

# ── Hidden Imports ──
# PyInstaller erkennt nicht alle dynamischen Imports
hiddenimports = [
    # GUI
    'customtkinter',
    'PIL', 'PIL._tkinter_finder', 'PIL.Image', 'PIL.ImageTk',
    'qrcode', 'qrcode.main', 'qrcode.image.pil',
    'tkinter', 'tkinter.filedialog',

    # Kryptographie
    'hashlib', 'hmac',
    'ecdsa', 'ecdsa.curves', 'ecdsa.keys',
    'mnemonic',
    'Crypto', 'Crypto.Cipher', 'Crypto.Cipher.AES',
    'Crypto.Random', 'Crypto.Util', 'Crypto.Util.Padding',

    # Web3 / Ethereum
    'web3', 'web3.auto', 'web3.middleware',
    'web3.providers', 'web3.providers.rpc',
    'eth_abi', 'eth_abi.abi',
    'eth_utils', 'eth_typing', 'eth_keys', 'eth_rlp',
    'eth_hash', 'eth_hash.auto',
    'eth_keyfile', 'rlp', 'hexbytes', 'bitarray',
    'parsimonious', 'regex', 'pydantic',
    'cytoolz', 'toolz', 'toolz.itertoolz', 'toolz.functoolz',
    'pyunormalize',

    # BIP-Utils (optional, nur wenn installiert)
    # 'bip_utils',

    # Netzwerk
    'requests', 'urllib3', 'certifi',
    'urllib.request', 'ssl', 'socket',

    # Konfiguration
    'yaml',

    # eth_account vollstaendig (inkl. hdaccount-Submodule fuer from_mnemonic)
    *collect_submodules('eth_account'),

    # Interne Module
    'src', 'src.wallet', 'src.exchange',
    'src.wallet.wallet_manager',
    'src.wallet.doi_wallet',
    'src.wallet.tron_wallet',
    'src.wallet.tron_crypto',
    'src.wallet.crypto_utils',
    'src.wallet.eth_wallet',
    'src.wallet.eth_network',
    'src.exchange.xt_client',
]

a = Analysis(
    ['wallet_gui.py'],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy', 'pandas',
        'tkinter.test', 'unittest', 'pytest',
        'IPython', 'notebook', 'jupyter',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DOI-Wallet-iX',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,           # True für Beta (Debug sichtbar!) → False für Release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='assets/doi-wallet.ico',  # Aktivieren wenn Icon vorhanden
)
