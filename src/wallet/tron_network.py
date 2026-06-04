"""
Tron Netzwerk-Client (TronGrid API)

HTTP-basierter Client für die Tron-Blockchain:
- TRX-Saldo abfragen
- TRC-20 Token-Saldo abfragen (USDT)
- Transaktionen erstellen und senden
- Netzwerk-Status und Ressourcen abfragen

Verwendet die TronGrid HTTP API (keine zusätzlichen Dependencies nötig).
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from .tron_crypto import (
    tron_address_to_hex,
    hex_to_tron_address,
    validate_tron_address,
    sign_transaction,
    sha256,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Netzwerk-Parameter
# ──────────────────────────────────────────────

TRON_MAINNET = {
    "name": "tron-mainnet",
    "base_url": "https://api.trongrid.io",
    "chain_id": 1,
    
    # USDT TRC-20 Contract (Mainnet)
    "usdt_contract": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    "usdt_decimals": 6,
    
    # BIP-44
    "bip44_coin_type": 195,
    "bip44_path": "m/44'/195'/0'",
    
    # Einheiten
    "sun_per_trx": 1_000_000,  # 1 TRX = 1.000.000 SUN
    
    # Standard-Ressourcen
    "default_fee_limit": 100_000_000,  # 100 TRX max Fee für Smart Contracts
}

TRON_NILE_TESTNET = {
    "name": "tron-nile-testnet",
    "base_url": "https://nile.trongrid.io",
    "chain_id": 3,
    
    "usdt_contract": "TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
    "usdt_decimals": 6,
    
    "bip44_coin_type": 195,
    "bip44_path": "m/44'/195'/0'",
    
    "sun_per_trx": 1_000_000,
    "default_fee_limit": 100_000_000,
}


# ──────────────────────────────────────────────
# TronGrid Client
# ──────────────────────────────────────────────

class TronClient:
    """
    HTTP-Client für die TronGrid API.
    
    Unterstützt:
    - TRX-Saldo und Account-Informationen
    - TRC-20 Token-Saldo (USDT)
    - TRX-Transfers
    - TRC-20 Token-Transfers (USDT)
    - Transaktions-History
    """
    
    def __init__(self, network: dict = None, api_key: str = ""):
        """
        Initialisiert den TronGrid Client.
        
        Args:
            network: Netzwerk-Parameter (default: TRON_MAINNET)
            api_key: Optionaler TronGrid API-Key für höhere Rate-Limits
        """
        self.network = network or TRON_MAINNET
        self.base_url = self.network["base_url"]
        self.api_key = api_key
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "Content-Type": "application/json",
        })
        if api_key:
            self._session.headers["TRON-PRO-API-KEY"] = api_key
    
    # ──────────────────────────────────────────
    # Low-Level API
    # ──────────────────────────────────────────
    
    def _get(self, endpoint: str, params: dict = None, timeout: int = 15) -> Optional[dict]:
        """GET-Request an TronGrid API."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self._session.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"TronGrid GET {endpoint} fehlgeschlagen: {e}")
            return None
    
    def _post(self, endpoint: str, data: dict = None, timeout: int = 15) -> Optional[dict]:
        """POST-Request an TronGrid API."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = self._session.post(url, json=data or {}, timeout=timeout)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"TronGrid POST {endpoint} fehlgeschlagen: {e}")
            return None
    
    # ──────────────────────────────────────────
    # Netzwerk-Status
    # ──────────────────────────────────────────
    
    def get_block_height(self) -> Optional[int]:
        """Gibt die aktuelle Blockhöhe zurück."""
        data = self._post("/wallet/getnowblock")
        if data:
            return data.get("block_header", {}).get("raw_data", {}).get("number")
        return None
    
    def get_chain_parameters(self) -> Optional[List[dict]]:
        """Gibt die Tron-Chain-Parameter zurück."""
        data = self._get("/wallet/getchainparameters")
        if data:
            return data.get("chainParameter", [])
        return None
    
    def is_connected(self) -> bool:
        """Prüft die Verbindung zum Tron-Netzwerk."""
        return self.get_block_height() is not None
    
    # ──────────────────────────────────────────
    # Account & Saldo
    # ──────────────────────────────────────────
    
    def get_account(self, address: str) -> Optional[dict]:
        """
        Gibt Account-Informationen zurück.
        
        Args:
            address: Tron-Adresse (Base58Check oder Hex)
        
        Returns:
            Account-Daten oder None
        """
        data = self._post("/wallet/getaccount", {
            "address": address,
            "visible": True,
        })
        return data if data and "address" in data else None
    
    def get_trx_balance(self, address: str) -> int:
        """
        Gibt den TRX-Saldo in SUN zurück.
        
        Args:
            address: Tron-Adresse
        
        Returns:
            Saldo in SUN (1 TRX = 1.000.000 SUN), 0 wenn Account nicht existiert
        """
        account = self.get_account(address)
        if account is None:
            return 0
        return account.get("balance", 0)
    
    def get_account_resources(self, address: str) -> Optional[dict]:
        """
        Gibt Ressourcen-Informationen zurück (Bandbreite, Energie).
        
        Returns:
            Dict mit freeNetLimit, NetLimit, EnergyLimit, etc.
        """
        return self._post("/wallet/getaccountresource", {
            "address": address,
            "visible": True,
        })
    
    # ──────────────────────────────────────────
    # TRC-20 Token (USDT)
    # ──────────────────────────────────────────
    
    def get_trc20_balance(self, address: str, contract: str = None) -> int:
        """
        Gibt den TRC-20 Token-Saldo zurück (in Raw-Einheiten).
        
        Args:
            address: Tron-Adresse
            contract: Contract-Adresse (default: USDT)
        
        Returns:
            Token-Saldo in Raw-Einheiten (für USDT: 6 Dezimalstellen)
        """
        if contract is None:
            contract = self.network["usdt_contract"]
        
        # TriggerConstantContract: balanceOf(address)
        owner_hex = tron_address_to_hex(address)
        contract_hex = tron_address_to_hex(contract)
        
        if not owner_hex or not contract_hex:
            return 0
        
        # ABI: balanceOf(address) = 0x70a08231 + padded address
        # Adresse: 20 Bytes → links mit Nullen auf 32 Bytes padden
        parameter = owner_hex[2:].rjust(64, "0")  # Ohne '41' Prefix, auf 64 Hex Zeichen
        
        data = self._post("/wallet/triggerconstantcontract", {
            "owner_address": address,
            "contract_address": contract,
            "function_selector": "balanceOf(address)",
            "parameter": parameter,
            "visible": True,
        })
        
        if not data or "constant_result" not in data:
            return 0
        
        results = data.get("constant_result", [])
        if not results or not results[0]:
            return 0
        
        try:
            return int(results[0], 16)
        except (ValueError, IndexError):
            return 0
    
    def get_usdt_balance(self, address: str) -> int:
        """Gibt den USDT-Saldo in Raw zurück (÷ 1.000.000 = USDT)."""
        return self.get_trc20_balance(address, self.network["usdt_contract"])
    
    # ──────────────────────────────────────────
    # Transaktions-History
    # ──────────────────────────────────────────
    
    def get_transactions(self, address: str, limit: int = 20, only_confirmed: bool = True) -> List[dict]:
        """
        Gibt die Transaktions-History einer Adresse zurück.
        
        Args:
            address: Tron-Adresse
            limit: Maximale Anzahl (default: 20)
            only_confirmed: Nur bestätigte Transaktionen
        
        Returns:
            Liste von Transaktions-Daten
        """
        params = {
            "limit": min(limit, 200),
            "only_confirmed": only_confirmed,
        }
        
        data = self._get(f"/v1/accounts/{address}/transactions", params)
        if data and "data" in data:
            return data["data"]
        return []
    
    def get_trc20_transactions(self, address: str, contract: str = None, limit: int = 20) -> List[dict]:
        """
        Gibt TRC-20 Token-Transaktionen zurück.
        
        Args:
            address: Tron-Adresse
            contract: Contract-Adresse (default: USDT)
            limit: Maximale Anzahl
        
        Returns:
            Liste von TRC-20 Transaktions-Daten
        """
        if contract is None:
            contract = self.network["usdt_contract"]
        
        params = {
            "limit": min(limit, 200),
            "only_confirmed": True,
            "contract_address": contract,
        }
        
        data = self._get(f"/v1/accounts/{address}/transactions/trc20", params)
        if data and "data" in data:
            return data["data"]
        return []
    
    # ──────────────────────────────────────────
    # TRX Transfer
    # ──────────────────────────────────────────
    
    def create_trx_transfer(self, from_address: str, to_address: str, amount_sun: int) -> Optional[dict]:
        """
        Erstellt eine unsignierte TRX-Transfer-Transaktion.
        
        Args:
            from_address: Absender-Adresse
            to_address: Empfänger-Adresse
            amount_sun: Betrag in SUN
        
        Returns:
            Unsignierte Transaktion oder None
        """
        if amount_sun <= 0:
            raise ValueError(f"Ungültiger Betrag: {amount_sun} SUN")
        
        if not validate_tron_address(to_address):
            raise ValueError(f"Ungültige Empfänger-Adresse: {to_address}")
        
        data = self._post("/wallet/createtransaction", {
            "owner_address": from_address,
            "to_address": to_address,
            "amount": amount_sun,
            "visible": True,
        })
        
        if data and "txID" in data:
            return data
        
        logger.error(f"TRX Transfer fehlgeschlagen: {data}")
        return None
    
    # ──────────────────────────────────────────
    # TRC-20 Transfer (USDT)
    # ──────────────────────────────────────────
    
    def create_trc20_transfer(
        self,
        from_address: str,
        to_address: str,
        amount_raw: int,
        contract: str = None,
        fee_limit: int = None,
    ) -> Optional[dict]:
        """
        Erstellt eine unsignierte TRC-20 Transfer-Transaktion.
        
        Args:
            from_address: Absender-Adresse
            to_address: Empfänger-Adresse
            amount_raw: Betrag in Raw-Einheiten (für USDT: × 1.000.000)
            contract: Contract-Adresse (default: USDT)
            fee_limit: Maximale Fee in SUN (default: Netzwerk-Standard)
        
        Returns:
            Unsignierte Transaktion oder None
        """
        if contract is None:
            contract = self.network["usdt_contract"]
        if fee_limit is None:
            fee_limit = self.network["default_fee_limit"]
        
        if amount_raw <= 0:
            raise ValueError(f"Ungültiger Betrag: {amount_raw}")
        
        if not validate_tron_address(to_address):
            raise ValueError(f"Ungültige Empfänger-Adresse: {to_address}")
        
        # ABI: transfer(address,uint256)
        to_hex = tron_address_to_hex(to_address)
        if not to_hex:
            raise ValueError(f"Kann Adresse nicht konvertieren: {to_address}")
        
        # Parameter: address (32 Bytes, links gepadded) + uint256 (32 Bytes)
        param_address = to_hex[2:].rjust(64, "0")  # Ohne '41', auf 64 Hex Zeichen
        param_amount = hex(amount_raw)[2:].rjust(64, "0")
        parameter = param_address + param_amount
        
        data = self._post("/wallet/triggersmartcontract", {
            "owner_address": from_address,
            "contract_address": contract,
            "function_selector": "transfer(address,uint256)",
            "parameter": parameter,
            "fee_limit": fee_limit,
            "call_value": 0,
            "visible": True,
        })
        
        if data and "transaction" in data:
            result = data.get("result", {})
            if result.get("result", False):
                return data["transaction"]
            else:
                msg = bytes.fromhex(result.get("message", "")).decode("utf-8", errors="ignore") if result.get("message") else "Unbekannter Fehler"
                logger.error(f"TRC-20 Transfer fehlgeschlagen: {msg}")
                return None
        
        logger.error(f"TRC-20 Transfer fehlgeschlagen: {data}")
        return None
    
    # ──────────────────────────────────────────
    # Signierung & Broadcast
    # ──────────────────────────────────────────
    
    def sign_and_broadcast(self, unsigned_tx: dict, private_key: bytes) -> Optional[dict]:
        """
        Signiert eine Transaktion lokal und sendet sie ans Netzwerk.
        
        Args:
            unsigned_tx: Unsignierte Transaktion (von create_*_transfer)
            private_key: 32-Byte Private Key
        
        Returns:
            Broadcast-Ergebnis oder None
        """
        # txID ist der Hash der raw_data
        tx_id = unsigned_tx.get("txID")
        if not tx_id:
            logger.error("Transaktion hat keine txID")
            return None
        
        tx_hash = bytes.fromhex(tx_id)
        
        # Signieren
        signature = sign_transaction(tx_hash, private_key)
        
        # Signatur zur Transaktion hinzufügen
        signed_tx = unsigned_tx.copy()
        signed_tx["signature"] = [signature.hex()]
        
        # Broadcast
        result = self._post("/wallet/broadcasttransaction", signed_tx)
        
        if result and result.get("result", False):
            logger.info(f"Transaktion gesendet: {tx_id}")
            return {"txID": tx_id, "result": result}
        else:
            msg = result.get("message", "Unbekannter Fehler") if result else "Keine Antwort"
            logger.error(f"Broadcast fehlgeschlagen: {msg}")
            return {"txID": tx_id, "error": msg, "result": result}
    
    # ──────────────────────────────────────────
    # Transaktions-Status
    # ──────────────────────────────────────────
    
    def get_transaction_info(self, tx_id: str) -> Optional[dict]:
        """
        Gibt detaillierte Informationen zu einer Transaktion zurück.
        
        Args:
            tx_id: Transaktions-ID (Hash)
        
        Returns:
            Transaktions-Info (Fee, Blocknum, Receipt, etc.)
        """
        return self._post("/wallet/gettransactioninfobyid", {"value": tx_id})
    
    def get_transaction(self, tx_id: str) -> Optional[dict]:
        """Gibt eine Transaktion anhand der ID zurück."""
        return self._post("/wallet/gettransactionbyid", {"value": tx_id, "visible": True})
    
    # ──────────────────────────────────────────
    # Cleanup
    # ──────────────────────────────────────────
    
    def close(self):
        """Schließt die HTTP-Session."""
        self._session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, *args):
        self.close()
