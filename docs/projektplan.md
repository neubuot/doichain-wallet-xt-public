# Doichain Trading Wallet – Gesamtprojektplan

## 1. Projektziel

Ein Multi-Chain-Wallet, das DOI (Doichain), USDT (Tron TRC-20) und TRX selbstständig verwaltet und über die XT.com-API den Kauf und Verkauf von DOI an der Börse ermöglicht – ohne dass Guthaben dauerhaft auf der Börse liegen muss.

---

## 2. Architektur-Übersicht

### 2.1 Verwaltete Assets

| Asset | Blockchain | Zweck | Schlüsseltyp |
|-------|-----------|-------|--------------|
| DOI | Doichain (Bitcoin-Fork) | Haupt-Asset, Trading | secp256k1 (BIP-44) |
| USDT | Tron (TRC-20 Token) | Stablecoin für Trading | secp256k1 (BIP-44) |
| TRX | Tron | Gas-Gebühren für USDT-Transfers | secp256k1 (BIP-44) |

### 2.2 Externe Anbindungen

| Dienst | Zweck | Protokoll |
|--------|-------|-----------|
| Doichain-Netzwerk | DOI-Transaktionen, Saldo | Electrum-Server (SPV) |
| Tron-Netzwerk | USDT/TRX-Transaktionen | TronGrid API / Full Node |
| XT.com API (v4) | Trading, Deposit, Withdrawal | REST + WebSocket |

### 2.3 Empfohlener Tech-Stack

| Komponente | Technologie | Begründung |
|------------|-------------|------------|
| Sprache | Python 3.11+ | Electrum-DOI ist Python, TronPy verfügbar, CCXT-Library |
| UI (Desktop) | Qt6 (PyQt6) | Electrum-Basis, plattformübergreifend |
| UI (Mobile, später) | React Native oder Flutter | Für spätere Mobile-App |
| DOI-Wallet-Kern | Electrum-DOI-Fork | Bewährt, SPV, Open Source |
| Tron-Anbindung | TronPy / tronweb | Offizielle Tron-Libraries |
| Börsen-API | CCXT oder direkte XT.com REST API | Abstraktion oder direkte Kontrolle |
| Schlüsselspeicher | BIP-39 Seed → BIP-44 Ableitung | Ein Seed für alle Chains |
| Verschlüsselung | AES-256 (Passwort-geschützt) | API-Keys, Wallet-Datei |

### 2.4 Schlüsselmanagement (ein Seed für alles)

```
BIP-39 Seed Phrase (12 oder 24 Wörter)
│
├── m/44'/0'/0'    → Doichain-Adressen (DOI) *
├── m/44'/195'/0'  → Tron-Adressen (USDT + TRX)
│
* Doichain-Coin-Type muss geprüft werden (evtl. eigener registrierter Typ)
```

Der Nutzer sichert einen einzigen Seed und hat damit Zugriff auf alle Assets.

---

## 3. Phasenplan

### Phase 0: Vorbereitung & Proof of Concept (1–2 Wochen)

**Ziel:** Technische Machbarkeit sicherstellen, Infrastruktur aufbauen.

| # | Aufgabe | Details | Dauer |
|---|---------|---------|-------|
| 0.1 | XT.com Account & API-Zugang | API-Trading beantragen (3–5 Werktage Prüfung). Trading- und Withdrawal-Berechtigungen aktivieren. IP-Whitelist konfigurieren. | 1 Woche (Wartezeit) |
| 0.2 | XT.com API testen (PoC) | Python-Skript: Authentifizierung, Saldo abrufen, Orderbuch `doi_usdt` abrufen, Test-Order platzieren (kleiner Betrag). | 2–3 Tage |
| 0.3 | Doichain-Netzwerk testen | Electrum-DOI-Fork klonen, Verbindung zum Doichain-Netzwerk herstellen, Test-Transaktion senden. | 2–3 Tage |
| 0.4 | Tron-Netzwerk testen | TronPy installieren, Tron-Wallet erstellen, TRC-20 USDT Transfer testen (Testnet oder Kleinstbetrag). | 2–3 Tage |
| 0.5 | Architektur finalisieren | Entscheidung Desktop vs. Web vs. Mobile. Repository-Struktur aufsetzen. CI/CD einrichten. | 1–2 Tage |

