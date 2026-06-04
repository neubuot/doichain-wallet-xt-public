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
"""

import json
import os
import time
from pathlib import Path
from typing import Optional

from .doichain_network import MAINNET, get_network
from .seed_manager import SeedManager
from .electrumx_client import ElectrumXClient
from .transaction import UTXO, Transaction, build_transaction, select_utxos
from .crypto_utils import (
    validate_address,
    satoshi_to_doi,
    doi_to_satoshi,
)


class DoiWallet:
    """
    Doichain SPV Wallet.
    
    Verwaltet Schlüssel, verbindet sich mit ElectrumX-Servern
    und ermöglicht das Senden/Empfangen von DOI.
    """

    # Maximale Anzahl an Adressen, die nach Gap durchsucht werden
    GAP_LIMIT = 20

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

    # ========================================================
    # Wallet erstellen / wiederherstellen
    # ========================================================

    def create(self, strength: int = 256, passphrase: str = "") -> str:
        """
        Erstellt ein neues Wallet mit einer frischen Seed-Phrase.
        
        Args:
            strength: Entropie (128=12 Wörter, 256=24 Wörter)
            passphrase: Optionale BIP-39 Passphrase
        
        Returns:
            Die generierte Seed-Phrase (MUSS sicher gespeichert werden!)
        """
        mnemonic = SeedManager.generate_mnemonic(strength)
        self.seed_manager.from_mnemonic(mnemonic, passphrase)
        self._derive_initial_addresses()
        return mnemonic

    def restore(self, mnemonic: str, passphrase: str = "") -> "DoiWallet":
        """
        Stellt ein Wallet aus einer Seed-Phrase wieder her.
        
        Args:
            mnemonic: BIP-39 Seed-Phrase (12 oder 24 Wörter)
            passphrase: Optionale BIP-39 Passphrase
        """
        self.seed_manager.from_mnemonic(mnemonic, passphrase)
        self._derive_initial_addresses()
        return self

    def _derive_initial_addresses(self, count: int = 5):
        """Leitet die initialen Adressen ab."""
        for i in range(count):
            self._register_keypair(i, change=0)
            self._register_keypair(i, change=1)
        self._receive_index = count
        self._change_index = count

    def _register_keypair(self, index: int, change: int = 0) -> dict:
        """Leitet ein Schlüsselpaar ab und registriert die Adresse."""
        keypair = self.seed_manager.get_keypair(index=index, change=change)
        self._known_addresses[keypair["address"]] = keypair
        return keypair

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
        """
        Verbindet zum ElectrumX-Server und entdeckt benutzte Adressen.
        
        Args:
            host: Optionaler Server-Host
            port: Optionaler Server-Port
        
        Returns:
            True bei erfolgreicher Verbindung
        """
        self.electrum = ElectrumXClient(host=host, port=port, network=self.network)
        connected = self.electrum.connect()
        if connected:
            self.discover_addresses()
        return connected

    def discover_addresses(self):
        """
        Entdeckt benutzte Adressen per Gap-Limit-Scan.
        
        Scannt Empfangs- und Wechselgeld-Adressen über die initialen
        hinaus, bis GAP_LIMIT aufeinanderfolgende leere Adressen
        gefunden werden. So werden auch Wechselgeld-Adressen aus
        früheren Transaktionen korrekt erkannt.
        """
        self._ensure_connected()
        
        for change in (0, 1):
            gap = 0
            index = 0
            while gap < self.GAP_LIMIT:
                keypair = self.seed_manager.get_keypair(index=index, change=change)
                addr = keypair["address"]
                
                # Adresse registrieren falls noch nicht bekannt
                if addr not in self._known_addresses:
                    self._known_addresses[addr] = keypair
                
                # Prüfen ob Adresse benutzt wurde
                try:
                    history = self.electrum.get_history(addr)
                    if history:
                        gap = 0  # Reset: Adresse wurde benutzt
                    else:
                        gap += 1
                except Exception:
                    gap += 1
                
                index += 1
            
            # Indizes aktualisieren
            if change == 0:
                self._receive_index = max(self._receive_index, index)
            else:
                self._change_index = max(self._change_index, index)

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

    # ========================================================
    # Saldo & UTXOs
    # ========================================================

    def get_balance(self, force_refresh: bool = False) -> dict:
        """
        Gibt den Gesamtsaldo des Wallets zurück.
        
        Args:
            force_refresh: Cache umgehen und direkt abfragen
        
        Returns:
            Dict mit confirmed, unconfirmed, total (in Satoshis)
            und confirmed_doi, unconfirmed_doi, total_doi (in DOI)
        """
        self._ensure_connected()

        total_confirmed = 0
        total_unconfirmed = 0

        for address in self._known_addresses:
            if force_refresh or address not in self._balance_cache:
                try:
                    balance = self.electrum.get_balance(address)
                    self._balance_cache[address] = balance
                except Exception:
                    continue

            bal = self._balance_cache.get(address, {})
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

    def get_utxos(self, force_refresh: bool = False) -> list[UTXO]:
        """
        Gibt alle UTXOs des Wallets zurück.
        
        Returns:
            Liste von UTXO-Objekten
        """
        self._ensure_connected()
        all_utxos = []

        for address in self._known_addresses:
            if force_refresh or address not in self._utxo_cache:
                try:
                    raw_utxos = self.electrum.get_utxos(address)
                    self._utxo_cache[address] = raw_utxos
                except Exception:
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
        """
        Sendet DOI an eine Empfängeradresse.
        
        Args:
            recipient: Empfängeradresse
            amount_doi: Betrag in DOI
            fee_per_byte: Gebühr pro Byte in Satoshis (Standard: 5)
            dry_run: Wenn True, wird die Transaktion nicht gesendet
        
        Returns:
            Dict mit txid, fee, size, hex (und bei dry_run: preview)
        """
        self._ensure_connected()

        # Adresse validieren (Legacy P2PKH, P2SH und SegWit Bech32)
        is_valid = validate_address(
            recipient,
            bech32_hrp=self.network.get("bech32_hrp", "dc")
        )
        # Auch explizit P2PKH und P2SH Version-Bytes akzeptieren
        if not is_valid:
            is_valid = (
                validate_address(recipient, self.network["pubkey_hash"])
                or validate_address(recipient, self.network.get("script_hash"))
            )
        if not is_valid:
            raise ValueError(f"Ungültige Empfängeradresse: {recipient}")

        # Betrag umrechnen
        amount_sat = doi_to_satoshi(amount_doi)
        if amount_sat <= 0:
            raise ValueError(f"Ungültiger Betrag: {amount_doi} DOI")

        # Dust-Check
        if amount_sat < self.network["dust_threshold"]:
            raise ValueError(
                f"Betrag unter Dust-Threshold: {amount_doi} DOI "
                f"(Minimum: {satoshi_to_doi(self.network['dust_threshold'])} DOI)"
            )

        # UTXOs laden
        utxos = self.get_utxos(force_refresh=True)
        if not utxos:
            raise ValueError("Keine UTXOs verfügbar. Wallet-Guthaben: 0 DOI")

        # Keypairs für alle UTXO-Adressen sammeln
        keypairs = {}
        for utxo in utxos:
            if utxo.address in self._known_addresses:
                keypairs[utxo.address] = self._known_addresses[utxo.address]["private_key"]

        # Wechselgeld-Adresse
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
        else:
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

    # ========================================================
    # Transaktionshistorie
    # ========================================================

    def get_history(self) -> list[dict]:
        """
        Gibt die Transaktionshistorie aller Adressen zurück.
        
        Returns:
            Liste von Transaktionen, sortiert nach Blockhöhe
        """
        self._ensure_connected()
        all_txs = {}  # txhash → info (dedupliziert)

        for address in self._known_addresses:
            try:
                history = self.electrum.get_history(address)
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
            except Exception:
                continue

        # Nach Höhe sortieren (neueste zuerst)
        txs = sorted(all_txs.values(), key=lambda t: t["height"], reverse=True)
        return txs

    # ========================================================
    # Gap-Limit Adress-Scan
    # ========================================================

    def scan_addresses(self, gap_limit: int = 20) -> int:
        """
        Scannt Adressen bis zum Gap-Limit, um benutzte Adressen zu finden.
        
        Nützlich beim Wiederherstellen eines Wallets aus Seed.
        
        Args:
            gap_limit: Anzahl aufeinanderfolgender leerer Adressen
        
        Returns:
            Anzahl der gefundenen Adressen mit Transaktionen
        """
        self._ensure_connected()
        found = 0

        for change in [0, 1]:
            consecutive_empty = 0
            index = 0

            while consecutive_empty < gap_limit:
                keypair = self.seed_manager.get_keypair(index=index, change=change)
                address = keypair["address"]
                self._known_addresses[address] = keypair

                try:
                    history = self.electrum.get_history(address)
                    if history:
                        consecutive_empty = 0
                        found += 1
                    else:
                        consecutive_empty += 1
                except Exception:
                    consecutive_empty += 1

                index += 1

            # Indizes aktualisieren
            if change == 0:
                self._receive_index = max(self._receive_index, index)
            else:
                self._change_index = max(self._change_index, index)

        return found

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
        }

    def __repr__(self):
        status = "✅" if (self.electrum and self.electrum.is_connected) else "❌"
        return f"DoiWallet({self.network['coin_name']}, connected={status})"
