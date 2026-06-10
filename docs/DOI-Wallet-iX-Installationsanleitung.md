# DOI-Wallet-iX – Installationsanleitung

**Version 0.9.7 (Beta)**

Schritt für Schritt für Einsteiger

© 2026 Ottmar Neuburger, WEBanizer AG – Open Source, MIT License

---

## Was ist DOI-Wallet-iX?

DOI-Wallet-iX ist eine Desktop-Anwendung zur Verwaltung von Kryptowährungen.
Mit dem Wallet können Sie folgende digitale Währungen sicher aufbewahren,
empfangen und versenden:

| Coin | Beschreibung |
|------|--------------|
| DOI (Doichain) | Die Haupt-Kryptowährung des Doichain-Netzwerks |
| TRX (Tron) | Eine weit verbreitete Kryptowährung |
| USDT (Tether) | Ein Stablecoin, der an den US-Dollar gekoppelt ist |
| ETH (Ethereum) | Die zweitgrößte Kryptowährung der Welt |
| wDOI (Wrapped DOI) | DOI als Token auf der Ethereum-Blockchain |

**Highlights in v0.9.7:**

- Umfassendes Sicherheits-Update: echte Passwort-Prüfung beim Senden,
  Verifikation von Tron-Transaktionen vor dem Signieren, strikte
  Adressvalidierung (Schutz vor Versand an fremde Netzwerke)
- Klare Fehlermeldungen statt falscher Erfolgsmeldungen
- Automatischer Wiederholungsversuch bei Tron-Rate-Limits
- Bis zu 10 separate Wallets in Tabs verwalten
- Transaktions-Notizen (persönliche Anmerkungen zu jeder TX)
- Tageslimit in EUR (Schutz vor versehentlich hohen Überweisungen)
- Undo-Timer (Transaktion innerhalb von Sekunden abbrechen)
- Bestätigungs-Anzeige bei Transaktionen

> ⚠️ **WARNUNG – Beta-Version:** Bitte verwenden Sie nur kleine Beträge!

---

## Systemvoraussetzungen

| Anforderung | Details |
|-------------|---------|
| Betriebssystem | Windows 10 oder Windows 11 |
| Architektur | 64-Bit (x64) |
| Festplatte | ca. 150 MB freier Speicherplatz |
| Internet | Aktive Internetverbindung erforderlich |
| Zusatzsoftware | Keine – alles ist in der EXE enthalten! |

---

## Installation in 3 Schritten

### 1. ZIP-Datei entpacken

Klicken Sie mit der rechten Maustaste auf `DOI-Wallet-iX-v0.9.7-win64.zip`.
Wählen Sie „Alle extrahieren…" und wählen Sie einen Zielordner (z. B.
Desktop).

### 2. Programm starten

Öffnen Sie den entpackten Ordner und doppelklicken Sie auf
`DOI-Wallet-iX.exe`. Beim ersten Start erscheint möglicherweise eine
Windows-Sicherheitswarnung (siehe unten).

### 3. Wallet einrichten

Beim ersten Start können Sie ein neues Wallet erstellen oder ein bestehendes
wiederherstellen. Vergeben Sie ein sicheres Passwort. **Notieren Sie sich
Ihre Seed-Phrase (24 Wörter) auf Papier!**

---

## Windows-Sicherheitswarnung

Beim ersten Start zeigt Windows möglicherweise eine blaue Warnung. Das ist
normal.

1. Klicken Sie auf **„Weitere Informationen"**
2. Klicken Sie auf **„Trotzdem ausführen"**

---

## API-Keys einrichten (optional, empfohlen)

**Neu seit v0.9.7:** Aus Sicherheitsgründen enthält das Paket keine fertige
Konfigurationsdatei mit Keys mehr, sondern nur die Vorlage
`config/config.example.yaml`.

Das Wallet funktioniert auch ohne API-Keys. Für den Exchange-Handel und
zuverlässige Tron-Transaktionen empfehlen wir:

