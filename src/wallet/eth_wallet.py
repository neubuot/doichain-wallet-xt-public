"""
Ethereum HD-Wallet mit wDOI (ERC-20) Unterstützung
====================================================

Leitet Ethereum-Adressen aus einer BIP-39 Seed-Phrase ab
und ermöglicht ETH- und wDOI-Token-Transfers.

Ableitungspfad: m/44'/60'/0'/0/x (BIP-44 Standard für Ethereum)

Funktionen:
    - ETH-Adressableitung aus Seed
    - ETH-Saldo abfragen
    - wDOI (ERC-20) Saldo abfragen
    - ETH senden
    - wDOI senden (ERC-20 transfer)
    - Gas-Schätzung

Abhängigkeiten:
    pip install web3 eth-account

© 2026 Ottmar Neuburger, WEBanizer AG
"""

import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Imports mit Fehlerbehandlung
# ──────────────────────────────────────────────

try:
    from web3 import Web3
    from web3.middleware import ExtraDataToPOAMiddleware
    from eth_account import Account
    # Aktiviere HD-Wallet-Support (BIP-44 Ableitung)
    Account.enable_unaudited_hdwallet_features()
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    logger.warning("web3 nicht installiert. pip install web3 eth-account")

from .eth_network import ETH_MAINNET, ERC20_ABI


# ──────────────────────────────────────────────
# Hilfsfunktionen
# ──────────────────────────────────────────────

def wei_to_eth(wei: int) -> float:
    """Konvertiert Wei zu ETH."""
    return wei / 10**18


def eth_to_wei(eth: float) -> int:
    """Konvertiert ETH zu Wei."""
    return int(Decimal(str(eth)) * Decimal(10**18))


def raw_to_wdoi(raw: int, decimals: int = 18) -> float:
    """Konvertiert rohen wDOI-Betrag (18 Dezimalstellen) in wDOI."""
    return raw / 10**decimals


def wdoi_to_raw(amount: float, decimals: int = 18) -> int:
    """Konvertiert wDOI in rohen Betrag."""
    return int(Decimal(str(amount)) * Decimal(10**decimals))


def validate_eth_address(address: str) -> bool:
    """Prüft ob eine Ethereum-Adresse gültig ist."""
    if not HAS_WEB3:
        return (
            isinstance(address, str)
            and address.startswith("0x")
            and len(address) == 42
        )
    return Web3.is_address(address)


# ──────────────────────────────────────────────
# Ethereum Wallet
# ──────────────────────────────────────────────

