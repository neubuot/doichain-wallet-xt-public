#!/usr/bin/env python3
"""
DOI-Wallet-iX – Desktop GUI
==================================

Grafische Benutzeroberfläche für das Multi-Chain Wallet (DOI/TRX/USDT/ETH/wDOI)
mit XT.com Exchange-Integration.

© 2026 Ottmar Neuburger, WEBanizer AG
Open Source – MIT License
https://github.com/neubuot/doichain-wallet-xt
"""

import os
import sys
import json
import logging
import threading
import time
from pathlib import Path
from typing import Optional

import customtkinter as ctk

# Zentrales Logging statt print("[DEBUG]...") – Level via config general.log_level
logger = logging.getLogger(__name__)

# QR-Code Support
try:
    import qrcode
    from PIL import Image, ImageTk
    HAS_QR = True
except ImportError:
    HAS_QR = False

# Projektroot
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.wallet.wallet_manager import WalletManager
from src.wallet.tron_crypto import validate_tron_address
from src.wallet.crypto_utils import validate_address as validate_doi_address

# Ethereum-Validierung (optional)
try:
    from src.wallet.eth_wallet import validate_eth_address
    HAS_ETH = True
except ImportError:
    HAS_ETH = False
    validate_eth_address = lambda addr: addr.startswith("0x") and len(addr) == 42

try:
    from src.exchange.xt_client import XTClient
except ImportError:
    XTClient = None


# ──────────────────────────────────────────────
# Konfiguration
# ──────────────────────────────────────────────

APP_NAME = "DOI-Wallet-iX"
APP_VERSION = "0.9.6"
COPYRIGHT = "© 2026 Ottmar Neuburger, WEBanizer AG"
LICENSE_INFO = "Open Source – MIT License"
GITHUB_URL = "https://github.com/neubuot/doichain-wallet-xt"
WALLET_FILE = "wallet.dat"
MAX_WALLET_SLOTS = 10

# Farben (v0.9.5: leicht aufgehellt für moderneren Look, Palette bleibt vertraut)
COLOR_BG = "#1e1e35"           # +Lift gegenüber #1a1a2e
COLOR_SIDEBAR = "#1a2645"      # +Lift gegenüber #16213e
COLOR_CARD = "#243352"         # +Lift gegenüber #1f2b47
COLOR_ACCENT = "#0f969c"
COLOR_ACCENT_HOVER = "#0db8a0"
COLOR_SUCCESS = "#00d26a"
COLOR_WARNING = "#f8d210"
COLOR_ERROR = "#ff4757"
COLOR_TEXT = "#e8e8e8"
COLOR_TEXT_DIM = "#8892a4"
COLOR_DOI = "#f7931a"
COLOR_TRX = "#ff0013"
COLOR_USDT = "#26a17b"
COLOR_ETH = "#627eea"
COLOR_WDOI = "#f7931a"  # Gleich wie DOI, da Wrapped Doichain

# Eckenradien (v0.9.5: durchgehend etwas geschmeidiger)
RADIUS_BUTTON = 10
RADIUS_CARD = 14
RADIUS_DIALOG = 12


def load_config():
    """Lädt config.yaml (fehlertolerant)."""
    try:
        config_path = PROJECT_ROOT / "config" / "config.yaml"
        logger.debug(f"load_config → {config_path} (exists={config_path.exists()})")
        if config_path.exists():
            import yaml
            with open(config_path, "r") as f:
                data = yaml.safe_load(f) or {}
            logger.debug(f"load_config OK, keys={list(data.keys())}")
            return data
    except Exception as e:
        logger.debug(f"load_config FEHLER: {e}")
    return {}


def save_config(config: dict):
    """Speichert config.yaml."""
    try:
        config_dir = PROJECT_ROOT / "config"
        config_dir.mkdir(exist_ok=True)
        config_path = config_dir / "config.yaml"
        logger.debug(f"save_config → {config_path}")
        import yaml
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.debug(f"save_config OK")
        return True
    except Exception as e:
        logger.debug(f"save_config FEHLER: {e}")
        return False


def setup_logging():
    """Konfiguriert das Logging-Level aus config general.log_level (Default: WARNING)."""
    level_name = str(
        load_config().get("general", {}).get("log_level", "WARNING")
    ).upper()
    level = getattr(logging, level_name, logging.WARNING)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


# ──────────────────────────────────────────────
# Eigener Passwort-Dialog (maskiert)
# ──────────────────────────────────────────────

class PasswordConfirmDialog(ctk.CTkToplevel):
    """Passwort-Bestätigungs-Dialog mit maskierter Eingabe."""

    def __init__(self, parent, title: str, message: str):
        super().__init__(parent)
        self.title(title)
        self.geometry("400x200")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self._result = None

        ctk.CTkLabel(
            self, text=message,
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT,
            wraplength=350,
        ).pack(padx=20, pady=(20, 10))

        self._entry = ctk.CTkEntry(
            self, show="●", width=300, height=38,
            font=ctk.CTkFont(size=14),
            placeholder_text="Passwort eingeben...",
        )
        self._entry.pack(padx=20)
        self._entry.bind("<Return>", lambda e: self._confirm())

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=15)

        ctk.CTkButton(
            btn_frame, text="Bestätigen", height=35, width=120,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._confirm,
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            btn_frame, text="Abbrechen", height=35, width=120,
            fg_color=COLOR_CARD, hover_color="#2a3a5c",
            command=self._cancel,
        ).pack(side="left", padx=5)

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(100, self._entry.focus_set)

    def _confirm(self):
        self._result = self._entry.get()
        self.destroy()

    def _cancel(self):
        self._result = None
        self.destroy()

    def get_input(self):
        self.wait_window()
        return self._result


# ──────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────

def format_doi(amount):
    return f"{amount:.8f}"

def format_trx(amount):
    return f"{amount:.6f}"

def format_usdt(amount):
    return f"{amount:.2f}"

def format_eth(amount):
    return f"{amount:.6f}"

def format_wdoi(amount):
    return f"{amount:.4f}"

def shorten_addr(addr, n=8):
    if len(addr) <= n * 2 + 3:
        return addr
    return f"{addr[:n]}...{addr[-n:]}"


# ──────────────────────────────────────────────
# Startup Dialog
# ──────────────────────────────────────────────