**Ergebnis Phase 0:** Alle drei Netzwerke (Doichain, Tron, XT.com) sind erreichbar und getestet. Architektur steht fest.

---

### Phase 1: Multi-Chain Wallet – Grundfunktionen (4–6 Wochen)

**Ziel:** Wallet erstellen, das DOI, USDT und TRX selbstständig verwaltet.

#### 1a: DOI On-Chain Wallet (2–3 Wochen)

| # | Aufgabe | Details |
|---|---------|---------|
| 1a.1 | Wallet-Erstellung | Neues Wallet mit BIP-39 Seed generieren. Seed Phrase anzeigen & Backup erzwingen. |
| 1a.2 | Wallet-Import | Bestehendes Wallet per Seed Phrase oder Private Key importieren. |
| 1a.3 | Adressverwaltung | DOI-Empfangsadressen generieren (HD-Wallet, neue Adresse pro Empfang). |
| 1a.4 | Saldo & Historie | DOI-Guthaben anzeigen. Transaktionshistorie mit Bestätigungen. |
| 1a.5 | DOI senden | Empfänger-Adresse + Betrag eingeben. Gebühr schätzen/anpassen. Transaktion signieren und broadcasten. |
| 1a.6 | DOI empfangen | QR-Code mit Empfangsadresse anzeigen. Benachrichtigung bei eingehender Transaktion. |

#### 1b: Tron-Wallet-Integration – USDT & TRX (2–3 Wochen)

