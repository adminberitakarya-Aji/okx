"""
Binance REST API client.

This module provides:
- Authenticated REST client for Binance Spot API
- Request signing (HMAC-SHA256, no passphrase)
- Retry logic
- Testnet/Live mode support (separate base URLs)

Security rules:
1. API keys: Read + Trade only, Withdraw DISABLED
2. Testnet and Live use separate credentials
3. Secrets never in logs

Reference: https://developers.binance.com/docs/binance-spot-api-docs
"""

import hashlib
import hmac
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from trading_grid.config.settings import BinanceSettings
from trading_grid.domain.exchange.errors import ExchangeAPIError

logger = structlog.get_logger()


def _should_retry_http_error(exc: BaseException) -> bool:
    """Return True for transient network/server errors (429, 5xx, timeouts). Do NOT retry 4xx errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    return False


class BinanceAPIError(ExchangeAPIError):
    """
    Binance API error.

    Inherits from ExchangeAPIError so the application layer can handle all
    exchange errors uniformly while preserving Binance-specific error detail
    (code + message) for debugging and audit logging.
    """

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        """Initialize with error details."""
        super().__init__(code=code, message=message, data=data or {})

    def __str__(self) -> str:
        """Preserve the Binance error message format."""
        return f"Binance API Error {self.code}: {self.message}"


class BinanceRestClient:
    """
    Binance Spot REST API client.

    Provides authenticated access to Binance REST endpoints.
    """

    def __init__(self, settings: BinanceSettings) -> None:
        """
        Initialize REST client.

        Args:
            settings: Binance API settings
        """
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "BinanceRestClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is created."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._settings.effective_base_url,
                timeout=self._settings.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _sign_query(self, query_string: str) -> str:
        """
        Sign query string using HMAC-SHA256.

        Binance signature: HMAC_SHA256(api_secret, query_string)
        """
        secret = self._settings.api_secret.get_secret_value()
        signature = hmac.new(
            secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def _get_auth_headers(self) -> dict[str, str]:
        """Get API key header for signed requests."""
        return {"X-MBX-APIKEY": self._settings.api_key.get_secret_value()}

    @retry(
        retry=retry_if_exception(_should_retry_http_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        signed: bool = False,
    ) -> Any:
        """
        Make API request.

        Args:
            method: HTTP method
            path: API path
            params: Query parameters
            signed: Whether to sign the request

        Returns:
            API response data

        Raises:
            BinanceAPIError: If API returns error
        """
        client = await self._ensure_client()

        query_params = dict(params or {})
        if signed:
            query_params["timestamp"] = str(int(time.time() * 1000))
            query_params["recvWindow"] = "5000"
            query_string = urlencode(query_params)
            query_params["signature"] = self._sign_query(query_string)

        headers = self._get_auth_headers() if signed else {}

        logger.debug("binance_request", method=method, path=path, signed=signed)

        response = await client.request(
            method=method,
            url=path,
            params=query_params,
            headers=headers,
        )

        # Binance returns JSON error body with "code" and "msg"
        if response.status_code >= 400:
            try:
                data = response.json()
                error_code = str(data.get("code", response.status_code))
                error_msg = data.get("msg", response.text)
            except Exception:
                error_code = str(response.status_code)
                error_msg = response.text
            logger.error("binance_api_error", code=error_code, message=error_msg, path=path)
            raise BinanceAPIError(
                code=error_code, message=error_msg, data={"status": response.status_code}
            )

        return response.json()

    # =========================================================================
    # Public endpoints (no authentication)
    # =========================================================================

    async def get_exchange_info(self) -> dict[str, Any]:
        """Get exchange information including all symbols and filters."""
        data: dict[str, Any] = await self._request("GET", "/api/v3/exchangeInfo")
        return data

    async def get_ticker(self, symbol: str) -> dict[str, Any]:
        """Get 24h ticker for symbol."""
        data: dict[str, Any] = await self._request(
            "GET", "/api/v3/ticker/24hr", params={"symbol": symbol}
        )
        return data

    async def get_orderbook(self, symbol: str, depth: int = 20) -> dict[str, Any]:
        """Get order book for symbol."""
        data: dict[str, Any] = await self._request(
            "GET", "/api/v3/depth", params={"symbol": symbol, "limit": str(depth)}
        )
        return data

    async def get_candles(
        self,
        symbol: str,
        interval: str = "1h",
        limit: int = 100,
        end_time: int | None = None,
    ) -> list[list[Any]]:
        """Get candlestick data."""
        params: dict[str, str] = {"symbol": symbol, "interval": interval, "limit": str(limit)}
        if end_time:
            params["endTime"] = str(end_time)
        data: list[list[Any]] = await self._request("GET", "/api/v3/klines", params=params)
        return data

    # =========================================================================
    # Private endpoints (authentication required)
    # =========================================================================

    async def get_account(self) -> dict[str, Any]:
        """Get account information including balances."""
        data: dict[str, Any] = await self._request("GET", "/api/v3/account", signed=True)
        return data

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: str,
        price: str | None = None,
        new_client_order_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Place order.

        Args:
            symbol: Trading symbol (e.g., "BTCUSDT")
            side: Order side (BUY/SELL)
            order_type: Order type (MARKET/LIMIT)
            quantity: Order quantity
            price: Price (for limit orders)
            new_client_order_id: Client order ID

        Returns:
            Order placement result
        """
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
        }
        if order_type.upper() == "LIMIT":
            params["timeInForce"] = "GTC"
            if price:
                params["price"] = price
        if new_client_order_id:
            params["newClientOrderId"] = new_client_order_id

        data: dict[str, Any] = await self._request(
            "POST", "/api/v3/order", params=params, signed=True
        )
        return data

    async def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Cancel order."""
        data: dict[str, Any] = await self._request(
            "DELETE", "/api/v3/order", params={"symbol": symbol, "orderId": order_id}, signed=True
        )
        return data

    async def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """Get order details."""
        data: dict[str, Any] = await self._request(
            "GET", "/api/v3/order", params={"symbol": symbol, "orderId": order_id}, signed=True
        )
        return data

    async def get_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
        """Get open orders."""
        params: dict[str, str] = {}
        if symbol:
            params["symbol"] = symbol
        data: list[dict[str, Any]] = await self._request(
            "GET", "/api/v3/openOrders", params=params, signed=True
        )
        return data

    async def get_my_trades(self, symbol: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get trade fills for a symbol."""
        data: list[dict[str, Any]] = await self._request(
            "GET", "/api/v3/myTrades", params={"symbol": symbol, "limit": str(limit)}, signed=True
        )
        return data
