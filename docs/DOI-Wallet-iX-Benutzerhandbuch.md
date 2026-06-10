# DOI-Wallet-iX – Benutzerhandbuch

**Version 0.9.7 (Beta)**

Multi-Chain Desktop Wallet für DOI, TRX, USDT, ETH und wDOI mit XT.com
Exchange-Integration, Multi-Wallet-Tabs, Transaktions-Notizen, Tageslimit und
Undo-Timer.

© 2026 Ottmar Neuburger, WEBanizer AG – MIT License

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Installation](#2-installation)
3. [Erster Start](#3-erster-start)
4. [Multi-Wallet-Tabs](#4-multi-wallet-tabs)
5. [Dashboard](#5-dashboard)
6. [Senden](#6-senden)
7. [Empfangen](#7-empfangen)
8. [Transaktionen und Notizen](#8-transaktionen-und-notizen)
9. [Exchange (XT.com)](#9-exchange-xtcom)
10. [Einstellungen und Sicherheit](#10-einstellungen-und-sicherheit)
11. [Sicherheit und Backup](#11-sicherheit-und-backup)
12. [Fehlerbehebung](#12-fehlerbehebung)
13. [Changelog](#13-changelog)

---

## 1. Übersicht

DOI-Wallet-iX ist eine Multi-Chain Desktop-Wallet mit folgenden Währungen:

| Coin | Netzwerk | Typ |
|------|----------|-----|
| DOI | Doichain | UTXO (Bitcoin-basiert) |
| TRX | Tron | Account-basiert |
| USDT | Tron (TRC-20) | Token |
| ETH | Ethereum | Account-basiert |
| wDOI | Ethereum (ERC-20) | Token |

Dazu: XT.com Exchange-Anbindung, bis zu 10 Wallet-Tabs, Transaktions-Notizen,
Tageslimit und Undo-Timer.

---

## 2. Installation

### 2.1 Windows (EXE)

`DOI-Wallet-iX.exe` starten. Keine Installation nötig.

Windows SmartScreen: **„Weitere Informationen" → „Trotzdem ausführen"**

**Neu seit v0.9.7:** Das Release-Paket enthält aus Sicherheitsgründen keine
fertige `config.yaml` mehr, sondern nur die Vorlage
`config/config.example.yaml`. Beim ersten Start funktioniert das Wallet auch
ohne Config; für Exchange-Handel und höhere Tron-Limits kopieren Sie die
Vorlage zu `config/config.yaml` und tragen Ihre eigenen API-Keys ein (siehe
Abschnitt 10.1).

### 2.2 Aus Quellcode

Python 3.10+:

```
pip install -r requirements.txt
python wallet_gui.py
```

---

## 3. Erster Start

Beim Start erscheint der Startup-Dialog:

- **Wallet öffnen** – Bestehende `wallet.dat` mit Passwort laden
- **Neues Wallet erstellen** – Neue 24-Wort Seed-Phrase generieren
- **Wallet wiederherstellen (Seed)** – Aus 24 Wörtern wiederherstellen
- **Andere Datei laden** – `wallet.dat` von beliebigem Speicherort

**Wichtig:** Seed-Phrase auf Papier notieren!

**Hinweis zur BIP-39-Passphrase (seit v0.9.7):** Wenn Sie Ihr Wallet mit einer
zusätzlichen Passphrase („25. Wort") erstellt haben, wird diese beim Laden
geprüft. Eine falsche oder fehlende Passphrase führt zu einer klaren
Fehlermeldung – statt wie früher stillschweigend ein leeres Wallet mit
anderen Adressen anzuzeigen.

---

## 4. Multi-Wallet-Tabs

Bis zu 10 separate Wallets in Tabs. Jedes mit eigenem Seed, eigenen Adressen
und eigenen Guthaben.

### 4.1 Tab-Leiste

Oben im Fenster. Geladene Wallets sind farblich hervorgehoben. Pfeil-Buttons
zum Scrollen.

### 4.2 Neues Wallet in Tab

Klick auf leeren Tab öffnet den Startup-Dialog.

### 4.3 Tab umbenennen

Doppelklick auf Tab-Name (z. B. „Haupt-Wallet", „Spar-Wallet").

### 4.4 Auto-Reload

Beim Start werden die zuletzt geöffneten Wallets vorgeschlagen. Passwörter
werden einzeln pro Wallet abgefragt. Einzelne Wallets können übersprungen
werden.

### 4.5 Dateien

Jedes Wallet als separate Datei: `wallet-1.dat`, `wallet-2.dat`, etc.
Bestehende `wallet.dat` wird automatisch als Wallet-1 erkannt.

---

## 5. Dashboard

Zeigt alle Salden (DOI, TRX, USDT, ETH, wDOI), Adressen, Portfolio-Wert in
USDT und Verbindungsstatus. „Aktualisieren" lädt alle Daten neu.

Die Transaktionsliste aktualisiert sich automatisch alle 60 Sekunden, solange
die Transaktions-Seite geöffnet ist (seit v0.9.6).

---

## 6. Senden

Währung wählen, Empfängeradresse und Betrag eingeben, bestätigen.

### 6.1 Sicherheits-Prüfungen beim Senden

Beim Senden werden automatisch folgende Prüfungen durchgeführt:

- **Adress-Validierung:** Prüft, ob die Adresse gültig ist. Seit v0.9.7 werden
  bei DOI ausschließlich Doichain-Adressen akzeptiert – Adressen fremder
  Netzwerke (z. B. versehentlich eingefügte Bitcoin-Adressen) werden
  abgelehnt. Das schützt vor unwiederbringlichem Geldverlust.
- **Saldo-Prüfung:** Prüft, ob genügend Guthaben vorhanden ist.
- **Tageslimit:** Warnung, falls das EUR-Tageslimit überschritten wird.
  Seit v0.9.7 wird das Limit nur noch durch tatsächlich erfolgreiche
  Transaktionen verbraucht – abgebrochene oder fehlgeschlagene Sendungen
  zählen nicht mehr.
- **Passwort-Bestätigung:** Das Wallet-Passwort wird wirklich gegen die
  verschlüsselte Wallet-Datei geprüft (seit v0.9.7). Ein falsches Passwort
  führt zu „❌ Falsches Passwort!". Die Prüfung dauert ein bis zwei
  Sekunden – das ist beabsichtigt (starke Schlüsselableitung).
- **Undo-Timer:** Countdown mit Abbruch-Möglichkeit (falls aktiviert).
- **Transaktions-Verifikation (Tron, seit v0.9.7):** Vor dem Signieren wird
  lokal verifiziert, dass die vom Netzwerk vorbereitete Transaktion exakt dem
  gewünschten Empfänger und Betrag entspricht. Manipulierte Server-Antworten
  werden erkannt und abgelehnt.

### 6.2 Fehlermeldungen

Schlägt eine Transaktion fehl, erscheint seit v0.9.7 immer eine sichtbare
Fehlermeldung mit der Ursache (z. B. Netzwerkfehler, Rate-Limit). Es gibt
keine falschen Erfolgsmeldungen mehr: „✅ Gesendet!" erscheint nur, wenn die
Transaktion tatsächlich an das Netzwerk übergeben wurde.

Bei TronGrid-Rate-Limits (Fehler 429) versucht das Wallet den Versand
automatisch bis zu dreimal erneut. Tritt der Fehler dauerhaft auf, hilft ein
kostenloser TronGrid-API-Key (siehe Abschnitt 10.1).

---

## 7. Empfangen

Adressen mit QR-Codes für alle Netzwerke. Klick auf Adresse zum Kopieren.

Bei DOI wird bei jedem Aufruf der Empfangen-Seite eine frische Adresse
erzeugt (seit v0.9.6) – das verbessert die Privatsphäre. Alle früheren
Adressen bleiben dauerhaft gültig.

---

## 8. Transaktionen und Notizen

Die Transaktionshistorie zeigt alle ein- und ausgehenden Transaktionen.
Filter-Tabs: Alle, DOI, TRX, USDT, ETH, wDOI.

### 8.1 Bestätigungen

Jede Transaktion zeigt den Bestätigungs-Status: Anzahl Bestätigungen oder
„Unbestätigt" (in Gelb) für noch nicht bestätigte Transaktionen. Unbestätigte
Transaktionen werden oben in der Liste angezeigt.

### 8.2 Transaktions-Notizen

Klicken Sie auf eine Transaktion, um eine persönliche Notiz hinzuzufügen.
Beispiele: „Bezahlung für Website", „Rückzahlung an Max",
„Test-Überweisung". Die Notiz wird unter der Transaktion angezeigt und bleibt
nach einem Neustart erhalten (gespeichert in `tx_notes.json`).

### 8.3 TX-Hash kopieren

Klick auf den (gekürzten) Transaktions-Hash kopiert die vollständige TX-ID in
die Zwischenablage (seit v0.9.6) – praktisch für Block-Explorer.

---

## 9. Exchange (XT.com)

Integrierter DOI/USDT-Handel über XT.com. Orderbuch, Kauf/Verkauf,
Exchange-Guthaben, Marktdaten. API-Key unter Einstellungen eintragen.

**Empfehlung:** Erstellen Sie den XT.com-API-Key ohne Auszahlungs-Berechtigung
(Withdrawal) und mit IP-Whitelist – das Wallet benötigt nur Trading-Rechte.

---

## 10. Einstellungen und Sicherheit

### 10.1 API-Schlüssel

TronGrid- und XT.com-API-Keys eingeben und speichern.

- **TronGrid-API-Key (empfohlen):** Ohne Key sind Tron-Anfragen stark
  limitiert; es kann zu „429 Too Many Requests"-Fehlern kommen. Ein
  kostenloser Key ist auf <https://www.trongrid.io> erhältlich (Account →
  API Keys).
- **Alternative – Umgebungsvariablen (seit v0.9.7):** Statt der Eingabe in
  der Config können die Keys auch über die Umgebungsvariablen `XT_API_KEY`,
  `XT_API_SECRET` und `TRONGRID_API_KEY` gesetzt werden. Diese haben Vorrang
  vor der `config.yaml`.

Die Keys werden in `config/config.yaml` gespeichert. Diese Datei wird niemals
mit dem Programm ausgeliefert und sollte nicht weitergegeben werden.

### 10.2 Sicherheits-Einstellungen

**Tageslimit (EUR):**
Legen Sie ein tägliches Sendelimit fest. Bei Überschreitung erscheint eine
Warnung mit dem heutigen Gesamtbetrag. Sie können trotzdem senden, müssen
aber ausdrücklich bestätigen. Wert 0 = kein Limit. Nur erfolgreich gesendete
Transaktionen zählen gegen das Limit.

**Undo-Timer (Sekunden):**
Wählen Sie 10, 30 oder 60 Sekunden. Nach dem Bestätigen einer Transaktion
erscheint ein großer Countdown. Solange der läuft, können Sie die Transaktion
mit dem roten ABBRECHEN-Button stoppen. Erst nach Ablauf wird gesendet.
Wert 0 = sofortiges Senden.

### 10.3 Wallet-Diagnose

Der Diagnose-Button zeigt technische Details: Bekannte Adressen,
ElectrumX-Status, Balancen pro Adresse, Tron/ETH-Status. Nützlich für die
Fehlerbehebung. Die Diagnose läuft seit v0.9.7 im Hintergrund – die Oberfläche
bleibt dabei bedienbar.

### 10.4 Seed-Phrase anzeigen

Zeigt die 24-Wort Seed-Phrase nach Passwort-Eingabe. Das Passwort wird dabei
durch echte Entschlüsselung der Wallet-Datei verifiziert (seit v0.9.7).

---

## 11. Sicherheit und Backup

- **Seed-Phrase:** Offline auf Papier aufbewahren. Bei Multi-Wallet hat jeder
  Tab eine eigene Seed-Phrase.
- **Wallet-Dateien:** Regelmäßig alle `.dat`-Dateien sichern. Verschlüsselung:
  AES-256-GCM mit scrypt-Schlüsselableitung. Seit v0.9.7 werden die Dateien
  mit restriktiven Zugriffsrechten angelegt.
- **BIP-39-Passphrase:** Falls verwendet, gehört sie zum Backup dazu – ohne
  Passphrase kann das Wallet aus dem Seed nicht wiederhergestellt werden.
- **API-Keys:** `config/config.yaml` enthält Ihre Keys im Klartext – nicht
  weitergeben, nicht in Cloud-Backups mit Dritten teilen.

**WARNUNG:** Beta-Software. Nur kleine Beträge!

---

## 12. Fehlerbehebung

| Problem | Lösung |
|---------|--------|
| Wallet startet nicht | Keine andere Instanz laufen lassen. |
| Salden zeigen 0 | „Aktualisieren" klicken. Verbindungs-Indikatoren prüfen. Diagnose-Button nutzen. Seit v0.9.7 wird bei Netzwerkfehlern eine Fehlermeldung statt fälschlich „0" angezeigt. |
| ETH zeigt ✕ | Internetverbindung prüfen. ETH benötigt RPC-Verbindung. Bei älteren EXE-Builds: auf v0.9.7 aktualisieren (Bundling-Fehler behoben). |
| „429 Too Many Requests" (Tron) | TronGrid-Rate-Limit. Das Wallet versucht es automatisch erneut. Dauerhaft: kostenlosen API-Key auf trongrid.io erstellen und unter Einstellungen eintragen. |
| „❌ Falsches Passwort!" beim Senden | Das Wallet-Passwort wurde falsch eingegeben (wird seit v0.9.7 wirklich geprüft). |
| „Passphrase oder Wallet-Daten stimmen nicht überein" | Das Wallet wurde mit BIP-39-Passphrase erstellt – beim Laden dieselbe Passphrase angeben. |
| Exchange zeigt keine Daten | API-Keys unter Einstellungen prüfen. Fehlermeldungen enthalten seit v0.9.7 die konkrete Ursache der Exchange-API. |
| Transaktion fehlgeschlagen | Genügend Guthaben plus Gebühren vorhanden? Fehlermeldung beachten – sie nennt die Ursache. |
| Windows SmartScreen | „Weitere Informationen" → „Trotzdem ausführen". |
| Charmap-Fehler beim Öffnen | `wallet.dat` umbenennen, Wallet per Seed wiederherstellen. |

---

## 13. Changelog

### v0.9.7 – Security- und Bugfix-Release

- **SICHERHEIT:** Passwort-Bestätigung beim Senden prüft das Passwort jetzt
  wirklich gegen die verschlüsselte Wallet-Datei
- **SICHERHEIT:** Tron-Transaktionen werden vor dem Signieren lokal
  verifiziert (Schutz vor manipulierten Server-Antworten)
- **SICHERHEIT:** DOI-Versand nur noch an gültige Doichain-Adressen
  (Bitcoin-/Fremdadressen werden abgelehnt)
- **SICHERHEIT:** Release-Paket enthält keine API-Keys mehr
  (`config.example.yaml` statt `config.yaml`)
- BIP-39-Passphrase wird beim Laden unterstützt und verifiziert
- Fehlgeschlagene Transaktionen zeigen sichtbare Fehlermeldungen; keine
  falschen Erfolgsmeldungen mehr
- Tageslimit wird nur durch erfolgreiche Sendungen verbraucht
- Automatischer Retry bei TronGrid-Rate-Limit (429)
- Exakte Betragsrundung bei TRX/USDT; präzisere DOI-Gebührenberechnung
- ETH-Adressableitung korrigiert (fehlerhafter Fallback entfernt);
  ETH funktioniert wieder in der EXE
- Netzwerkfehler werden nicht mehr als Saldo 0 angezeigt
- Stabilität: Tab-Wechsel während Hintergrund-Updates, sauberes Beenden,
  robusteres Build-Skript

### v0.9.6

- Mempool-Anzeige-Fix, ElectrumX-Socket-Guard
- TX-Hash klickbar (Kopieren in Zwischenablage)
- Auto-Refresh der Transaktionsliste (60 s)
- Neue DOI-Empfangsadresse pro Aufruf der Empfangen-Seite
- Block-Höhen-Fix, Verbesserungen beim Slot-Wechsel

### v0.9.5

- Optische Auffrischung (Farben, Eckenradien)
- Robustheitsfixes ElectrumX/DOI

### v0.9.4

- NEU: Transaktions-Notizen – persönliche Anmerkungen pro Transaktion
- NEU: Tageslimit in EUR – Schutz vor versehentlich hohen Überweisungen
- NEU: Undo-Timer – Transaktion innerhalb von Sekunden abbrechen
- NEU: Bestätigungs-Anzeige in der Transaktionsliste
- NEU: Wallet-Diagnose-Button unter Einstellungen
- NEU: Beenden-Button in der Sidebar

### v0.9.3

- Multi-Wallet-Tabs (bis zu 10 Wallets)
- Auto-Reload beim Start
- Tab-Umbenennung per Doppelklick
- ETH-Verbindung gefixt (EXE-Seed-Problem gelöst)
- wDOI-Transaktionshistorie via Blockscout API
- Seed-Wiederherstellung gefixt
- Abwärtskompatibel mit bestehender `wallet.dat`

---

© 2026 Ottmar Neuburger, WEBanizer AG – MIT License
