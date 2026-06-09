"""
XT.com Exchange Client
=======================

REST-API Client für XT.com (Spot Trading).
Unterstützt öffentliche und private (authentifizierte) Endpoints.

Öffentlich (kein API-Key):
- Ticker (aktueller Preis)
- Orderbuch
- Kerzendaten (Klines)
- Währungsinfos (Deposit/Withdrawal Status)

Privat (API-Key + Secret):
- Kontosaldo
- Order erstellen (Limit/Market)
- Offene Orders anzeigen
- Order stornieren
- Order-History

Verwendung:
    from src.exchange.xt_client import XTClient

    # Öffentlich (kein Key nötig)
    xt = XTClient()
    price = xt.get_ticker()
    orderbook = xt.get_orderbook()

    # Privat (Key nötig)
    xt = XTClient(api_key="...", api_secret="...")
    balance = xt.get_balance()
    order = xt.place_limit_order("BUY", price=0.033, quantity=100)
"""

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Union

import requests

logger = logging.getLogger(__name__)

# Akzeptierte Eingabetypen für Preise/Mengen
Amount = Union[float, str, Decimal]


def _format_amount(value: Amount) -> str:
    """
    Konvertiert float/str/Decimal verlustarm in einen API-String.

    Vermeidet Float-Artefakte wie "0.30000000000000004" und
    Exponenten-Notation wie "1e-05" (XT.com erwartet Dezimalschreibweise).
    """
    try:
        d = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"Ungültiger Zahlenwert: {value!r}")
    if not d.is_finite():
        raise ValueError(f"Ungültiger Zahlenwert: {value!r}")
    return format(d, "f")  # keine Exponenten-Notation

# ──────────────────────────────────────────────
# Konstanten
# ──────────────────────────────────────────────

DEFAULT_BASE_URL = "https://sapi.xt.com"
DEFAULT_SYMBOL = "doi_usdt"
DEFAULT_TIMEOUT = 15


# ──────────────────────────────────────────────
# XT.com Client
# ──────────────────────────────────────────────