class EthWallet:
    """
    Ethereum HD-Wallet mit wDOI (ERC-20) Unterstützung.

    Leitet Adressen aus einer BIP-39 Seed-Phrase ab und
    kommuniziert mit der Ethereum-Blockchain über Web3 RPC.

    Verwendung:
        wallet = EthWallet()
        wallet.from_mnemonic("word1 word2 ... word24")
        balance = wallet.get_eth_balance()
        wdoi = wallet.get_wdoi_balance()
    """

    def __init__(self, network: dict = None, rpc_url: str = None):
        """
        Initialisiert das Ethereum Wallet.

        Args:
            network: Netzwerk-Konfiguration (default: ETH_MAINNET)
            rpc_url: Optionaler benutzerdefinierter RPC-URL
        """
        self.network = network or ETH_MAINNET
        self._w3: Optional[Web3] = None
        self._rpc_url: Optional[str] = rpc_url
        self._address: Optional[str] = None
        self._private_key: Optional[str] = None
        self._all_addresses: List[Dict] = []
        self._connected = False

    # ──────────────────────────────────────
    # Verbindung
    # ──────────────────────────────────────

    def connect(self, rpc_url: str = None) -> bool:
        """
        Stellt eine Verbindung zum Ethereum-Netzwerk her.

        Args:
            rpc_url: Optionaler RPC-URL (überschreibt Konfiguration)

        Returns:
            True bei erfolgreicher Verbindung
        """
        if not HAS_WEB3:
            logger.error("web3 nicht verfügbar")
            return False

        urls_to_try = []
        if rpc_url:
            urls_to_try.append(rpc_url)
        if self._rpc_url:
            urls_to_try.append(self._rpc_url)
        urls_to_try.extend(self.network.get("rpc_urls", []))

        for url in urls_to_try:
            try:
                w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 10}))
                w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
                if w3.is_connected():
                    self._w3 = w3
                    self._rpc_url = url
                    self._connected = True
                    chain_id = w3.eth.chain_id
                    block = w3.eth.block_number
                    logger.info(f"Verbunden mit {url} (Chain-ID: {chain_id}, Block: {block})")
                    return True
            except Exception as e:
                logger.debug(f"Verbindung zu {url} fehlgeschlagen: {e}")
                continue

        logger.error("Konnte keine Verbindung zu Ethereum herstellen")
        return False

    @property
    def is_connected(self) -> bool:
        """Prüft ob eine aktive Verbindung besteht."""
        if self._w3 is None:
            return False
        try:
            return self._w3.is_connected()
        except Exception:
            return False

    # ──────────────────────────────────────
    # Wallet-Erstellung / Ableitung
    # ──────────────────────────────────────

    def from_mnemonic(self, mnemonic: str, account_index: int = 0) -> str:
        """
        Leitet die Ethereum-Adresse aus einer BIP-39 Seed-Phrase ab.

        Verwendet eth-account's eingebauten HD-Wallet-Support (BIP-44).
        Ableitungspfad: m/44'/60'/0'/0/{account_index}

        Args:
            mnemonic: BIP-39 Seed-Phrase (12/24 Wörter)
            account_index: Adress-Index (default: 0)

        Returns:
            Ethereum-Adresse (0x...)
        """
        if not HAS_WEB3:
            raise RuntimeError("web3/eth-account nicht installiert: pip install web3 eth-account")

        path = f"m/44'/60'/0'/0/{account_index}"

        # HD-Wallet-Features sicherstellen (idempotent; normalerweise
        # bereits beim Modul-Import aktiviert)
        Account.enable_unaudited_hdwallet_features()

        # WICHTIG: Kein manueller BIP-32-Fallback! Ein früherer Fallback
        # hat bei beliebigen Fehlern (z.B. ungültiger Mnemonic) FALSCHE
        # Adressen abgeleitet – dorthin gesendete Coins wären verloren.
        # Fehler werden stattdessen mit klarer Meldung weitergereicht.
        try:
            acct = Account.from_mnemonic(mnemonic, account_path=path)
        except Exception as e:
            raise ValueError(
                f"ETH-Adressableitung fehlgeschlagen – Mnemonic ungültig "
                f"oder eth-account-Fehler: {e}"
            ) from e

        self._private_key = acct.key.hex()
        if self._private_key.startswith("0x"):
            self._private_key = self._private_key[2:]
        self._address = acct.address

        logger.info(f"ETH-Adresse abgeleitet: {self._address}")
        return self._address

    def derive_addresses(self, mnemonic: str, count: int = 5) -> List[Dict]:
        """
        Leitet mehrere Ethereum-Adressen ab.

        Args:
            mnemonic: BIP-39 Seed-Phrase
            count: Anzahl der Adressen

        Returns:
            Liste von {index, address, path}
        """
        if not HAS_WEB3:
            raise RuntimeError("web3/eth-account nicht installiert")

        addresses = []
        for i in range(count):
            path = f"m/44'/60'/0'/0/{i}"
            acct = Account.from_mnemonic(mnemonic, account_path=path)
            addresses.append({
                "index": i,
                "address": acct.address,
                "path": path,
            })

        self._all_addresses = addresses
        return addresses

    @property
    def address(self) -> Optional[str]:
        """Gibt die primäre Ethereum-Adresse zurück."""
        return self._address

    @property
    def private_key(self) -> Optional[str]:
        """Gibt den Private Key zurück (Hex ohne 0x-Prefix)."""
        return self._private_key

    # ──────────────────────────────────────
    # Balance-Abfragen
    # ──────────────────────────────────────

    def get_eth_balance(self, address: str = None) -> float:
        """
        Fragt den ETH-Saldo einer Adresse ab.

        Args:
            address: Ethereum-Adresse (default: eigene Adresse)

        Returns:
            Saldo in ETH
        """
        if not self.is_connected:
            if not self.connect():
                raise ConnectionError("Keine Verbindung zu Ethereum")

        addr = address or self._address
        if not addr:
            raise ValueError("Keine Adresse angegeben")

        addr = Web3.to_checksum_address(addr)
        balance_wei = self._w3.eth.get_balance(addr)
        return wei_to_eth(balance_wei)

    def get_wdoi_balance(self, address: str = None) -> float:
        """
        Fragt den wDOI (ERC-20) Saldo einer Adresse ab.

        Args:
            address: Ethereum-Adresse (default: eigene Adresse)

        Returns:
            Saldo in wDOI
        """
        if not self.is_connected:
            if not self.connect():
                raise ConnectionError("Keine Verbindung zu Ethereum")

        addr = address or self._address
        if not addr:
            raise ValueError("Keine Adresse angegeben")

        contract_addr = self.network.get("wdoi_contract")
        if not contract_addr:
            logger.warning("Kein wDOI-Contract konfiguriert")
            return 0.0

        addr = Web3.to_checksum_address(addr)
        contract_addr = Web3.to_checksum_address(contract_addr)
        decimals = self.network.get("wdoi_decimals", 18)

        contract = self._w3.eth.contract(address=contract_addr, abi=ERC20_ABI)
        raw_balance = contract.functions.balanceOf(addr).call()
        return raw_to_wdoi(raw_balance, decimals)

    def get_all_balances(self, address: str = None) -> Dict[str, float]:
        """
        Fragt ETH- und wDOI-Saldo ab.

        Returns:
            {"ETH": float, "wDOI": float}
        """
        result = {"ETH": 0.0, "wDOI": 0.0}
        try:
            result["ETH"] = self.get_eth_balance(address)
        except Exception as e:
            logger.error(f"ETH-Saldo Fehler: {e}")
        try:
            result["wDOI"] = self.get_wdoi_balance(address)
        except Exception as e:
            logger.error(f"wDOI-Saldo Fehler: {e}")
        return result

    # ──────────────────────────────────────
    # Gas-Schätzung
    # ──────────────────────────────────────

    def estimate_gas_price(self) -> Dict[str, float]:
        """
        Schätzt aktuelle Gas-Preise.

        Returns:
            {"gas_price_gwei": float, "eth_transfer_cost_eth": float,
             "erc20_transfer_cost_eth": float}
        """
        if not self.is_connected:
            if not self.connect():
                raise ConnectionError("Keine Verbindung zu Ethereum")

        gas_price = self._w3.eth.gas_price
        gas_price_gwei = gas_price / 10**9

        eth_gas = 21_000
        erc20_gas = 65_000

        return {
            "gas_price_gwei": gas_price_gwei,
            "gas_price_wei": gas_price,
            "eth_transfer_gas": eth_gas,
            "erc20_transfer_gas": erc20_gas,
            "eth_transfer_cost_eth": wei_to_eth(gas_price * eth_gas),
            "erc20_transfer_cost_eth": wei_to_eth(gas_price * erc20_gas),
        }

    # ──────────────────────────────────────
    # ETH senden
    # ──────────────────────────────────────

    def send_eth(self, to_address: str, amount_eth: float) -> str:
        """
        Sendet ETH an eine Adresse.

        Args:
            to_address: Empfänger-Adresse
            amount_eth: Betrag in ETH

        Returns:
            Transaktions-Hash (0x...)
        """
        if not self.is_connected:
            if not self.connect():
                raise ConnectionError("Keine Verbindung zu Ethereum")

        if not self._private_key:
            raise ValueError("Kein Private Key geladen")

        if not validate_eth_address(to_address):
            raise ValueError(f"Ungültige ETH-Adresse: {to_address}")

        from_addr = Web3.to_checksum_address(self._address)
        to_addr = Web3.to_checksum_address(to_address)
        amount_wei = eth_to_wei(amount_eth)

        balance = self._w3.eth.get_balance(from_addr)
        gas_price = self._w3.eth.gas_price
        gas_limit = 21_000
        total_cost = amount_wei + (gas_price * gas_limit)

        if balance < total_cost:
            raise ValueError(
                f"Unzureichender ETH-Saldo! "
                f"Benötigt: {wei_to_eth(total_cost):.6f} ETH "
                f"(inkl. ~{wei_to_eth(gas_price * gas_limit):.6f} ETH Gas), "
                f"Vorhanden: {wei_to_eth(balance):.6f} ETH"
            )

        # "pending" berücksichtigt noch nicht bestätigte Transaktionen,
        # damit aufeinanderfolgende Sends nicht denselben Nonce verwenden
        nonce = self._w3.eth.get_transaction_count(from_addr, "pending")
        tx = {
            "nonce": nonce,
            "to": to_addr,
            "value": amount_wei,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": self.network["chain_id"],
        }

        signed = self._w3.eth.account.sign_transaction(tx, self._private_key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hex = tx_hash.hex()

        logger.info(f"ETH gesendet: {amount_eth} ETH -> {to_addr}, TX: {tx_hex}")
        return tx_hex

    # ──────────────────────────────────────
    # wDOI (ERC-20) senden
    # ──────────────────────────────────────

    def send_wdoi(self, to_address: str, amount: float) -> str:
        """
        Sendet wDOI (ERC-20) an eine Adresse.

        Args:
            to_address: Empfänger-Adresse (0x...)
            amount: Betrag in wDOI

        Returns:
            Transaktions-Hash (0x...)
        """
        if not self.is_connected:
            if not self.connect():
                raise ConnectionError("Keine Verbindung zu Ethereum")

        if not self._private_key:
            raise ValueError("Kein Private Key geladen")

        if not validate_eth_address(to_address):
            raise ValueError(f"Ungültige ETH-Adresse: {to_address}")

        contract_addr = self.network.get("wdoi_contract")
        if not contract_addr:
            raise ValueError("Kein wDOI-Contract konfiguriert")

        decimals = self.network.get("wdoi_decimals", 18)
        from_addr = Web3.to_checksum_address(self._address)
        to_addr = Web3.to_checksum_address(to_address)
        contract_addr = Web3.to_checksum_address(contract_addr)
        raw_amount = wdoi_to_raw(amount, decimals)

        contract = self._w3.eth.contract(address=contract_addr, abi=ERC20_ABI)
        wdoi_balance = contract.functions.balanceOf(from_addr).call()
        if wdoi_balance < raw_amount:
            raise ValueError(
                f"Unzureichender wDOI-Saldo! "
                f"Benötigt: {amount:.6f} wDOI, "
                f"Vorhanden: {raw_to_wdoi(wdoi_balance, decimals):.6f} wDOI"
            )

        gas_price = self._w3.eth.gas_price
        try:
            gas_estimate = contract.functions.transfer(
                to_addr, raw_amount
            ).estimate_gas({"from": from_addr})
            gas_limit = int(gas_estimate * 1.2)
        except Exception:
            gas_limit = 80_000

        eth_balance = self._w3.eth.get_balance(from_addr)
        gas_cost = gas_price * gas_limit
        if eth_balance < gas_cost:
            raise ValueError(
                f"Unzureichendes ETH für Gas! "
                f"Benötigt: ~{wei_to_eth(gas_cost):.6f} ETH, "
                f"Vorhanden: {wei_to_eth(eth_balance):.6f} ETH"
            )

        # "pending" berücksichtigt noch nicht bestätigte Transaktionen,
        # damit aufeinanderfolgende Sends nicht denselben Nonce verwenden
        nonce = self._w3.eth.get_transaction_count(from_addr, "pending")
        tx = contract.functions.transfer(to_addr, raw_amount).build_transaction({
            "from": from_addr,
            "nonce": nonce,
            "gas": gas_limit,
            "gasPrice": gas_price,
            "chainId": self.network["chain_id"],
        })

        signed = self._w3.eth.account.sign_transaction(tx, self._private_key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
        tx_hex = tx_hash.hex()

        logger.info(f"wDOI gesendet: {amount} wDOI -> {to_addr}, TX: {tx_hex}")
        return tx_hex

    # ──────────────────────────────────────
    # Transaktions-Info
    # ──────────────────────────────────────

    def get_transaction(self, tx_hash: str) -> Optional[Dict]:
        """Ruft Details einer Transaktion ab."""
        if not self.is_connected:
            return None
        try:
            tx = self._w3.eth.get_transaction(tx_hash)
            receipt = self._w3.eth.get_transaction_receipt(tx_hash)
            return {
                "hash": tx_hash,
                "from": tx["from"],
                "to": tx["to"],
                "value_eth": wei_to_eth(tx["value"]),
                "gas_used": receipt["gasUsed"] if receipt else None,
                "status": receipt["status"] if receipt else None,
                "block": receipt["blockNumber"] if receipt else None,
            }
        except Exception as e:
            logger.error(f"TX-Abfrage Fehler: {e}")
            return None

    def get_explorer_url(self, tx_hash: str) -> str:
        """Gibt den Explorer-Link für eine Transaktion zurück."""
        explorer = self.network.get("explorer", "https://etherscan.io")
        return f"{explorer}/tx/{tx_hash}"

    def get_address_explorer_url(self, address: str = None) -> str:
        """Gibt den Explorer-Link für eine Adresse zurück."""
        addr = address or self._address
        explorer = self.network.get("explorer", "https://etherscan.io")
        return f"{explorer}/address/{addr}"

    # ──────────────────────────────────────
    # Token-Info
    # ──────────────────────────────────────

    def get_wdoi_info(self) -> Optional[Dict]:
        """Ruft Informationen über den wDOI-Token ab."""
        if not self.is_connected:
            if not self.connect():
                return None

        contract_addr = self.network.get("wdoi_contract")
        if not contract_addr:
            return None

        try:
            contract_addr = Web3.to_checksum_address(contract_addr)
            contract = self._w3.eth.contract(address=contract_addr, abi=ERC20_ABI)

            name = contract.functions.name().call()
            symbol = contract.functions.symbol().call()
            decimals = contract.functions.decimals().call()
            total_supply_raw = contract.functions.totalSupply().call()
            total_supply = total_supply_raw / 10**decimals

            return {
                "name": name,
                "symbol": symbol,
                "decimals": decimals,
                "total_supply": total_supply,
                "contract": contract_addr,
            }
        except Exception as e:
            logger.error(f"wDOI-Info Fehler: {e}")
            return None

    # ──────────────────────────────────────
    # Transaktions-History (via RPC Event Logs)
    # ──────────────────────────────────────

    def get_eth_history(self, address: str = None, limit: int = 20) -> List[Dict]:
        """
        Ruft ETH-Transaktionshistory über RPC ab.
        Scannt die letzten Blöcke nach normalen ETH-Transaktionen.

        Hinweis: Normale ETH-Transfers sind nicht über Event Logs abrufbar.
        Wir nutzen einen Fallback über die letzten Blöcke oder geben [] zurück,
        da kostenlose RPCs keine Volltextsuche nach ETH-Transfers unterstützen.
        """
        # ETH-Transfers sind keine Events und können nicht über getLogs gefunden werden.
        # Ohne Etherscan API-Key gibt es keinen zuverlässigen Weg.
        # Wir geben eine leere Liste zurück – der Benutzer kann Etherscan manuell prüfen.
        logger.info("ETH-History: Nicht über kostenlose RPCs verfügbar (nutze Etherscan Explorer)")
        return []

    def get_wdoi_history(self, address: str = None, limit: int = 20) -> List[Dict]:
        """
        Ruft wDOI (ERC-20) Transfer-History ab.
        Primaer: Blockscout Token-Transfer API (unbegrenzt).
        Fallback: RPC Event Logs.
        """
        addr = address or self._address
        if not addr:
            return []

        contract_addr_str = self.network.get("wdoi_contract")
        if not contract_addr_str:
            return []

        decimals = self.network.get("wdoi_decimals", 18)

        # -- Methode 1: Blockscout Token-Transfer API --
        try:
            import requests
            addr_lower = addr.lower()
            contract_lower = contract_addr_str.lower()
            url = f"https://eth.blockscout.com/api/v2/addresses/{addr_lower}/token-transfers"
            params = {"token": contract_lower, "type": "ERC-20", "limit": limit}

            logger.debug(f"wDOI-History: Blockscout -> {url}")
            resp = requests.get(url, params=params, timeout=15)

            if resp.status_code == 200:
                data = resp.json()
                items = data.get("items", [])
                logger.debug(f"wDOI-History: Blockscout lieferte {len(items)} Transfers")

                result = []
                for item in items[:limit]:
                    try:
                        from_addr = item.get("from", {}).get("hash", "")
                        to_addr = item.get("to", {}).get("hash", "")

                        total = item.get("total", {})
                        if isinstance(total, dict):
                            raw_value = int(total.get("value", "0"))
                        else:
                            raw_value = int(total) if total else 0
                        value = raw_value / 10 ** decimals

                        direction = "received" if to_addr.lower() == addr_lower else "sent"
                        tx_hash = item.get("tx_hash", "")

                        timestamp = 0
                        ts_str = item.get("timestamp", "")
                        if ts_str:
                            try:
                                from datetime import datetime, timezone
                                dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                                timestamp = int(dt.timestamp())
                            except Exception:
                                pass

                        block_num = item.get("block_number", 0)

                        result.append({
                            "hash": tx_hash,
                            "from": from_addr,
                            "to": to_addr,
                            "value": value,
                            "symbol": "wDOI",
                            "timestamp": timestamp,
                            "direction": direction,
                            "block": block_num,
                        })
                    except Exception as e:
                        logger.debug(f"wDOI-History: Transfer-Parse-Fehler: {e}")
                        continue

                if result:
                    logger.info(f"wDOI-History: {len(result)} Transfers (Blockscout)")
                    return result

            logger.debug(f"wDOI-History: Blockscout Status {resp.status_code}")
        except Exception as e:
            logger.debug(f"wDOI-History: Blockscout fehlgeschlagen: {e}")

        # -- Methode 2: Fallback RPC Event Logs --
        try:
            from web3 import Web3

            transfer_abi = {
                "anonymous": False,
                "inputs": [
                    {"indexed": True, "name": "from", "type": "address"},
                    {"indexed": True, "name": "to", "type": "address"},
                    {"indexed": False, "name": "value", "type": "uint256"},
                ],
                "name": "Transfer",
                "type": "event",
            }

            rpc_configs = [
                (self._w3, 5000, 40),
                (None, 10000, 20),
            ]

            addr_cs = Web3.to_checksum_address(addr)
            contract_cs = Web3.to_checksum_address(contract_addr_str)

            for w3_instance, chunk_size, max_chunks in rpc_configs:
                if w3_instance is None:
                    try:
                        w3_instance = Web3(Web3.HTTPProvider(
                            "https://1rpc.io/eth",
                            request_kwargs={"timeout": 15}
                        ))
                        if not w3_instance.is_connected():
                            continue
                    except Exception:
                        continue

                try:
                    contract = w3_instance.eth.contract(
                        address=contract_cs, abi=[transfer_abi]
                    )
                    latest = w3_instance.eth.block_number
                    all_events = []

                    for i in range(max_chunks):
                        to_block = latest - (i * chunk_size)
                        from_block = max(0, to_block - chunk_size + 1)
                        if to_block < 0:
                            break

                        try:
                            received = contract.events.Transfer.get_logs(
                                from_block=from_block, to_block=to_block,
                                argument_filters={"to": addr_cs},
                            )
                            for evt in received:
                                all_events.append((evt, "received"))
                        except Exception:
                            pass

                        try:
                            sent = contract.events.Transfer.get_logs(
                                from_block=from_block, to_block=to_block,
                                argument_filters={"from": addr_cs},
                            )
                            for evt in sent:
                                all_events.append((evt, "sent"))
                        except Exception:
                            pass

                        if len(all_events) >= limit:
                            break

                    if all_events:
                        all_events.sort(key=lambda x: x[0]["blockNumber"], reverse=True)
                        result = []
                        for evt, direction in all_events[:limit]:
                            value = evt["args"]["value"] / 10 ** decimals
                            tx_hash = evt["transactionHash"].hex()
                            block_num = evt["blockNumber"]

                            try:
                                block_info = w3_instance.eth.get_block(block_num)
                                timestamp = block_info["timestamp"]
                            except Exception:
                                timestamp = 0

                            result.append({
                                "hash": tx_hash,
                                "from": evt["args"]["from"],
                                "to": evt["args"]["to"],
                                "value": value,
                                "symbol": "wDOI",
                                "timestamp": timestamp,
                                "direction": direction,
                                "block": block_num,
                            })

                        logger.info(f"wDOI-History: {len(result)} Transfers (RPC Fallback)")
                        return result

                except Exception as e:
                    logger.debug(f"wDOI-History: RPC fehlgeschlagen: {e}")
                    continue

            return []

        except Exception as e:
            logger.error(f"wDOI-History Fehler: {e}")
            return []
