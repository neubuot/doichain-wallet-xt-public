# DOI-Wallet-iX – Build & Distribution
# =====================================
# © 2026 Ottmar Neuburger, WEBanizer AG – MIT License


## Voraussetzungen

- **Python 3.10+** (https://python.org)
- **Visual C++ Build Tools** (für bip-utils Kompilierung)
  → https://visualstudio.microsoft.com/visual-cpp-build-tools/
  → Bei der Installation "Desktop-Entwicklung mit C++" auswählen


## EXE erstellen (Automatisch)

```powershell
.\build_exe.ps1
```

Das Script installiert alle Abhängigkeiten und erstellt `dist\DOI-Wallet-iX.exe`.


## EXE erstellen (Manuell)

```powershell
# 1. Abhängigkeiten
pip install -r requirements.txt
pip install pyinstaller

# 2. Cache bereinigen
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

# 3. EXE bauen
pyinstaller wallet_gui.spec --clean --noconfirm

# 4. Ergebnis
.\dist\DOI-Wallet-iX.exe
```


## Distribution (ZIP für IT-Muffel)

Nach erfolgreichem Build:

```powershell
# ZIP erstellen
Compress-Archive -Path "dist\DOI-Wallet-iX.exe" -DestinationPath "DOI-Wallet-iX-v0.9.1.1-win64.zip"
```

Falls config.yaml benötigt wird:
```powershell
# Mit Config
Copy-Item "config" "dist\" -Recurse
Compress-Archive -Path "dist\*" -DestinationPath "DOI-Wallet-iX-v0.9.1.1-win64.zip"
```

Der Empfänger muss nur die ZIP entpacken und die EXE starten – kein Python nötig!


## Dateistruktur nach Build

```
dist/
├── DOI-Wallet-iX.exe     ← Hauptprogramm (alles in einer Datei!)
└── config/
    └── config.yaml        ← Optional: API-Keys, RPC-URLs
```


## Häufige Probleme

### "bip-utils" kompiliert nicht
→ Visual C++ Build Tools installieren (s.o.)
→ Alternativ: `pip install bip-utils --only-binary :all:`

### Antivirus blockiert die EXE
→ False Positive – PyInstaller-EXEs werden oft fälschlicherweise markiert
→ Projektordner und dist-Ordner als Ausnahme hinzufügen

### EXE startet nicht / Fenster schließt sofort
→ Die EXE im Terminal starten um Fehlermeldungen zu sehen:
```powershell
cd dist
.\DOI-Wallet-iX.exe
```

### "console=True" vs "console=False"
→ In der Beta: `console=True` im .spec (Debug-Ausgaben sichtbar)
→ Für Release: `console=False` setzen (kein schwarzes Fenster)


## Für Release-Version (später)

In `wallet_gui.spec` ändern:
```python
console=False,                              # Kein Konsolenfenster
# icon='assets/doi-wallet.ico',             # Icon einkommentieren
```

In `wallet_gui.py` ändern:
```python
APP_VERSION = "1.0.0"                       # Version hochsetzen
# Beta-Warnung entfernen
```
