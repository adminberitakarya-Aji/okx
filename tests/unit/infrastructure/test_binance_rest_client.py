"""Tests for Binance REST client — full request/response lifecycle.

Mocks httpx.AsyncClient to test:
- Client creation (testnet/live base URL)
- Request construction (signed vs unsigned, timestamp, signature)
- Response parsing for all endpoints
- Error handling (API errors with JSON body, HTTP errors)
- Context manager
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import tenacity

from trading_grid.config.settings import BinanceSettings
from trading_grid.infrastructure.binance.rest_client import BinanceAPIError, BinanceRestClient


def _make_settings(testnet: bool = True) -> BinanceSettings:
    return BinanceSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_client(testnet: bool = True) -> BinanceRestClient:
    return BinanceRestClient(_make_settings(testnet))


def _mock_response(data, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.text = str(data)
    return resp


# ---------------------------------------------------------------------------
# Client lifecycle
# ---------------------------------------------------------------------------


class TestClientLifecycle:
    async def test_ensure_client_creates_once(self):
        client = _make_client()
        c1 = await client._ensure_client()
        c2 = await client._ensure_client()
        assert c1 is c2
        await client.close()

    async def test_ensure_client_testnet_base_url(self):
        client = _make_client(testnet=True)
        http_client = await client._ensure_client()
        assert "testnet" in str(http_client.base_url)
        await client.close()

    async def test_ensure_client_live_base_url(self):
        client = _make_client(testnet=False)
        http_client = await client._ensure_client()
        assert "testnet" not in str(http_client.base_url)
        await client.close()

    async def test_close_resets_client(self):
        client = _make_client()
        await client._ensure_client()
        assert client._client is not None
        await client.close()
        assert client._client is None

    async def test_close_idempotent(self):
        client = _make_client()
        await client.close()
        await client.close()

    async def test_context_manager(self):
        async with _make_client() as client:
            assert client._client is not None
        assert client._client is None


# ---------------------------------------------------------------------------
# _request() internals
# ---------------------------------------------------------------------------


class TestRequestInternals:
    async def test_request_unsigned_no_signature(self):
        client = _make_client()
        mock_resp = _mock_response({"symbol": "BTCUSDT"})

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            await client._request("GET", "/api/v3/ticker/24hr", params={"symbol": "BTCUSDT"})

            call_kwargs = mock_http.request.call_args[1]
            params = call_kwargs["params"]
            assert "signature" not in params
            assert "timestamp" not in params
            assert call_kwargs["headers"] == {}

    async def test_request_signed_adds_timestamp_and_signature(self):
        client = _make_client()
        mock_resp = _mock_response({"balances": []})

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            await client._request("GET", "/api/v3/account", signed=True)

            call_kwargs = mock_http.request.call_args[1]
            params = call_kwargs["params"]
            assert "timestamp" in params
            assert "recvWindow" in params
            assert "signature" in params
            assert params["recvWindow"] == "5000"
            # Auth header present
            assert call_kwargs["headers"]["X-MBX-APIKEY"] == "test-key"

    async def test_request_api_error_with_json_body(self):
        """Binance returns error JSON with code/msg on 4xx."""
        client = _make_client()
        error_body = {"code": -1121, "msg": "Invalid symbol."}
        mock_resp = _mock_response(error_body, status_code=400)

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with pytest.raises(tenacity.RetryError) as exc_info:
                await client._request("GET", "/api/v3/ticker/24hr", params={"symbol": "INVALID"})

            last_exc = exc_info.value.last_attempt.exception()
            assert isinstance(last_exc, BinanceAPIError)
            assert last_exc.code == "-1121"
            assert "Invalid symbol" in last_exc.message

    async def test_request_api_error_non_json_body(self):
        """Non-JSON error body falls back to status code + text."""
        client = _make_client()
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 502
        mock_resp.json.side_effect = Exception("not json")
        mock_resp.text = "Bad Gateway"

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with pytest.raises(tenacity.RetryError) as exc_info:
                await client._request("GET", "/api/v3/exchangeInfo")

            last_exc = exc_info.value.last_attempt.exception()
            assert isinstance(last_exc, BinanceAPIError)
            assert last_exc.code == "502"

    async def test_request_returns_json(self):
        client = _make_client()
        mock_resp = _mock_response({"serverTime": 1234567890})

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            result = await client._request("GET", "/api/v3/time")
            assert result["serverTime"] == 1234567890


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


class TestPublicEndpoints:
    async def test_get_exchange_info(self):
        client = _make_client()
        info = {"symbols": [{"symbol": "BTCUSDT"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=info):
            result = await client.get_exchange_info()
            assert result["symbols"][0]["symbol"] == "BTCUSDT"

    async def test_get_ticker(self):
        client = _make_client()
        ticker = {"symbol": "BTCUSDT", "lastPrice": "50000.00"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=ticker):
            result = await client.get_ticker("BTCUSDT")
            assert result["lastPrice"] == "50000.00"

    async def test_get_orderbook(self):
        client = _make_client()
        ob = {"bids": [["50000", "1"]], "asks": [["50001", "2"]]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=ob):
            result = await client.get_orderbook("BTCUSDT", depth=5)
            assert result["bids"][0][0] == "50000"

    async def test_get_candles(self):
        client = _make_client()
        candles = [[1691841600000, "50000", "51000", "49000", "50500", "100"]]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=candles):
            result = await client.get_candles("BTCUSDT", interval="1h", limit=10)
            assert len(result) == 1

    async def test_get_candles_with_end_time(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            await client.get_candles("BTCUSDT", end_time=1691841600000)
            params = mock_req.call_args[1]["params"]
            assert params["endTime"] == "1691841600000"


# ---------------------------------------------------------------------------
# Private endpoints
# ---------------------------------------------------------------------------


class TestPrivateEndpoints:
    async def test_get_account(self):
        client = _make_client()
        account = {"balances": [{"asset": "USDT", "free": "1000"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=account):
            result = await client.get_account()
            assert result["balances"][0]["asset"] == "USDT"

    async def test_get_account_is_signed(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.get_account()
            assert mock_req.call_args[1]["signed"] is True

    async def test_place_order_limit(self):
        client = _make_client()
        order = {"orderId": 123, "status": "NEW"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=order):
            result = await client.place_order(
                symbol="BTCUSDT",
                side="buy",
                order_type="limit",
                quantity="0.001",
                price="50000",
            )
            assert result["orderId"] == 123

    async def test_place_order_limit_params(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.place_order(
                symbol="BTCUSDT",
                side="buy",
                order_type="LIMIT",
                quantity="0.001",
                price="50000",
                new_client_order_id="my-order",
            )
            params = mock_req.call_args[1]["params"]
            assert params["side"] == "BUY"
            assert params["type"] == "LIMIT"
            assert params["timeInForce"] == "GTC"
            assert params["price"] == "50000"
            assert params["newClientOrderId"] == "my-order"

    async def test_place_order_market_no_time_in_force(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.place_order(
                symbol="BTCUSDT", side="BUY", order_type="MARKET", quantity="0.001"
            )
            params = mock_req.call_args[1]["params"]
            assert "timeInForce" not in params
            assert "price" not in params

    async def test_cancel_order(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"orderId": "123"}
            await client.cancel_order("BTCUSDT", "123")
            # method and path are positional args
            call_args = mock_req.call_args[0]
            call_kwargs = mock_req.call_args[1]
            assert call_args[0] == "DELETE"
            assert call_args[1] == "/api/v3/order"
            assert call_kwargs["params"]["symbol"] == "BTCUSDT"
            assert call_kwargs["params"]["orderId"] == "123"

    async def test_get_order(self):
        client = _make_client()
        order = {"orderId": "123", "status": "FILLED"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=order):
            result = await client.get_order("BTCUSDT", "123")
            assert result["status"] == "FILLED"

    async def test_get_open_orders(self):
        client = _make_client()
        orders = [{"orderId": "1"}, {"orderId": "2"}]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=orders):
            result = await client.get_open_orders()
            assert len(result) == 2

    async def test_get_open_orders_with_symbol(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = []
            await client.get_open_orders(symbol="BTCUSDT")
            params = mock_req.call_args[1]["params"]
            assert params["symbol"] == "BTCUSDT"

    async def test_get_my_trades(self):
        client = _make_client()
        trades = [{"id": 1, "symbol": "BTCUSDT"}]
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=trades):
            result = await client.get_my_trades("BTCUSDT", limit=50)
            assert len(result) == 1


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------


class TestBinanceAPIError:
    def test_error_str_format(self):
        err = BinanceAPIError(code="-1121", message="Invalid symbol.")
        assert str(err) == "Binance API Error -1121: Invalid symbol."

    def test_error_data_default_empty(self):
        err = BinanceAPIError(code="1", message="test")
        assert err.data == {}

    def test_error_data_preserved(self):
        err = BinanceAPIError(code="1", message="test", data={"status": 400})
        assert err.data["status"] == 400
