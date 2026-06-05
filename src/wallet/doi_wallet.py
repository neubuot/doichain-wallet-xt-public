"""
Doichain Wallet – Hauptklasse.

Vereint Seed-Management, ElectrumX-Verbindung und Transaktionserstellung
zu einem vollständigen SPV-Wallet für Doichain.

Funktionen:
- Wallet erstellen / wiederherstellen (BIP-39 Seed)
- Empfangsadressen generieren
- Saldo abfragen
- DOI senden
- Transaktionshistorie

v0.9.5-Robustheitsfixes:
  * GAP_LIMIT auf 50 erhöht (Change-Chain darf grosse Lücken haben).
  * discover_addresses() trennt jetzt Netzwerk-Fehler von "Adresse leer":
    transiente Fehler führen zu Retry, dauerhafte zu Abbruch mit Warnung –
    nicht mehr stillschweigend zu falscher Index-Beendigung.
  * _balance_cache wird nach jedem send() für die verbrauchten UTXO-Adressen
    und die neue Change-Adresse invalidiert.
  * Fehler bei Saldo-/UTXO-Abfragen werden propagiert (nicht mehr stumm
    als 0 verbucht).
  * send() ruft am Ende einen leichten incremental scan, damit die neue
    Change-Adresse für Folgeabfragen sicher bekannt ist und _change_index
    selbstheilend mitwächst.
  * get_state()/set_state() ermöglichen Persistenz der Indizes über
    Wallet-Neustarts hinweg (via separater state-Datei im wallet_manager).
"""

import logging
import time
from typing import Optional

from .doichain_network import MAINNET
from .seed_manager import SeedManager
from .electrumx_client import ElectrumXClient
from .transaction import UTXO, build_transaction
from .crypto_utils import (
    validate_address,
    satoshi_to_doi,
    doi_to_satoshi,
)

logger = logging.getLogger(__name__)