class XTClient:
    """
    XT.com Spot Trading API Client.

    Args:
        api_key: API-Key für private Endpoints (optional)
        api_secret: API-Secret für Signierung (optional)
        base_url: API Basis-URL
        symbol: Trading-Paar (default: doi_usdt)
    """

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        base_url: str = DEFAULT_BASE_URL,
        symbol: str = DEFAULT_SYMBOL,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.symbol = symbol
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "DoichainWalletXT/1.0",
        })

    # ──────────────────────────────────────────
    # HTTP Helpers
    # ──────────────────────────────────────────

    @staticmethod
    def _build_query(params: dict = None) -> str:
        """
        Baut den Query-String, der sowohl signiert als auch gesendet wird.

        Wichtig: Signatur und Request müssen byte-identisch sein, deshalb
        wird der String genau einmal hier erzeugt (URL-encodiert, sortiert)
        und anschließend unverändert an die URL angehängt.
        Booleans werden zu "true"/"false" normalisiert (nicht Python "True").
        """
        if not params:
            return ""
        normalized = []
        for key, value in sorted(params.items()):
            if isinstance(value, bool):
                value = "true" if value else "false"
            normalized.append((key, str(value)))
        return urllib.parse.urlencode(normalized)

    def _sign(self, method: str, path: str, query: str = "", body: str = "") -> dict:
        """
        Erstellt die XT.com v4 Signatur-Header.

        Format laut Doku:
            X = validate-algorithms=HmacSHA256&validate-appkey=...&validate-recvwindow=...&validate-timestamp=...
            Y = #METHOD#path[#query][#body]
            original = X + Y
            signature = HmacSHA256(secret, original)

        Args:
            query: Fertiger Query-String aus _build_query() – wird exakt
                   so signiert, wie er gesendet wird.
        """
        timestamp = str(int(time.time() * 1000))
        recvwindow = "60000"
        query_string = query or ""

        # X: Header-Paare alphabetisch sortiert
        header_params = {
            "validate-algorithms": "HmacSHA256",
            "validate-appkey": self.api_key,
            "validate-recvwindow": recvwindow,
            "validate-timestamp": timestamp,
        }
        x_part = "&".join(f"{k}={v}" for k, v in sorted(header_params.items()))

        # Y: #METHOD#path[#query][#body]
        y_part = f"#{method.upper()}#{path}"
        if query_string:
            y_part += f"#{query_string}"
        if body:
            y_part += f"#{body}"

        # Signatur berechnen
        original = x_part + y_part
        signature = hmac.new(
            self.api_secret.encode("utf-8"),
            original.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return {
            "validate-algorithms": "HmacSHA256",
            "validate-appkey": self.api_key,
            "validate-recvwindow": recvwindow,
            "validate-timestamp": timestamp,
            "validate-signature": signature,
        }

    @staticmethod
    def _raise_http_error(path: str, e: requests.exceptions.HTTPError):
        """
        Wandelt einen HTTPError in eine aussagekräftige Exception um.

        Der Response-Body (auf ~300 Zeichen gekürzt) wird mitgegeben,
        damit die XT.com Fehlermeldung nicht verloren geht.
        HTTP 429 wird als Rate-Limit gesondert ausgewiesen.
        """
        resp = e.response
        status = resp.status_code if resp is not None else "?"
        body = (resp.text or "").strip()[:300] if resp is not None else ""
        if status == 429:
            raise ConnectionError(
                f"XT.com Rate-Limit erreicht (HTTP 429) bei {path} – "
                f"bitte Anfragen drosseln. Antwort: {body}"
            )
        raise ConnectionError(f"XT.com HTTP-Fehler {status} bei {path}: {body}")

    def _public_get(self, path: str, params: dict = None) -> dict:
        """Öffentlicher GET-Request."""
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if data.get("rc") != 0:
                # Fehler hart melden statt leere Daten (z.B. Preis 0.0) weiterzugeben
                raise RuntimeError(f"XT.com API-Fehler: {data.get('mc', 'Unbekannt')}")
            return data
        except requests.exceptions.HTTPError as e:
            logger.error(f"XT.com GET {path}: {e}")
            self._raise_http_error(path, e)
        except requests.exceptions.RequestException as e:
            logger.error(f"XT.com GET {path}: {e}")
            raise ConnectionError(f"XT.com API nicht erreichbar: {e}")

    def _private_get(self, path: str, params: dict = None) -> dict:
        """Authentifizierter GET-Request."""
        self._require_auth()
        # Query-String einmal bauen: identisch signieren und senden
        query = self._build_query(params)
        headers = self._sign("GET", path, query=query)
        url = f"{self.base_url}{path}"
        if query:
            url += f"?{query}"
        try:
            resp = self.session.get(url, headers=headers, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"XT.com private GET {path}: {e}")
            self._raise_http_error(path, e)
        except requests.exceptions.RequestException as e:
            logger.error(f"XT.com private GET {path}: {e}")
            raise ConnectionError(f"XT.com API nicht erreichbar: {e}")

    def _private_post(self, path: str, data: dict = None) -> dict:
        """Authentifizierter POST-Request."""
        self._require_auth()
        body = json.dumps(data, separators=(",", ":")) if data else ""
        headers = self._sign("POST", path, body=body)
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.post(url, data=body, headers=headers, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"XT.com private POST {path}: {e}")
            self._raise_http_error(path, e)
        except requests.exceptions.RequestException as e:
            logger.error(f"XT.com private POST {path}: {e}")
            raise ConnectionError(f"XT.com API nicht erreichbar: {e}")

    def _private_delete(self, path: str, params: dict = None) -> dict:
        """Authentifizierter DELETE-Request."""
        self._require_auth()
        # Query-String einmal bauen: identisch signieren und senden
        query = self._build_query(params)
        headers = self._sign("DELETE", path, query=query)
        url = f"{self.base_url}{path}"
        if query:
            url += f"?{query}"
        try:
            resp = self.session.delete(url, headers=headers, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            logger.error(f"XT.com private DELETE {path}: {e}")
            self._raise_http_error(path, e)
        except requests.exceptions.RequestException as e:
            logger.error(f"XT.com private DELETE {path}: {e}")
            raise ConnectionError(f"XT.com API nicht erreichbar: {e}")

    def _require_auth(self):
        """Prüft ob API-Credentials vorhanden sind."""
        if not self.api_key or not self.api_secret:
            raise ValueError(
                "XT.com API-Key und Secret benötigt! "
                "Konfiguriere sie in config/config.yaml"
            )

    # ──────────────────────────────────────────
    # Öffentliche Endpoints
    # ──────────────────────────────────────────

    def get_ticker(self, symbol: str = None) -> dict:
        """
        Aktueller Preis eines Trading-Paars.

        Returns:
            {"symbol": "doi_usdt", "price": 0.033, "time": ...}
        """
        sym = symbol or self.symbol
        data = self._public_get("/v4/public/ticker/price", {"symbol": sym})
        result = data.get("result", {})
        if isinstance(result, list):
            result = result[0] if result else {}

        return {
            "symbol": result.get("s", sym),
            "price": float(result.get("p", 0)),
            "time": result.get("t"),
        }

    def get_ticker_24h(self, symbol: str = None) -> dict:
        """
        24h Ticker-Statistiken.

        Returns:
            {"price": float, "high": float, "low": float,
             "volume": float, "change_pct": float, ...}
        """
        sym = symbol or self.symbol
        data = self._public_get("/v4/public/ticker/24h", {"symbol": sym})
        result = data.get("result", {})
        if isinstance(result, list):
            result = result[0] if result else {}

        return {
            "symbol": result.get("s", sym),
            "price": float(result.get("c", 0)),     # Close
            "open": float(result.get("o", 0)),       # Open
            "high": float(result.get("h", 0)),       # High
            "low": float(result.get("l", 0)),        # Low
            "volume": float(result.get("v", 0)),     # Volume (base)
            "quote_volume": float(result.get("qv", 0)),  # Volume (quote/USDT)
            "change_pct": float(result.get("cr", 0)) * 100,  # Change %
        }

    def get_orderbook(self, symbol: str = None, limit: int = 10) -> dict:
        """
        Orderbuch (Asks + Bids).

        Returns:
            {
                "asks": [{"price": float, "quantity": float}, ...],
                "bids": [{"price": float, "quantity": float}, ...],
                "best_ask": float, "best_bid": float,
                "spread": float, "spread_pct": float
            }
        """
        sym = symbol or self.symbol
        data = self._public_get("/v4/public/depth", {"symbol": sym, "limit": limit})
        result = data.get("result", {})

        asks = sorted([
            {"price": float(a[0]), "quantity": float(a[1])}
            for a in result.get("asks", [])
        ], key=lambda x: x["price"])  # aufsteigend: billigste zuerst

        bids = sorted([
            {"price": float(b[0]), "quantity": float(b[1])}
            for b in result.get("bids", [])
        ], key=lambda x: x["price"], reverse=True)  # absteigend: teuerste zuerst

        best_ask = asks[0]["price"] if asks else 0
        best_bid = bids[0]["price"] if bids else 0
        spread = best_ask - best_bid if best_ask and best_bid else 0
        spread_pct = (spread / best_ask * 100) if best_ask else 0

        return {
            "asks": asks,
            "bids": bids,
            "best_ask": best_ask,
            "best_bid": best_bid,
            "spread": spread,
            "spread_pct": spread_pct,
        }

    def get_klines(self, interval: str = "1h", limit: int = 24, symbol: str = None) -> List[dict]:
        """
        Kerzendaten (OHLCV).

        Args:
            interval: "1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w"
            limit: Anzahl Kerzen (max 1000)

        Returns:
            [{"time": int, "open": float, "high": float, "low": float,
              "close": float, "volume": float}, ...]
        """
        sym = symbol or self.symbol
        data = self._public_get("/v4/public/kline", {
            "symbol": sym,
            "interval": interval,
            "limit": limit,
        })
        result = data.get("result", [])

        return [
            {
                "time": int(k.get("t", 0)),
                "open": float(k.get("o", 0)),
                "high": float(k.get("h", 0)),
                "low": float(k.get("l", 0)),
                "close": float(k.get("c", 0)),
                "volume": float(k.get("v", 0)),
            }
            for k in result
        ]

    def get_currency_info(self, currency: str = "doi") -> Optional[dict]:
        """
        Währungsinfos (Deposit/Withdrawal Status, Gebühren).

        Returns:
            {"currency": str, "chains": [{"chain": str, "deposit": bool,
             "withdraw": bool, "withdraw_fee": float, "withdraw_min": float}]}
        """
        data = self._public_get("/v4/public/wallet/support/currency")
        currencies = data.get("result", [])

        info = next((c for c in currencies if c.get("currency", "").lower() == currency.lower()), None)
        if not info:
            return None

        chains = []
        for chain_info in info.get("supportChains", []):
            chains.append({
                "chain": chain_info.get("chain", "?"),
                "deposit": chain_info.get("depositEnabled", False),
                "withdraw": chain_info.get("withdrawEnabled", False),
                "withdraw_fee": float(chain_info.get("withdrawFeeAmount", 0)),
                "withdraw_min": float(chain_info.get("withdrawMinAmount", 0)),
            })

        return {"currency": currency.upper(), "chains": chains}

    def calculate_vwap(self, quantity: float, side: str = "BUY", symbol: str = None) -> dict:
        """
        Berechnet den volumengewichteten Durchschnittspreis (VWAP)
        für eine bestimmte Menge basierend auf dem Orderbuch.

        Args:
            quantity: Menge DOI
            side: "BUY" (durch Asks) oder "SELL" (durch Bids)

        Returns:
            {"vwap": float, "total_cost": float, "filled": float,
             "slippage_pct": float, "fills": [...]}
        """
        ob = self.get_orderbook(symbol=symbol, limit=50)
        side = side.upper()
        levels = ob["asks"] if side == "BUY" else ob["bids"]
        base_price = ob["best_ask"] if side == "BUY" else ob["best_bid"]

        if not levels:
            # Leeres Orderbuch: Fehler melden statt vwap=0 zurückzugeben
            raise RuntimeError(
                f"Orderbuch für {symbol or self.symbol} ist leer ({side}-Seite) – "
                f"VWAP kann nicht berechnet werden."
            )

        total_cost = 0.0
        total_filled = 0.0
        fills = []

        for level in levels:
            remaining = quantity - total_filled
            if remaining <= 0:
                break

            fill_qty = min(level["quantity"], remaining)
            fill_cost = fill_qty * level["price"]
            fills.append({
                "price": level["price"],
                "quantity": fill_qty,
                "cost": fill_cost,
            })
            total_cost += fill_cost
            total_filled += fill_qty

        if total_filled <= 0:
            raise RuntimeError(
                f"Keine Liquidität im Orderbuch für {symbol or self.symbol} ({side}) – "
                f"VWAP kann nicht berechnet werden."
            )

        vwap = total_cost / total_filled
        slippage = ((vwap - base_price) / base_price * 100) if base_price else 0

        return {
            "vwap": vwap,
            "total_cost": total_cost,
            "filled": total_filled,
            "requested": quantity,
            "slippage_pct": abs(slippage),
            "fills": fills,
            "fully_filled": total_filled >= quantity,
        }

    # ──────────────────────────────────────────
    # Private Endpoints – Konto
    # ──────────────────────────────────────────

    def get_balances(self) -> List[dict]:
        """
        Alle Kontosalden.

        Hinweis: Beträge werden als Decimal zurückgegeben (verlustfrei,
        z.B. für Order-Mengen). Decimal verhält sich bei Vergleichen und
        Formatierung (f"{x:.6f}") wie float.

        Returns:
            [{"currency": str, "available": Decimal, "frozen": Decimal, "total": Decimal}, ...]
        """
        data = self._private_get("/v4/balances")
        if data.get("rc") != 0:
            raise ValueError(f"XT.com API-Fehler: {data.get('mc', 'Unbekannt')}")

        result = data.get("result", {})
        # Assets können unter result.assets oder direkt in result liegen
        assets = result.get("assets", result) if isinstance(result, dict) else result

        if not isinstance(assets, list):
            assets = []

        def _dec(value) -> Decimal:
            """API-Betrag verlustfrei in Decimal wandeln."""
            try:
                return Decimal(str(value))
            except (InvalidOperation, ValueError, TypeError):
                return Decimal(0)

        return [
            {
                "currency": a.get("currency", "").upper(),
                "available": _dec(a.get("availableAmount", 0)),
                "frozen": _dec(a.get("frozenAmount", 0)),
                "total": _dec(a.get("totalAmount", 0)),
            }
            for a in assets
            if _dec(a.get("totalAmount", 0)) > 0
        ]

    def get_balance(self, currency: str) -> dict:
        """
        Saldo einer bestimmten Währung.

        Returns:
            {"currency": str, "available": Decimal, "frozen": Decimal}
        """
        balances = self.get_balances()
        bal = next((b for b in balances if b["currency"] == currency.upper()), None)
        return bal or {
            "currency": currency.upper(),
            "available": Decimal(0),
            "frozen": Decimal(0),
            "total": Decimal(0),
        }

    # ──────────────────────────────────────────
    # Private Endpoints – Orders
    # ──────────────────────────────────────────

    def place_limit_order(
        self,
        side: str,
        price: Amount,
        quantity: Amount,
        symbol: str = None,
    ) -> dict:
        """
        Erstellt eine Limit-Order.

        Args:
            side: "BUY" oder "SELL"
            price: Limit-Preis in USDT (float, str oder Decimal)
            quantity: Menge DOI (float, str oder Decimal)
            symbol: Trading-Paar (default: doi_usdt)

        Returns:
            {"order_id": str, ...}
        """
        sym = symbol or self.symbol
        order_data = {
            "symbol": sym,
            "side": side.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",  # Good Till Cancelled
            "bizType": "SPOT",
            # Decimal-basiert formatieren: keine Float-Artefakte, kein Exponent
            "price": _format_amount(price),
            "quantity": _format_amount(quantity),
        }

        data = self._private_post("/v4/order", order_data)

        if data.get("rc") != 0:
            raise ValueError(f"Order fehlgeschlagen: {data.get('mc', 'Unbekannt')}")

        result = data.get("result", {})
        return {
            "order_id": str(result.get("orderId", "")),
            "symbol": sym,
            "side": side.upper(),
            "price": price,
            "quantity": quantity,
            "type": "LIMIT",
            "status": "NEW",
        }

    def place_market_order(
        self,
        side: str,
        quantity: Amount = None,
        quote_quantity: Amount = None,
        symbol: str = None,
    ) -> dict:
        """
        Erstellt eine Market-Order.

        Args:
            side: "BUY" oder "SELL"
            quantity: Menge DOI (nur für SELL)
            quote_quantity: USDT-Betrag (Pflicht für BUY – XT.com Spot
                            akzeptiert bei MARKET-BUY nur quoteQty)
            symbol: Trading-Paar

        Returns:
            {"order_id": str, ...}
        """
        sym = symbol or self.symbol
        order_data = {
            "symbol": sym,
            "side": side.upper(),
            "type": "MARKET",
            "bizType": "SPOT",
        }

        if side.upper() == "BUY":
            if not quote_quantity:
                # XT.com Spot lehnt MARKET-BUY mit quantity ab –
                # früh und verständlich fehlschlagen statt ungültige Order zu senden
                raise ValueError(
                    "MARKET-BUY benötigt quote_quantity (USDT-Betrag). "
                    "XT.com akzeptiert bei Market-Käufen nur quoteQty, keine Stückzahl."
                )
            order_data["quoteQty"] = _format_amount(quote_quantity)
        elif quantity:
            order_data["quantity"] = _format_amount(quantity)
        else:
            raise ValueError("quantity oder quote_quantity muss angegeben werden")

        data = self._private_post("/v4/order", order_data)

        if data.get("rc") != 0:
            raise ValueError(f"Order fehlgeschlagen: {data.get('mc', 'Unbekannt')}")

        result = data.get("result", {})
        return {
            "order_id": str(result.get("orderId", "")),
            "symbol": sym,
            "side": side.upper(),
            "type": "MARKET",
            "status": "NEW",
        }

    def get_open_orders(self, symbol: str = None) -> List[dict]:
        """
        Offene Orders abfragen.

        Returns:
            [{"order_id": str, "side": str, "price": float,
              "quantity": float, "filled": float, "status": str}, ...]
        """
        sym = symbol or self.symbol
        data = self._private_get("/v4/open-order", {"symbol": sym})

        if data.get("rc") != 0:
            raise ValueError(f"XT.com API-Fehler: {data.get('mc', 'Unbekannt')}")

        orders = data.get("result", [])
        return [
            {
                "order_id": str(o.get("orderId", "")),
                "symbol": o.get("symbol", sym),
                "side": o.get("side", ""),
                "type": o.get("type", ""),
                "price": float(o.get("price", 0)),
                "quantity": float(o.get("origQty", 0)),
                "filled": float(o.get("executedQty", 0)),
                "status": o.get("state", ""),
                "time": o.get("time", 0),
            }
            for o in orders
        ]

    def cancel_order(self, order_id: str) -> dict:
        """
        Storniert eine Order.

        Args:
            order_id: Order-ID

        Returns:
            {"order_id": str, "status": "CANCELED"}
        """
        data = self._private_delete(f"/v4/order/{order_id}")

        if data.get("rc") != 0:
            raise ValueError(f"Stornierung fehlgeschlagen: {data.get('mc', 'Unbekannt')}")

        return {"order_id": order_id, "status": "CANCELED"}

    def cancel_all_orders(self, symbol: str = None) -> dict:
        """Storniert alle offenen Orders."""
        sym = symbol or self.symbol
        data = self._private_delete("/v4/open-order", {"symbol": sym})

        if data.get("rc") != 0:
            raise ValueError(f"Stornierung fehlgeschlagen: {data.get('mc', 'Unbekannt')}")

        return {"symbol": sym, "status": "ALL_CANCELED"}

    def get_order(self, order_id: str) -> dict:
        """
        Einzelne Order abfragen.

        Returns:
            {"order_id": str, "side": str, "price": float, ...}
        """
        data = self._private_get(f"/v4/order/{order_id}")

        if data.get("rc") != 0:
            raise ValueError(f"XT.com API-Fehler: {data.get('mc', 'Unbekannt')}")

        o = data.get("result", {})
        return {
            "order_id": str(o.get("orderId", "")),
            "symbol": o.get("symbol", ""),
            "side": o.get("side", ""),
            "type": o.get("type", ""),
            "price": float(o.get("price", 0)),
            "quantity": float(o.get("origQty", 0)),
            "filled": float(o.get("executedQty", 0)),
            "avg_price": float(o.get("avgPrice", 0)),
            "status": o.get("state", ""),
            "time": o.get("time", 0),
        }

    def get_order_history(self, symbol: str = None, limit: int = 20) -> List[dict]:
        """
        Order-History (abgeschlossene Orders).

        Returns:
            [{"order_id": str, "side": str, ...}, ...]
        """
        sym = symbol or self.symbol
        data = self._private_get("/v4/history-order", {"symbol": sym, "limit": limit})

        if data.get("rc") != 0:
            raise ValueError(f"XT.com API-Fehler: {data.get('mc', 'Unbekannt')}")

        orders = data.get("result", [])
        return [
            {
                "order_id": str(o.get("orderId", "")),
                "symbol": o.get("symbol", sym),
                "side": o.get("side", ""),
                "type": o.get("type", ""),
                "price": float(o.get("price", 0)),
                "quantity": float(o.get("origQty", 0)),
                "filled": float(o.get("executedQty", 0)),
                "avg_price": float(o.get("avgPrice", 0)),
                "status": o.get("state", ""),
                "time": o.get("time", 0),
            }
            for o in orders
        ]

    # ──────────────────────────────────────────
    # Hilfsfunktionen
    # ──────────────────────────────────────────

    @property
    def has_credentials(self) -> bool:
        """Prüft ob API-Credentials konfiguriert sind."""
        return bool(self.api_key and self.api_secret)

    def is_connected(self) -> bool:
        """Prüft die Verbindung zur API."""
        try:
            self.get_ticker()
            return True
        except Exception:
            return False

    def __repr__(self):
        auth = "authenticated" if self.has_credentials else "public only"
        return f"XTClient({self.symbol}, {auth})"
