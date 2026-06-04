# 🔗 Doichain Wallet XT

**Multi-Chain Desktop Wallet für Doichain (DOI), Tron (TRX), USDT TRC-20 mit XT.com Exchange-Integration.**

![Version](https://img.shields.io/badge/version-1.0.0-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Python](https://img.shields.io/badge/python-3.10+-yellow)

---

## ✨ Features

- **DOI Wallet** – Doichain mit SegWit-Unterstützung (Bech32, HRP: `dc`)
- **TRX Wallet** – Tron-Blockchain (TRX Transfers)
- **USDT Wallet** – Tether TRC-20 Token auf Tron
- **XT.com Exchange** – Live-Preise, Orderbuch, VWAP, Kontosaldo
- **Sichere Verschlüsselung** – AES-256-GCM mit scrypt KDF
- **BIP-39 Seed** – 24-Wort Seed-Phrase, ein Seed für alle Chains
- **QR-Codes** – Empfangsadressen als QR-Code
- **Desktop GUI** – Modernes Dark-Theme mit CustomTkinter
- **CLI-Modus** – Interaktive Kommandozeile (`wallet_app.py`)

---

## 🚀 Installation

### Voraussetzungen

- Python 3.10 oder höher
- Windows 10/11 (für EXE) oder Linux/macOS

### Schnellstart

```bash
git clone https://github.com/neubuot/doichain-wallet-xt.git
cd doichain-wallet-xt
pip install -r requirements.txt
```

### GUI starten

```bash
python wallet_gui.py
```

### CLI starten

```bash
python wallet_app.py
```

---

## 📦 Windows EXE erstellen

```bash
# Build-Script ausführen:
build_exe.bat

# Oder manuell:
pip install pyinstaller
pyinstaller wallet_gui.spec --clean --noconfirm
```

Die EXE wird erstellt unter: `dist/DoichainWalletXT.exe`

---

## ⚙️ Konfiguration

API-Keys werden in `config/config.yaml` gespeichert:

```yaml
tron:
  api_key: "dein-trongrid-api-key"

xt_com:
  api_key: "dein-xt-api-key"
  api_secret: "dein-xt-secret"
```

> ⚠️ `config.yaml` ist in `.gitignore` – niemals API-Keys commiten!

---

## 🏗️ Projektstruktur

```
doichain-wallet-xt/
├── wallet_gui.py           # Desktop GUI (CustomTkinter)
├── wallet_app.py           # CLI-Interface
├── wallet_gui.spec         # PyInstaller Build-Config
├── build_exe.bat           # Windows Build-Script
├── requirements.txt        # Python-Abhängigkeiten
├── config/
│   └── config.yaml         # API-Keys (nicht im Repo)
└── src/
    ├── wallet/
    │   ├── wallet_manager.py   # Unified Wallet Manager
    │   ├── doi_wallet.py       # Doichain (SegWit)
    │   ├── tron_wallet.py      # Tron (TRX + USDT)
    │   ├── tron_crypto.py      # Tron Signierung
    │   └── crypto_utils.py     # Kryptographie-Utilities
    └── exchange/
        └── xt_client.py        # XT.com REST API Client
```

---

## 🔐 Sicherheit

- **AES-256-GCM** Verschlüsselung der Wallet-Datei
- **scrypt** Key Derivation (N=2¹⁸, r=8, p=1)
- **BIP-39** standardkonforme Seed-Phrase (24 Wörter)
- **Kein Klartext** – Private Keys werden niemals unverschlüsselt gespeichert
- **Lokale Speicherung** – Keine Cloud, kein Tracking

---

## 📋 Lizenz

MIT License – Siehe [LICENSE](LICENSE)

---

## 👤 Autor

**Ottmar Neuburger**
WEBanizer AG

GitHub: [neubuot](https://github.com/neubuot)

---

*Doichain Wallet XT ist ein Community-Projekt und kein finanzielles Produkt. Nutzung auf eigenes Risiko.*
