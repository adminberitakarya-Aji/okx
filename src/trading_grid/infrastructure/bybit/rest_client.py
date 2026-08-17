"""
Bybit REST API client (API v5).

This module provides:
- Authenticated REST client for Bybit API v5
- Request signing (HMAC-SHA256, no passphrase)
- Retry logic
- Testnet/Live mode support (separate base URLs)

Security rules:
1. API keys: Read + Trade only, Withdraw DISABLED
2. Testnet and Live use separate credentials
3. Secrets never in logs

Reference: https://bybit-exchange.github.io/docs/v5/intro
"""

import hashlib
import hmac
import json
import time
from typing import Any

import httpx
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from trading_grid.config.settings import BybitSettings
from trading_grid.domain.exchange.errors import ExchangeAPIError

logger = structlog.get_logger()

RECV_WINDOW = "5000"


class BybitAPIError(ExchangeAPIError):
    """
    Bybit API error.

    Inherits from ExchangeAPIError so the application layer can handle all
    exchange errors uniformly while preserving Bybit-specific error detail
    (retCode + retMsg) for debugging and audit logging.
    """

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        """Initialize with error details."""
        super().__init__(code=code, message=message, data=data or {})

    def __str__(self) -> str:
        """Preserve the Bybit error message format."""
        return f"Bybit API Error {self.code}: {self.message}"


