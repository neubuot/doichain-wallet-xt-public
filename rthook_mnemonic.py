import os, sys
# Mnemonic Wortlisten-Pfad in PyInstaller setzen
if getattr(sys, 'frozen', False):
    import mnemonic
    bundle_dir = sys._MEIPASS
    wl_path = os.path.join(bundle_dir, 'mnemonic', 'wordlist')
    if os.path.exists(wl_path):
        mnemonic.Mnemonic.WORDLIST_DIR = wl_path
