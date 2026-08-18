"""
OKX REST API client.

This module provides:
- Authenticated REST client for OKX API v5
- Request signing (HMAC-SHA256)
- Rate limiting and retry logic
- Demo/Live mode support

Security rules:
1. API keys: Read + Trade only, Withdraw DISABLED
2. DEMO and LIVE use separate credentials
3. Secrets never in logs
"""

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from trading_grid.config.settings import OKXSettings
from trading_grid.domain.exchange.errors import ExchangeAPIError

logger = structlog.get_logger()


def _should_retry_http_error(exc: BaseException) -> bool:
    """Return True for transient network/server errors (429, 5xx, timeouts). Do NOT retry 4xx errors."""
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code == 429 or exc.response.status_code >= 500
    if isinstance(exc, (httpx.TransportError, httpx.TimeoutException)):
        return True
    return False


class OKXRestClient:
    """
    OKX REST API v5 client.

    Provides authenticated access to OKX REST endpoints.
    """

    def __init__(self, settings: OKXSettings) -> None:
        """
        Initialize REST client.

        Args:
            settings: OKX API settings
        """
        self._settings = settings
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "OKXRestClient":
        """Async context manager entry."""
        await self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is created."""
        if self._client is None or self._client.is_closed:
            headers = {"Content-Type": "application/json"}
            if self._settings.demo_mode:
                headers["x-simulated-trading"] = "1"
            self._client = httpx.AsyncClient(
                base_url=self._settings.base_url,
                headers=headers,
                timeout=self._settings.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_timestamp(self) -> str:
        """Get ISO format timestamp for OKX API."""
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"

    def _sign_request(self, timestamp: str, method: str, path: str, body: str = "") -> str:
        """
        Sign request with HMAC-SHA256.

        Format: timestamp + method + path + body
        """
        message = f"{timestamp}{method.upper()}{path}{body}"
        secret = self._settings.api_secret.get_secret_value().encode("utf-8")
        signature = hmac.new(secret, message.encode("utf-8"), hashlib.sha256).digest()
        return base64.b64encode(signature).decode("utf-8")

    def _get_auth_headers(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Get authentication headers for request."""
        timestamp = self._get_timestamp()
        signature = self._sign_request(timestamp, method, path, body)

        return {
            "OK-ACCESS-KEY": self._settings.api_key.get_secret_value(),
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self._settings.passphrase.get_secret_value(),
        }

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
        body: dict[str, Any] | None = None,
        authenticated: bool = True,
    ) -> dict[str, Any]:
        """
        Make API request.

        Args:
            method: HTTP method
            path: API path
            params: Query parameters
            body: Request body
            authenticated: Whether to include auth headers

        Returns:
            API response data

        Raises:
            OKXAPIError: If API returns error
        """
        client = await self._ensure_client()

        # Build query string for signing
        query_string = ""
        if params:
            query_string = "?" + "&".join(f"{k}={v}" for k, v in params.items())
        full_path = path + query_string

        # Prepare body
        body_str = json.dumps(body) if body else ""

        # Build headers
        headers = {}
        if authenticated:
            headers = self._get_auth_headers(method.upper(), full_path, body_str)

        logger.debug(
            "okx_request",
            method=method,
            path=path,
            authenticated=authenticated,
        )

        response = await client.request(
            method=method,
            url=full_path,
            content=body_str if body else None,
            headers=headers,
        )

        response.raise_for_status()
        data: dict[str, Any] = response.json()

        # Check OKX API response code
        if data.get("code") != "0":
            error_msg = data.get("msg", "Unknown error")
            error_code = data.get("code", "UNKNOWN")
            logger.error("okx_api_error", code=error_code, message=error_msg, path=path)
            raise OKXAPIError(code=error_code, message=error_msg, data=data)

        return data

    # =========================================================================
    # Public endpoints (no authentication)
    # =========================================================================

    async def get_instruments(self, inst_type: str = "SPOT") -> list[dict[str, Any]]:
        """Get available instruments."""
        data = await self._request(
            "GET",
            "/api/v5/public/instruments",
            params={"instType": inst_type},
            authenticated=False,
        )
        result: list[dict[str, Any]] = data.get("data", [])
        return result

    async def get_ticker(self, inst_id: str) -> dict[str, Any]:
        """Get ticker for instrument."""
        data = await self._request(
            "GET",
            "/api/v5/market/ticker",
            params={"instId": inst_id},
            authenticated=False,
        )
        items = data.get("data", [])
        result: dict[str, Any] = items[0] if items else {}
        return result

    async def get_orderbook(self, inst_id: str, depth: int = 20) -> dict[str, Any]:
        """Get order book for instrument."""
        data = await self._request(
            "GET",
            "/api/v5/market/books",
            params={"instId": inst_id, "sz": str(depth)},
            authenticated=False,
        )
        items = data.get("data", [])
        result: dict[str, Any] = items[0] if items else {}
        return result

    async def get_candles(
        self,
        inst_id: str,
        bar: str = "1H",
        limit: int = 100,
        after: str | None = None,
    ) -> list[list[str]]:
        """Get candlestick data."""
        params: dict[str, str] = {"instId": inst_id, "bar": bar, "limit": str(limit)}
        if after:
            params["after"] = after
        data = await self._request(
            "GET",
            "/api/v5/market/candles",
            params=params,
            authenticated=False,
        )
        result: list[list[str]] = data.get("data", [])
        return result

    # =========================================================================
    # Private endpoints (authentication required)
    # =========================================================================

    async def get_account_balance(self, ccy: str | None = None) -> dict[str, Any]:
        """Get account balance."""
        params = {"ccy": ccy} if ccy else None
        data = await self._request("GET", "/api/v5/account/balance", params=params)
        items = data.get("data", [])
        result: dict[str, Any] = items[0] if items else {}
        return result

    async def get_positions(self, inst_type: str = "SPOT") -> list[dict[str, Any]]:
        """Get positions."""
        data = await self._request(
            "GET",
            "/api/v5/account/positions",
            params={"instType": inst_type},
        )
        result: list[dict[str, Any]] = data.get("data", [])
        return result

    async def place_order(
        self,
        inst_id: str,
        side: str,
        ord_type: str,
        sz: str,
        px: str | None = None,
        td_mode: str = "cash",
        cl_ord_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Place order.

        Args:
            inst_id: Instrument ID
            side: Order side (buy/sell)
            ord_type: Order type (market/limit)
            sz: Order size
            px: Price (for limit orders)
            td_mode: Trade mode (cash for spot)
            cl_ord_id: Client order ID

        Returns:
            Order placement result
        """
        body: dict[str, Any] = {
            "instId": inst_id,
            "tdMode": td_mode,
            "side": side.lower(),
            "ordType": ord_type.lower(),
            "sz": sz,
        }
        if px:
            body["px"] = px
        if cl_ord_id:
            body["clOrdId"] = cl_ord_id

        data = await self._request("POST", "/api/v5/trade/order", body=body)
        items = data.get("data", [])
        result: dict[str, Any] = items[0] if items else {}
        return result

    async def cancel_order(self, inst_id: str, ord_id: str) -> dict[str, Any]:
        """Cancel order."""
        body = {"instId": inst_id, "ordId": ord_id}
        data = await self._request("POST", "/api/v5/trade/cancel-order", body=body)
        items = data.get("data", [])
        result: dict[str, Any] = items[0] if items else {}
        return result

    async def get_order(self, inst_id: str, ord_id: str) -> dict[str, Any]:
        """Get order details."""
        data = await self._request(
            "GET",
            "/api/v5/trade/order",
            params={"instId": inst_id, "ordId": ord_id},
        )
        items = data.get("data", [])
        result: dict[str, Any] = items[0] if items else {}
        return result

    async def get_pending_orders(self, inst_type: str = "SPOT") -> list[dict[str, Any]]:
        """Get pending orders."""
        data = await self._request(
            "GET",
            "/api/v5/trade/orders-pending",
            params={"instType": inst_type},
        )
        result: list[dict[str, Any]] = data.get("data", [])
        return result

    async def get_fills(
        self,
        inst_type: str = "SPOT",
        inst_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Get trade fills."""
        params: dict[str, str] = {"instType": inst_type, "limit": str(limit)}
        if inst_id:
            params["instId"] = inst_id
        data = await self._request("GET", "/api/v5/trade/fills", params=params)
        result: list[dict[str, Any]] = data.get("data", [])
        return result


class OKXAPIError(ExchangeAPIError):
    """
    OKX API error.

    Inherits from ExchangeAPIError so the application layer can handle all
    exchange errors uniformly while preserving OKX-specific error detail
    (code + message) for debugging and audit logging.
    """

    def __init__(self, code: str, message: str, data: dict[str, Any] | None = None) -> None:
        """Initialize with error details."""
        super().__init__(code=code, message=message, data=data or {})

    def __str__(self) -> str:
        """Preserve the historical OKX error message format."""
        return f"OKX API Error {self.code}: {self.message}"