1. Kopieren Sie `config/config.example.yaml` zu `config/config.yaml`
   (im selben Ordner).
2. **TronGrid-Key (kostenlos, empfohlen):** Auf <https://www.trongrid.io>
   registrieren, API-Key erstellen und in `config.yaml` unter
   `tron: api_key:` eintragen. Ohne Key kann es bei Tron/USDT zu
   „Rate-Limit"-Fehlern kommen.
3. **XT.com-Keys (nur für Exchange-Handel):** API-Key auf XT.com erstellen –
   am besten **ohne** Auszahlungs-Berechtigung und mit IP-Whitelist – und
   unter `xt_com:` eintragen.

Alternativ können die Keys in den **Einstellungen** der App eingegeben oder
über die Umgebungsvariablen `XT_API_KEY`, `XT_API_SECRET` und
`TRONGRID_API_KEY` gesetzt werden.

> Die `config.yaml` enthält Ihre Keys im Klartext – geben Sie diese Datei
> niemals weiter.

---

## Mehrere Wallets (Tabs)

Sie können bis zu 10 separate Wallets in Tabs verwalten. Jedes Wallet hat
einen eigenen Seed und eigene Adressen.

- **Klick auf leeren Tab:** Neues Wallet erstellen oder laden
- **Klick auf geladenen Tab:** Zum Wallet wechseln
- **Doppelklick auf Tab:** Tab umbenennen
- **Auto-Reload:** Beim Start werden die zuletzt geöffneten Wallets
  vorgeschlagen

---

## Sicherheits-Features

Unter **Einstellungen** konfigurierbar:

### Tageslimit (EUR)

Legen Sie ein tägliches Sendelimit in EUR fest (z. B. 100 EUR). Wenn eine
Transaktion das Limit überschreitet, erscheint eine Warnung. Sie können
trotzdem senden, müssen aber ausdrücklich bestätigen. Setzen Sie den Wert auf
0, um das Limit zu deaktivieren. Seit v0.9.7 zählen nur erfolgreich gesendete
Transaktionen gegen das Limit.

### Undo-Timer

Stellen Sie ein, wie viele Sekunden Sie nach dem Senden Zeit haben, die
Transaktion abzubrechen (10, 30 oder 60 Sekunden). Ein großer Countdown und
ein roter ABBRECHEN-Button werden angezeigt. Erst nach Ablauf des Timers wird
die Transaktion tatsächlich ausgeführt. Setzen Sie den Wert auf 0 für
sofortiges Senden.

### Passwort-Prüfung beim Senden (seit v0.9.7)

Jede Transaktion erfordert die Eingabe des Wallet-Passworts, das gegen die
verschlüsselte Wallet-Datei geprüft wird. Die Prüfung dauert ein bis zwei
Sekunden – das ist beabsichtigt und schützt vor Angriffen.

---

## Was ist in der ZIP-Datei?

| Datei | Beschreibung |
|-------|--------------|
| `DOI-Wallet-iX.exe` | Das Hauptprogramm |
| `config/config.example.yaml` | Konfigurations-Vorlage (eigene Keys eintragen) |
| `DOI-Wallet-iX-Schnellstart.md/.pdf` | Kurzanleitung |
| `DOI-Wallet-iX-Benutzerhandbuch.md/.pdf` | Ausführliche Dokumentation |
| `DOI-Wallet-iX-Installationsanleitung.md/.pdf` | Diese Anleitung |

---

## Deinstallation

Einfach den Ordner löschen. Wallet-Dateien (`wallet-1.dat`, etc.) bleiben
erhalten.

---

## Hilfe und Kontakt

| Kanal | Adresse |
|-------|---------|
| E-Mail | support@webanizer.de |
| GitHub | [github.com/neubuot/doichain-wallet-xt](https://github.com/neubuot/doichain-wallet-xt) |
| Doichain | [www.doichain.org](https://www.doichain.org) |

---

© 2026 Ottmar Neuburger, WEBanizer AG – MIT License