class BybitRestClient:
    """
    Bybit REST API v5 client.

    Provides authenticated access to Bybit REST endpoints.
    """

    def __init__(self, settings: BybitSettings) -> None:
        """
        Initialize REST client.

        Args:
            settings: Bybit API settings
        """
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BybitRestClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is created."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self._settings.effective_base_url,
                timeout=self._settings.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _sign(self, timestamp: str, params_str: str) -> str:
        """
        Sign request using HMAC-SHA256.

        Bybit v5 signature: HMAC_SHA256(secret, timestamp + api_key + recv_window + params_str)
        """
        api_key = self._settings.api_key.get_secret_value()
        secret = self._settings.api_secret.get_secret_value()
        message = f"{timestamp}{api_key}{RECV_WINDOW}{params_str}"
        signature = hmac.new(
            secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_auth_headers(self, timestamp: str, params_str: str) -> dict[str, str]:
        """Get authentication headers for signed request."""
        api_key = self._settings.api_key.get_secret_value()
        signature = self._sign(timestamp, params_str)
        return {
            "X-BAPI-API-KEY": api_key,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "X-BAPI-SIGN": signature,
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> dict[str, Any]:
        """
        Make API request.

        Args:
            method: HTTP method
            path: API path
            params: Query parameters (GET)
            body: Request body (POST)
            signed: Whether to sign the request

        Returns:
            API response "result" payload

        Raises:
            BybitAPIError: If API returns non-zero retCode
        """
        client = await self._ensure_client()

        timestamp = str(int(time.time() * 1000))
        headers: dict[str, str] = {}

        if method.upper() == "GET":
            params_str = ""
            if params:
                params_str = "&".join(f"{k}={v}" for k, v in params.items())
            if signed:
                headers = self._get_auth_headers(timestamp, params_str)
            response = await client.request(method=method, url=path, params=params, headers=headers)
        else:
            body_str = json.dumps(body) if body else ""
            if signed:
                headers = self._get_auth_headers(timestamp, body_str)
            response = await client.request(
                method=method, url=path, content=body_str, headers=headers
            )

        data: dict[str, Any] = response.json()

        # Bybit v5: retCode 0 = success
        ret_code = data.get("retCode", -1)
        if ret_code != 0:
            ret_msg = data.get("retMsg", "Unknown error")
            logger.error("bybit_api_error", code=ret_code, message=ret_msg, path=path)
            raise BybitAPIError(code=str(ret_code), message=ret_msg, data=data)

        result: dict[str, Any] = data.get("result", {})
        return result

    # =========================================================================
    # Public endpoints (no authentication)
    # =========================================================================

    async def get_instruments(self, category: str = "spot") -> dict[str, Any]:
        """Get available instruments."""
        return await self._request(
            "GET", "/v5/market/instruments-info", params={"category": category}
        )

    async def get_ticker(self, symbol: str, category: str = "spot") -> dict[str, Any]:
        """Get ticker for symbol."""
        result = await self._request(
            "GET",
            "/v5/market/tickers",
            params={"category": category, "symbol": symbol},
        )
        return result

    async def get_orderbook(
        self, symbol: str, depth: int = 20, category: str = "spot"
    ) -> dict[str, Any]:
        """Get order book for symbol."""
        result = await self._request(
            "GET",
            "/v5/market/orderbook",
            params={"category": category, "symbol": symbol, "limit": str(depth)},
        )
        return result

    async def get_candles(
        self,
        symbol: str,
        interval: str = "60",
        limit: int = 100,
        category: str = "spot",
    ) -> dict[str, Any]:
        """Get candlestick data."""
        return await self._request(
            "GET",
            "/v5/market/kline",
            params={
                "category": category,
                "symbol": symbol,
                "interval": interval,
                "limit": str(limit),
            },
        )

    # =========================================================================
    # Private endpoints (authentication required)
    # =========================================================================

    async def get_wallet_balance(self, account_type: str = "UNIFIED") -> dict[str, Any]:
        """Get wallet balance."""
        return await self._request(
            "GET",
            "/v5/account/wallet-balance",
            params={"accountType": account_type},
            signed=True,
        )

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: str | None = None,
        order_link_id: str | None = None,
        category: str = "spot",
    ) -> dict[str, Any]:
        """
        Place order.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: Order side ("Buy"/"Sell")
            order_type: Order type ("Market"/"Limit")
            qty: Order quantity
            price: Price (for limit orders)
            order_link_id: Client order ID
            category: Product category ("spot")

        Returns:
            Order placement result
        """
        body: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side,
            "orderType": order_type,
            "qty": qty,
        }
        if price:
            body["price"] = price
        if order_link_id:
            body["orderLinkId"] = order_link_id

        return await self._request("POST", "/v5/order/create", body=body, signed=True)

    async def cancel_order(
        self, symbol: str, order_id: str, category: str = "spot"
    ) -> dict[str, Any]:
        """Cancel order."""
        body = {"category": category, "symbol": symbol, "orderId": order_id}
        return await self._request("POST", "/v5/order/cancel", body=body, signed=True)

    async def get_order(self, symbol: str, order_id: str, category: str = "spot") -> dict[str, Any]:
        """Get order details (realtime first, fallback to history)."""
        try:
            result = await self._request(
                "GET",
                "/v5/order/realtime",
                params={"category": category, "orderId": order_id},
                signed=True,
            )
            order_list = result.get("list", [])
            if order_list:
                order: dict[str, Any] = order_list[0]
                return order
        except BybitAPIError:
            pass

        # Fallback to history
        result = await self._request(
            "GET",
            "/v5/order/history",
            params={"category": category, "orderId": order_id},
            signed=True,
        )
        order_list = result.get("list", [])
        if order_list:
            order = order_list[0]
            return order
        raise BybitAPIError(code="ORDER_NOT_FOUND", message=f"Order {order_id} not found")

    async def get_open_orders(self, category: str = "spot") -> list[dict[str, Any]]:
        """Get open orders."""
        result = await self._request(
            "GET",
            "/v5/order/realtime",
            params={"category": category},
            signed=True,
        )
        order_list: list[dict[str, Any]] = result.get("list", [])
        return order_list

    async def get_fills(
        self, symbol: str | None = None, category: str = "spot"
    ) -> list[dict[str, Any]]:
        """Get trade fills."""
        params: dict[str, str] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        result = await self._request("GET", "/v5/execution/list", params=params, signed=True)
        fill_list: list[dict[str, Any]] = result.get("list", [])
        return fill_list
