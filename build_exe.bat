@echo off
REM ============================================
REM  DOI-Wallet-iX - Windows EXE Build
REM  (c) 2026 Ottmar Neuburger, WEBanizer AG
REM ============================================

echo.
echo  ============================================
echo   DOI-Wallet-iX - EXE Build
echo  ============================================
echo.

REM -- Schritt 1: Python pruefen --
echo  [1/5] Python pruefen...
python --version >nul 2>&1
if errorlevel 1 (
    echo  [FEHLER] Python nicht gefunden!
    echo  Bitte Python 3.10+ installieren: https://python.org
    pause
    exit /b 1
)
python --version

REM -- Schritt 2: Venv --
echo  [2/5] Virtuelle Umgebung...
if not exist "venv" (
    echo  Erstelle neues venv...
    python -m venv venv
)
call venv\Scripts\activate.bat

REM -- Schritt 3: Abhaengigkeiten --
echo  [3/5] Abhaengigkeiten installieren...
pip install --upgrade pip -q 2>nul
if exist "requirements.txt" (
    pip install -r requirements.txt -q
) else (
    pip install customtkinter Pillow qrcode -q
    pip install ecdsa mnemonic pycryptodome -q
    pip install web3 eth-account bip-utils -q
    pip install requests pyyaml certifi -q
)
pip install pyinstaller -q

REM -- Schritt 4: Bereinigen --
echo  [4/5] Cache bereinigen...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

REM -- Schritt 5: Build --
echo  [5/5] EXE erstellen (2-5 Minuten)...
echo.
pyinstaller wallet_gui.spec --clean --noconfirm

echo.
if exist "dist\DOI-Wallet-iX.exe" (
    echo  ============================================
    echo   ERFOLG!
    echo  ============================================
    echo.
    echo   EXE: dist\DOI-Wallet-iX.exe
    echo.
    if exist "config\config.yaml" (
        if not exist "dist\config" mkdir "dist\config"
        copy "config\config.yaml" "dist\config\" >nul
        echo   Config kopiert nach dist\config\
    )
    echo  ============================================
) else (
    echo  ============================================
    echo   FEHLER: Build fehlgeschlagen!
    echo  ============================================
    echo.
    echo   Visual C++ Build Tools noetig?
    echo   https://visualstudio.microsoft.com/visual-cpp-build-tools/
)

echo.
pause