| # | Aufgabe | Details |
|---|---------|---------|
| 1b.1 | Tron-Schlüssel ableiten | Aus dem gleichen BIP-39 Seed den Tron-Schlüssel ableiten (m/44'/195'/0'). |
| 1b.2 | TRX-Verwaltung | TRX-Saldo anzeigen. TRX senden/empfangen (für Gas-Gebühren). |
| 1b.3 | USDT (TRC-20) Verwaltung | USDT-Saldo über Smart Contract abfragen (Contract: TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t). USDT senden (TRC-20 Transfer, verbraucht TRX als Energie/Gas). USDT empfangen. |
| 1b.4 | Gas-Management | Warnung anzeigen, wenn TRX-Guthaben zu niedrig für USDT-Transfer. Empfehlung: Mindest-TRX-Reserve (ca. 15–30 TRX für mehrere Transfers). |
| 1b.5 | Energie-Optimierung | Tron nutzt „Energy" und „Bandwidth" statt klassischem Gas. Prüfen ob Staking von TRX für kostenlose Transfers sinnvoll ist. |

#### 1c: Gemeinsame Wallet-Oberfläche (1 Woche)

| # | Aufgabe | Details |
|---|---------|---------|
| 1c.1 | Dashboard | Gesamtübersicht aller Assets mit Gegenwert in USD/EUR. DOI-Saldo (On-Chain), USDT-Saldo (On-Chain), TRX-Saldo (On-Chain). |
| 1c.2 | Einheitliche Seed-Verwaltung | Ein Backup = alle Chains. Seed-Phrase-Export/Anzeige mit Passwortschutz. |
| 1c.3 | Passwortschutz | Wallet-Datei mit AES-256 verschlüsseln. Passwort-Abfrage bei jedem Start. |

**Ergebnis Phase 1:** Nutzer kann DOI, USDT und TRX selbstständig verwalten – unabhängig von jeder Börse.

---

### Phase 2: XT.com Börsenanbindung – Deposit & Withdrawal (3–4 Wochen)

**Ziel:** Assets zwischen dem eigenen Wallet und XT.com hin- und hertransferieren.

#### 2a: API-Verbindung & Kontoverwaltung (1 Woche)

| # | Aufgabe | Details |
|---|---------|---------|
| 2a.1 | API-Key Verwaltung | API-Key + Secret verschlüsselt im Wallet speichern. Verbindungstest bei Eingabe. |
| 2a.2 | Börsensaldo abrufen | XT.com-Kontostände (DOI, USDT) anzeigen. Getrennte Anzeige: „Eigenes Wallet" vs. „Auf Börse". |
| 2a.3 | Signatur-Implementierung | HMAC-SHA256 Signatur für authentifizierte API-Calls. Timestamp-Synchronisation. |

#### 2b: Einzahlung auf XT.com (1–2 Wochen)

| # | Aufgabe | Details |
|---|---------|---------|
| 2b.1 | DOI einzahlen | Deposit-Adresse von XT.com abrufen (GET /v4/deposit-address, currency=doi). „Auf Börse einzahlen"-Button → DOI vom eigenen Wallet an Deposit-Adresse senden. Bestätigungs-Tracking (Doichain-Confirmations). |
| 2b.2 | USDT einzahlen | Deposit-Adresse von XT.com abrufen (currency=usdt, chain=TRC20). USDT vom eigenen Tron-Wallet an Deposit-Adresse senden. Bestätigungs-Tracking. |
| 2b.3 | Deposit-Status | Laufende Einzahlungen mit Status anzeigen (Pending → Confirming → Completed). API-Polling oder WebSocket für Updates. |

#### 2c: Auszahlung von XT.com (1–2 Wochen)

| # | Aufgabe | Details |
|---|---------|---------|
| 2c.1 | DOI abheben | POST /v4/withdraw (currency=doi, address=eigene DOI-Adresse, amount). Minimum-Betrag und Gebühren vorab anzeigen. |
| 2c.2 | USDT abheben | POST /v4/withdraw (currency=usdt, chain=TRC20, address=eigene Tron-Adresse). Minimum-Betrag und Gebühren vorab anzeigen. |
| 2c.3 | Withdrawal-Status | Laufende Auszahlungen mit Status tracken. Automatische Saldo-Aktualisierung nach Abschluss. |
| 2c.4 | Sicherheit | Betragslimit pro Transaktion (konfigurierbar). Bestätigungsdialog mit Zusammenfassung. Adress-Whitelist (nur eigene Adressen). |

**Ergebnis Phase 2:** Nutzer kann DOI und USDT nahtlos zwischen eigenem Wallet und Börse bewegen.

---

### Phase 3: Trading – Kauf & Verkauf von DOI (4–5 Wochen)

**Ziel:** DOI direkt aus dem Wallet heraus kaufen und verkaufen.

#### 3a: Orderbuch & Preisermittlung (1–2 Wochen)

| # | Aufgabe | Details |
|---|---------|---------|
| 3a.1 | Orderbuch abrufen | GET /v4/public/depth?symbol=doi_usdt&limit=20. Ask-Seite (Verkaufsangebote) und Bid-Seite (Kaufangebote) parsen. |
| 3a.2 | Preisberechnung (Kauf) | Durch Ask-Seite iterieren bis gewünschte DOI-Menge erreicht. Volumengewichteten Durchschnittspreis (VWAP) berechnen. Gesamtkosten = VWAP × Menge + Trading-Fee. |
| 3a.3 | Preisberechnung (Verkauf) | Analog durch Bid-Seite iterieren. Erlös = VWAP × Menge − Trading-Fee. |
| 3a.4 | Liquiditätsanzeige | Orderbuch-Tiefe visualisieren. Warnung bei dünnem Orderbuch (< X USDT Volumen). Slippage-Schätzung anzeigen. |

#### 3b: Kauf-Flow (1–2 Wochen)

| Schritt | Aktion | Details |
|---------|--------|---------|
| 1 | Eingabe | Nutzer gibt ein: Anzahl DOI ODER USDT-Budget. Bei USDT-Budget: System rechnet automatisch in DOI-Menge um. |
| 2 | Vorschau | Orderbuch abrufen → VWAP berechnen. Anzeige: „Ca. X DOI für Y USDT (Preis: Z USDT/DOI)". Geschätzte Gebühren anzeigen. |
| 3 | Bestätigung | Nutzer bestätigt den Kauf. |
| 4 | Pre-Check | Prüfen: Ausreichend USDT auf XT.com-Konto? Falls nicht: Automatischer Deposit-Vorschlag. |
| 5 | Order platzieren | POST /v4/order: symbol=doi_usdt, side=BUY, type=LIMIT, price=(VWAP + 5%), quantity, timeInForce=GTC. |
| 6 | Überwachung | Order-Status tracken (NEW → PARTIALLY_FILLED → FILLED). Bei Teilfüllung: Restmenge anzeigen. |
| 7 | Abschluss | Nach Fill: DOI-Guthaben auf XT.com aktualisieren. Optional: Automatischer Withdrawal auf eigenes Wallet vorschlagen. |

#### 3c: Verkauf-Flow (1 Woche)

| Schritt | Aktion | Details |
|---------|--------|---------|
| 1 | Eingabe | Nutzer gibt Anzahl zu verkaufender DOI ein. |
| 2 | Vorschau | Bid-Seite des Orderbuchs → VWAP berechnen. Anzeige: „Ca. Y USDT Erlös für X DOI (Preis: Z USDT/DOI)". |
| 3 | Bestätigung | Nutzer bestätigt den Verkauf. |
| 4 | Pre-Check | Prüfen: Ausreichend DOI auf XT.com-Konto? Falls nicht: Automatischer Deposit-Vorschlag. |
| 5 | Order platzieren | POST /v4/order: symbol=doi_usdt, side=SELL, type=LIMIT, price=(VWAP − 5%), quantity, timeInForce=GTC. |
| 6 | Überwachung | Wie beim Kauf. |
| 7 | Abschluss | Nach Fill: USDT-Guthaben aktualisieren. Optional: Automatischer USDT-Withdrawal vorschlagen. |

#### 3d: Order-Management (1 Woche)

| # | Aufgabe | Details |
|---|---------|---------|
| 3d.1 | Offene Orders | Liste aller offenen Orders mit Status, Preis, Menge, Füllgrad. |
| 3d.2 | Order stornieren | DELETE /v4/order/{orderId}. Bestätigungsdialog. |
| 3d.3 | Order-Historie | Abgeschlossene und stornierte Orders anzeigen. Durchschnittlicher Ausführungspreis bei Teilfüllungen. |
| 3d.4 | WebSocket (optional) | Echtzeit-Updates für Order-Status und Orderbuch. wss://stream.xt.com/public, wss://stream.xt.com/private. |

#### 3e: Sicherheit & Fehlerbehandlung (1 Woche)

| # | Aufgabe | Details |
|---|---------|---------|
| 3e.1 | Slippage-Schutz | Maximaler Preisaufschlag konfigurierbar (Standard: 5%). Order wird abgelehnt wenn Orderbuch zu dünn. |
| 3e.2 | Timeout-Handling | Order nach X Minuten/Stunden automatisch stornieren (konfigurierbar). Nutzer benachrichtigen. |
| 3e.3 | Fehler-Recovery | Was passiert bei Netzwerkabbruch während Order? Was wenn Deposit noch nicht angekommen? Retry-Logik für API-Calls. |
| 3e.4 | Rate-Limiting | XT.com erlaubt 10 Requests/Sekunde pro User. Request-Queue implementieren. |

**Ergebnis Phase 3:** Vollständiger Trading-Workflow aus dem Wallet heraus.

---

## 4. Gesamtübersicht der Meilensteine

| Phase | Meilenstein | Dauer | Kumuliert |
|-------|-------------|-------|-----------|
| 0 | PoC abgeschlossen, alle Netzwerke getestet | 1–2 Wochen | 2 Wochen |
| 1 | Multi-Chain-Wallet funktionsfähig (DOI + USDT + TRX) | 4–6 Wochen | 8 Wochen |
| 2 | Deposit & Withdrawal über XT.com | 3–4 Wochen | 12 Wochen |
| 3 | Trading (Kauf/Verkauf mit Orderbuch) | 4–5 Wochen | 17 Wochen |
| | **Gesamt** | **~12–17 Wochen** | |

---

## 5. Typischer Nutzer-Flow (End-to-End)

### DOI kaufen (aus Sicht des Nutzers)

```
1. Wallet öffnen → Dashboard zeigt:
   DOI:  150.00 DOI  (eigenes Wallet)
   USDT: 500.00 USDT (eigenes Wallet)
   TRX:  50.00 TRX   (eigenes Wallet)
   ──────────────────────────────
   Auf Börse (XT.com):
   DOI:  0.00
   USDT: 0.00

2. Nutzer klickt „DOI kaufen"
   → Eingabe: „100 DOI kaufen"
   → System prüft: USDT auf Börse = 0 → „Bitte USDT einzahlen"
   → Nutzer bestätigt: 300 USDT auf XT.com einzahlen

3. USDT-Transfer: Eigenes Wallet → XT.com (TRC-20)
   → Status: „Einzahlung wird bestätigt..." (ca. 1–3 Min)
   → Status: „300 USDT auf XT.com verfügbar"

4. Orderbuch wird abgerufen:
   → „100 DOI kosten ca. 245 USDT (Preis: 2.45 USDT/DOI)"
   → „Limit-Order bei 2.5725 USDT/DOI (+ 5% Aufschlag)"
   → Nutzer bestätigt

5. Order läuft...
   → Status: „50/100 DOI gefüllt..." → „100/100 DOI gefüllt ✓"
   → „Möchten Sie die 100 DOI auf Ihr Wallet abheben?"

6. Nutzer bestätigt → DOI-Withdrawal von XT.com auf eigenes Wallet
   → Dashboard aktualisiert:
   DOI:  250.00 DOI
   USDT: 200.00 USDT (Rest nach Kauf zurückgeholt)
```

---

## 6. Risiken & Offene Punkte

| Risiko | Auswirkung | Maßnahme |
|--------|-----------|----------|
| XT.com API-Zugang wird nicht genehmigt | Projekt blockiert | Frühzeitig beantragen (Phase 0); Alternative Börse evaluieren (Xeggex) |
| DOI-Liquidität auf XT.com sehr gering | Große Orders nicht ausführbar | Liquiditätswarnung einbauen; Teilkäufe ermöglichen |
| Doichain-Coin-Type für BIP-44 nicht registriert | Seed-Ableitung nicht standardkonform | Prüfen ob offizieller Coin-Type existiert; ggf. eigenen Ableitungspfad definieren |
| Tron Energy-Kosten schwanken | USDT-Transfers werden teurer | Energy-Kosten vorab anzeigen; TRX-Staking als Option |
| XT.com ändert API ohne Vorwarnung | Funktionen brechen | API-Version pinnen; Monitoring einrichten |
| Regulatorische Anforderungen | Je nach Jurisdiktion KYC/AML relevant | Rechtliche Prüfung empfohlen |

---

## 7. Nächste konkrete Schritte

1. **Sofort:** XT.com API-Zugang beantragen
2. **Diese Woche:** Electrum-DOI-Fork klonen und testen
3. **Diese Woche:** TronPy PoC – Tron-Wallet erstellen, USDT-Transfer testen
4. **Nächste Woche:** XT.com API PoC – Orderbuch abrufen, Saldo lesen
5. **Entscheidung:** Desktop-App (Electron/Qt) oder Web-App?