class StartupDialog(ctk.CTkToplevel):
    """Dialog zum Erstellen/Wiederherstellen/Laden eines Wallets."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title(f"{APP_NAME} – Start")
        self.geometry("520x750")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        self.result = None  # ("create"|"restore"|"load", data)

        # Header
        ctk.CTkLabel(
            self, text="🔗 DOI-Wallet-iX",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color=COLOR_ACCENT,
        ).pack(pady=(30, 5))

        ctk.CTkLabel(
            self, text="Multi-Chain Wallet · DOI · TRX · USDT · ETH · wDOI",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 25))

        # Buttons
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=50)

        # Wallet.dat auto-detect
        wallet_exists = Path(WALLET_FILE).exists()

        if wallet_exists:
            ctk.CTkButton(
                btn_frame,
                text="🔓  Wallet öffnen (wallet.dat)",
                font=ctk.CTkFont(size=16, weight="bold"),
                height=50,
                fg_color=COLOR_ACCENT,
                hover_color=COLOR_ACCENT_HOVER,
                command=self._load_existing,
            ).pack(fill="x", pady=(0, 12))

        ctk.CTkButton(
            btn_frame,
            text="✨  Neues Wallet erstellen",
            font=ctk.CTkFont(size=15),
            height=45,
            fg_color=COLOR_CARD,
            hover_color="#2a3a5c",
            border_width=1,
            border_color=COLOR_ACCENT,
            command=self._create_new,
        ).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="📥  Wallet wiederherstellen (Seed)",
            font=ctk.CTkFont(size=15),
            height=45,
            fg_color=COLOR_CARD,
            hover_color="#2a3a5c",
            border_width=1,
            border_color=COLOR_ACCENT,
            command=self._restore_seed,
        ).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            btn_frame,
            text="📂  Andere Datei laden...",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color="transparent",
            hover_color="#2a3a5c",
            text_color=COLOR_TEXT_DIM,
            command=self._load_file,
        ).pack(fill="x", pady=(0, 10))

        # Footer
        ctk.CTkLabel(
            self, text=f"{COPYRIGHT}\n{LICENSE_INFO}",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_DIM,
        ).pack(side="bottom", pady=5)

        # Passwort-Eingabefeld (versteckt, wird bei Bedarf angezeigt)
        self._pw_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._pw_label = ctk.CTkLabel(
            self._pw_frame, text="", font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT,
        )
        self._pw_label.pack(pady=(5, 5))
        self._pw_entry = ctk.CTkEntry(
            self._pw_frame, show="●", width=300, height=38,
            font=ctk.CTkFont(size=14),
            placeholder_text="Passwort (min. 8 Zeichen)",
        )
        self._pw_entry.pack(pady=(0, 5))
        self._pw_entry.bind("<Return>", lambda e: self._pw_confirm())
        self._pw_confirm_btn = ctk.CTkButton(
            self._pw_frame, text="Bestätigen", height=35,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._pw_confirm,
        )
        self._pw_confirm_btn.pack(pady=(0, 5))
        self._pw_error = ctk.CTkLabel(
            self._pw_frame, text="", font=ctk.CTkFont(size=12),
            text_color=COLOR_ERROR,
        )
        self._pw_error.pack()

        # Seed-Eingabe (versteckt)
        self._seed_frame = ctk.CTkFrame(self, fg_color="transparent")
        ctk.CTkLabel(
            self._seed_frame, text="24-Wort Seed-Phrase eingeben:",
            font=ctk.CTkFont(size=13), text_color=COLOR_TEXT,
        ).pack(pady=(5, 5))
        self._seed_entry = ctk.CTkTextbox(
            self._seed_frame, width=380, height=80,
            font=ctk.CTkFont(size=13),
        )
        self._seed_entry.pack(pady=(0, 5))

        self._pending_action = None
        self._pending_path = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._pw_entry.focus_set)

    def _show_password(self, action, label_text, path=None):
        """Zeigt das Passwort-Feld an."""
        self._pending_action = action
        self._pending_path = path
        self._pw_label.configure(text=label_text)
        self._pw_error.configure(text="")
        self._pw_entry.delete(0, "end")

        if action == "restore":
            self._seed_frame.pack(fill="x", padx=50)
        else:
            self._seed_frame.pack_forget()

        self._pw_frame.pack(fill="x", padx=50)
        self._pw_entry.focus_set()

    def _pw_confirm(self):
        """Passwort bestätigen und Aktion ausführen."""
        password = self._pw_entry.get()
        if len(password) < 8:
            self._pw_error.configure(text="Passwort muss min. 8 Zeichen haben!")
            return

        if self._pending_action == "create":
            self.result = ("create", {"password": password})
        elif self._pending_action == "restore":
            seed = self._seed_entry.get("1.0", "end").strip()
            words = seed.split()
            if len(words) not in (12, 18, 24):
                self._pw_error.configure(text="Seed muss 12, 18 oder 24 Wörter haben!")
                return
            self.result = ("restore", {"password": password, "mnemonic": seed})
        elif self._pending_action == "load":
            self.result = ("load", {"password": password, "path": self._pending_path})

        self.destroy()

    def _create_new(self):
        self._show_password("create", "Passwort für das neue Wallet:")

    def _restore_seed(self):
        self._show_password("restore", "Passwort für das wiederhergestellte Wallet:")

    def _load_existing(self):
        self._show_password("load", f"Passwort für {WALLET_FILE}:", WALLET_FILE)

    def _load_file(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Wallet-Datei auswählen",
            filetypes=[("Wallet", "*.dat *.wallet"), ("Alle", "*.*")],
        )
        if path:
            self._show_password("load", f"Passwort für {Path(path).name}:", path)

    def _on_close(self):
        self.result = None
        self.destroy()


# ──────────────────────────────────────────────
# Seed-Anzeige Dialog
# ──────────────────────────────────────────────

class SeedDialog(ctk.CTkToplevel):
    """Zeigt die Seed-Phrase nach dem Erstellen an."""

    def __init__(self, parent, mnemonic: str):
        super().__init__(parent)
        self.title("⚠️ Seed-Phrase sichern!")
        self.geometry("550x480")
        self.resizable(False, False)
        self.configure(fg_color=COLOR_BG)
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(
            self, text="⚠️  Seed-Phrase sichern!",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_WARNING,
        ).pack(pady=(25, 10))

        ctk.CTkLabel(
            self, text="Schreibe diese 24 Wörter auf und bewahre sie sicher auf.\n"
                       "Sie sind der einzige Weg, dein Wallet wiederherzustellen!",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT,
            wraplength=450,
        ).pack(pady=(0, 15))

        # Seed Wörter als Grid
        words = mnemonic.split()
        seed_frame = ctk.CTkFrame(self, fg_color=COLOR_CARD, corner_radius=12)
        seed_frame.pack(padx=30, fill="x")

        for i, word in enumerate(words):
            row, col = divmod(i, 4)
            label = ctk.CTkLabel(
                seed_frame,
                text=f"{i+1:2d}. {word}",
                font=ctk.CTkFont(family="Consolas", size=14),
                text_color=COLOR_TEXT,
                anchor="w",
            )
            label.grid(row=row, column=col, padx=12, pady=4, sticky="w")

        seed_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            self,
            text="❌ Niemals digital speichern oder teilen!",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLOR_ERROR,
        ).pack(pady=(15, 10))

        ctk.CTkButton(
            self, text="✅  Ich habe die Seed-Phrase gesichert",
            height=42, font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self.destroy,
        ).pack(pady=(5, 20))

        self.protocol("WM_DELETE_WINDOW", self.destroy)


# ──────────────────────────────────────────────
# Hauptfenster
# ──────────────────────────────────────────────

class WalletApp(ctk.CTk):
    """Hauptfenster der Wallet-Anwendung."""

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("900x680")
        self.minsize(800, 620)
        self.configure(fg_color=COLOR_BG)

        self.wm: Optional[WalletManager] = None
        self.xt: Optional[XTClient] = None
        self._balances = {"doi": 0, "trx": 0, "usdt": 0, "eth": 0, "wdoi": 0}
        self._doi_connected = False
        self._price_doi = 0.0

        # Multi-Wallet Slots
        self._wallet_slots = []
        for i in range(MAX_WALLET_SLOTS):
            self._wallet_slots.append({
                "name": f"Wallet-{i+1}",
                "wm": None,
                "xt": None,
                "balances": {"doi": 0, "trx": 0, "usdt": 0, "eth": 0, "wdoi": 0},
                "doi_connected": False,
                "price_doi": 0.0,
                "dat_file": None,
                "loaded": False, "was_loaded": False, "hist_data": {},
            })
        self._active_slot = 0
        self._tab_scroll_offset = 0
        self._block_heights = {"doi": 0, "eth": 0}  # Aktuelle Block-Hoehen

        # v0.9.6: Auto-Refresh-Timer fuer die TX-Liste (60s, nur waehrend
        # der "history"-Tab sichtbar ist)
        self._current_page: str = "dashboard"
        self._history_autorefresh_id = None
        self.HISTORY_AUTOREFRESH_MS = 60_000  # 60 Sekunden

        # Generationszaehler gegen ueberlappende History-Refreshes:
        # nur das Ergebnis der juengsten Generation wird uebernommen.
        self._hist_gen = 0
        self._hist_loading = False

        # In-Memory-Cache fuer geladene Roh-Transaktionen (txid → verbose dict).
        # Bestaetigte TXs sind unveraenderlich, daher chain-global cachebar –
        # spart beim 60s-Auto-Refresh dutzende ElectrumX-Roundtrips.
        self._tx_cache = {}

        # Sauberes Beenden: Worker duerfen nach Fenster-Schliessen kein
        # self.after() mehr aufrufen; laufende Sends werden abgefragt.
        self._closing = False
        self._send_in_progress = False

        # Verzoegerter Einzelklick auf Wallet-Tabs (Doppelklick = Umbenennen)
        self._tab_click_after_id = None

        # Killer Features
        self._tx_notes = {}       # {tx_hash: "notiz"}
        self._daily_limit_eur = 0  # 0 = kein Limit
        self._undo_seconds = 0     # 0 = sofort senden
        self._daily_sends = {}     # {datum: betrag_eur}
        self._load_tx_notes()
        self._load_safety_settings()

        # Layout
        self._build_sidebar()
        self._build_content_area()
        self._build_wallet_tabs()
        self._build_footer()

        # Seiten
        self._pages = {}
        self._create_pages()
        self._show_page("dashboard")

        # Startup
        self.after(200, self._startup)

    # ──────────────────────────────────────
    # Layout
    # ──────────────────────────────────────

    def _build_sidebar(self):
        """Sidebar mit Navigation."""
        self.sidebar = ctk.CTkFrame(self, width=200, fg_color=COLOR_SIDEBAR, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Logo
        ctk.CTkLabel(
            self.sidebar, text="🔗",
            font=ctk.CTkFont(size=36),
        ).pack(pady=(20, 2))
        ctk.CTkLabel(
            self.sidebar, text="Doichain",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_ACCENT,
        ).pack()
        ctk.CTkLabel(
            self.sidebar, text=f"Wallet-iX  v{APP_VERSION}",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 4))
        ctk.CTkLabel(
            self.sidebar, text="⚠ Beta – nur kleine Beträge!",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_WARNING,
        ).pack(pady=(0, 16))

        # Nav-Buttons
        self._nav_buttons = {}
        nav_items = [
            ("dashboard", "📊  Dashboard"),
            ("send", "📤  Senden"),
            ("receive", "📥  Empfangen"),
            ("history", "📜  Transaktionen"),
            ("exchange", "📈  Exchange"),
            ("settings", "⚙️  Einstellungen"),
        ]

        for page_id, label in nav_items:
            btn = ctk.CTkButton(
                self.sidebar, text=label,
                font=ctk.CTkFont(size=14),
                height=40, anchor="w",
                fg_color="transparent",
                hover_color="#283e60",
                text_color=COLOR_TEXT,
                corner_radius=RADIUS_BUTTON,
                command=lambda p=page_id: self._show_page(p),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._nav_buttons[page_id] = btn

        # Schliessen-Button ganz unten
        ctk.CTkButton(
            self.sidebar, text="🚪  Beenden",
            font=ctk.CTkFont(size=14),
            height=40, anchor="w",
            fg_color="transparent",
            hover_color="#5c1a1a",
            text_color=COLOR_TEXT_DIM,
            corner_radius=RADIUS_BUTTON,
            command=self._on_close,
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 10))

        # Info-Button direkt darüber – öffnet Dialog, keine Seitennavigation
        ctk.CTkButton(
            self.sidebar, text="ℹ️  Info",
            font=ctk.CTkFont(size=14),
            height=40, anchor="w",
            fg_color="transparent",
            hover_color="#283e60",
            text_color=COLOR_TEXT_DIM,
            corner_radius=RADIUS_BUTTON,
            command=self._show_info_dialog,
        ).pack(side="bottom", fill="x", padx=10, pady=(0, 2))

    def _build_content_area(self):
        """Hauptinhalt mit Platz fuer Tab-Leiste."""
        self._right_panel = ctk.CTkFrame(self, fg_color="transparent")
        self._right_panel.pack(side="left", fill="both", expand=True, padx=0, pady=0)

        # Content-Bereich (unterhalb der Tabs)
        self.content = ctk.CTkFrame(self._right_panel, fg_color="transparent")
        self.content.pack(side="top", fill="both", expand=True, padx=0, pady=0)

    def _build_footer(self):
        """Statusleiste."""
        self.footer = ctk.CTkFrame(self.content, height=28, fg_color=COLOR_SIDEBAR, corner_radius=0)
        self.footer.pack(side="bottom", fill="x")
        self.footer.pack_propagate(False)

        self.status_label = ctk.CTkLabel(
            self.footer, text=f"{COPYRIGHT} · {LICENSE_INFO}",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_DIM,
        )
        self.status_label.pack(side="left", padx=10)

        self.conn_label = ctk.CTkLabel(
            self.footer, text="⏳ Verbinde...",
            font=ctk.CTkFont(size=10),
            text_color=COLOR_TEXT_DIM,
        )
        self.conn_label.pack(side="right", padx=10)


    def _build_wallet_tabs(self):
        """Horizontale Wallet-Tab-Leiste mit Scroll-Pfeilen."""
        self._tab_bar = ctk.CTkFrame(
            self._right_panel, height=36, fg_color="#0d1527", corner_radius=0
        )
        self._tab_bar.pack(side="top", fill="x", before=self.content)
        self._tab_bar.pack_propagate(False)

        # Scroll-Pfeil links
        self._tab_left_btn = ctk.CTkButton(
            self._tab_bar, text="◀", width=28, height=28,
            fg_color="transparent", hover_color="#1e3050",
            text_color=COLOR_TEXT_DIM,
            font=ctk.CTkFont(size=14),
            command=lambda: self._scroll_tabs(-1),
        )
        self._tab_left_btn.pack(side="left", padx=(4, 0))

        # Container fuer Tabs (scrollbar)
        self._tab_container = ctk.CTkFrame(
            self._tab_bar, fg_color="transparent", height=32
        )
        self._tab_container.pack(side="left", fill="x", expand=True, padx=2)

        # Scroll-Pfeil rechts
        self._tab_right_btn = ctk.CTkButton(
            self._tab_bar, text="▶", width=28, height=28,
            fg_color="transparent", hover_color="#1e3050",
            text_color=COLOR_TEXT_DIM,
            font=ctk.CTkFont(size=14),
            command=lambda: self._scroll_tabs(1),
        )
        self._tab_right_btn.pack(side="right", padx=(0, 4))

        # Tab-Buttons erstellen
        self._tab_buttons = []
        for i in range(MAX_WALLET_SLOTS):
            btn = ctk.CTkButton(
                self._tab_container,
                text=self._wallet_slots[i]["name"],
                width=90, height=28,
                font=ctk.CTkFont(size=11),
                fg_color="transparent" if i != 0 else COLOR_ACCENT,
                hover_color="#1e3050",
                text_color=COLOR_TEXT_DIM if i != 0 else "white",
                corner_radius=4,
                command=lambda idx=i: self._on_tab_click(idx),
            )
            btn.bind("<Double-Button-1>", lambda e, idx=i: self._rename_tab(idx))
            self._tab_buttons.append(btn)

        self._render_visible_tabs()

    def _render_visible_tabs(self):
        """Zeigt die sichtbaren Tabs basierend auf Scroll-Offset."""
        for btn in self._tab_buttons:
            btn.pack_forget()

        # Berechne wie viele Tabs sichtbar sind (ca. 96px pro Tab)
        try:
            container_width = self._tab_container.winfo_width()
            if container_width < 50:
                container_width = 600  # Fallback beim Start
        except Exception:
            container_width = 600

        visible_count = max(3, container_width // 96)
        start = self._tab_scroll_offset
        end = min(start + visible_count, MAX_WALLET_SLOTS)

        for i in range(start, end):
            self._tab_buttons[i].pack(side="left", padx=2, pady=2)

        # Scroll-Pfeile ein/ausblenden
        self._tab_left_btn.configure(
            text_color=COLOR_TEXT if start > 0 else "#2a2a3e"
        )
        self._tab_right_btn.configure(
            text_color=COLOR_TEXT if end < MAX_WALLET_SLOTS else "#2a2a3e"
        )

    def _scroll_tabs(self, direction):
        """Scrollt die Tab-Leiste links/rechts."""
        new_offset = self._tab_scroll_offset + direction
        if 0 <= new_offset < MAX_WALLET_SLOTS - 2:
            self._tab_scroll_offset = new_offset
            self._render_visible_tabs()

    def _safe_after(self, ms, callback):
        """
        after()-Wrapper fuer Hintergrund-Threads: waehrend des Beendens
        (self._closing) werden Callbacks verworfen, damit kein Worker mehr
        auf zerstoerte Tk-Widgets zugreift.
        """
        if self._closing:
            return None
        try:
            return self.after(ms, callback)
        except Exception:
            return None

    def _cancel_pending_tab_click(self):
        """Storniert einen anstehenden (verzoegerten) Einzelklick auf einen Tab."""
        if self._tab_click_after_id is not None:
            try:
                self.after_cancel(self._tab_click_after_id)
            except Exception:
                pass
            self._tab_click_after_id = None

    def _on_tab_click(self, index):
        """
        Klick auf einen Wallet-Tab.

        Der eigentliche Wechsel wird ~250 ms verzoegert ausgefuehrt, damit ein
        Doppelklick (Umbenennen) den Einzelklick stornieren kann – sonst
        oeffnet ein Doppelklick auf einen leeren Slot faelschlich den
        StartupDialog.
        """
        self._cancel_pending_tab_click()
        self._tab_click_after_id = self.after(
            250, lambda idx=index: self._do_tab_click(idx))

    def _do_tab_click(self, index):
        """Fuehrt den (ggf. verzoegerten) Tab-Wechsel aus."""
        self._tab_click_after_id = None
        if index == self._active_slot:
            return

        slot = self._wallet_slots[index]
        if not slot["loaded"]:
            # Neues Wallet fuer diesen Slot erstellen/laden
            self._open_wallet_for_slot(index)
            return

        # Aktuellen Slot-State speichern
        self._save_slot_state(self._active_slot)

        # Neuen Slot aktivieren
        self._active_slot = index
        self._restore_slot_state(index)

        # UI aktualisieren
        self._update_tab_buttons()
        self._update_addresses()
        self._update_receive_page()
        self._refresh_dashboard()
        # v0.9.6: bei Slot-Wechsel auch History neu laden, sonst sieht der User
        # einen alten Snapshot des neuen Slots (z.B. ohne die soeben getaetigte Tx).
        if getattr(self, "_current_page", None) == "history":
            self._refresh_history_async(force=True)

    def _save_slot_state(self, index):
        """Speichert den aktuellen State in einen Slot."""
        slot = self._wallet_slots[index]
        slot["wm"] = self.wm
        slot["xt"] = self.xt
        slot["balances"] = self._balances.copy()
        slot["doi_connected"] = self._doi_connected
        slot["price_doi"] = self._price_doi
        slot["hist_data"] = self._hist_data.copy() if self._hist_data else {}

    def _restore_slot_state(self, index):
        """Stellt den State eines Slots wieder her."""
        slot = self._wallet_slots[index]
        self.wm = slot["wm"]
        self.xt = slot["xt"]
        self._balances = slot["balances"].copy()
        self._doi_connected = slot["doi_connected"]
        self._price_doi = slot["price_doi"]
        self._hist_data = slot.get("hist_data", {}).copy()

        # Verbindungsstatus aktualisieren
        self.after(0, lambda: self.conn_label.configure(
            text=self._get_conn_text(), text_color=COLOR_TEXT_DIM))

    def _update_tab_buttons(self):
        """Aktualisiert die Tab-Button-Farben."""
        for i, btn in enumerate(self._tab_buttons):
            slot = self._wallet_slots[i]
            if i == self._active_slot:
                btn.configure(fg_color=COLOR_ACCENT, text_color="white")
            elif slot["loaded"]:
                btn.configure(fg_color="#1e3050", text_color=COLOR_TEXT)
            else:
                btn.configure(fg_color="transparent", text_color=COLOR_TEXT_DIM)

    def _open_wallet_for_slot(self, index):
        """Oeffnet den StartupDialog fuer einen bestimmten Slot."""
        dialog = StartupDialog(self)
        self.wait_window(dialog)

        if dialog.result is None:
            return

        # Aktuellen State speichern bevor wir wechseln
        if self._wallet_slots[self._active_slot]["loaded"]:
            self._save_slot_state(self._active_slot)

        action, data = dialog.result
        config = load_config()
        tron_api_key = config.get("tron", {}).get("api_key", "")

        try:
            wm = WalletManager(tron_api_key=tron_api_key)

            if action == "create":
                mnemonic = wm.create(data["password"])
                dat_file = f"wallet-{index+1}.dat"
                wm.save(dat_file)
                seed_dlg = SeedDialog(self, mnemonic)
                self.wait_window(seed_dlg)
            elif action == "restore":
                wm.restore(data["mnemonic"], data["password"])
                dat_file = f"wallet-{index+1}.dat"
                wm.save(dat_file)
            elif action == "load":
                wm.load(data["path"], data["password"])
                dat_file = data["path"]

        except Exception as e:
            self._show_error(f"Wallet-Fehler: {e}")
            return

        # Slot konfigurieren
        slot = self._wallet_slots[index]
        slot["wm"] = wm
        slot["dat_file"] = dat_file
        slot["loaded"] = True
        slot["balances"] = {"doi": 0, "trx": 0, "usdt": 0, "eth": 0, "wdoi": 0}
        slot["doi_connected"] = False
        slot["price_doi"] = 0.0

        # XT.com Client
        if XTClient:
            xt_conf = config.get("xt_com", {})
            slot["xt"] = XTClient(
                api_key=xt_conf.get("api_key", ""),
                api_secret=xt_conf.get("api_secret", ""),
            )

        # Aktivieren
        self._active_slot = index
        self._restore_slot_state(index)
        self._update_tab_buttons()
        self._save_tab_config()
        self._update_addresses()
        self._update_receive_page()

        # Verbindungen im Hintergrund
        threading.Thread(target=self._connect_and_refresh, daemon=True).start()

    def _rename_tab(self, index):
        """Doppelklick auf Tab: Name aendern."""
        # Anstehenden Einzelklick stornieren – Doppelklick hat Vorrang
        self._cancel_pending_tab_click()
        dialog = ctk.CTkToplevel(self)
        dialog.title("Tab umbenennen")
        dialog.geometry("300x140")
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Neuer Name:",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT,
        ).pack(pady=(15, 5))

        name_entry = ctk.CTkEntry(
            dialog, width=220, height=35,
            font=ctk.CTkFont(size=13),
        )
        name_entry.pack(pady=5)
        name_entry.insert(0, self._wallet_slots[index]["name"])
        name_entry.select_range(0, "end")

        def confirm(event=None):
            new_name = name_entry.get().strip()
            if new_name:
                self._wallet_slots[index]["name"] = new_name
                self._tab_buttons[index].configure(text=new_name)
                self._save_tab_config()
            dialog.destroy()

        name_entry.bind("<Return>", confirm)
        ctk.CTkButton(
            dialog, text="OK", height=32,
            fg_color=COLOR_ACCENT,
            command=confirm,
        ).pack(pady=10)

        dialog.after(100, name_entry.focus_set)

    def _save_tab_config(self):
        """Speichert Tab-Namen und Zuordnungen in tab_config.json."""
        cfg = []
        for i, slot in enumerate(self._wallet_slots):
            cfg.append({
                "name": slot["name"],
                "dat_file": slot["dat_file"],
                "was_loaded": slot["loaded"],
            })
        try:
            with open("tab_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_tab_config(self):
        """Laedt Tab-Namen und Zuordnungen aus tab_config.json."""
        try:
            if os.path.exists("tab_config.json"):
                with open("tab_config.json", "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                for i, entry in enumerate(cfg):
                    if i < MAX_WALLET_SLOTS:
                        self._wallet_slots[i]["name"] = entry.get("name", f"Wallet-{i+1}")
                        self._wallet_slots[i]["dat_file"] = entry.get("dat_file")
                        self._wallet_slots[i]["was_loaded"] = entry.get("was_loaded", False)
                        self._tab_buttons[i].configure(text=self._wallet_slots[i]["name"])
        except Exception:
            pass

    def _load_tx_notes(self):
        """Laedt Transaktions-Notizen aus tx_notes.json."""
        try:
            if os.path.exists("tx_notes.json"):
                with open("tx_notes.json", "r", encoding="utf-8") as f:
                    self._tx_notes = json.load(f)
        except Exception:
            self._tx_notes = {}

    def _save_tx_notes(self):
        """Speichert Transaktions-Notizen in tx_notes.json."""
        try:
            with open("tx_notes.json", "w", encoding="utf-8") as f:
                json.dump(self._tx_notes, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def _load_safety_settings(self):
        """Laedt Tageslimit und Undo-Timer aus config."""
        config = load_config()
        safety = config.get("safety", {})
        self._daily_limit_eur = safety.get("daily_limit_eur", 0)
        self._undo_seconds = safety.get("undo_seconds", 0)
        # Tagesumsaetze laden
        try:
            if os.path.exists("daily_sends.json"):
                with open("daily_sends.json", "r", encoding="utf-8") as f:
                    self._daily_sends = json.load(f)
        except Exception:
            self._daily_sends = {}

    def _save_safety_settings(self):
        """Speichert Tageslimit und Undo-Timer in config."""
        config = load_config()
        config["safety"] = {
            "daily_limit_eur": self._daily_limit_eur,
            "undo_seconds": self._undo_seconds,
        }
        save_config(config)

    def _save_daily_sends(self):
        """Speichert Tagesumsaetze."""
        try:
            with open("daily_sends.json", "w", encoding="utf-8") as f:
                json.dump(self._daily_sends, f, indent=2)
        except Exception:
            pass

    def _get_today_sent_eur(self):
        """Gibt den heutigen Gesamtbetrag in EUR zurueck."""
        from datetime import date
        today = date.today().isoformat()
        return self._daily_sends.get(today, 0.0)

    def _add_daily_send(self, amount_eur):
        """Fuegt einen Betrag zum heutigen Tagesumsatz hinzu."""
        from datetime import date
        today = date.today().isoformat()
        self._daily_sends[today] = self._daily_sends.get(today, 0.0) + amount_eur
        self._save_daily_sends()

    def _edit_tx_note(self, tx_hash):
        """Dialog zum Bearbeiten einer Transaktions-Notiz."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Notiz bearbeiten")
        dialog.geometry("420x180")
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="Notiz fuer diese Transaktion:",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_TEXT,
        ).pack(pady=(15, 5))

        ctk.CTkLabel(
            dialog, text=f"TX: {shorten_addr(tx_hash, 12)}",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 8))

        note_entry = ctk.CTkEntry(
            dialog, width=350, height=35,
            font=ctk.CTkFont(size=13),
            placeholder_text="z.B. Bezahlung fuer Website...",
        )
        note_entry.pack(pady=5)
        existing = self._tx_notes.get(tx_hash, "")
        if existing:
            note_entry.insert(0, existing)
            note_entry.select_range(0, "end")

        def save(event=None):
            note = note_entry.get().strip()
            if note:
                self._tx_notes[tx_hash] = note
            elif tx_hash in self._tx_notes:
                del self._tx_notes[tx_hash]
            self._save_tx_notes()
            dialog.destroy()
            # History neu rendern um Notiz anzuzeigen
            self._render_history()

        note_entry.bind("<Return>", save)
        ctk.CTkButton(
            dialog, text="Speichern", height=32,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=save,
        ).pack(pady=8)

        dialog.after(100, note_entry.focus_set)

    def _show_page(self, page_id):
        """Zeigt eine Seite an."""
        for pid, btn in self._nav_buttons.items():
            if pid == page_id:
                btn.configure(fg_color=COLOR_ACCENT, text_color="white")
            else:
                btn.configure(fg_color="transparent", text_color=COLOR_TEXT)

        for pid, frame in self._pages.items():
            if pid == page_id:
                frame.pack(fill="both", expand=True, padx=15, pady=(10, 0))
            else:
                frame.pack_forget()

        # v0.9.6: aktuellen Page-Namen merken (fuer Auto-Refresh-Timer)
        self._current_page = page_id

        # Refresh bei Seitenwechsel
        if page_id == "dashboard":
            # Cache-Hygiene: alte Mempool-Eintraege koennen inzwischen bestaetigt
            # oder evictet sein – Dashboard frisch validieren bevor Salden angezeigt
            self._validate_unconfirmed_async()
            self._refresh_dashboard()
        elif page_id == "exchange":
            self._refresh_exchange()
        elif page_id == "receive":
            # v0.9.6: jeder Tab-Aufruf erzeugt eine neue DOI-Empfangsadresse
            self._update_receive_page(generate_new=True)
        elif page_id == "history":
            # v0.9.6: jeder Tab-Aufruf triggert frischen Fetch (war: nur bei leerem Cache)
            self._refresh_history_async()

        # v0.9.6: Auto-Refresh nur waehrend "history" sichtbar
        self._tick_history_autorefresh()

    def _tick_history_autorefresh(self):
        """
        Startet/stoppt den 60-Sekunden-Auto-Refresh der TX-Liste in Abhaengigkeit
        davon, ob der "history"-Tab gerade aktiv ist. Wird bei jedem Page-Wechsel
        aufgerufen und nach jeder eigenen Iteration via self.after() erneut.
        """
        # Alten geplanten Aufruf aufraeumen
        if self._history_autorefresh_id is not None:
            try:
                self.after_cancel(self._history_autorefresh_id)
            except Exception:
                pass
            self._history_autorefresh_id = None

        # Nur weiterticken, wenn wir auf dem history-Tab sind
        if self._current_page != "history":
            return

        def _tick():
            self._history_autorefresh_id = None
            if self._current_page != "history":
                return  # User hat inzwischen gewechselt
            try:
                self._refresh_history_async()
            except Exception:
                pass
            # Neu schedulen
            self._tick_history_autorefresh()

        self._history_autorefresh_id = self.after(self.HISTORY_AUTOREFRESH_MS, _tick)

    def _validate_unconfirmed_async(self):
        """
        Stoesst eine Validierung der gecachten unconfirmed-Salden im Hintergrund an.

        Stille Operation – kein UI-Feedback, ausser die Dashboard-Werte aktualisieren
        sich kurz nach Tab-Wechsel auf 'dashboard' selbsttaetig.
        """
        if not self.wm or not self.wm.doi:
            return

        def _do():
            try:
                result = self.wm.doi.validate_unconfirmed()
                if result.get("invalidated", 0) > 0:
                    # Dashboard nach Cache-Update neu rendern
                    self.after(0, self._refresh_dashboard)
            except Exception:
                pass

        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────
    # Seiten erstellen
    # ──────────────────────────────────────

    def _create_pages(self):
        self._create_dashboard_page()
        self._create_send_page()
        self._create_receive_page()
        self._create_history_page()
        self._create_exchange_page()
        self._create_settings_page()

    # ── Dashboard ──

    def _create_dashboard_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self._pages["dashboard"] = page

        ctk.CTkLabel(
            page, text="Dashboard",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", pady=(5, 10))

        # Balance Cards
        cards = ctk.CTkFrame(page, fg_color="transparent")
        cards.pack(fill="x")
        cards.grid_columnconfigure((0, 1, 2), weight=1, uniform="col")

        self._doi_card = self._make_balance_card(cards, "DOI", "0.00000000", COLOR_DOI, 0, 0)
        self._trx_card = self._make_balance_card(cards, "TRX", "0.000000", COLOR_TRX, 0, 1)
        self._usdt_card = self._make_balance_card(cards, "USDT", "0.00", COLOR_USDT, 0, 2)
        self._eth_card = self._make_balance_card(cards, "ETH", "0.000000", COLOR_ETH, 1, 0)
        self._wdoi_card = self._make_balance_card(cards, "wDOI", "0.0000", COLOR_WDOI, 1, 1)

        # Adressen
        addr_frame = ctk.CTkFrame(page, fg_color=COLOR_CARD, corner_radius=10)
        addr_frame.pack(fill="x", pady=(12, 0))

        ctk.CTkLabel(
            addr_frame, text="Adressen",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        self._addr_doi_label = ctk.CTkLabel(
            addr_frame, text="DOI:   –",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self._addr_doi_label.pack(fill="x", padx=15, pady=1)

        self._addr_tron_label = ctk.CTkLabel(
            addr_frame, text="Tron:  –",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self._addr_tron_label.pack(fill="x", padx=15, pady=1)

        self._addr_eth_label = ctk.CTkLabel(
            addr_frame, text="ETH:   –",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self._addr_eth_label.pack(fill="x", padx=15, pady=(1, 10))

        # Refresh Button
        ctk.CTkButton(
            page, text="🔄  Aktualisieren",
            font=ctk.CTkFont(size=13),
            height=35, width=160,
            fg_color=COLOR_CARD, hover_color="#2a3a5c",
            border_width=1, border_color=COLOR_ACCENT,
            command=self._refresh_balances_async,
        ).pack(pady=(12, 0))

        # DOI Preis
        self._price_label = ctk.CTkLabel(
            page, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        )
        self._price_label.pack(pady=(8, 0))

    def _make_balance_card(self, parent, name, value, color, row, col):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=10, height=100)
        card.grid(row=row, column=col, padx=5, pady=(0, 5), sticky="nsew")
        card.grid_propagate(False)

        ctk.CTkLabel(
            card, text=name,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=color,
        ).pack(anchor="w", padx=15, pady=(12, 0))

        val_label = ctk.CTkLabel(
            card, text=value,
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=COLOR_TEXT,
        )
        val_label.pack(anchor="w", padx=15, pady=(2, 0))

        return val_label

    # ── Senden ──

    def _create_send_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self._pages["send"] = page

        ctk.CTkLabel(
            page, text="Senden",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", pady=(5, 10))

        # Chain-Auswahl
        chain_frame = ctk.CTkFrame(page, fg_color="transparent")
        chain_frame.pack(fill="x", pady=(0, 10))

        self._send_chain = ctk.CTkSegmentedButton(
            chain_frame,
            values=["DOI", "TRX", "USDT", "ETH", "wDOI"],
            font=ctk.CTkFont(size=14),
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            command=self._on_chain_select,
        )
        self._send_chain.set("DOI")
        self._send_chain.pack(fill="x")

        # Formular
        form = ctk.CTkFrame(page, fg_color=COLOR_CARD, corner_radius=10)
        form.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            form, text="Empfänger-Adresse:",
            font=ctk.CTkFont(size=13), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(12, 3))

        self._send_addr = ctk.CTkEntry(
            form, height=38, font=ctk.CTkFont(size=13),
            placeholder_text="Adresse eingeben...",
        )
        self._send_addr.pack(fill="x", padx=15)

        ctk.CTkLabel(
            form, text="Betrag:",
            font=ctk.CTkFont(size=13), text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 3))

        amount_frame = ctk.CTkFrame(form, fg_color="transparent")
        amount_frame.pack(fill="x", padx=15, pady=(0, 12))

        self._send_amount = ctk.CTkEntry(
            amount_frame, height=38, font=ctk.CTkFont(size=13),
            placeholder_text="0.00", width=200,
        )
        self._send_amount.pack(side="left")

        self._send_chain_label = ctk.CTkLabel(
            amount_frame, text="DOI",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_ACCENT,
        )
        self._send_chain_label.pack(side="left", padx=10)

        self._send_balance_label = ctk.CTkLabel(
            amount_frame, text="Verfügbar: –",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        )
        self._send_balance_label.pack(side="right")

        # Senden Button
        self._send_btn = ctk.CTkButton(
            page, text="📤  Senden",
            font=ctk.CTkFont(size=16, weight="bold"),
            height=45,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._do_send,
        )
        self._send_btn.pack(fill="x", pady=(5, 5))

        self._send_status = ctk.CTkLabel(
            page, text="",
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT,
            wraplength=600,
        )
        self._send_status.pack(pady=(5, 0))

    def _on_chain_select(self, chain):
        self._send_chain_label.configure(text=chain)
        bal = self._balances.get(chain.lower(), 0)
        if chain == "DOI":
            self._send_balance_label.configure(text=f"Verfügbar: {format_doi(bal)} DOI")
        elif chain == "TRX":
            self._send_balance_label.configure(text=f"Verfügbar: {format_trx(bal)} TRX")
        elif chain == "USDT":
            self._send_balance_label.configure(text=f"Verfügbar: {format_usdt(bal)} USDT")
        elif chain == "ETH":
            self._send_balance_label.configure(text=f"Verfügbar: {format_eth(bal)} ETH")
        elif chain == "wDOI":
            self._send_balance_label.configure(text=f"Verfügbar: {format_wdoi(bal)} wDOI")

    # ── Empfangen ──

    def _create_receive_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self._pages["receive"] = page

        # Scrollable container
        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            scroll, text="Empfangen",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", pady=(5, 10))

        # DOI Adresse (v0.9.6: mit Refresh-Button, jeder Aufruf eine neue Adresse)
        self._recv_doi_frame = self._make_address_card(scroll, "DOI", COLOR_DOI, with_refresh=True)
        # Tron Adresse
        self._recv_tron_frame = self._make_address_card(scroll, "Tron (TRX/USDT)", COLOR_TRX)
        # ETH Adresse
        self._recv_eth_frame = self._make_address_card(scroll, "Ethereum (ETH/wDOI)", COLOR_ETH)

        # Privacy-Hinweis fuer die DOI-Empfangs-Logik
        ctk.CTkLabel(
            scroll,
            text="ℹ️  Jeder Aufruf dieser Seite zeigt eine neue DOI-Empfangsadresse "
                 "(BIP-44, mehr Privatsphäre). Frühere Adressen bleiben gültig.",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_DIM,
            wraplength=600, justify="left",
        ).pack(fill="x", pady=(4, 10), padx=4)

    def _make_address_card(self, parent, label, color, with_refresh=False):
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=RADIUS_CARD)
        card.pack(fill="x", pady=(0, 10))

        header = ctk.CTkFrame(card, fg_color="transparent")
        header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            header, text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=color,
        ).pack(side="left")

        # Index-Label rechts im Header (v0.9.6, nur fuer DOI)
        index_label = None
        if with_refresh:
            index_label = ctk.CTkLabel(
                header, text="",
                font=ctk.CTkFont(size=11),
                text_color=COLOR_TEXT_DIM,
            )
            index_label.pack(side="right")

        addr_label = ctk.CTkLabel(
            card, text="–",
            font=ctk.CTkFont(family="Consolas", size=15),
            text_color=COLOR_TEXT,
        )
        addr_label.pack(padx=15, pady=(0, 3))

        # Button-Reihe (Kopieren + optional Refresh)
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(pady=(0, 10))

        copy_btn = ctk.CTkButton(
            btn_row, text="📋 Kopieren", height=30, width=120,
            font=ctk.CTkFont(size=12),
            fg_color="transparent", hover_color="#2a3a5c",
            border_width=1, border_color=COLOR_ACCENT,
            corner_radius=RADIUS_BUTTON,
        )
        copy_btn.pack(side="left", padx=4)

        refresh_btn = None
        if with_refresh:
            refresh_btn = ctk.CTkButton(
                btn_row, text="🔄 Neue Adresse", height=30, width=140,
                font=ctk.CTkFont(size=12),
                fg_color="transparent", hover_color="#2a3a5c",
                border_width=1, border_color=COLOR_TEXT_DIM,
                corner_radius=RADIUS_BUTTON,
            )
            refresh_btn.pack(side="left", padx=4)

        # QR placeholder
        qr_label = ctk.CTkLabel(card, text="")
        qr_label.pack(pady=(0, 10))

        return {
            "card": card, "addr_label": addr_label,
            "copy_btn": copy_btn, "refresh_btn": refresh_btn,
            "qr_label": qr_label, "index_label": index_label,
        }

    def _update_receive_page(self, generate_new=False):
        if not self.wm:
            return

        # DOI: optional eine frische Adresse generieren (v0.9.6: bei jedem Tab-Aufruf)
        doi_idx = None
        if generate_new and self.wm.doi:
            try:
                doi_addr = self.wm.doi.get_new_receive_address()
                doi_idx = self.wm.doi._receive_index - 1
                # Index persistieren, damit Restart nichts verliert
                try:
                    self.wm.save_state()
                except Exception:
                    pass
            except Exception:
                doi_addr = self.wm.primary_addresses.get("doi", "–")
        else:
            doi_addr = self.wm.primary_addresses.get("doi", "–")
            doi_idx = 0  # Standard-Adresse ist Index 0

        tron_addr = self.wm.primary_addresses.get("tron", "–")
        eth_addr = self.wm.primary_addresses.get("eth", "–")

        self._recv_doi_frame["addr_label"].configure(text=doi_addr)
        self._recv_tron_frame["addr_label"].configure(text=tron_addr)
        self._recv_eth_frame["addr_label"].configure(text=eth_addr)

        # Index in der Ecke anzeigen (nur DOI)
        if self._recv_doi_frame.get("index_label") is not None and doi_idx is not None:
            self._recv_doi_frame["index_label"].configure(text=f"Adresse #{doi_idx}")

        self._recv_doi_frame["copy_btn"].configure(
            command=lambda a=doi_addr: self._copy_to_clipboard(a))
        self._recv_tron_frame["copy_btn"].configure(
            command=lambda: self._copy_to_clipboard(tron_addr))
        self._recv_eth_frame["copy_btn"].configure(
            command=lambda: self._copy_to_clipboard(eth_addr))

        # Refresh-Button verdrahten (nur DOI hat einen)
        refresh_btn = self._recv_doi_frame.get("refresh_btn")
        if refresh_btn is not None:
            refresh_btn.configure(command=lambda: self._update_receive_page(generate_new=True))

        # QR-Codes generieren
        if HAS_QR:
            self._set_qr(self._recv_doi_frame["qr_label"], doi_addr)
            self._set_qr(self._recv_tron_frame["qr_label"], tron_addr)
            self._set_qr(self._recv_eth_frame["qr_label"], eth_addr)

    def _set_qr(self, label, data):
        try:
            qr = qrcode.make(data, box_size=4, border=2)
            qr = qr.resize((150, 150))
            img = ImageTk.PhotoImage(qr)
            label.configure(image=img, text="")
            label._qr_img = img  # Referenz halten
        except Exception:
            pass

    def _copy_to_clipboard(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)
        self.conn_label.configure(text="📋 Kopiert!", text_color=COLOR_SUCCESS)
        self.after(2000, lambda: self.conn_label.configure(
            text=self._get_conn_text(), text_color=COLOR_TEXT_DIM))

    # ── Transaktionen ──

    def _create_history_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self._pages["history"] = page

        # Header mit Titel und Filter
        header = ctk.CTkFrame(page, fg_color="transparent")
        header.pack(fill="x", pady=(5, 10))

        ctk.CTkLabel(
            header, text="Transaktionen",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            header, text="🔄", width=35, height=35,
            fg_color=COLOR_CARD, hover_color="#2a3a5c",
            command=self._refresh_history_async,
        ).pack(side="right")

        # Chain-Filter
        self._hist_filter = ctk.CTkSegmentedButton(
            page,
            values=["Alle", "DOI", "TRX", "USDT", "ETH", "wDOI"],
            font=ctk.CTkFont(size=13),
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            command=self._on_hist_filter,
        )
        self._hist_filter.set("Alle")
        self._hist_filter.pack(fill="x", pady=(0, 10))

        # Scrollbare Transaktionsliste
        self._hist_scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        self._hist_scroll.pack(fill="both", expand=True)

        # Interner Cache
        self._hist_data = {}  # {chain: [tx, ...]}

    def _on_hist_filter(self, value):
        """Filter gewechselt → Anzeige aktualisieren."""
        self._render_history()

    def _refresh_history_async(self, force=False):
        """
        History im Hintergrund laden.

        Schutz gegen ueberlappende Refreshes (z.B. 60s-Auto-Refresh waehrend
        ein manueller Refresh noch laeuft): Generationszaehler – nur das
        Ergebnis der juengsten Generation wird uebernommen. Laeuft bereits
        ein Load, wird (ausser bei force=True) kein neuer gestartet.
        """
        if self._hist_loading and not force:
            return
        self._hist_gen += 1
        gen = self._hist_gen
        self._hist_loading = True
        slot_idx = self._active_slot

        # Status direkt in der Liste anzeigen (alte Einträge löschen)
        for widget in self._hist_scroll.winfo_children():
            widget.destroy()
        ctk.CTkLabel(
            self._hist_scroll, text="⏳ Lade Transaktionen...",
            font=ctk.CTkFont(size=13), text_color=COLOR_WARNING,
        ).pack(pady=20)
        threading.Thread(
            target=self._load_history, args=(slot_idx, gen), daemon=True
        ).start()

    def _update_hist_status(self, text):
        """Zeigt Status-Text in der Transaktionsliste."""
        try:
            for widget in self._hist_scroll.winfo_children():
                widget.destroy()
            ctk.CTkLabel(
                self._hist_scroll, text=text,
                font=ctk.CTkFont(size=13), text_color=COLOR_WARNING,
            ).pack(pady=20)
        except Exception:
            pass

    def _load_history(self, slot_idx=None, gen=None):
        """
        Lädt Transaktionen aller Chains (Hintergrund-Thread).

        Slot-gebunden: wm wird beim Thread-Start eingefroren und das Ergebnis
        in den Slot-eigenen Speicher geschrieben. Die UI wird nur aktualisiert,
        wenn der Slot noch aktiv und die Generation noch aktuell ist – sonst
        wuerde ein Tab-Wechsel mitten im Fetch Daten von Wallet A in Slot B
        anzeigen/speichern.
        """
        if slot_idx is None:
            slot_idx = self._active_slot
        slot = self._wallet_slots[slot_idx]
        wm = slot["wm"]

        def _still_current():
            return (slot_idx == self._active_slot
                    and (gen is None or gen == self._hist_gen))

        def _finish():
            # Lade-Flag nur zuruecksetzen, wenn keine neuere Generation laeuft
            if gen is None or gen == self._hist_gen:
                self._hist_loading = False

        if not wm:
            self._safe_after(0, _finish)
            return

        data = {}

        # ETH + wDOI Transaktionen (RPC-basiert)
        if wm.eth:
            # wDOI-History (Event Logs – funktioniert)
            try:
                data["wdoi"] = wm.eth.get_wdoi_history(limit=20)
                logger.debug(f"wDOI-History: {len(data['wdoi'])} TXs")
                if data["wdoi"]:
                    logger.debug(f"wDOI TX[0]: {data['wdoi'][0]}")
            except Exception as e:
                logger.debug(f"wDOI-History Error: {e}")
                data["wdoi"] = []

            # ETH-History: Rekonstruiere aus wDOI-TXs + Etherscan
            try:
                data["eth"] = self._load_eth_history_rpc(wm, data.get("wdoi", []))
                logger.debug(f"ETH-History (RPC): {len(data['eth'])} TXs")
            except Exception as e:
                logger.debug(f"ETH-History Error: {e}", exc_info=True)
                data["eth"] = []

        # DOI-Transaktionen (mit Beträgen via ElectrumX TX-Lookup)
        if wm.doi:
            try:
                doi_hist = wm.doi.get_history()
                logger.debug(f"DOI raw history type: {type(doi_hist).__name__}")
                if isinstance(doi_hist, list):
                    logger.debug(f"DOI raw history: {len(doi_hist)} TXs")
                    if doi_hist:
                        logger.debug(f"DOI TX[0] keys: {list(doi_hist[0].keys()) if isinstance(doi_hist[0], dict) else 'not a dict'}")
                    # Status-Update im UI (nur falls Slot/Generation noch aktuell)
                    def _status(n=len(doi_hist)):
                        if _still_current():
                            self._update_hist_status(f"⏳ Lade DOI-Beträge ({n} TXs)...")
                    self._safe_after(0, _status)
                    data["doi"] = self._enrich_doi_history(wm, doi_hist)
                elif isinstance(doi_hist, dict):
                    logger.debug(f"DOI raw history keys: {list(doi_hist.keys())}")
                    for key in ["transactions", "txs", "history", "data"]:
                        if key in doi_hist and isinstance(doi_hist[key], list):
                            logger.debug(f"DOI raw: using dict['{key}'] with {len(doi_hist[key])} TXs")
                            data["doi"] = self._enrich_doi_history(wm, doi_hist[key])
                            break
                    else:
                        data["doi"] = []
                else:
                    data["doi"] = []
                # v0.9.6.6: Reconcile - falls Enrich TXs schluckt, Platzhalter anlegen
                if isinstance(doi_hist, list) and isinstance(data.get("doi"), list):
                    _enriched_hashes = {_e.get("hash", "") for _e in data["doi"] if isinstance(_e, dict)}
                    for _raw in doi_hist:
                        if not isinstance(_raw, dict):
                            continue
                        _rh = _raw.get("tx_hash", "")
                        if _rh and _rh not in _enriched_hashes:
                            data["doi"].append({
                                "hash": _rh,
                                "direction": "unknown",
                                "value": 0,
                                "symbol": "DOI",
                                "timestamp": 0,
                                "from": "",
                                "to": "",
                                "block": _raw.get("height", 0),
                            })

                logger.debug(f"DOI-History: {len(data.get('doi',[]))} TXs (enriched)")
            except Exception as e:
                logger.debug(f"DOI-History Error: {e}", exc_info=True)
                data["doi"] = []

        # Tron-Transaktionen
        if wm.tron:
            try:
                trx_hist = wm.tron.get_history(limit=20)
                logger.debug(f"TRX-History Typ: {type(trx_hist).__name__}")
                if isinstance(trx_hist, list):
                    data["trx"] = trx_hist
                    if trx_hist:
                        logger.debug(f"TRX TX[0]: {trx_hist[0]}")
                elif isinstance(trx_hist, dict) and "data" in trx_hist:
                    data["trx"] = trx_hist["data"]
                else:
                    data["trx"] = []
            except Exception as e:
                logger.debug(f"TRX-History Error: {e}")
                data["trx"] = []

            try:
                usdt_hist = wm.tron.get_usdt_history(limit=20)
                logger.debug(f"USDT-History Typ: {type(usdt_hist).__name__}")
                if isinstance(usdt_hist, list):
                    data["usdt"] = usdt_hist
                elif isinstance(usdt_hist, dict) and "data" in usdt_hist:
                    data["usdt"] = usdt_hist["data"]
                else:
                    data["usdt"] = []
            except Exception as e:
                logger.debug(f"USDT-History Error: {e}")
                data["usdt"] = []

        # Ergebnis in den Slot-eigenen Speicher schreiben; UI nur aktualisieren,
        # wenn dieser Slot noch aktiv und die Generation noch aktuell ist.
        slot["hist_data"] = data

        def _apply():
            _finish()
            if not _still_current():
                return
            self._hist_data = data
            self._render_history()

        self._safe_after(0, _apply)

    def _load_eth_history_rpc(self, wm, wdoi_txs: list = None) -> list:
        """
        Lädt ETH-Transaktionshistory über Web3 RPC.
        Nutzt wDOI TX-Hashes + Etherscan API Fallback.
        """
        eth = wm.eth
        w3 = getattr(eth, "_w3", None)
        if not w3:
            logger.debug("ETH-RPC: Kein Web3-Client")
            return []

        addr = eth.address
        if not addr:
            return []

        addr_lower = addr.lower()
        seen_hashes = set()
        eth_txs = []

        # ── Schritt 1: wDOI TX-Hashes → ETH-Details laden ──
        if wdoi_txs:
            logger.debug(f"ETH-RPC: Lade Details für {len(wdoi_txs)} wDOI-TXs")
            for wdoi_tx in wdoi_txs:
                tx_hash = wdoi_tx.get("hash", "")
                if not tx_hash or tx_hash in seen_hashes:
                    continue
                seen_hashes.add(tx_hash)

                try:
                    tx = w3.eth.get_transaction(tx_hash)
                    receipt = w3.eth.get_transaction_receipt(tx_hash)
                    if not tx or not receipt:
                        continue

                    from_addr = (tx.get("from", "") or "")
                    to_addr = (tx.get("to", "") or "")
                    value_wei = tx.get("value", 0)
                    gas_used = receipt.get("gasUsed", 0)
                    gas_price = receipt.get("effectiveGasPrice",
                                tx.get("gasPrice", 0))
                    gas_cost_wei = gas_used * gas_price
                    block_num = tx.get("blockNumber", 0)
                    is_from_us = from_addr.lower() == addr_lower

                    # Timestamp aus wDOI-TX oder Block
                    ts = wdoi_tx.get("timestamp", 0)
                    if not ts:
                        try:
                            block = w3.eth.get_block(block_num)
                            ts = block.get("timestamp", 0)
                        except Exception:
                            pass

                    # Gas-Kosten als ETH-TX
                    if is_from_us and gas_cost_wei > 0:
                        gas_eth = gas_cost_wei / 1e18
                        if value_wei > 0:
                            total = (value_wei + gas_cost_wei) / 1e18
                            eth_txs.append({
                                "hash": tx_hash, "from": from_addr, "to": to_addr,
                                "value": total, "symbol": "ETH", "timestamp": ts,
                                "direction": "sent", "block": block_num,
                            })
                        else:
                            eth_txs.append({
                                "hash": tx_hash, "from": from_addr, "to": to_addr,
                                "value": gas_eth, "symbol": "ETH", "timestamp": ts,
                                "direction": "sent", "block": block_num,
                                "note": "gas",
                            })
                    elif value_wei > 0:
                        eth_txs.append({
                            "hash": tx_hash, "from": from_addr, "to": to_addr,
                            "value": value_wei / 1e18, "symbol": "ETH",
                            "timestamp": ts, "direction": "received",
                            "block": block_num,
                        })

                    logger.debug(f"ETH-RPC TX {tx_hash[:12]}: "
                          f"val={value_wei/1e18:.6f} gas={gas_cost_wei/1e18:.6f} "
                          f"{'from_us' if is_from_us else 'to_us'}")

                except Exception as e:
                    logger.debug(f"ETH-RPC TX {tx_hash[:12]} error: {e}")

        # ── Schritt 2: Blockscout API (kostenlos, kein Key nötig) ──
        import urllib.request
        import json as _json

        api_sources = [
            ("Blockscout",
             f"https://eth.blockscout.com/api/v2/addresses/{addr_lower}/transactions"),
            ("Etherscan",
             f"https://api.etherscan.io/api?module=account&action=txlist"
             f"&address={addr}&startblock=0&endblock=99999999"
             f"&page=1&offset=20&sort=desc"),
        ]

        for api_name, url in api_sources:
            try:
                logger.debug(f"ETH-RPC: {api_name} → {url[:80]}...")
                req = urllib.request.Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                    "Accept": "application/json",
                })
                with urllib.request.urlopen(req, timeout=15) as resp:
                    api_data = _json.loads(resp.read().decode())

                if api_name == "Blockscout":
                    # Blockscout v2 Format: {"items": [{...}, ...]}
                    items = api_data.get("items", [])
                    logger.debug(f"ETH-RPC: Blockscout lieferte {len(items)} TXs")
                    if items:
                        first = items[0]
                        logger.debug(f"ETH-RPC: Blockscout TX[0] keys: {list(first.keys())[:15]}")
                        logger.debug(f"ETH-RPC: Blockscout TX[0] value={first.get('value')} "
                              f"fee={first.get('fee')} from={first.get('from')} to={first.get('to')}")
                    for tx_item in items:
                        tx_hash = tx_item.get("hash", "")
                        if tx_hash in seen_hashes:
                            continue
                        seen_hashes.add(tx_hash)

                        value_wei = int(tx_item.get("value", "0") or "0")
                        # Fee kann String oder Dict sein
                        fee_raw = tx_item.get("fee", {})
                        if isinstance(fee_raw, dict):
                            fee_wei = int(fee_raw.get("value", "0") or "0")
                        else:
                            fee_wei = int(fee_raw or "0")
                        from_addr = tx_item.get("from", {})
                        to_addr = tx_item.get("to", {})
                        from_hash = (from_addr.get("hash", "") if isinstance(from_addr, dict)
                                     else str(from_addr))
                        to_hash = (to_addr.get("hash", "") if isinstance(to_addr, dict)
                                   else str(to_addr))
                        ts_str = tx_item.get("timestamp", "")
                        block_num = tx_item.get("block_number",
                                    tx_item.get("block", 0))

                        # Timestamp: ISO → Unix
                        ts = 0
                        if ts_str:
                            try:
                                from datetime import datetime, timezone
                                dt = datetime.fromisoformat(
                                    ts_str.replace("Z", "+00:00"))
                                ts = int(dt.timestamp())
                            except Exception:
                                pass

                        is_from_us = from_hash.lower() == addr_lower

                        logger.debug(f"ETH-RPC: Blockscout TX {tx_hash[:12]}: "
                              f"val={value_wei} fee={fee_wei} "
                              f"{'from_us' if is_from_us else 'to_us'}")

                        if is_from_us:
                            total = (value_wei + fee_wei) / 1e18
                            if total > 0:
                                eth_txs.append({
                                    "hash": tx_hash, "from": from_hash,
                                    "to": to_hash, "value": total,
                                    "symbol": "ETH", "timestamp": ts,
                                    "direction": "sent", "block": block_num,
                                })
                        elif value_wei > 0:
                            eth_txs.append({
                                "hash": tx_hash, "from": from_hash,
                                "to": to_hash, "value": value_wei / 1e18,
                                "symbol": "ETH", "timestamp": ts,
                                "direction": "received", "block": block_num,
                            })

                    if items:
                        break  # Blockscout hat funktioniert

                elif api_name == "Etherscan":
                    status = api_data.get("status")
                    result_list = api_data.get("result", [])
                    logger.debug(f"ETH-RPC: Etherscan status={status} "
                          f"count={len(result_list) if isinstance(result_list, list) else 'N/A'}")

                    if status == "1" and isinstance(result_list, list):
                        for tx_item in result_list:
                            tx_hash = tx_item.get("hash", "")
                            if tx_hash in seen_hashes:
                                continue
                            seen_hashes.add(tx_hash)

                            value_wei = int(tx_item.get("value", 0))
                            gas_used = int(tx_item.get("gasUsed", 0))
                            gas_price = int(tx_item.get("gasPrice", 0))
                            from_addr = tx_item.get("from", "")
                            to_addr = tx_item.get("to", "")
                            ts = int(tx_item.get("timeStamp", 0))
                            block_num = int(tx_item.get("blockNumber", 0))
                            is_from_us = from_addr.lower() == addr_lower

                            if is_from_us:
                                total = (value_wei + gas_used * gas_price) / 1e18
                                eth_txs.append({
                                    "hash": tx_hash, "from": from_addr,
                                    "to": to_addr,
                                    "value": max(total, gas_used * gas_price / 1e18),
                                    "symbol": "ETH", "timestamp": ts,
                                    "direction": "sent", "block": block_num,
                                })
                            elif value_wei > 0:
                                eth_txs.append({
                                    "hash": tx_hash, "from": from_addr,
                                    "to": to_addr, "value": value_wei / 1e18,
                                    "symbol": "ETH", "timestamp": ts,
                                    "direction": "received", "block": block_num,
                                })
                        break  # Etherscan hat funktioniert

            except Exception as e:
                logger.debug(f"ETH-RPC: {api_name} Fehler: {e}")

        # ── Deduplizieren und sortieren ──
        unique = {}
        for tx in eth_txs:
            key = tx["hash"] + tx.get("note", "")
            if key not in unique:
                unique[key] = tx
        result = sorted(unique.values(),
                        key=lambda x: x.get("timestamp", 0), reverse=True)

        logger.debug(f"ETH-RPC: {len(result)} unique ETH-TXs")
        return result

    def _enrich_doi_history(self, wm, raw_history: list, max_txs: int = 200) -> list:
        """
        Reichert DOI-Transaktionen mit Beträgen an via ElectrumX get_transaction.

        Für jede TX wird die volle Transaktion geladen und der Netto-Betrag
        für unsere Wallet-Adressen berechnet (Outputs - Inputs).
        """
        if not wm or not wm.doi:
            logger.debug("DOI-Enrich: wm.doi nicht verfügbar")
            return raw_history

        # ── TX-Fetch-Funktion ermitteln ──
        tx_fetch_fn = self._find_doi_tx_fetch(wm)
        if not tx_fetch_fn:
            return raw_history

        # ── Alle Wallet-Adressen sammeln ──
        our_addrs = self._collect_doi_addresses(wm, raw_history)
        if not our_addrs:
            logger.debug("DOI-Enrich: Keine Wallet-Adressen gefunden")
            return raw_history

        logger.debug(f"DOI-Enrich: {len(our_addrs)} Adressen, {len(raw_history)} TXs")

        # ── Test-Aufruf ──
        test_hash = next(
            (e.get("tx_hash", e.get("txid", ""))
             for e in raw_history if e.get("tx_hash", e.get("txid", ""))),
            None,
        )
        if test_hash:
            try:
                test_result = tx_fetch_fn(test_hash)
                if isinstance(test_result, str):
                    logger.debug("DOI-Enrich: Raw-Hex → verbose nicht unterstützt")
                    return raw_history
                elif isinstance(test_result, dict):
                    keys = list(test_result.keys())[:8]
                    logger.debug(f"DOI-Enrich: Test OK, Keys: {keys}")
                else:
                    logger.debug(f"DOI-Enrich: Unerwarteter Typ: {type(test_result)}")
                    return raw_history
            except Exception as e:
                logger.debug(f"DOI-Enrich: Test fehlgeschlagen: {e}")
                return raw_history

        # ── Transaktionen laden und anreichern ──
        sorted_hist = sorted(raw_history, key=lambda x: x.get("height", 0), reverse=True)
        # Persistenter In-Memory-Cache (txid → verbose dict): bestaetigte TXs
        # sind unveraenderlich, der 60s-Auto-Refresh muss sie nicht neu laden.
        tx_cache = self._tx_cache

        def _fetch_cached(txid):
            cached = tx_cache.get(txid)
            if cached is not None:
                return cached
            fetched = tx_fetch_fn(txid)
            # Nur bestaetigte TXs cachen (unbestaetigte aendern sich noch,
            # z.B. bekommen sie spaeter blocktime/Confirmations).
            if isinstance(fetched, dict) and fetched.get("blocktime"):
                tx_cache[txid] = fetched
            return fetched

        enriched = []

        for entry in sorted_hist[:max_txs]:
            tx_hash = entry.get("tx_hash", entry.get("txid", ""))
            height = entry.get("height", 0)
            if not tx_hash:
                continue

            try:
                tx_data = _fetch_cached(tx_hash)

                if not tx_data or not isinstance(tx_data, dict):
                    continue

                # ── Outputs summieren (was an unsere Adressen geht) ──
                our_output = 0.0
                for vout in tx_data.get("vout", []):
                    value = vout.get("value", 0)
                    spk = vout.get("scriptPubKey", {})
                    addrs = spk.get("addresses", [])
                    if not addrs and "address" in spk:
                        addrs = [spk["address"]]
                    if any(a in our_addrs for a in addrs):
                        our_output += float(value)

                # ── Inputs summieren (was von unseren Adressen kommt) ──
                our_input = 0.0
                for vin in tx_data.get("vin", []):
                    prev_txid = vin.get("txid", "")
                    prev_vout_idx = vin.get("vout", 0)
                    if not prev_txid:
                        continue  # Coinbase TX

                    try:
                        prev_tx = _fetch_cached(prev_txid)

                        if prev_tx and isinstance(prev_tx, dict) and "vout" in prev_tx:
                            prev_vout = prev_tx["vout"]
                            if prev_vout_idx < len(prev_vout):
                                pv = prev_vout[prev_vout_idx]
                                pv_addrs = pv.get("scriptPubKey", {}).get("addresses", [])
                                if not pv_addrs:
                                    pv_addr = pv.get("scriptPubKey", {}).get("address", "")
                                    pv_addrs = [pv_addr] if pv_addr else []
                                if any(a in our_addrs for a in pv_addrs):
                                    our_input += float(pv.get("value", 0))
                    except Exception as e:
                        logger.debug(f"DOI-Enrich vin error: {e}")

                # ── Netto-Betrag ──
                net = our_output - our_input
                logger.debug(f"DOI TX {tx_hash[:12]}: out={our_output:.8f} in={our_input:.8f} net={net:.8f}")

                if abs(net) < 0.00000001:
                    continue  # Kein relevanter Transfer

                direction = "received" if net > 0 else "sent"
                timestamp = tx_data.get("time", tx_data.get("blocktime", 0))

                enriched.append({
                    "hash": tx_hash,
                    "direction": direction,
                    "value": abs(net),
                    "symbol": "DOI",
                    "timestamp": timestamp,
                    "from": "",
                    "to": "",
                    "block": height,
                })

            except Exception as e:
                logger.debug(f"DOI-Enrich error {tx_hash[:16]}: {e}")
                enriched.append({
                    "hash": tx_hash,
                    "direction": "unknown",
                    "value": 0,
                    "symbol": "DOI",
                    "timestamp": 0,
                    "from": "",
                    "to": "",
                    "block": height,
                })

        logger.debug(f"DOI-Enrich: {len(enriched)} von {len(raw_history)} angereichert")
        return enriched if enriched else raw_history

    def _find_doi_tx_fetch(self, wm):
        """Findet die beste Methode um DOI-Transaktionen per Hash zu laden."""
        doi = wm.doi

        # ── Versuch 1: Direkt auf dem DOI-Wallet ──
        if hasattr(doi, "get_transaction"):
            logger.debug("DOI-Enrich: Verwende doi.get_transaction()")
            return lambda h: doi.get_transaction(h)

        # ── Versuch 2: ElectrumX-Client suchen ──
        electrumx = None
        # Priorität: electrumx > electrum > client > server > _electrumx > _client
        for attr in ("electrumx", "electrum", "client", "server", "_electrumx",
                      "_client", "rpc", "network"):
            obj = getattr(doi, attr, None)
            if obj is None:
                continue
            # Dicts überspringen (z.B. network={host, port} Config)
            if isinstance(obj, dict):
                logger.debug(f"DOI-Enrich: '{attr}' ist ein Dict (Config), überspringe")
                continue
            electrumx = obj
            logger.debug(f"DOI-Enrich: ElectrumX-Client via doi.{attr}")
            break

        if electrumx:
            # Alle bekannten Methoden-Signaturen testen
            for method_name in ("get_transaction", "call", "_call", "request",
                                "send_request", "synchronous_get"):
                fn = getattr(electrumx, method_name, None)
                if not fn or not callable(fn):
                    continue
                logger.debug(f"DOI-Enrich: Verwende electrumx.{method_name}()")
                if method_name == "get_transaction":
                    return lambda h, _fn=fn: _fn(h, verbose=True)
                else:
                    return lambda h, _fn=fn: _fn("blockchain.transaction.get", [h, True])

            # Kein bekannter Methodenname → alle callable Attribute zeigen
            callables = [m for m in dir(electrumx) if not m.startswith('_')
                         and callable(getattr(electrumx, m, None))]
            logger.debug(f"DOI-Enrich: Callable methods auf Client: {callables}")

        # ── Versuch 3: Direkte JSON-RPC über TCP/SSL ──
        host, port = None, None

        # Aus network-Dict lesen (häufig: {host: ..., port: ...})
        net_dict = getattr(doi, "network", None)
        if isinstance(net_dict, dict):
            host = net_dict.get("host", net_dict.get("server", None))
            port = net_dict.get("port", net_dict.get("ssl_port",
                   net_dict.get("tcp_port", None)))
            if host:
                logger.debug(f"DOI-Enrich: Host/Port aus network-Dict: {host}:{port}")

        # Fallback: Attribute auf doi oder electrumx
        if not host:
            for obj in (doi, electrumx):
                if not obj:
                    continue
                host = getattr(obj, "_host", None) or getattr(obj, "host", None)
                port = getattr(obj, "_port", None) or getattr(obj, "port", None)
                if host:
                    break

        if host and port:
            logger.debug(f"DOI-Enrich: Verwende direkten JSON-RPC → {host}:{port}")

            # Gepinnte Fingerprints analog src/wallet/electrumx_client.py
            # (per-Host-Dict bevorzugt, Legacy-Liste gilt fuer alle Hosts).
            _net_cfg = net_dict if isinstance(net_dict, dict) else {}

            def _pinned_for_host(h):
                pinned = _net_cfg.get("ssl_pinned_fingerprints") or {}
                fps = (pinned.get(h) or []) if isinstance(pinned, dict) else pinned
                return {str(fp).lower().replace(":", "").replace(" ", "")
                        for fp in fps}

            def _wrap_tls(_host, _port):
                """
                TLS-Verbindung mit echter Validierung:
                  1. Strikte CA-/Hostname-Pruefung (certifi/System-CAs).
                  2. Nur bei Zertifikatsfehler: Fingerprint-Pinning wie im
                     ElectrumXClient. NIEMALS blind jedes Zertifikat akzeptieren.
                """
                import socket
                import ssl as _ssl
                import hashlib as _hashlib

                raw = socket.create_connection((_host, _port), timeout=10)
                try:
                    try:
                        import certifi
                        ctx = _ssl.create_default_context(cafile=certifi.where())
                    except ImportError:
                        ctx = _ssl.create_default_context()
                    return ctx.wrap_socket(raw, server_hostname=_host)
                except _ssl.SSLCertVerificationError:
                    try:
                        raw.close()
                    except Exception:
                        pass
                    pinned = _pinned_for_host(_host)
                    if not pinned:
                        raise  # Kein Pinning konfiguriert → Fehler durchreichen

                # Fallback: Pinning (self-signed Zertifikate). Identitaet wird
                # ueber den SHA-256 Fingerprint des DER-Zertifikats geprueft.
                raw = socket.create_connection((_host, _port), timeout=10)
                ctx = _ssl.SSLContext(_ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = _ssl.CERT_NONE
                tls = ctx.wrap_socket(raw, server_hostname=_host)
                der_cert = tls.getpeercert(binary_form=True)
                actual = _hashlib.sha256(der_cert or b"").hexdigest()
                if actual not in pinned:
                    tls.close()
                    raise _ssl.SSLError(
                        f"Certificate-Pinning fehlgeschlagen für {_host}: "
                        f"Fingerprint nicht in ssl_pinned_fingerprints.")
                return tls

            def _fetch_direct(tx_hash, _host=host, _port=int(port)):
                import socket
                import json as _json
                if _port in (50002, 51002):
                    sock = _wrap_tls(_host, _port)
                else:
                    sock = socket.create_connection((_host, _port), timeout=10)
                try:
                    req = _json.dumps({
                        "jsonrpc": "2.0",
                        "method": "blockchain.transaction.get",
                        "params": [tx_hash, True],
                        "id": 1
                    }) + "\n"
                    sock.sendall(req.encode())
                    data = b""
                    while b"\n" not in data:
                        chunk = sock.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                    resp = _json.loads(data.decode().strip())
                    return resp.get("result", resp)
                finally:
                    sock.close()

            return _fetch_direct

        # Nichts gefunden – ausführliches Debug
        logger.debug("DOI-Enrich: Keine TX-Fetch-Methode gefunden!")
        doi_attrs = [a for a in dir(doi) if not a.startswith('__')]
        logger.debug(f"DOI attrs: {doi_attrs}")
        if electrumx:
            ex_attrs = [a for a in dir(electrumx) if not a.startswith('__')]
            logger.debug(f"ElectrumX attrs: {ex_attrs}")
        if isinstance(net_dict, dict):
            logger.debug(f"network dict keys: {list(net_dict.keys())}")
            logger.debug(f"network dict: {net_dict}")
        return None

    def _collect_doi_addresses(self, wm, raw_history):
        """Sammelt alle DOI-Wallet-Adressen."""
        our_addrs = set()
        doi = wm.doi

        try:
            all_addr = doi.get_all_addresses()
            if isinstance(all_addr, dict):
                for val in all_addr.values():
                    if isinstance(val, list):
                        our_addrs.update(val)
            elif isinstance(all_addr, list):
                our_addrs.update(all_addr)
        except Exception:
            pass

        if not our_addrs:
            try:
                our_addrs = set(
                    doi.get_receive_addresses() +
                    doi.get_change_addresses()
                )
            except Exception:
                pass

        if not our_addrs:
            try:
                sm = doi.seed_manager
                for i in range(20):
                    try:
                        our_addrs.add(sm.get_receive_address(i))
                    except Exception:
                        break
                for i in range(20):
                    try:
                        our_addrs.add(sm.get_change_address(i))
                    except Exception:
                        break
            except Exception:
                pass

        if not our_addrs:
            for entry in raw_history:
                for a in entry.get("addresses", []):
                    our_addrs.add(a)

        return our_addrs

    def _render_history(self):
        """Transaktionsliste rendern."""
        # Alte Einträge löschen
        for widget in self._hist_scroll.winfo_children():
            widget.destroy()

        chain_filter = self._hist_filter.get()

        # Alle Transaktionen sammeln und normalisieren
        all_txs = []
        for chain, txs in self._hist_data.items():
            if chain_filter != "Alle" and chain.lower() != chain_filter.lower():
                continue
            if not isinstance(txs, list):
                continue
            for tx in txs:
                normalized = self._normalize_tx(tx, chain)
                if normalized:
                    all_txs.append(normalized)
                else:
                    logger.debug(f"normalize returned None for {chain}: {str(tx)[:80]}")

        logger.debug(f"_render_history: filter={chain_filter}, chains={list(self._hist_data.keys())}, total_txs={len(all_txs)}")

        # Unbestaetigte TXs mit aktuellem Timestamp versehen (damit sie oben stehen)
        import time as _time
        for tx in all_txs:
            if tx.get("block", tx.get("height", 0)) == 0 and tx.get("timestamp", 0) == 0:
                tx["timestamp"] = int(_time.time())

        # Nach Zeitstempel sortieren (neueste zuerst)
        all_txs.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        if not all_txs:
            ctk.CTkLabel(
                self._hist_scroll,
                text="Keine Transaktionen gefunden.",
                font=ctk.CTkFont(size=14),
                text_color=COLOR_TEXT_DIM,
            ).pack(pady=30)
            return

        # Transaktionen anzeigen
        for tx in all_txs[:50]:  # Max 50 anzeigen
            self._make_tx_card(self._hist_scroll, tx)

        # Scroll-Position zurücksetzen (nach oben)
        try:
            self._hist_scroll._parent_canvas.yview_moveto(0)
        except Exception:
            pass

    def _normalize_tx(self, tx, chain):
        """Normalisiert verschiedene TX-Formate in einheitliches Format."""
        try:
            # Bereits normalisiertes Format (ETH/wDOI aus RPC Event Logs)
            if "hash" in tx and "direction" in tx and "symbol" in tx:
                return tx

            # ── DOI (ElectrumX: {tx_hash, height, addresses}) ──
            if chain == "doi":
                tx_hash = tx.get("tx_hash", tx.get("txid", tx.get("hash", "")))
                height = tx.get("height", tx.get("block_height", 0))
                timestamp = tx.get("timestamp", tx.get("time", 0))
                addresses = tx.get("addresses", [])

                # ElectrumX liefert keinen Betrag – nur TX-Hash + Blockhöhe
                value = tx.get("value", tx.get("amount", None))
                if value is not None:
                    if isinstance(value, str):
                        value = float(value)
                    if abs(value) > 100000:
                        value = value / 1e8
                    direction = "received" if value >= 0 else "sent"
                    value = abs(value)
                else:
                    value = 0
                    direction = "unknown"

                return {
                    "hash": tx_hash,
                    "direction": direction,
                    "value": value,
                    "symbol": "DOI",
                    "timestamp": timestamp,
                    "to": ", ".join(addresses) if addresses else "",
                    "from": "",
                    "block": height,
                }

            # ── TRX (Tron raw_data-Format) ──
            if chain == "trx":
                tx_id = tx.get("txID", tx.get("transaction_id", ""))
                ts = tx.get("block_timestamp", tx.get("timestamp", 0))
                if ts > 1e12:
                    ts = ts / 1000

                raw_data = tx.get("raw_data", {})
                contracts = raw_data.get("contract", [])
                value = 0
                from_hex = ""
                to_hex = ""
                contract_type = ""
                for c in contracts:
                    contract_type = c.get("type", "")
                    pv = c.get("parameter", {}).get("value", {})

                    # TRC-10 Token-Transfers überspringen (asset_name vorhanden)
                    if pv.get("asset_name"):
                        return None  # Kein TRX-Transfer

                    value = pv.get("amount", 0)
                    from_hex = pv.get("owner_address", "")
                    to_hex = pv.get("to_address", "")

                # Nur TransferContract = echter TRX-Transfer
                # Alles andere (TriggerSmartContract, etc.) überspringen
                if contract_type != "TransferContract":
                    return None

                # Sun → TRX (1 TRX = 1.000.000 Sun) – immer konvertieren
                value = value / 1e6

                direction = "sent"
                addr = self.wm.tron.primary_address if self.wm and self.wm.tron else ""
                if addr and to_hex:
                    to_b58 = self._tron_hex_to_base58(to_hex)
                    if to_b58:
                        direction = "received" if to_b58 == addr else "sent"

                return {
                    "hash": tx_id,
                    "direction": direction,
                    "value": abs(value),
                    "symbol": "TRX",
                    "timestamp": int(ts),
                    "from": from_hex,
                    "to": to_hex,
                    # v0.9.6: block-Feld aus TronGrid-Antwort uebernehmen,
                    # sonst zeigt _make_tx_card immer "Unbestaetigt"
                    "block": tx.get("blockNumber", tx.get("block_number", 0)),
                }

            # ── USDT (TRC-20 Token-Transfer) ──
            if chain == "usdt":
                tx_id = tx.get("transaction_id", tx.get("txID", ""))
                ts = tx.get("block_timestamp", tx.get("timestamp", 0))
                if ts > 1e12:
                    ts = ts / 1000

                from_addr = tx.get("from", tx.get("transferFromAddress", ""))
                to_addr = tx.get("to", tx.get("transferToAddress", ""))
                value = tx.get("value", tx.get("amount", 0))
                if isinstance(value, str):
                    value = float(value)

                # USDT TRC-20: Wert in kleinster Einheit (6 Dezimalstellen)
                if abs(value) > 100000:
                    value = value / 1e6

                # Fallback: aus raw_data extrahieren
                if not from_addr and not to_addr:
                    raw_data = tx.get("raw_data", {})
                    for c in raw_data.get("contract", []):
                        pv = c.get("parameter", {}).get("value", {})
                        from_addr = pv.get("owner_address", "")
                        to_addr = pv.get("to_address", "")

                direction = "sent"
                addr = self.wm.tron.primary_address if self.wm and self.wm.tron else ""
                if addr and to_addr:
                    # to_addr kann Base58 (T...) oder Hex (41...) sein
                    if to_addr.startswith("41") and len(to_addr) == 42:
                        to_b58 = self._tron_hex_to_base58(to_addr)
                        direction = "received" if to_b58 == addr else "sent"
                    elif to_addr.startswith("T"):
                        direction = "received" if to_addr == addr else "sent"

                return {
                    "hash": tx_id,
                    "direction": direction,
                    "value": abs(value),
                    "symbol": "USDT",
                    "timestamp": int(ts),
                    "from": from_addr,
                    "to": to_addr,
                    # v0.9.6: gleicher Fix wie TRX
                    "block": tx.get("blockNumber", tx.get("block_number", 0)),
                }

            return None
        except Exception as e:
            logger.debug(f"normalize_tx error ({chain}): {e}")
            return None

    @staticmethod
    def _tron_hex_to_base58(hex_addr: str) -> str:
        """Konvertiert Tron Hex-Adresse (41...) in Base58Check-Format (T...)."""
        import hashlib
        try:
            addr_bytes = bytes.fromhex(hex_addr)
            h1 = hashlib.sha256(addr_bytes).digest()
            h2 = hashlib.sha256(h1).digest()
            raw = addr_bytes + h2[:4]
            # Base58-Kodierung
            alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
            n = int.from_bytes(raw, "big")
            result = ""
            while n > 0:
                n, r = divmod(n, 58)
                result = alphabet[r] + result
            # Führende Null-Bytes → "1"
            for b in raw:
                if b == 0:
                    result = "1" + result
                else:
                    break
            return result
        except Exception:
            return ""

    def _make_tx_card(self, parent, tx):
        """Erstellt eine Transaktions-Karte."""
        symbol = tx.get("symbol", "?")
        logger.debug(f"_make_tx_card: {symbol} {tx.get('direction','?')} {tx.get('value',0)}")
                # Notiz vorhanden?
        tx_hash_check = tx.get("hash", "")
        has_note = tx_hash_check in self._tx_notes
        card_height = 82 if has_note else 65
        card = ctk.CTkFrame(parent, fg_color=COLOR_CARD, corner_radius=8, height=card_height)
        card.pack(fill="x", pady=(0, 4))
        card.pack_propagate(False)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=12, pady=8)

        # Links: Richtung + Symbol
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="y")

        direction = tx.get("direction", "sent")
        arrow = "📥" if direction == "received" else "📤" if direction == "sent" else "🔗"
        dir_color = COLOR_SUCCESS if direction == "received" else COLOR_ERROR if direction == "sent" else COLOR_TEXT_DIM
        symbol = tx.get("symbol", "?")

        # Symbol-Farbe
        sym_colors = {
            "DOI": COLOR_DOI, "TRX": COLOR_TRX, "USDT": COLOR_USDT,
            "ETH": COLOR_ETH, "wDOI": COLOR_WDOI,
        }
        sym_color = sym_colors.get(symbol, COLOR_TEXT)

        ctk.CTkLabel(
            left, text=f"{arrow}  {symbol}",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=sym_color,
        ).pack(anchor="w")

        # Zeitstempel
        ts = tx.get("timestamp", 0)
        if ts > 0:
            from datetime import datetime
            try:
                dt = datetime.fromtimestamp(ts)
                time_str = dt.strftime("%d.%m.%Y %H:%M")
            except Exception:
                time_str = "–"
        else:
            # Fallback: Block-Höhe anzeigen
            block = tx.get("block", 0)
            if block > 0:
                time_str = f"Block {block}"
            else:
                time_str = "–"

        # Bestaetigungs-Status ermitteln
        block = tx.get("block", tx.get("height", 0))
        symbol = tx.get("symbol", "?")
        if block == 0 or block is None:
            confirm_str = "Unbestaetigt"
            confirm_color = COLOR_WARNING
        else:
            # Bestaetigungen berechnen
            chain_key = "eth" if symbol in ("ETH", "wDOI") else "doi"
            current_height = self._block_heights.get(chain_key, 0)
            if current_height > 0 and block > 0:
                confirmations = current_height - block + 1
                if confirmations < 1:
                    confirmations = 1
                confirm_str = f"{confirmations} Best."
            else:
                confirm_str = "Bestaetigt"
            confirm_color = COLOR_TEXT_DIM

        ctk.CTkLabel(
            left, text=f"{time_str}  ·  {confirm_str}",
            font=ctk.CTkFont(size=11),
            text_color=confirm_color if block == 0 or block is None else COLOR_TEXT_DIM,
        ).pack(anchor="w")

        # Rechts: Betrag
        right = ctk.CTkFrame(inner, fg_color="transparent")
        right.pack(side="right", fill="y")

        value = tx.get("value", 0)
        if value == 0 and direction == "unknown":
            val_str = "–"
            dir_color = COLOR_TEXT_DIM
        else:
            prefix = "+" if direction == "received" else "−"
            val_str = f"{prefix}{value:.6f}" if value < 1000 else f"{prefix}{value:.2f}"

        ctk.CTkLabel(
            right, text=f"{val_str} {symbol}",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=dir_color,
        ).pack(anchor="e")

        # TX-Hash (gekuerzt) – klickbar zum Kopieren (v0.9.6)
        tx_hash = tx.get("hash", "")
        tx_hash_label = None
        if tx_hash:
            tx_hash_short = shorten_addr(tx_hash, 8)
            tx_hash_label = ctk.CTkLabel(
                right, text=tx_hash_short,
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=COLOR_TEXT_DIM,
                cursor="hand2",
            )
            tx_hash_label.pack(anchor="e")

        # Notiz anzeigen (falls vorhanden)
        if tx_hash and tx_hash in self._tx_notes:
            ctk.CTkLabel(
                card, text=f"📝 {self._tx_notes[tx_hash]}",
                font=ctk.CTkFont(size=10),
                text_color=COLOR_ACCENT,
                anchor="w",
            ).pack(fill="x", padx=14, pady=(0, 4))

        # Klick-Logik (v0.9.6 / Korrektur):
        # Tkinter propagiert <Button-1> NICHT automatisch zu Parent-Widgets.
        # Wir binden deshalb explizit rekursiv auf jedes Widget der Karte –
        # mit dem TX-Hash-Label als Sonderfall (Hash kopieren).
        if tx_hash:
            def _on_hash_click(e, h=tx_hash, lbl=tx_hash_label,
                               short=tx_hash_short if tx_hash_label else ""):
                self._copy_to_clipboard(h)
                try:
                    lbl.configure(text="📋 kopiert!", text_color=COLOR_ACCENT)
                    self.after(1500, lambda l=lbl, t=short:
                               l.configure(text=t, text_color=COLOR_TEXT_DIM))
                except Exception:
                    pass
                return "break"

            def _on_card_click(e, h=tx_hash):
                self._edit_tx_note(h)
                return "break"

            # Sonderfall: das TX-Hash-Label fängt selbst (eigener Handler)
            if tx_hash_label is not None:
                tx_hash_label.bind("<Button-1>", _on_hash_click)

            # Alles übrige in der Karte → Notiz bearbeiten
            def _bind_card_clicks(w, skip=tx_hash_label):
                if w is skip:
                    return
                try:
                    w.bind("<Button-1>", _on_card_click)
                except Exception:
                    pass
                try:
                    children = w.winfo_children()
                except Exception:
                    children = []
                for c in children:
                    _bind_card_clicks(c, skip)

            _bind_card_clicks(card)

    # ── Exchange ──

    def _create_exchange_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self._pages["exchange"] = page

        # Scrollable container
        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            scroll, text="XT.com Exchange",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", pady=(5, 10))

        # ── Preis-Card ──
        price_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        price_card.pack(fill="x", pady=(0, 8))

        self._xt_price_label = ctk.CTkLabel(
            price_card, text="DOI/USDT: –",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color=COLOR_DOI,
        )
        self._xt_price_label.pack(padx=15, pady=(12, 2))

        self._xt_stats_label = ctk.CTkLabel(
            price_card, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        )
        self._xt_stats_label.pack(padx=15, pady=(0, 10))

        # ── Orderbuch ──
        ob_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        ob_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            ob_frame, text="Orderbuch",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        self._ob_text = ctk.CTkTextbox(
            ob_frame, font=ctk.CTkFont(family="Consolas", size=12),
            height=180, state="disabled",
            fg_color="#141c2f",
        )
        self._ob_text.pack(fill="x", padx=10, pady=(0, 10))

        # ── VWAP-Berechnung ──
        vwap_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        vwap_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            vwap_frame, text="VWAP-Berechnung (Kauf/Verkauf-Simulation)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        vwap_input = ctk.CTkFrame(vwap_frame, fg_color="transparent")
        vwap_input.pack(fill="x", padx=15, pady=(0, 5))

        self._vwap_side = ctk.CTkSegmentedButton(
            vwap_input, values=["Kaufen", "Verkaufen"],
            font=ctk.CTkFont(size=12), width=180,
            selected_color=COLOR_ACCENT,
        )
        self._vwap_side.set("Kaufen")
        self._vwap_side.pack(side="left", padx=(0, 10))

        self._vwap_amount = ctk.CTkEntry(
            vwap_input, height=32, width=120,
            font=ctk.CTkFont(size=13),
            placeholder_text="Menge DOI",
        )
        self._vwap_amount.pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            vwap_input, text="Berechnen", height=32, width=100,
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._calc_vwap,
        ).pack(side="left")

        self._vwap_result = ctk.CTkLabel(
            vwap_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM, anchor="w",
        )
        self._vwap_result.pack(fill="x", padx=15, pady=(0, 10))

        # ── XT.com Kontosaldo ──
        bal_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        bal_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            bal_frame, text="XT.com Kontosaldo",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        self._xt_balance_text = ctk.CTkTextbox(
            bal_frame, font=ctk.CTkFont(family="Consolas", size=12),
            height=100, state="disabled",
            fg_color="#141c2f",
        )
        self._xt_balance_text.pack(fill="x", padx=10, pady=(0, 10))

        # ── Order erstellen ──
        order_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        order_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            order_frame, text="Order erstellen (DOI/USDT)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        order_row1 = ctk.CTkFrame(order_frame, fg_color="transparent")
        order_row1.pack(fill="x", padx=15, pady=(0, 5))

        self._order_side = ctk.CTkSegmentedButton(
            order_row1, values=["BUY", "SELL"],
            font=ctk.CTkFont(size=12), width=140,
            selected_color=COLOR_SUCCESS,
        )
        self._order_side.set("BUY")
        self._order_side.pack(side="left", padx=(0, 10))

        self._order_type = ctk.CTkSegmentedButton(
            order_row1, values=["LIMIT", "MARKET"],
            font=ctk.CTkFont(size=12), width=160,
            selected_color=COLOR_ACCENT,
        )
        self._order_type.set("LIMIT")
        self._order_type.pack(side="left")

        order_row2 = ctk.CTkFrame(order_frame, fg_color="transparent")
        order_row2.pack(fill="x", padx=15, pady=(0, 5))

        ctk.CTkLabel(order_row2, text="Preis:", font=ctk.CTkFont(size=12),
                      text_color=COLOR_TEXT_DIM).pack(side="left")
        self._order_price = ctk.CTkEntry(
            order_row2, height=30, width=120,
            font=ctk.CTkFont(size=12), placeholder_text="0.00000",
        )
        self._order_price.pack(side="left", padx=(5, 15))

        ctk.CTkLabel(order_row2, text="Menge:", font=ctk.CTkFont(size=12),
                      text_color=COLOR_TEXT_DIM).pack(side="left")
        self._order_quantity = ctk.CTkEntry(
            order_row2, height=30, width=120,
            font=ctk.CTkFont(size=12), placeholder_text="0.00",
        )
        self._order_quantity.pack(side="left", padx=(5, 0))

        order_row3 = ctk.CTkFrame(order_frame, fg_color="transparent")
        order_row3.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkButton(
            order_row3, text="📝 Order aufgeben", height=35,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._place_order,
        ).pack(side="left", padx=(0, 10))

        self._order_status = ctk.CTkLabel(
            order_row3, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        )
        self._order_status.pack(side="left", fill="x")

        # ── Offene Orders ──
        open_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        open_frame.pack(fill="x", pady=(0, 8))

        open_header = ctk.CTkFrame(open_frame, fg_color="transparent")
        open_header.pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            open_header, text="Offene Orders",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            open_header, text="❌ Alle stornieren", height=28, width=130,
            font=ctk.CTkFont(size=11),
            fg_color=COLOR_ERROR, hover_color="#cc3344",
            command=self._cancel_all_orders,
        ).pack(side="right")

        self._open_orders_text = ctk.CTkTextbox(
            open_frame, font=ctk.CTkFont(family="Consolas", size=12),
            height=80, state="disabled",
            fg_color="#141c2f",
        )
        self._open_orders_text.pack(fill="x", padx=10, pady=(0, 10))

        # ── Deposit/Withdrawal Status ──
        dw_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        dw_frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(
            dw_frame, text="Deposit/Withdrawal Status",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        self._dw_status_label = ctk.CTkLabel(
            dw_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM, anchor="w",
            wraplength=600, justify="left",
        )
        self._dw_status_label.pack(fill="x", padx=15, pady=(0, 10))

        # ── Aktualisieren-Button ──
        ctk.CTkButton(
            scroll, text="🔄  Alles aktualisieren",
            font=ctk.CTkFont(size=13),
            height=35, width=180,
            fg_color=COLOR_CARD, hover_color="#2a3a5c",
            border_width=1, border_color=COLOR_ACCENT,
            command=self._refresh_exchange,
        ).pack(pady=(5, 15))

    # ── Info/Settings ──

    def _create_settings_page(self):
        page = ctk.CTkFrame(self.content, fg_color="transparent")
        self._pages["settings"] = page

        scroll = ctk.CTkScrollableFrame(page, fg_color="transparent")
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            scroll, text="Einstellungen & Info",
            font=ctk.CTkFont(size=22, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", pady=(5, 10))

        # ── API-Keys ──
        api_frame = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        api_frame.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            api_frame, text="🔑  API-Schlüssel",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 8))

        # TronGrid
        ctk.CTkLabel(
            api_frame, text="TronGrid API-Key:",
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 2))

        self._tron_api_entry = ctk.CTkEntry(
            api_frame, height=32, font=ctk.CTkFont(size=12),
            placeholder_text="TronGrid API-Key eingeben...",
        )
        self._tron_api_entry.pack(fill="x", padx=15, pady=(0, 8))

        # XT.com API-Key
        ctk.CTkLabel(
            api_frame, text="XT.com API-Key:",
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 2))

        self._xt_key_entry = ctk.CTkEntry(
            api_frame, height=32, font=ctk.CTkFont(size=12),
            placeholder_text="XT.com API-Key eingeben...",
        )
        self._xt_key_entry.pack(fill="x", padx=15, pady=(0, 8))

        # XT.com API-Secret
        ctk.CTkLabel(
            api_frame, text="XT.com API-Secret:",
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 2))

        self._xt_secret_entry = ctk.CTkEntry(
            api_frame, height=32, font=ctk.CTkFont(size=12),
            show="●",
            placeholder_text="XT.com API-Secret eingeben...",
        )
        self._xt_secret_entry.pack(fill="x", padx=15, pady=(0, 8))

        # Speichern-Button
        api_btn_frame = ctk.CTkFrame(api_frame, fg_color="transparent")
        api_btn_frame.pack(fill="x", padx=15, pady=(0, 10))

        ctk.CTkButton(
            api_btn_frame, text="💾  API-Keys speichern",
            height=35, font=ctk.CTkFont(size=13),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._save_api_keys,
        ).pack(side="left", padx=(0, 10))

        self._api_status = ctk.CTkLabel(
            api_btn_frame, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        )
        self._api_status.pack(side="left")

        # Aktuelle Keys laden
        self._load_api_keys_into_fields()

        # ── App-Info ──
        info_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        info_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            info_card, text="ℹ️  App-Info",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        info_items = [
            ("App", f"{APP_NAME} v{APP_VERSION} (Beta)"),
            ("Copyright", COPYRIGHT),
            ("Lizenz", LICENSE_INFO),
            ("GitHub", GITHUB_URL),
            ("Chains", "DOI · TRX · USDT TRC-20 · ETH · wDOI ERC-20"),
            ("Exchange", "XT.com (Spot)"),
            ("Verschlüsselung", "AES-256-GCM · scrypt KDF"),
            ("Hinweis", "⚠ Beta – bitte nur kleine Beträge verwalten!"),
        ]

        for key, val in info_items:
            row = ctk.CTkFrame(info_card, fg_color="transparent")
            row.pack(fill="x", padx=15, pady=3)
            ctk.CTkLabel(
                row, text=f"{key}:", width=130,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=COLOR_TEXT_DIM, anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                row, text=val,
                font=ctk.CTkFont(size=13),
                text_color=COLOR_TEXT, anchor="w",
            ).pack(side="left", fill="x", expand=True)

        # Extra padding
        ctk.CTkLabel(info_card, text="").pack(pady=3)

        # Wallet-Info
        self._wallet_info_label = ctk.CTkLabel(
            scroll, text="",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
            wraplength=600, justify="left",
        )
        self._wallet_info_label.pack(pady=(5, 0), anchor="w")

        # Wallet speichern
        ctk.CTkButton(
            scroll, text="💾  Wallet speichern",
            font=ctk.CTkFont(size=14),
            height=38,
            fg_color=COLOR_CARD, hover_color="#2a3a5c",
            border_width=1, border_color=COLOR_ACCENT,
            command=self._save_wallet,
        ).pack(pady=(10, 10))

        # ── Sicherheit ──
        safety_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        safety_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            safety_card, text="🛡  Sicherheit",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 8))

        # Tageslimit
        limit_row = ctk.CTkFrame(safety_card, fg_color="transparent")
        limit_row.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            limit_row, text="Tageslimit (EUR):",
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_DIM,
        ).pack(side="left")

        self._limit_entry = ctk.CTkEntry(
            limit_row, width=100, height=30,
            font=ctk.CTkFont(size=12),
            placeholder_text="0 = aus",
        )
        self._limit_entry.pack(side="left", padx=10)
        if self._daily_limit_eur > 0:
            self._limit_entry.insert(0, str(int(self._daily_limit_eur)))

        ctk.CTkLabel(
            limit_row, text="(0 = kein Limit)",
            font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM,
        ).pack(side="left")

        # Undo-Timer
        undo_row = ctk.CTkFrame(safety_card, fg_color="transparent")
        undo_row.pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkLabel(
            undo_row, text="Undo-Timer (Sek.):",
            font=ctk.CTkFont(size=12), text_color=COLOR_TEXT_DIM,
        ).pack(side="left")

        self._undo_var = ctk.StringVar(value=str(self._undo_seconds))
        self._undo_menu = ctk.CTkOptionMenu(
            undo_row, width=80, height=30,
            values=["0", "10", "30", "60"],
            variable=self._undo_var,
            font=ctk.CTkFont(size=12),
            fg_color=COLOR_BG,
        )
        self._undo_menu.pack(side="left", padx=10)

        ctk.CTkLabel(
            undo_row, text="(0 = sofort senden)",
            font=ctk.CTkFont(size=10), text_color=COLOR_TEXT_DIM,
        ).pack(side="left")

        # Speichern
        ctk.CTkButton(
            safety_card, text="💾  Sicherheits-Einstellungen speichern",
            height=32, font=ctk.CTkFont(size=12),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=self._save_safety_ui,
        ).pack(padx=15, pady=(0, 12))

        # ── Debug / Diagnose ──
        debug_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        debug_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            debug_card, text="🔍  Wallet-Diagnose",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            debug_card,
            text="Zeigt technische Details zum Wallet-Status (fuer Fehlerbehebung).",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkButton(
            debug_card, text="🔍  Diagnose ausfuehren",
            height=38, font=ctk.CTkFont(size=13),
            fg_color="#2a4a6c", hover_color="#3a5a7c",
            command=self._show_debug_info,
        ).pack(padx=15, pady=(0, 12))

        # ── Seed-Phrase anzeigen ──
        seed_card = ctk.CTkFrame(scroll, fg_color=COLOR_CARD, corner_radius=10)
        seed_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            seed_card, text="🔐  Seed-Phrase (Backup)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=COLOR_TEXT, anchor="w",
        ).pack(fill="x", padx=15, pady=(10, 5))

        ctk.CTkLabel(
            seed_card,
            text="Zeigt Ihre 24-Wort Seed-Phrase an. Passwort erforderlich.",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM, anchor="w",
        ).pack(fill="x", padx=15, pady=(0, 8))

        ctk.CTkButton(
            seed_card, text="👁  Seed-Phrase anzeigen",
            height=38, font=ctk.CTkFont(size=13),
            fg_color="#6B2737", hover_color="#8B3747",
            command=self._show_seed_phrase,
        ).pack(padx=15, pady=(0, 12))

    def _load_api_keys_into_fields(self):
        """Lädt gespeicherte API-Keys in die Eingabefelder."""
        config = load_config()
        tron_key = config.get("tron", {}).get("api_key", "")
        xt_key = config.get("xt_com", {}).get("api_key", "")
        xt_secret = config.get("xt_com", {}).get("api_secret", "")

        if tron_key:
            self._tron_api_entry.insert(0, tron_key)
        if xt_key:
            self._xt_key_entry.insert(0, xt_key)
        if xt_secret:
            self._xt_secret_entry.insert(0, xt_secret)

    def _save_api_keys(self):
        """Speichert API-Keys in config.yaml und aktualisiert Clients."""
        config = load_config()

        tron_key = self._tron_api_entry.get().strip()
        xt_key = self._xt_key_entry.get().strip()
        xt_secret = self._xt_secret_entry.get().strip()

        if tron_key:
            config.setdefault("tron", {})["api_key"] = tron_key
        if xt_key or xt_secret:
            config.setdefault("xt_com", {})
            if xt_key:
                config["xt_com"]["api_key"] = xt_key
            if xt_secret:
                config["xt_com"]["api_secret"] = xt_secret

        if save_config(config):
            self._api_status.configure(
                text="✅ Gespeichert! Neustart für volle Wirkung.",
                text_color=COLOR_SUCCESS,
            )
            # XT-Client sofort aktualisieren
            if XTClient and xt_key:
                self.xt = XTClient(api_key=xt_key, api_secret=xt_secret)
        else:
            self._api_status.configure(
                text="❌ Speichern fehlgeschlagen!",
                text_color=COLOR_ERROR,
            )

    # ──────────────────────────────────────
    # Startup
    # ──────────────────────────────────────

    def _startup(self):
        """Startup-Prozess: Wallets laden mit Auto-Reload."""
        # Tab-Konfiguration laden
        self._load_tab_config()
        self._render_visible_tabs()

        # Abwaertskompatibilitaet: alte wallet.dat als Slot 0
        if os.path.exists(WALLET_FILE) and not os.path.exists("wallet-1.dat"):
            self._wallet_slots[0]["dat_file"] = WALLET_FILE

        # Pruefen ob zuvor geladene Wallets existieren
        previous_wallets = []
        for i, slot in enumerate(self._wallet_slots):
            dat = slot.get("dat_file")
            if dat and os.path.exists(dat) and slot.get("was_loaded", False):
                previous_wallets.append((i, slot["name"], dat))

        if previous_wallets:
            # Auto-Reload Dialog anzeigen
            if self._ask_reload(previous_wallets):
                # Passwort pro Wallet abfragen und laden
                if self._reload_wallets(previous_wallets):
                    return  # Erfolgreich geladen
                # Falls fehlgeschlagen, normaler Start

        # Normaler Start: StartupDialog fuer Slot 0
        self._normal_startup()

    def _ask_reload(self, wallets):
        """Fragt ob die zuletzt geoeffneten Wallets geladen werden sollen."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"{APP_NAME} – Wallets laden")
        dialog.geometry("460x280")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        dialog._result = None

        ctk.CTkLabel(
            dialog, text="Letzte Wallets wiederherstellen?",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_ACCENT,
        ).pack(pady=(25, 10))

        # Liste der Wallets anzeigen
        names = ", ".join([f"{name}" for _, name, _ in wallets])
        ctk.CTkLabel(
            dialog,
            text=f"Beim letzten Mal waren folgende Wallets geladen:",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT,
        ).pack(pady=(5, 2))

        ctk.CTkLabel(
            dialog,
            text=names,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=COLOR_TEXT,
            wraplength=400,
        ).pack(pady=(2, 15))

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=40)

        def yes():
            dialog._result = True
            dialog.destroy()

        def no():
            dialog._result = False
            dialog.destroy()

        ctk.CTkButton(
            btn_frame, text="Ja, alle laden",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=45,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            command=yes,
        ).pack(fill="x", pady=(0, 10))

        ctk.CTkButton(
            btn_frame, text="Nein, neu starten",
            font=ctk.CTkFont(size=14),
            height=40,
            fg_color=COLOR_CARD,
            hover_color="#2a3a5c",
            border_width=1,
            border_color=COLOR_ACCENT,
            command=no,
        ).pack(fill="x")

        self.wait_window(dialog)
        return dialog._result is True

    def _ask_password_for_wallet(self, wallet_name, dat_file):
        """Fragt das Passwort fuer ein bestimmtes Wallet ab."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Passwort – {wallet_name}")
        dialog.geometry("420x200")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        dialog._password = None

        ctk.CTkLabel(
            dialog,
            text=f"Passwort fuer {wallet_name}:",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color=COLOR_TEXT,
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            dialog,
            text=f"Datei: {dat_file}",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 10))

        pw_entry = ctk.CTkEntry(
            dialog, show="*", width=300, height=38,
            font=ctk.CTkFont(size=14),
            placeholder_text="Passwort eingeben...",
        )
        pw_entry.pack(pady=5)

        def confirm(event=None):
            pw = pw_entry.get().strip()
            if pw:
                dialog._password = pw
                dialog.destroy()

        def skip():
            dialog._password = None
            dialog.destroy()

        pw_entry.bind("<Return>", confirm)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(fill="x", padx=40, pady=10)

        ctk.CTkButton(
            btn_frame, text="Entsperren", height=36,
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            command=confirm,
        ).pack(side="left", expand=True, fill="x", padx=(0, 5))

        ctk.CTkButton(
            btn_frame, text="Ueberspringen", height=36,
            fg_color=COLOR_CARD, hover_color="#2a3a5c",
            border_width=1, border_color=COLOR_ACCENT,
            command=skip,
        ).pack(side="right", expand=True, fill="x", padx=(5, 0))

        dialog.after(100, pw_entry.focus_set)
        self.wait_window(dialog)
        return dialog._password

    def _reload_wallets(self, wallets):
        """Laedt alle zuvor geoeffneten Wallets mit Passwort-Abfrage."""
        config = load_config()
        tron_api_key = config.get("tron", {}).get("api_key", "")
        xt_conf = config.get("xt_com", {})

        loaded_any = False
        first_loaded_slot = None

        for slot_idx, wallet_name, dat_file in wallets:
            password = self._ask_password_for_wallet(wallet_name, dat_file)

            if password is None:
                # Uebersprungen
                continue

            try:
                wm = WalletManager(tron_api_key=tron_api_key)
                wm.load(dat_file, password)

                slot = self._wallet_slots[slot_idx]
                slot["wm"] = wm
                slot["dat_file"] = dat_file
                slot["loaded"] = True
                slot["balances"] = {"doi": 0, "trx": 0, "usdt": 0, "eth": 0, "wdoi": 0}
                slot["doi_connected"] = False
                slot["price_doi"] = 0.0

                if XTClient:
                    slot["xt"] = XTClient(
                        api_key=xt_conf.get("api_key", ""),
                        api_secret=xt_conf.get("api_secret", ""),
                    )

                if first_loaded_slot is None:
                    first_loaded_slot = slot_idx

                loaded_any = True

            except Exception as e:
                self._show_error(f"Fehler beim Laden von {wallet_name}: {e}")
                continue

        if loaded_any:
            # Ersten geladenen Slot aktivieren
            self._active_slot = first_loaded_slot
            slot = self._wallet_slots[first_loaded_slot]
            self.wm = slot["wm"]
            self.xt = slot.get("xt")
            self._balances = slot["balances"].copy()
            self._doi_connected = slot["doi_connected"]
            self._price_doi = slot["price_doi"]

            self._update_tab_buttons()
            self._save_tab_config()
            self._update_addresses()
            self._update_receive_page()

            # Verbindungen fuer alle geladenen Wallets im Hintergrund
            threading.Thread(target=self._connect_all_loaded, daemon=True).start()
            return True

        return False

    def _connect_all_loaded(self):
        """Verbindet alle geladenen Wallets im Hintergrund."""
        for i, slot in enumerate(self._wallet_slots):
            if not slot["loaded"] or not slot["wm"]:
                continue

            wm = slot["wm"]

            # DOI
            try:
                wm.connect_doi()
                slot["doi_connected"] = True
            except Exception:
                slot["doi_connected"] = False

            # ETH
            try:
                if wm.eth:
                    wm.connect_eth()
            except Exception:
                pass

            # Salden laden
            try:
                doi_bal = wm.doi.get_balance(force_refresh=True)
                slot["balances"]["doi"] = doi_bal.get("confirmed_doi", 0)
            except Exception:
                pass
            try:
                slot["balances"]["trx"] = wm.tron.get_trx_balance()
            except Exception:
                pass
            try:
                slot["balances"]["usdt"] = wm.tron.get_usdt_balance()
            except Exception:
                pass
            if wm.eth:
                try:
                    slot["balances"]["eth"] = wm.eth.get_eth_balance()
                except Exception:
                    pass
                try:
                    slot["balances"]["wdoi"] = wm.eth.get_wdoi_balance()
                except Exception:
                    pass

        # DOI-Preis einmal holen
        for slot in self._wallet_slots:
            if slot.get("xt"):
                try:
                    t = slot["xt"].get_ticker()
                    price = t["price"]
                    # Preis fuer alle Slots setzen
                    for s in self._wallet_slots:
                        if s["loaded"]:
                            s["price_doi"] = price
                    break
                except Exception:
                    pass

        # Block-Hoehen aktualisieren (v0.9.6: get_server_info gibt's nicht mehr,
        # nutze get_tip aus v0.9.5 + History-Max als Fallback)
        for slot in self._wallet_slots:
            if slot["loaded"] and slot["wm"]:
                try:
                    if slot["wm"].doi and slot["wm"].doi.electrum:
                        ec = slot["wm"].doi.electrum
                        h = 0
                        try:
                            tip = ec.get_tip()
                            if isinstance(tip, dict) and tip.get("height", 0) > 0:
                                h = tip["height"]
                        except Exception:
                            pass
                        if h == 0:
                            # Fallback: max height aus History
                            try:
                                hist = slot["wm"].doi.get_history()
                                if isinstance(hist, list):
                                    h = max((tx.get("height", 0) for tx in hist
                                             if tx.get("height", 0) > 0), default=0)
                            except Exception:
                                pass
                        if h > 0:
                            self._block_heights["doi"] = h
                except Exception:
                    pass
                try:
                    if slot["wm"].eth and hasattr(slot["wm"].eth, '_w3') and slot["wm"].eth._w3:
                        self._block_heights["eth"] = slot["wm"].eth._w3.eth.block_number
                except Exception:
                    pass
                break  # Ein Mal reicht

        # Aktiven Slot aktualisieren – im Main-Thread, damit ein Tab-Wechsel
        # waehrend des Ladens keinen veralteten Slot anzeigt (v0.9.6)
        def _apply():
            active = self._wallet_slots[self._active_slot]
            self._balances = active["balances"].copy()
            self._doi_connected = active["doi_connected"]
            self._price_doi = active["price_doi"]
            self._refresh_dashboard()
            self.conn_label.configure(
                text=self._get_conn_text(), text_color=COLOR_TEXT_DIM)

        self._safe_after(0, _apply)

    def _normal_startup(self):
        """Normaler Start mit StartupDialog fuer Slot 0."""
        dialog = StartupDialog(self)
        self.wait_window(dialog)

        if dialog.result is None:
            self.destroy()
            return

        action, data = dialog.result
        config = load_config()
        tron_api_key = config.get("tron", {}).get("api_key", "")

        try:
            self.wm = WalletManager(tron_api_key=tron_api_key)

            if action == "create":
                mnemonic = self.wm.create(data["password"])
                dat_file = "wallet-1.dat"
                self.wm.save(dat_file)
                self._wallet_slots[0]["dat_file"] = dat_file
                seed_dlg = SeedDialog(self, mnemonic)
                self.wait_window(seed_dlg)

            elif action == "restore":
                self.wm.restore(data["mnemonic"], data["password"])
                dat_file = "wallet-1.dat"
                self.wm.save(dat_file)
                self._wallet_slots[0]["dat_file"] = dat_file

            elif action == "load":
                self.wm.load(data["path"], data["password"])
                self._wallet_slots[0]["dat_file"] = data["path"]

        except Exception as e:
            self._show_error(f"Wallet-Fehler: {e}")
            self.after(100, self._startup)
            return

        # XT.com Client
        if XTClient:
            xt_conf = config.get("xt_com", {})
            self.xt = XTClient(
                api_key=xt_conf.get("api_key", ""),
                api_secret=xt_conf.get("api_secret", ""),
            )

        # Slot 0 als geladen markieren
        self._wallet_slots[0]["wm"] = self.wm
        self._wallet_slots[0]["xt"] = self.xt
        self._wallet_slots[0]["loaded"] = True
        self._active_slot = 0
        self._update_tab_buttons()
        self._save_tab_config()

        # UI aktualisieren
        self._update_addresses()
        self._update_receive_page()

        # Verbindungen im Hintergrund
        threading.Thread(target=self._connect_and_refresh, daemon=True).start()

    def _connect_and_refresh(self):
        """
        Hintergrund: DOI verbinden + Salden laden.

        Slot-gebunden: Der Slot-Kontext (Index, wm, xt) wird beim Thread-Start
        eingefroren und alle Ergebnisse landen im Slot-eigenen Speicher.
        UI-Updates erfolgen nur, wenn der Slot beim Apply noch aktiv ist –
        sonst wuerde ein Tab-Wechsel waehrend des Ladens die Daten von
        Wallet A in Slot B anzeigen/speichern.
        """
        slot_idx = self._active_slot
        slot = self._wallet_slots[slot_idx]
        wm = slot["wm"]
        xt = slot.get("xt")
        if not wm:
            return

        def _update_conn():
            if slot_idx != self._active_slot:
                return
            self._doi_connected = slot["doi_connected"]
            self.conn_label.configure(
                text=self._get_conn_text(), text_color=COLOR_TEXT_DIM)

        # DOI ElectrumX
        try:
            wm.connect_doi()
            slot["doi_connected"] = True
        except Exception:
            slot["doi_connected"] = False

        self._safe_after(0, _update_conn)

        # ETH RPC
        try:
            if wm.eth:
                wm.connect_eth()
        except Exception:
            pass

        # Verbindungsstatus nach ETH-Connect aktualisieren
        self._safe_after(0, _update_conn)

        # Block-Hoehen aktualisieren (DOI)
        # v0.9.6: get_server_info()/_client.call existieren nicht in unserem Client.
        # Nutze stattdessen das in v0.9.5 ergaenzte get_tip().
        try:
            if wm.doi and wm.doi.electrum:
                ec = wm.doi.electrum
                h = 0
                # Primaer: get_tip (blockchain.headers.subscribe)
                try:
                    tip = ec.get_tip()
                    if isinstance(tip, dict) and tip.get("height", 0) > 0:
                        h = tip["height"]
                except Exception:
                    pass
                # Fallback: max height aus eigener TX-History
                if h == 0:
                    try:
                        hist = wm.doi.get_history()
                        if isinstance(hist, list):
                            h = max((tx.get("height", 0) for tx in hist
                                     if tx.get("height", 0) > 0), default=0)
                    except Exception:
                        pass
                if h > 0:
                    self._block_heights["doi"] = h
        except Exception:
            pass
        try:
            if wm.eth and hasattr(wm.eth, '_w3') and wm.eth._w3:
                self._block_heights["eth"] = wm.eth._w3.eth.block_number
        except Exception:
            pass

        # Salden in den Slot-eigenen Speicher laden
        self._load_balances(wm, slot["balances"])

        # DOI-Preis
        if xt:
            try:
                t = xt.get_ticker()
                slot["price_doi"] = t["price"]
            except Exception:
                pass

        # Ergebnisse nur uebernehmen, wenn der Slot noch aktiv ist
        def _apply():
            if slot_idx != self._active_slot:
                return
            self._balances = slot["balances"].copy()
            self._doi_connected = slot["doi_connected"]
            self._price_doi = slot["price_doi"]
            self._refresh_dashboard()

        self._safe_after(0, _apply)

    def _get_conn_text(self):
        doi = "✅" if self._doi_connected else "❌"
        tron = "✅" if (self.wm and self.wm.tron) else "❌"
        eth = "✅" if (self.wm and self.wm.eth and self.wm.eth.is_connected) else "❌"
        return f"DOI {doi}  ·  Tron {tron}  ·  ETH {eth}"

    # ──────────────────────────────────────
    # Salden
    # ──────────────────────────────────────

    def _load_balances(self, wm, balances):
        """
        Lädt Salden des uebergebenen Wallets in das uebergebene Dict.

        Slot-gebunden (v0.9.6): wm + Ziel-Dict werden vom Aufrufer beim
        Thread-Start eingefroren, damit ein Tab-Wechsel waehrend des Ladens
        keine Salden in den falschen Slot schreibt.
        """
        if not wm:
            return

        try:
            doi_bal = wm.doi.get_balance(force_refresh=True)
            balances["doi"] = doi_bal.get("confirmed_doi", 0)
        except Exception:
            pass

        try:
            balances["trx"] = wm.tron.get_trx_balance()
        except Exception:
            pass

        try:
            balances["usdt"] = wm.tron.get_usdt_balance()
        except Exception:
            pass

        if wm.eth:
            try:
                balances["eth"] = wm.eth.get_eth_balance()
            except Exception:
                pass

            try:
                balances["wdoi"] = wm.eth.get_wdoi_balance()
            except Exception:
                pass

    def _refresh_balances_async(self):
        """Salden im Hintergrund aktualisieren."""
        self.conn_label.configure(text="⏳ Lade Salden...", text_color=COLOR_WARNING)
        slot_idx = self._active_slot
        threading.Thread(target=self._do_refresh, args=(slot_idx,), daemon=True).start()

    def _do_refresh(self, slot_idx=None):
        """Hintergrund-Refresh der Salden (slot-gebunden, siehe _load_balances)."""
        if slot_idx is None:
            slot_idx = self._active_slot
        slot = self._wallet_slots[slot_idx]
        wm = slot["wm"]
        xt = slot.get("xt")
        if not wm:
            return

        self._load_balances(wm, slot["balances"])
        if xt:
            try:
                t = xt.get_ticker()
                slot["price_doi"] = t["price"]
            except Exception:
                pass

        def _apply():
            if slot_idx != self._active_slot:
                return
            self._balances = slot["balances"].copy()
            self._price_doi = slot["price_doi"]
            self._refresh_dashboard()
            self.conn_label.configure(
                text=self._get_conn_text(), text_color=COLOR_TEXT_DIM)

        self._safe_after(0, _apply)

    def _refresh_dashboard(self):
        """Dashboard-Anzeige aktualisieren."""
        self._doi_card.configure(text=format_doi(self._balances["doi"]))
        self._trx_card.configure(text=format_trx(self._balances["trx"]))
        self._usdt_card.configure(text=format_usdt(self._balances["usdt"]))
        self._eth_card.configure(text=format_eth(self._balances["eth"]))
        self._wdoi_card.configure(text=format_wdoi(self._balances["wdoi"]))

        if self._price_doi > 0:
            doi_val = self._balances["doi"] * self._price_doi
            wdoi_val = self._balances["wdoi"] * self._price_doi  # wDOI ≈ DOI Preis
            total_usdt = doi_val + wdoi_val + self._balances["trx"] * 0.28 + self._balances["usdt"]
            self._price_label.configure(
                text=f"DOI: {self._price_doi:.6f} USDT  ·  "
                     f"Portfolio: ~{total_usdt:.2f} USDT"
            )

        # Send-Seite auch aktualisieren
        chain = self._send_chain.get()
        self._on_chain_select(chain)

    def _update_addresses(self):
        """Adressen-Labels aktualisieren."""
        if not self.wm:
            return
        addrs = self.wm.primary_addresses
        doi_addr = addrs.get("doi", "–")
        tron_addr = addrs.get("tron", "–")
        eth_addr = addrs.get("eth", "–")

        self._addr_doi_label.configure(text=f"DOI:   {doi_addr}")
        self._addr_tron_label.configure(text=f"Tron:  {tron_addr}")
        self._addr_eth_label.configure(text=f"ETH:   {eth_addr}")

    # ──────────────────────────────────────
    # Senden
    # ──────────────────────────────────────

    def _do_send(self):
        """Transaktion senden."""
        chain = self._send_chain.get()
        addr = self._send_addr.get().strip()
        amount_str = self._send_amount.get().strip()

        # Validierung
        if not addr:
            self._send_status.configure(text="❌ Adresse eingeben!", text_color=COLOR_ERROR)
            return

        if chain == "DOI":
            if not validate_doi_address(addr, bech32_hrp="dc"):
                self._send_status.configure(text="❌ Ungültige DOI-Adresse!", text_color=COLOR_ERROR)
                return
        elif chain in ("ETH", "wDOI"):
            if not validate_eth_address(addr):
                self._send_status.configure(text="❌ Ungültige Ethereum-Adresse!", text_color=COLOR_ERROR)
                return
        else:
            if not validate_tron_address(addr):
                self._send_status.configure(text="❌ Ungültige Tron-Adresse!", text_color=COLOR_ERROR)
                return

        try:
            amount = float(amount_str)
            if amount <= 0:
                raise ValueError
        except ValueError:
            self._send_status.configure(text="❌ Ungültiger Betrag!", text_color=COLOR_ERROR)
            return

        # Saldo prüfen
        bal = self._balances.get(chain.lower(), 0)
        if amount > bal:
            self._send_status.configure(text="❌ Unzureichender Saldo!", text_color=COLOR_ERROR)
            return

        # Bestätigung
        dialog = PasswordConfirmDialog(
            self,
            title="Transaktion bestätigen",
            message=f"Sende {amount} {chain} an\n{shorten_addr(addr)}",
        )
        pw = dialog.get_input()
        if not pw:
            self._send_status.configure(text="Abgebrochen.", text_color=COLOR_TEXT_DIM)
            return

        # Passwort WIRKLICH verifizieren (scrypt, ~1s) – vorher autorisierte
        # jede beliebige nicht-leere Eingabe die Transaktion!
        self._send_status.configure(text="⏳ Prüfe Passwort...", text_color=COLOR_WARNING)
        self.update_idletasks()
        if not self.wm or not self.wm.verify_password(pw):
            self._send_status.configure(text="❌ Falsches Passwort!", text_color=COLOR_ERROR)
            return

        # Tageslimit pruefen (nur Pruefung – verbucht wird erst nach Erfolg)
        if not self._check_daily_limit(amount, chain):
            self._send_status.configure(text="Abgebrochen (Tageslimit).", text_color=COLOR_TEXT_DIM)
            return
        eur_value = self._estimate_eur_value(amount, chain)

        # Undo-Timer
        if not self._show_undo_countdown(chain, addr, amount):
            self._send_status.configure(text="Abgebrochen.", text_color=COLOR_TEXT_DIM)
            return

        # Senden
        self._send_btn.configure(state="disabled", text="⏳ Sende...")
        self._send_status.configure(text="Sende Transaktion...", text_color=COLOR_WARNING)

        # Slot-Kontext einfrieren – ein Tab-Wechsel waehrend des Sendens darf
        # weder das falsche Wallet benutzen noch fremde Slots ueberschreiben.
        slot_idx = self._active_slot
        slot = self._wallet_slots[slot_idx]
        wm = slot["wm"] or self.wm
        self._send_in_progress = True

        def _send_thread():
            try:
                result = wm.send(chain, addr, amount)
                tx_id = result.get("txid", result.get("tx_id", "N/A"))
                self._safe_after(0, lambda: self._send_status.configure(
                    text=f"✅ Gesendet! TX: {shorten_addr(tx_id, 12)}",
                    text_color=COLOR_SUCCESS,
                ))
                # Tageslimit erst NACH erfolgreichem Senden verbuchen –
                # Abbrueche/Fehler duerfen das Limit nicht verbrauchen.
                self._safe_after(0, lambda: self._add_daily_send(eur_value))
                # Salden aktualisieren (in den Slot-eigenen Speicher)
                self._load_balances(wm, slot["balances"])

                def _apply_balances():
                    if slot_idx != self._active_slot:
                        return
                    self._balances = slot["balances"].copy()
                    self._refresh_dashboard()

                self._safe_after(500, _apply_balances)
                # v0.9.6: History async neu laden – damit die soeben gesendete
                # Tx in der Transaktionsliste als unbestätigt erscheint
                def _refresh_hist():
                    if slot_idx == self._active_slot:
                        self._refresh_history_async(force=True)
                self._safe_after(800, _refresh_hist)
            except Exception as e:
                # 'e' wird nach dem except-Block geloescht – fuer das deferred
                # Lambda muss die Meldung vorher gebunden werden (NameError-Fix).
                msg = str(e)
                self._safe_after(0, lambda m=msg: self._send_status.configure(
                    text=f"❌ {m}", text_color=COLOR_ERROR,
                ))
            finally:
                self._send_in_progress = False
                self._safe_after(0, lambda: self._send_btn.configure(
                    state="normal", text="📤  Senden"))

        threading.Thread(target=_send_thread, daemon=True).start()

    # ──────────────────────────────────────
    # Exchange
    # ──────────────────────────────────────

    def _refresh_exchange(self):
        if not self.xt:
            self._xt_price_label.configure(text="XT.com Client nicht verfügbar")
            return

        threading.Thread(target=self._load_exchange_data, daemon=True).start()

    def _load_exchange_data(self):
        try:
            logger.debug(f"Exchange: xt={self.xt}, has_cred={getattr(self.xt, 'has_credentials', '?')}")
            t = self.xt.get_ticker()
            logger.debug(f"Exchange: ticker={t}")
            t24 = self.xt.get_ticker_24h()
            ob = self.xt.get_orderbook(limit=8)

            self.after(0, lambda: self._xt_price_label.configure(
                text=f"DOI/USDT: {t['price']:.6f}"))

            stats = (f"24h: {t24['change_pct']:+.2f}%  ·  "
                     f"H: {t24['high']:.6f}  ·  L: {t24['low']:.6f}  ·  "
                     f"Vol: {t24['volume']:,.0f} DOI  ·  "
                     f"Spread: {ob['spread_pct']:.2f}%")
            self.after(0, lambda: self._xt_stats_label.configure(text=stats))

            # Orderbuch formatieren
            lines = []
            lines.append(f"{'':>6s}  {'Preis':>10s}  {'Menge':>10s}  {'Kumuliert':>10s}")
            lines.append("─" * 42)

            # Asks: billigste unten (am Spread), kumulativ von unten nach oben
            ask_levels = ob["asks"][:6]  # bereits aufsteigend sortiert
            cumul = 0
            ask_cumuls = []
            for a in ask_levels:
                cumul += a["quantity"]
                ask_cumuls.append(cumul)
            # Anzeige: teuerste oben → reversed
            for i in range(len(ask_levels) - 1, -1, -1):
                a = ask_levels[i]
                lines.append(f"{'ASK':>6s}  {a['price']:>10.6f}  {a['quantity']:>10.2f}  {ask_cumuls[i]:>10.2f}")

            # Spread-Linie
            spread_line = f"  ── Spread: {ob['spread']:.6f} ({ob['spread_pct']:.2f}%) ──"
            lines.append(spread_line)

            # Bids: teuerste oben (am Spread), kumulativ von oben nach unten
            cumul = 0
            for b in ob["bids"][:6]:
                cumul += b["quantity"]
                lines.append(f"{'BID':>6s}  {b['price']:>10.6f}  {b['quantity']:>10.2f}  {cumul:>10.2f}")

            ob_text = "\n".join(lines)
            def _update_ob():
                self._ob_text.configure(state="normal")
                self._ob_text.delete("1.0", "end")
                self._ob_text.insert("1.0", ob_text)
                self._ob_text.configure(state="disabled")
            self.after(0, _update_ob)

            # Kontosaldo
            if self.xt.has_credentials:
                try:
                    balances = self.xt.get_balances()
                    logger.debug(f"Exchange: balances={balances[:3] if balances else 'EMPTY'}")
                    bal_lines = [f"{'Währung':<10s}  {'Verfügbar':>14s}  {'Gesperrt':>14s}"]
                    bal_lines.append("─" * 42)
                    for b in balances:
                        if b["available"] > 0 or b.get("frozen", 0) > 0:
                            bal_lines.append(
                                f"{b['currency'].upper():<10s}  "
                                f"{b['available']:>14.6f}  "
                                f"{b.get('frozen', 0):>14.6f}"
                            )
                    bal_text = "\n".join(bal_lines)
                    def _update_bal():
                        self._xt_balance_text.configure(state="normal")
                        self._xt_balance_text.delete("1.0", "end")
                        self._xt_balance_text.insert("1.0", bal_text)
                        self._xt_balance_text.configure(state="disabled")
                    self.after(0, _update_bal)
                except Exception as e:
                    # 'e' wird nach dem except-Block geloescht – Meldung fuer
                    # den deferred Callback vorher binden (NameError-Fix).
                    msg = str(e)
                    def _update_bal_err(m=msg):
                        self._xt_balance_text.configure(state="normal")
                        self._xt_balance_text.delete("1.0", "end")
                        self._xt_balance_text.insert("1.0", f"🔓 Kein API-Key oder Fehler: {m}")
                        self._xt_balance_text.configure(state="disabled")
                    self.after(0, _update_bal_err)

                # Offene Orders
                try:
                    orders = self.xt.get_open_orders()
                    if orders:
                        o_lines = [f"{'ID':<10s}  {'Seite':<6s}  {'Preis':>10s}  {'Menge':>10s}"]
                        o_lines.append("─" * 42)
                        for o in orders:
                            o_lines.append(
                                f"{str(o.get('orderId',''))[:10]:<10s}  "
                                f"{o.get('side',''):<6s}  "
                                f"{float(o.get('price',0)):>10.6f}  "
                                f"{float(o.get('origQty',0)):>10.2f}"
                            )
                        oo_text = "\n".join(o_lines)
                    else:
                        oo_text = "Keine offenen Orders."
                    def _update_oo():
                        self._open_orders_text.configure(state="normal")
                        self._open_orders_text.delete("1.0", "end")
                        self._open_orders_text.insert("1.0", oo_text)
                        self._open_orders_text.configure(state="disabled")
                    self.after(0, _update_oo)
                except Exception:
                    pass

            else:
                # Kein API-Key konfiguriert – KEINE Key-Fragmente loggen!
                logger.debug("Exchange: has_credentials=False")
                def _no_cred():
                    self._xt_balance_text.configure(state="normal")
                    self._xt_balance_text.delete("1.0", "end")
                    self._xt_balance_text.insert("1.0", "🔑 Kein API-Key konfiguriert.\n→ Einstellungen → API-Schlüssel eintragen")
                    self._xt_balance_text.configure(state="disabled")
                self.after(0, _no_cred)

            # Deposit/Withdrawal Status
            try:
                dw_parts = []
                for currency in ["doi", "usdt"]:
                    info = self.xt.get_currency_info(currency)
                    dep = "✅" if info.get("deposit_enabled") else "❌"
                    wd = "✅" if info.get("withdraw_enabled") else "❌"
                    dw_parts.append(f"{currency.upper()}: Deposit {dep}  Withdrawal {wd}")
                dw_text = "  ·  ".join(dw_parts)
                self.after(0, lambda: self._dw_status_label.configure(text=dw_text))
            except Exception:
                self.after(0, lambda: self._dw_status_label.configure(text="Status nicht verfügbar"))

        except Exception as e:
            logger.debug(f"Exchange FEHLER: {e}", exc_info=True)
            # NameError-Fix: 'e' fuer das deferred Lambda binden
            msg = str(e)
            self.after(0, lambda m=msg: self._xt_price_label.configure(
                text=f"Fehler: {m}"))

    def _calc_vwap(self):
        """VWAP-Berechnung."""
        if not self.xt:
            return
        try:
            qty = float(self._vwap_amount.get())
        except ValueError:
            self._vwap_result.configure(text="❌ Ungültige Menge!", text_color=COLOR_ERROR)
            return

        side = "BUY" if self._vwap_side.get() == "Kaufen" else "SELL"

        def _do():
            try:
                result = self.xt.calculate_vwap(qty, side)
                vwap = result["vwap"]
                total = result["total_cost"]
                filled = result["filled"]
                text = (f"VWAP: {vwap:.6f} USDT  ·  "
                        f"Gesamt: {total:.4f} USDT  ·  "
                        f"Gefüllt: {filled:.2f} / {qty:.2f} DOI")
                self.after(0, lambda: self._vwap_result.configure(
                    text=text, text_color=COLOR_SUCCESS))
            except Exception as e:
                # NameError-Fix: 'e' fuer das deferred Lambda binden
                msg = str(e)
                self.after(0, lambda m=msg: self._vwap_result.configure(
                    text=f"❌ {m}", text_color=COLOR_ERROR))

        threading.Thread(target=_do, daemon=True).start()

    def _place_order(self):
        """Order bei XT.com aufgeben."""
        if not self.xt or not self.xt.has_credentials:
            self._order_status.configure(text="❌ Kein API-Key!", text_color=COLOR_ERROR)
            return

        side = self._order_side.get().lower()
        order_type = self._order_type.get().lower()

        try:
            quantity = float(self._order_quantity.get())
        except ValueError:
            self._order_status.configure(text="❌ Ungültige Menge!", text_color=COLOR_ERROR)
            return

        # Preis ebenfalls im Main-Thread lesen und validieren – Tkinter-Widgets
        # duerfen nicht aus dem Worker-Thread gelesen werden.
        price = None
        if order_type == "limit":
            try:
                price = float(self._order_price.get())
            except ValueError:
                self._order_status.configure(text="❌ Ungültiger Preis!", text_color=COLOR_ERROR)
                return

        def _do():
            try:
                if order_type == "limit":
                    result = self.xt.place_limit_order(side, price, quantity)
                else:
                    result = self.xt.place_market_order(side, quantity)
                order_id = result.get("orderId", "N/A")
                self.after(0, lambda: self._order_status.configure(
                    text=f"✅ Order #{order_id}", text_color=COLOR_SUCCESS))
            except Exception as e:
                err = str(e)
                if "SYMBOL_005" in err:
                    err = "API-Trading für DOI/USDT nicht freigeschaltet (SYMBOL_005)"
                self.after(0, lambda: self._order_status.configure(
                    text=f"❌ {err}", text_color=COLOR_ERROR))

        threading.Thread(target=_do, daemon=True).start()

    def _cancel_all_orders(self):
        """Alle offenen Orders stornieren."""
        if not self.xt or not self.xt.has_credentials:
            return

        def _do():
            try:
                result = self.xt.cancel_all_orders()
                self.after(0, lambda: self._order_status.configure(
                    text="✅ Alle Orders storniert", text_color=COLOR_SUCCESS))
                self._load_exchange_data()
            except Exception as e:
                err = str(e)
                if "SYMBOL_005" in err:
                    err = "API-Trading nicht freigeschaltet (SYMBOL_005)"
                self.after(0, lambda: self._order_status.configure(
                    text=f"❌ {err}", text_color=COLOR_ERROR))

        threading.Thread(target=_do, daemon=True).start()

    # ──────────────────────────────────────
    # Wallet speichern
    # ──────────────────────────────────────


    def _show_info_dialog(self):
        """
        Info-Dialog: App-Version, geladene Wallet-Slots, Pfade.

        Bewusst kompakt und kein Diagnose-Doppelgänger – für die ausführliche
        technische Diagnose existiert _show_debug_info().
        """
        import platform as _platform
        import sys as _sys

        dialog = ctk.CTkToplevel(self)
        dialog.title(f"Info – {APP_NAME}")
        dialog.geometry("560x520")
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        # Header
        ctk.CTkLabel(
            dialog, text=f"ℹ️  {APP_NAME}  v{APP_VERSION}",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_ACCENT,
        ).pack(pady=(15, 4))
        ctk.CTkLabel(
            dialog, text=COPYRIGHT + "  ·  " + LICENSE_INFO,
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 10))

        # Inhalt
        text = ctk.CTkTextbox(
            dialog, height=380,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
            corner_radius=RADIUS_CARD,
        )
        text.pack(fill="both", expand=True, padx=15, pady=5)

        lines: list[str] = []
        lines.append("─── System ──────────────────────────────────────")
        lines.append(f"Python    : {_sys.version.split()[0]}")
        lines.append(f"Plattform : {_platform.platform()}")
        lines.append(f"Projekt   : {PROJECT_ROOT}")
        lines.append("")

        lines.append("─── Geöffnete Wallets ───────────────────────────")
        any_loaded = False
        for i, slot in enumerate(self._wallet_slots):
            if not slot.get("loaded") and not slot.get("dat_file"):
                continue
            any_loaded = True
            marker = "●" if slot.get("loaded") else "○"
            name = slot.get("name", f"Wallet-{i+1}")
            dat = slot.get("dat_file") or "(kein Pfad gespeichert)"
            lines.append(f"{marker} Slot {i+1}: {name}")
            lines.append(f"    Datei : {dat}")

            if dat and dat != "(kein Pfad gespeichert)":
                state_path = str(dat) + ".state.json"
                exists = os.path.exists(state_path)
                lines.append(f"    State : {state_path}  [{'gefunden' if exists else 'noch nicht angelegt'}]")

            wm = slot.get("wm")
            if wm and wm.doi:
                try:
                    info = wm.doi.info()
                    lines.append(
                        f"    Netz  : {info.get('network','?')}  "
                        f"|  Adressen: {info.get('total_addresses','?')}  "
                        f"(receive={info.get('receive_addresses','?')}, "
                        f"change={info.get('change_addresses','?')})"
                    )
                    last_disc = info.get("last_discover")
                    if last_disc:
                        lines.append(f"    Discovery: {last_disc}")
                except Exception as e:
                    lines.append(f"    (Wallet-Info-Fehler: {e})")

                # DOI-Saldo, falls verbunden – cache-basiert, keine neue Abfrage
                bal_cache = getattr(wm.doi, "_balance_cache", {}) or {}
                if bal_cache:
                    try:
                        total_sat = sum(b.get("confirmed", 0) + b.get("unconfirmed", 0)
                                        for b in bal_cache.values())
                        from src.wallet.crypto_utils import satoshi_to_doi
                        lines.append(f"    Saldo : {satoshi_to_doi(total_sat):.8f} DOI")
                    except Exception:
                        pass
            lines.append("")

        if not any_loaded:
            lines.append("  (Keine Wallets geladen)")
            lines.append("")

        lines.append("─── Quellen ─────────────────────────────────────")
        lines.append(f"GitHub: {GITHUB_URL}")

        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")

        # Close-Button
        ctk.CTkButton(
            dialog, text="Schliessen",
            font=ctk.CTkFont(size=13),
            fg_color=COLOR_ACCENT, hover_color=COLOR_ACCENT_HOVER,
            corner_radius=RADIUS_BUTTON,
            command=dialog.destroy,
        ).pack(pady=(8, 14), padx=15, fill="x")

    def _show_debug_info(self):
        """
        Zeigt Diagnose-Informationen zum aktuellen Wallet.

        Die Datensammlung macht dutzende Netzwerk-Calls und laeuft deshalb in
        einem Worker-Thread; der Dialog zeigt solange "⏳ Sammle Diagnose...".
        """
        dialog = ctk.CTkToplevel(self)
        dialog.title("Wallet-Diagnose")
        dialog.geometry("550x520")
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="🔍 Wallet-Diagnose",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_ACCENT,
        ).pack(pady=(15, 10))

        # Diagnose-Text
        text = ctk.CTkTextbox(
            dialog, height=400, font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=COLOR_CARD, text_color=COLOR_TEXT,
        )
        text.pack(fill="both", expand=True, padx=15, pady=5)
        text.insert("1.0", "⏳ Sammle Diagnose...")
        text.configure(state="disabled")

        ctk.CTkButton(
            dialog, text="Schliessen", height=35,
            fg_color=COLOR_ACCENT, command=dialog.destroy,
        ).pack(pady=10)

        # Kontext fuer den Worker einfrieren
        wm = self.wm
        slot = self._wallet_slots[self._active_slot]
        active_slot = self._active_slot
        block_heights = dict(self._block_heights)

        def _gather():
            lines = self._collect_debug_lines(wm, slot, active_slot, block_heights)

            def _fill():
                try:
                    text.configure(state="normal")
                    text.delete("1.0", "end")
                    text.insert("1.0", "\n".join(lines))
                    text.configure(state="disabled")
                except Exception:
                    pass  # Dialog wurde inzwischen geschlossen

            self._safe_after(0, _fill)

        threading.Thread(target=_gather, daemon=True).start()

    def _collect_debug_lines(self, wm, slot, active_slot, block_heights):
        """Sammelt die Diagnose-Zeilen (laeuft im Worker-Thread, netzwerk-lastig)."""
        lines = []
        lines.append(f"=== DOI-Wallet-iX v{APP_VERSION} - Diagnose ===")
        lines.append(f"Aktiver Tab: {slot['name']} (Slot {active_slot})")
        lines.append(f"Wallet-Datei: {slot.get('dat_file', '?')}")
        lines.append(f"Block-Hoehen: DOI={block_heights.get('doi', '?')} ETH={block_heights.get('eth', '?')}")
        lines.append("")

        if wm:
            # DOI
            lines.append("── DOI ──")
            if wm.doi:
                doi = wm.doi
                addrs = getattr(doi, '_known_addresses', {})
                lines.append(f"Seed initialisiert: {doi.seed_manager.is_initialized if doi.seed_manager else '?'}")
                lines.append(f"ElectrumX verbunden: {doi.electrum is not None}")
                lines.append(f"Known Addresses: {len(addrs)}")

                receive_addrs = [a for a, i in addrs.items() if i.get('change') == 0]
                change_addrs = [a for a, i in addrs.items() if i.get('change') == 1]
                lines.append(f"  Empfangs-Adressen: {len(receive_addrs)}")
                lines.append(f"  Wechselgeld-Adressen: {len(change_addrs)}")

                # Primary Address
                try:
                    primary = doi.seed_manager.get_receive_address(0)
                    lines.append(f"Primaer-Adresse: {primary}")
                    lines.append(f"  In known_addresses: {'Ja' if primary in addrs else 'NEIN!'}")
                except Exception as e:
                    lines.append(f"Primaer-Adresse: Fehler ({e})")

                # Balance direkt abfragen
                if doi.electrum:
                    try:
                        bal = doi.get_balance(force_refresh=True)
                        lines.append(f"Balance (confirmed): {bal.get('confirmed_doi', 0)} DOI")
                        lines.append(f"Balance (unconfirmed): {bal.get('unconfirmed_doi', 0)} DOI")
                        lines.append(f"Balance (total): {bal.get('total_doi', 0)} DOI")
                    except Exception as e:
                        lines.append(f"Balance: Fehler ({e})")

                    # Einzelne Adressen mit Balance
                    lines.append("")
                    lines.append("Adressen mit Guthaben:")
                    found_any = False
                    for addr in list(addrs.keys())[:30]:
                        try:
                            ab = doi.electrum.get_balance(addr)
                            total = ab.get('confirmed', 0) + ab.get('unconfirmed', 0)
                            if total > 0:
                                found_any = True
                                idx = addrs[addr].get('index', '?')
                                chg = 'change' if addrs[addr].get('change') else 'receive'
                                lines.append(f"  {addr} ({chg} #{idx}): {total/1e8:.8f} DOI")
                        except Exception:
                            pass
                    if not found_any:
                        lines.append("  (keine)")
                else:
                    lines.append("ElectrumX: NICHT VERBUNDEN")
            else:
                lines.append("DOI-Wallet: nicht initialisiert")

            lines.append("")

            # Tron
            lines.append("── Tron ──")
            if wm.tron:
                lines.append(f"Adresse: {wm.tron.primary_address}")
                try:
                    lines.append(f"TRX: {wm.tron.get_trx_balance()}")
                    lines.append(f"USDT: {wm.tron.get_usdt_balance()}")
                except Exception as e:
                    lines.append(f"Balance: Fehler ({e})")
            else:
                lines.append("Tron: nicht initialisiert")

            lines.append("")

            # ETH
            lines.append("── Ethereum ──")
            if wm.eth:
                lines.append(f"Adresse: {wm.eth.address}")
                lines.append(f"Verbunden: {wm.eth.is_connected}")
                try:
                    lines.append(f"ETH: {wm.eth.get_eth_balance()}")
                    lines.append(f"wDOI: {wm.eth.get_wdoi_balance()}")
                except Exception as e:
                    lines.append(f"Balance: Fehler ({e})")
            else:
                lines.append("ETH: nicht initialisiert")
        else:
            lines.append("Kein WalletManager geladen!")

        return lines

    def _show_seed_phrase(self):
        """Zeigt die Seed-Phrase nach Passwort-Bestätigung an."""
        if not self.wm:
            return

        # Prüfe ob Mnemonic verfügbar
        mnemonic = getattr(self.wm, '_mnemonic', None)
        if not mnemonic:
            self._show_error("Seed-Phrase nicht verfügbar.\nBitte Wallet neu laden.")
            return

        # Passwort-Dialog
        dialog = ctk.CTkToplevel(self)
        dialog.title("Seed-Phrase anzeigen")
        dialog.geometry("420x220")
        dialog.resizable(False, False)
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="🔐  Passwort bestätigen",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLOR_WARNING,
        ).pack(pady=(20, 5))

        ctk.CTkLabel(
            dialog, text="Geben Sie Ihr Wallet-Passwort ein,\num die Seed-Phrase anzuzeigen:",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=(0, 10))

        pw_entry = ctk.CTkEntry(
            dialog, width=300, height=38,
            font=ctk.CTkFont(size=14), show="●",
            placeholder_text="Passwort eingeben...",
        )
        pw_entry.pack(pady=(0, 5))

        error_label = ctk.CTkLabel(
            dialog, text="", font=ctk.CTkFont(size=11),
            text_color=COLOR_ERROR,
        )
        error_label.pack()

        def confirm(event=None):
            password = pw_entry.get()
            if not password:
                error_label.configure(text="Bitte Passwort eingeben!")
                return

            # Passwort kryptographisch verifizieren (scrypt, ~1s) –
            # kein unsicherer String-Vergleich mit gespeichertem Klartext mehr.
            error_label.configure(text="⏳ Prüfe Passwort...")
            dialog.update_idletasks()
            if self.wm.verify_password(password):
                dialog.destroy()
                SeedDialog(self, mnemonic)
            else:
                error_label.configure(text="❌ Falsches Passwort!")
                pw_entry.delete(0, "end")

        pw_entry.bind("<Return>", confirm)

        ctk.CTkButton(
            dialog, text="🔓  Anzeigen", height=36,
            font=ctk.CTkFont(size=13),
            fg_color="#6B2737", hover_color="#8B3747",
            command=confirm,
        ).pack(pady=(5, 15))

        dialog.after(100, pw_entry.focus_set)


    def _save_safety_ui(self):
        """Speichert Sicherheitseinstellungen aus der UI."""
        try:
            limit_str = self._limit_entry.get().strip()
            self._daily_limit_eur = float(limit_str) if limit_str else 0
        except ValueError:
            self._daily_limit_eur = 0

        try:
            self._undo_seconds = int(self._undo_var.get())
        except ValueError:
            self._undo_seconds = 0

        self._save_safety_settings()

    def _estimate_eur_value(self, amount, chain):
        """Rechnet einen Betrag grob in EUR um (vereinfacht: USDT ≈ EUR)."""
        if chain == "DOI":
            return amount * self._price_doi  # DOI → USDT ≈ EUR
        elif chain == "USDT":
            return amount
        elif chain == "TRX":
            return amount * 0.28  # Grobe Schaetzung
        elif chain in ("ETH", "wDOI"):
            return amount * self._price_doi if chain == "wDOI" else amount * 2500
        return amount

    def _check_daily_limit(self, amount, chain):
        """
        Prueft ob das Tageslimit ueberschritten wird. Gibt True zurueck wenn OK.

        Reine Pruefung – verbucht wird der Betrag erst nach erfolgreichem
        wm.send() im Send-Thread (_add_daily_send). Abbrueche und Fehler
        verbrauchen das Limit damit nicht mehr.
        """
        if self._daily_limit_eur <= 0:
            return True  # Kein Limit

        eur_value = self._estimate_eur_value(amount, chain)
        today_total = self._get_today_sent_eur()
        new_total = today_total + eur_value

        if new_total > self._daily_limit_eur:
            # Warndialog
            dialog = ctk.CTkToplevel(self)
            dialog.title("Tageslimit")
            dialog.geometry("420x250")
            dialog.configure(fg_color=COLOR_BG)
            dialog.transient(self)
            dialog.grab_set()
            dialog._result = False

            ctk.CTkLabel(
                dialog, text="⚠️ Tageslimit ueberschritten!",
                font=ctk.CTkFont(size=18, weight="bold"),
                text_color=COLOR_WARNING,
            ).pack(pady=(20, 10))

            ctk.CTkLabel(
                dialog,
                text=f"Tageslimit: {self._daily_limit_eur:.2f} EUR\n"
                     f"Heute gesendet: {today_total:.2f} EUR\n"
                     f"Dieser Transfer: ~{eur_value:.2f} EUR\n"
                     f"Neuer Tagesstand: ~{new_total:.2f} EUR",
                font=ctk.CTkFont(size=12),
                text_color=COLOR_TEXT,
                justify="left",
            ).pack(padx=20, pady=5)

            btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_frame.pack(fill="x", padx=30, pady=15)

            def confirm():
                dialog._result = True
                dialog.destroy()

            ctk.CTkButton(
                btn_frame, text="Trotzdem senden",
                height=35, fg_color="#8B3747", hover_color="#AB4757",
                command=confirm,
            ).pack(side="left", expand=True, fill="x", padx=(0, 5))

            ctk.CTkButton(
                btn_frame, text="Abbrechen",
                height=35, fg_color=COLOR_CARD, hover_color="#2a3a5c",
                border_width=1, border_color=COLOR_ACCENT,
                command=dialog.destroy,
            ).pack(side="right", expand=True, fill="x", padx=(5, 0))

            self.wait_window(dialog)

            # Kein _add_daily_send hier – Verbuchung erst nach Sende-Erfolg
            return bool(dialog._result)
        else:
            return True

    def _show_undo_countdown(self, chain, addr, amount):
        """Zeigt Countdown-Dialog. Gibt True zurueck wenn TX ausgefuehrt werden soll."""
        if self._undo_seconds <= 0:
            return True

        dialog = ctk.CTkToplevel(self)
        dialog.title("Transaktion wird vorbereitet...")
        dialog.geometry("420x280")
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()
        dialog._cancelled = False
        dialog._finished = False

        ctk.CTkLabel(
            dialog, text="⏱ Transaktion wird gesendet in...",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color=COLOR_WARNING,
        ).pack(pady=(25, 10))

        countdown_label = ctk.CTkLabel(
            dialog, text=str(self._undo_seconds),
            font=ctk.CTkFont(size=52, weight="bold"),
            text_color=COLOR_ACCENT,
        )
        countdown_label.pack(pady=10)

        ctk.CTkLabel(
            dialog,
            text=f"{amount} {chain} an {shorten_addr(addr)}",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_DIM,
        ).pack(pady=5)

        def cancel():
            dialog._cancelled = True
            dialog.destroy()

        cancel_btn = ctk.CTkButton(
            dialog, text="❌  ABBRECHEN",
            height=50, width=300,
            font=ctk.CTkFont(size=18, weight="bold"),
            fg_color=COLOR_ERROR, hover_color="#ff6b7a",
            command=cancel,
        )
        cancel_btn.pack(pady=15)

        # Countdown
        remaining = [self._undo_seconds]

        def tick():
            if dialog._cancelled:
                return
            remaining[0] -= 1
            if remaining[0] <= 0:
                dialog._finished = True
                dialog.destroy()
                return
            try:
                countdown_label.configure(text=str(remaining[0]))
                # Farbe aendern wenn wenig Zeit
                if remaining[0] <= 5:
                    countdown_label.configure(text_color=COLOR_ERROR)
                dialog.after(1000, tick)
            except Exception:
                pass  # Dialog wurde geschlossen

        dialog.after(1000, tick)
        self.wait_window(dialog)

        return dialog._finished and not dialog._cancelled

    def _save_wallet(self):
        if not self.wm:
            return
        try:
            slot = self._wallet_slots[self._active_slot]
            path = slot.get("dat_file") or self.wm.wallet_path or f"wallet-{self._active_slot+1}.dat"
            self.wm.save(path)
            slot["dat_file"] = path
            self._wallet_info_label.configure(
                text=f"✅ Gespeichert: {path}",
                text_color=COLOR_SUCCESS,
            )
        except Exception as e:
            self._wallet_info_label.configure(
                text=f"❌ Fehler: {e}",
                text_color=COLOR_ERROR,
            )

    # ──────────────────────────────────────
    # Fehleranzeige
    # ──────────────────────────────────────

    def _on_close(self):
        """Wallet sauber beenden."""
        # Laufende Sendung? Erst nachfragen – sonst geht die Status-Anzeige
        # der Transaktion verloren.
        if self._send_in_progress:
            from tkinter import messagebox
            if not messagebox.askyesno(
                "Transaktion läuft",
                "Eine Transaktion wird gerade gesendet.\n"
                "Wirklich beenden?",
                parent=self,
            ):
                return

        # Ab jetzt keine Worker-Callbacks mehr annehmen (_safe_after no-op)
        self._closing = True

        # Geplanten History-Auto-Refresh stornieren
        if self._history_autorefresh_id is not None:
            try:
                self.after_cancel(self._history_autorefresh_id)
            except Exception:
                pass
            self._history_autorefresh_id = None

        # Anstehenden Tab-Klick stornieren
        self._cancel_pending_tab_click()

        try:
            self._save_tab_config()
        except Exception:
            pass
        self.destroy()

    def _show_error(self, msg):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Fehler")
        dialog.geometry("400x180")
        dialog.configure(fg_color=COLOR_BG)
        dialog.transient(self)
        dialog.grab_set()

        ctk.CTkLabel(
            dialog, text="❌ Fehler",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=COLOR_ERROR,
        ).pack(pady=(20, 10))

        ctk.CTkLabel(
            dialog, text=msg,
            font=ctk.CTkFont(size=13),
            text_color=COLOR_TEXT,
            wraplength=350,
        ).pack(padx=20)

        ctk.CTkButton(
            dialog, text="OK", height=35,
            fg_color=COLOR_ACCENT,
            command=dialog.destroy,
        ).pack(pady=15)


# ──────────────────────────────────────────────
# Hauptprogramm
# ──────────────────────────────────────────────

def main():
    setup_logging()
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")

    app = WalletApp()
    app.mainloop()


if __name__ == "__main__":
    main()
