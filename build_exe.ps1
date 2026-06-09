<#
.SYNOPSIS
    DOI-Wallet-iX – Windows EXE Build-Script
.DESCRIPTION
    Erstellt eine eigenständige DOI-Wallet-iX.exe für Windows.
    Installiert alle Abhängigkeiten und baut die EXE mit PyInstaller.
.NOTES
    © 2026 Ottmar Neuburger, WEBanizer AG – MIT License
.EXAMPLE
    .\build_exe.ps1
#>

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host "   DOI-Wallet-iX – EXE Build" -ForegroundColor Cyan
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""

# ── Schritt 1: Python prüfen ──
Write-Host "  [1/5] Python prüfen..." -ForegroundColor Yellow
try {
    $pyVersion = python --version 2>&1
    Write-Host "        $pyVersion" -ForegroundColor Green
} catch {
    Write-Host "  [FEHLER] Python nicht gefunden!" -ForegroundColor Red
    Write-Host "  Bitte Python 3.10+ installieren: https://python.org" -ForegroundColor Red
    exit 1
}

# ── Schritt 2: Venv prüfen / aktivieren ──
Write-Host "  [2/5] Virtuelle Umgebung..." -ForegroundColor Yellow
if (Test-Path "venv\Scripts\Activate.ps1") {
    . .\venv\Scripts\Activate.ps1
    Write-Host "        Bestehendes venv aktiviert" -ForegroundColor Green
} elseif (Test-Path "venv\Scripts\activate.bat") {
    cmd /c "venv\Scripts\activate.bat"
    Write-Host "        Bestehendes venv aktiviert (bat)" -ForegroundColor Green
} else {
    Write-Host "        Erstelle neues venv..." -ForegroundColor Yellow
    python -m venv venv
    . .\venv\Scripts\Activate.ps1
    Write-Host "        Neues venv erstellt und aktiviert" -ForegroundColor Green
}

# ── Schritt 3: Abhängigkeiten installieren ──
Write-Host "  [3/5] Abhängigkeiten installieren..." -ForegroundColor Yellow
pip install --upgrade pip -q 2>$null

# requirements.txt verwenden falls vorhanden
if (Test-Path "requirements.txt") {
    pip install -r requirements.txt -q
    Write-Host "        requirements.txt installiert" -ForegroundColor Green
} else {
    # Manuell installieren
    pip install customtkinter Pillow qrcode -q
    pip install ecdsa mnemonic pycryptodome -q
    pip install web3 eth-account bip-utils -q
    pip install requests pyyaml certifi -q
    Write-Host "        Pakete manuell installiert" -ForegroundColor Green
}

pip install pyinstaller -q
Write-Host "        PyInstaller bereit" -ForegroundColor Green

# ── Schritt 4: Cache bereinigen ──
Write-Host "  [4/5] Cache bereinigen..." -ForegroundColor Yellow
Get-ChildItem -Path . -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
if (Test-Path "build") { Remove-Item -Path "build" -Recurse -Force }
if (Test-Path "dist")  { Remove-Item -Path "dist"  -Recurse -Force }
Write-Host "        Bereinigt" -ForegroundColor Green

# ── Schritt 5: EXE bauen ──
Write-Host "  [5/5] EXE erstellen..." -ForegroundColor Yellow
Write-Host "        Das kann 2-5 Minuten dauern..." -ForegroundColor Gray
Write-Host ""

pyinstaller wallet_gui.spec --clean --noconfirm

# ── Ergebnis ──
Write-Host ""
$exePath = "dist\DOI-Wallet-iX.exe"
if (Test-Path $exePath) {
    $size = (Get-Item $exePath).Length
    $sizeMB = [math]::Round($size / 1MB, 1)

    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host "   ERFOLG!" -ForegroundColor Green
    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "   EXE:    $exePath" -ForegroundColor White
    Write-Host "   Größe:  $sizeMB MB" -ForegroundColor White
    Write-Host ""
    Write-Host "   Starten: .\dist\DOI-Wallet-iX.exe" -ForegroundColor Cyan
    Write-Host ""

    # Beispiel-Config kopieren falls vorhanden.
    # WICHTIG: Niemals die echte config.yaml ausliefern – sie enthaelt API-Keys/Secrets!
    if (Test-Path "config\config.example.yaml") {
        if (-not (Test-Path "dist\config")) { New-Item -Path "dist\config" -ItemType Directory | Out-Null }
        Copy-Item "config\config.example.yaml" "dist\config\" -Force
        Write-Host "   Beispiel-Config kopiert → dist\config\config.example.yaml" -ForegroundColor Gray
    }

    Write-Host "  ============================================" -ForegroundColor Green
    Write-Host "   Für Distribution: den Ordner 'dist' als" -ForegroundColor Gray
    Write-Host "   ZIP verpacken und weitergeben." -ForegroundColor Gray
    Write-Host "  ============================================" -ForegroundColor Green
} else {
    Write-Host "  ============================================" -ForegroundColor Red
    Write-Host "   FEHLER: Build fehlgeschlagen!" -ForegroundColor Red
    Write-Host "  ============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Häufige Probleme:" -ForegroundColor Yellow
    Write-Host "  - Visual C++ Build Tools fehlen (für bip-utils)" -ForegroundColor Gray
    Write-Host "    → https://visualstudio.microsoft.com/visual-cpp-build-tools/" -ForegroundColor Gray
    Write-Host "  - Antivirus blockiert PyInstaller" -ForegroundColor Gray
    Write-Host "    → Projektordner als Ausnahme hinzufügen" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  Debug: Mit 'pyinstaller wallet_gui.spec --clean --noconfirm --log-level DEBUG'" -ForegroundColor Gray
}

Write-Host ""