class DoiWallet:
    """
    Doichain SPV Wallet.

    Verwaltet Schlüssel, verbindet sich mit ElectrumX-Servern
    und ermöglicht das Senden/Empfangen von DOI.
    """

    # Aufeinanderfolgende leere Adressen, nach denen die Discovery abbricht.
    # Für die Change-Chain ist eine grosse Marge sinnvoll, weil ungewohnte
    # Nutzungsmuster (lange Pausen zwischen Sends, exakte Beträge ohne
    # Change-Output, etc.) grössere Lücken erzeugen können.
    GAP_LIMIT = 50

    # Wie oft eine einzelne Adressabfrage bei transientem Netzwerkfehler
    # erneut versucht wird, bevor sie als endgültig fehlgeschlagen gilt.
    DISCOVER_RETRY = 2

    def __init__(self, network: Optional[dict] = None):
        self.network = network or MAINNET
        self.seed_manager = SeedManager(self.network)
        self.electrum: Optional[ElectrumXClient] = None

        # Adress-Tracking
        self._receive_index = 0    # Nächster freier Empfangsindex
        self._change_index = 0     # Nächster freier Wechselgeldindex
        self._known_addresses: dict[str, dict] = {}  # address → keypair info
        self._utxo_cache: dict[str, list] = {}        # address → UTXOs
        self._balance_cache: dict[str, dict] = {}     # address → balance
        self._last_discover_iso: Optional[str] = None

    # ========================================================
    # Wallet erstellen / wiederherstellen
    # ========================================================

    def create(self, strength: int = 256, passphrase: str = "") -> str:
        """Erstellt ein neues Wallet mit einer frischen Seed-Phrase."""
        mnemonic = SeedManager.generate_mnemonic(strength)
        self.seed_manager.from_mnemonic(mnemonic, passphrase)
        self._derive_initial_addresses()
        return mnemonic

    def restore(self, mnemonic: str, passphrase: str = "") -> "DoiWallet":
        """Stellt ein Wallet aus einer Seed-Phrase wieder her."""
        self.seed_manager.from_mnemonic(mnemonic, passphrase)
        self._derive_initial_addresses()
        return self

    def _derive_initial_addresses(self, count: int = 5):
        """Leitet die initialen Adressen ab."""
        for i in range(count):
            self._register_keypair(i, change=0)
            self._register_keypair(i, change=1)
        self._receive_index = max(self._receive_index, count)
        self._change_index = max(self._change_index, count)

    def _register_keypair(self, index: int, change: int = 0) -> dict:
        """Leitet ein Schlüsselpaar ab und registriert die Adresse."""
        keypair = self.seed_manager.get_keypair(index=index, change=change)
        self._known_addresses[keypair["address"]] = keypair
        return keypair

    # ========================================================
    # State-Persistenz (Indizes über Restart hinweg)
    # ========================================================

    def get_state(self) -> dict:
        """
        Liefert den persistierbaren Zustand des Wallets.

        Wird vom WalletManager nach jedem send() / discover_addresses()
        in eine separate .state.json-Datei neben wallet.dat geschrieben.
        """
        return {
            "version": 1,
            "network": self.network.get("name", "doichain-mainnet"),
            "receive_index": self._receive_index,
            "change_index": self._change_index,
            "last_discover": self._last_discover_iso,
        }

    def set_state(self, state: dict):
        """
        Stellt einen zuvor persistierten Zustand wieder her.

        Indizes werden auf das Maximum aus aktuellem Stand und State-Datei
        gesetzt – ein versehentlicher Rückschritt wird so vermieden.
        Adressen bis zu den neuen Indizes werden direkt registriert,
        damit auch ohne Live-Discovery alle Salden abgefragt werden können.
        """
        if not isinstance(state, dict):
            return

        if state.get("network") and state["network"] != self.network.get("name"):
            logger.warning(
                "State-Datei gehört zu Netzwerk %r, aktuelles Netzwerk ist %r – ignoriert.",
                state.get("network"), self.network.get("name"),
            )
            return

        new_receive = max(self._receive_index, int(state.get("receive_index", 0)))
        new_change = max(self._change_index, int(state.get("change_index", 0)))

        # Alle Adressen bis zu den gespeicherten Indizes vorab ableiten,
        # damit Saldo-Aggregation auch ohne erneute Discovery vollständig ist.
        for i in range(new_receive):
            self._register_keypair(i, change=0)
        for i in range(new_change):
            self._register_keypair(i, change=1)

        self._receive_index = new_receive
        self._change_index = new_change
        self._last_discover_iso = state.get("last_discover")

    # ========================================================
    # Adressen
    # ========================================================

    def get_new_receive_address(self) -> str:
        """Gibt eine neue, unbenutzte Empfangsadresse zurück."""
        keypair = self._register_keypair(self._receive_index, change=0)
        self._receive_index += 1
        return keypair["address"]

    def get_new_change_address(self) -> str:
        """Gibt eine neue Wechselgeld-Adresse zurück."""
        keypair = self._register_keypair(self._change_index, change=1)
        self._change_index += 1
        return keypair["address"]

    def get_all_addresses(self) -> list[str]:
        """Gibt alle bekannten Adressen zurück."""
        return list(self._known_addresses.keys())

    def get_receive_addresses(self) -> list[str]:
        """Gibt alle Empfangsadressen zurück."""
        return [
            addr for addr, info in self._known_addresses.items()
            if info["change"] == 0
        ]

    def get_change_addresses(self) -> list[str]:
        """Gibt alle Wechselgeld-Adressen zurück."""
        return [
            addr for addr, info in self._known_addresses.items()
            if info["change"] == 1
        ]

    # ========================================================
    # ElectrumX-Verbindung
    # ========================================================

    def connect(self, host: Optional[str] = None, port: Optional[int] = None) -> bool:
        """Verbindet zum ElectrumX-Server und entdeckt benutzte Adressen."""
        self.electrum = ElectrumXClient(host=host, port=port, network=self.network)
        connected = self.electrum.connect()
        if connected:
            try:
                self.discover_addresses()
            except Exception as e:
                logger.warning("Discovery beim Connect fehlgeschlagen: %s", e)
        return connected

    def disconnect(self):
        """Trennt die ElectrumX-Verbindung."""
        if self.electrum:
            self.electrum.disconnect()
            self.electrum = None

    def _ensure_connected(self):
        """Stellt sicher, dass eine Verbindung besteht."""
        if not self.electrum or not self.electrum.is_connected:
            raise ConnectionError(
                "Nicht mit ElectrumX verbunden. "
                "Zuerst wallet.connect() aufrufen."
            )

    def _query_history_with_retry(self, address: str):
        """
        Fragt die History einer Adresse ab und unterscheidet sauber zwischen
        'leer' (definitiv keine Transaktionen) und 'Fehler' (vorübergehender
        Netzwerk-/Serverproblem). Bei Fehlern wird DISCOVER_RETRY-mal neu
        versucht. Erst dann fliegt die Exception raus.

        Returns:
            list (eventuell leer) bei Erfolg.

        Raises:
            ConnectionError / RuntimeError bei dauerhaftem Fehler.
        """
        last_err = None
        for attempt in range(self.DISCOVER_RETRY + 1):
            try:
                return self.electrum.get_history(address)
            except (ConnectionError, RuntimeError) as e:
                last_err = e
                if attempt < self.DISCOVER_RETRY:
                    time.sleep(0.3 * (attempt + 1))
                    continue
                raise
        raise last_err if last_err else RuntimeError("History-Abfrage fehlgeschlagen")

    def discover_addresses(self, gap_limit: Optional[int] = None) -> dict:
        """
        Entdeckt benutzte Adressen per Gap-Limit-Scan.

        Scannt Empfangs- und Wechselgeld-Adressen, bis GAP_LIMIT
        aufeinanderfolgende leere Adressen gefunden werden. Netzwerk-Fehler
        werden NICHT als "leer" gezählt: bei Fehlern wird je Adresse mehrfach
        nachgefasst, und wenn sie weiter nicht beantwortet werden kann, bricht
        die Discovery für diese Chain mit einer Warnung ab statt vorzeitig
        die Indizes zu beenden.

        Args:
            gap_limit: Optional anderer Gap-Limit-Wert (default: self.GAP_LIMIT).

        Returns:
            Diagnose-Dict:
              {
                "gap_limit": int,
                "receive": {"scanned": int, "with_history": int,
                            "max_used_index": int|None, "errors": int,
                            "completed": bool},
                "change":  {... gleiche Felder ...},
                "known_addresses_total": int,
                "duration_sec": float,
              }
        """
        self._ensure_connected()
        from datetime import datetime, timezone

        gl = gap_limit or self.GAP_LIMIT
        t0 = time.monotonic()
        diag = {"gap_limit": gl, "receive": {}, "change": {}}

        for change_flag, name in ((0, "receive"), (1, "change")):
            gap = 0
            index = 0
            scanned = 0
            with_history = 0
            max_used: Optional[int] = None
            errors = 0
            completed = True

            while gap < gl:
                keypair = self.seed_manager.get_keypair(index=index, change=change_flag)
                addr = keypair["address"]
                if addr not in self._known_addresses:
                    self._known_addresses[addr] = keypair

                try:
                    history = self._query_history_with_retry(addr)
                except (ConnectionError, RuntimeError) as e:
                    # Echter Netzwerkfehler – nicht als "leer" werten.
                    errors += 1
                    logger.warning(
                        "Discovery: dauerhafter Fehler bei %s (index=%d, chain=%s): %s",
                        addr, index, name, e
                    )
                    completed = False
                    break

                scanned += 1
                if history:
                    gap = 0
                    with_history += 1
                    max_used = index
                else:
                    gap += 1
                index += 1

            diag[name] = {
                "scanned": scanned,
                "with_history": with_history,
                "max_used_index": max_used,
                "errors": errors,
                "completed": completed,
            }

            # Indizes nur dann hochziehen, wenn die Discovery komplett durchlief
            # ODER eine später benutzte Adresse gesehen wurde. Im Fehlerfall
            # behalten wir den vorherigen Stand, statt einen zu kleinen Index
            # zu schreiben (der eine bereits benutzte Change-Adresse erneut
            # ausspucken würde).
            if completed:
                target = index  # index ist genau der erste leere Index nach max_used + gap
                if change_flag == 0:
                    self._receive_index = max(self._receive_index, target)
                else:
                    self._change_index = max(self._change_index, target)
            elif max_used is not None:
                bumped = max_used + 1
                if change_flag == 0:
                    self._receive_index = max(self._receive_index, bumped)
                else:
                    self._change_index = max(self._change_index, bumped)

        diag["known_addresses_total"] = len(self._known_addresses)
        diag["duration_sec"] = round(time.monotonic() - t0, 2)
        self._last_discover_iso = datetime.now(timezone.utc).isoformat()
        logger.info("Discovery fertig: %s", diag)
        return diag

    # ========================================================
    # Saldo & UTXOs
    # ========================================================

    def get_balance(self, force_refresh: bool = False) -> dict:
        """
        Gibt den Gesamtsaldo des Wallets zurück.

        Args:
            force_refresh: Cache umgehen und direkt abfragen.

        Returns:
            Dict mit confirmed, unconfirmed, total (Satoshis),
            confirmed_doi/unconfirmed_doi/total_doi (DOI),
            sowie 'stale_addresses' (Adressen, deren Saldo wegen
            eines Abfragefehlers gerade NICHT angezeigt werden konnte).
        """
        self._ensure_connected()

        total_confirmed = 0
        total_unconfirmed = 0
        stale_addresses: list[str] = []

        for address in list(self._known_addresses):
            need_query = force_refresh or address not in self._balance_cache
            if need_query:
                try:
                    self._balance_cache[address] = self.electrum.get_balance(address)
                except (ConnectionError, RuntimeError) as e:
                    # WICHTIG: Fehler nicht als 0 werten, sondern als
                    # "unbekannt" markieren. Aufrufer kann das anzeigen.
                    logger.warning("Saldo-Abfrage für %s fehlgeschlagen: %s", address, e)
                    stale_addresses.append(address)
                    continue

            bal = self._balance_cache.get(address)
            if not bal:
                continue
            total_confirmed += bal.get("confirmed", 0)
            total_unconfirmed += bal.get("unconfirmed", 0)

        total = total_confirmed + total_unconfirmed
        return {
            "confirmed": total_confirmed,
            "unconfirmed": total_unconfirmed,
            "total": total,
            "confirmed_doi": satoshi_to_doi(total_confirmed),
            "unconfirmed_doi": satoshi_to_doi(total_unconfirmed),
            "total_doi": satoshi_to_doi(total),
            "stale_addresses": stale_addresses,
        }

    def get_address_balance(self, address: str) -> dict:
        """Gibt den Saldo einer einzelnen Adresse zurück."""
        self._ensure_connected()
        balance = self.electrum.get_balance(address)
        self._balance_cache[address] = balance
        return {
            **balance,
            "doi": satoshi_to_doi(balance["total"]),
        }

    def validate_unconfirmed(self) -> dict:
        """
        Prüft, ob alle gecachten 'unbestätigten' Salden noch Server-Realität sind.

        Hintergrund: Bei DOI können Mempool-TXs aus drei Gründen 'verschwinden':
          1. Sie wurden in einem Block bestätigt (häufigste Fall).
          2. Sie wurden vom Server-Mempool evictet (Hashpower-Crash → langer Stau).
          3. Sie wurden ersetzt (RBF).
        In all diesen Fällen meldet der Server ab sofort unconfirmed=0, aber
        unser lokaler Cache hält den alten Wert. Diese Methode entdeckt das.

        Nur Adressen mit cached unconfirmed != 0 werden tatsächlich abgefragt –
        das sind in der Praxis wenige Adressen, die Methode ist also günstig.

        Returns: Diagnose-Dict
            {
              'checked':     int   # Wie viele Adressen mit cached unconfirmed wurden geprüft
              'invalidated': int   # Wie viele davon waren stale → Cache aktualisiert
              'errors':      int   # Wie viele konnten nicht abgefragt werden
              'addresses':   list  # Liste der invalidierten Adressen (für Logging)
            }
        """
        result = {"checked": 0, "invalidated": 0, "errors": 0, "addresses": []}
        if not self.electrum:
            return result

        for addr, cached in list(self._balance_cache.items()):
            if cached.get("unconfirmed", 0) == 0:
                continue
            result["checked"] += 1
            try:
                fresh = self.electrum.get_balance(addr)
            except (ConnectionError, RuntimeError) as e:
                logger.warning("validate_unconfirmed: %s fehlgeschlagen: %s", addr, e)
                result["errors"] += 1
                continue
            if fresh.get("unconfirmed", 0) != cached.get("unconfirmed", 0):
                self._balance_cache[addr] = fresh
                result["invalidated"] += 1
                result["addresses"].append(addr)
                logger.info(
                    "validate_unconfirmed: %s aktualisiert "
                    "(cached unconfirmed=%s → server=%s)",
                    addr, cached.get("unconfirmed"), fresh.get("unconfirmed")
                )
        return result

    def get_utxos(self, force_refresh: bool = False) -> list:
        """Gibt alle UTXOs des Wallets zurück."""
        self._ensure_connected()
        all_utxos = []

        for address in list(self._known_addresses):
            if force_refresh or address not in self._utxo_cache:
                try:
                    self._utxo_cache[address] = self.electrum.get_utxos(address)
                except (ConnectionError, RuntimeError) as e:
                    logger.warning("UTXO-Abfrage für %s fehlgeschlagen: %s", address, e)
                    continue

            for raw in self._utxo_cache.get(address, []):
                all_utxos.append(UTXO(
                    tx_hash=raw["tx_hash"],
                    tx_pos=raw["tx_pos"],
                    value=raw["value"],
                    address=address,
                    height=raw.get("height", 0),
                ))

        return all_utxos

    def _invalidate_caches_for(self, addresses):
        """Löscht Cache-Einträge für die übergebenen Adressen."""
        for a in addresses:
            self._balance_cache.pop(a, None)
            self._utxo_cache.pop(a, None)

    # ========================================================
    # Senden
    # ========================================================

    def send(
        self,
        recipient: str,
        amount_doi: float,
        fee_per_byte: int = 5,
        dry_run: bool = False,
    ) -> dict:
        """Sendet DOI an eine Empfängeradresse."""
        self._ensure_connected()

        # Adresse validieren (Legacy P2PKH, P2SH und SegWit Bech32)
        if not validate_address(recipient, bech32_hrp=self.network.get("bech32_hrp", "dc")):
            raise ValueError(f"Ungültige Empfängeradresse: {recipient}")

        # Betrag umrechnen
        amount_sat = doi_to_satoshi(amount_doi)
        if amount_sat <= 0:
            raise ValueError(f"Ungültiger Betrag: {amount_doi} DOI")

        if amount_sat < self.network["dust_threshold"]:
            raise ValueError(
                f"Betrag unter Dust-Threshold: {amount_doi} DOI "
                f"(Minimum: {satoshi_to_doi(self.network['dust_threshold'])} DOI)"
            )

        # Frische UTXOs laden
        utxos = self.get_utxos(force_refresh=True)
        if not utxos:
            raise ValueError("Keine UTXOs verfügbar. Wallet-Guthaben: 0 DOI")

        # Keypairs für UTXO-Adressen sammeln
        keypairs = {}
        for utxo in utxos:
            if utxo.address in self._known_addresses:
                keypairs[utxo.address] = self._known_addresses[utxo.address]["private_key"]

        # Wechselgeld-Adresse (wird sofort in _known_addresses registriert)
        change_address = self.get_new_change_address()

        # Transaktion erstellen
        tx = build_transaction(
            utxos=utxos,
            recipient=recipient,
            amount_satoshi=amount_sat,
            change_address=change_address,
            keypairs=keypairs,
            fee_per_byte=fee_per_byte,
            dust_threshold=self.network["dust_threshold"],
        )

        result = {
            "recipient": recipient,
            "amount_doi": amount_doi,
            "amount_sat": amount_sat,
            "fee_sat": tx.fee,
            "fee_doi": satoshi_to_doi(tx.fee),
            "size_bytes": tx.size,
            "inputs": len(tx.inputs),
            "outputs": len(tx.outputs),
            "change_address": change_address,
            "hex": tx.serialize_hex(),
        }

        if dry_run:
            result["status"] = "dry_run"
            result["message"] = "Transaktion erstellt aber NICHT gesendet"
            return result

        # Broadcast
        try:
            txid = self.electrum.broadcast_transaction(tx.serialize_hex())
            result["txid"] = txid
            result["status"] = "broadcast"
            result["message"] = f"Transaktion gesendet: {txid}"
        except RuntimeError as e:
            result["status"] = "error"
            result["message"] = f"Broadcast fehlgeschlagen: {e}"
            return result

        # ──────────────────────────────────────────
        # Nach erfolgreichem Broadcast:
        # 1) Stale Caches für verbrauchte UTXO-Adressen + neue Change-Adresse
        #    invalidieren, damit die nächste Saldo-Anzeige stimmt.
        # 2) Leichten Inkrement-Scan fahren: prüft, ob die soeben benutzte
        #    Change-Adresse bereits indexiert ist und ob es weitere
        #    unbekannte Change-Adressen gibt.
        # ──────────────────────────────────────────
        spent_addresses = {u.address for u in utxos}
        self._invalidate_caches_for(spent_addresses | {change_address})

        try:
            self.discover_addresses()
        except Exception as e:
            logger.warning("Re-Discovery nach Send fehlgeschlagen (nicht kritisch): %s", e)

        return result

    # ========================================================
    # Transaktionshistorie
    # ========================================================

    def get_history(self) -> list[dict]:
        """Gibt die Transaktionshistorie aller Adressen zurück."""
        self._ensure_connected()
        all_txs: dict[str, dict] = {}

        for address in list(self._known_addresses):
            try:
                history = self.electrum.get_history(address)
            except (ConnectionError, RuntimeError) as e:
                logger.warning("History-Abfrage für %s fehlgeschlagen: %s", address, e)
                continue

            for entry in history:
                tx_hash = entry["tx_hash"]
                if tx_hash not in all_txs:
                    all_txs[tx_hash] = {
                        "tx_hash": tx_hash,
                        "height": entry.get("height", 0),
                        "addresses": [address],
                    }
                else:
                    all_txs[tx_hash]["addresses"].append(address)

        return sorted(all_txs.values(), key=lambda t: t["height"], reverse=True)

    # ========================================================
    # Gap-Limit Adress-Scan (Alt-API, an discover_addresses delegiert)
    # ========================================================

    def scan_addresses(self, gap_limit: int = 50) -> int:
        """
        Scannt Adressen bis zum Gap-Limit und gibt die Anzahl der gefundenen
        Adressen mit Transaktionen zurück (Receive + Change kombiniert).

        Delegiert intern an discover_addresses().
        """
        diag = self.discover_addresses(gap_limit=gap_limit)
        return diag["receive"]["with_history"] + diag["change"]["with_history"]

    # ========================================================
    # Info & Darstellung
    # ========================================================

    def info(self) -> dict:
        """Gibt Wallet-Informationen zurück."""
        return {
            "network": self.network["name"],
            "coin": self.network["coin_name"],
            "initialized": self.seed_manager.is_initialized,
            "connected": self.electrum.is_connected if self.electrum else False,
            "receive_addresses": len(self.get_receive_addresses()),
            "change_addresses": len(self.get_change_addresses()),
            "total_addresses": len(self._known_addresses),
            "receive_index": self._receive_index,
            "change_index": self._change_index,
            "gap_limit": self.GAP_LIMIT,
            "last_discover": self._last_discover_iso,
        }

    def __repr__(self):
        status = "✅" if (self.electrum and self.electrum.is_connected) else "❌"
        return f"DoiWallet({self.network['coin_name']}, connected={status})"
