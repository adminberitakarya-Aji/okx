"""Tests for Bybit REST client — full request/response lifecycle.

Mocks httpx.AsyncClient to test:
- Client creation (testnet/live base URL)
- Request construction (GET params vs POST body signing)
- Response parsing (retCode envelope, result extraction)
- Error handling (retCode != 0)
- get_order fallback logic (realtime → history)
- Context manager
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import tenacity

from trading_grid.config.settings import BybitSettings
from trading_grid.infrastructure.bybit.rest_client import (
    RECV_WINDOW,
    BybitAPIError,
    BybitRestClient,
)


def _make_settings(testnet: bool = True) -> BybitSettings:
    return BybitSettings(
        api_key="test-key",
        api_secret="test-secret",
        testnet_mode=testnet,
        _env_file=None,
    )


def _make_client(testnet: bool = True) -> BybitRestClient:
    return BybitRestClient(_make_settings(testnet))


def _mock_response(data: dict) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = data
    return resp


def _bybit_response(result: dict | None = None, ret_code: int = 0, ret_msg: str = "OK") -> dict:
    """Build a standard Bybit v5 response envelope."""
    return {"retCode": ret_code, "retMsg": ret_msg, "result": result if result is not None else {}}


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
    async def test_request_get_unsigned(self):
        client = _make_client()
        mock_resp = _mock_response(_bybit_response({"list": []}))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            result = await client._request(
                "GET", "/v5/market/tickers", params={"symbol": "BTCUSDT"}
            )

            call_kwargs = mock_http.request.call_args[1]
            assert call_kwargs["params"] == {"symbol": "BTCUSDT"}
            assert call_kwargs["headers"] == {}
            assert result == {"list": []}

    async def test_request_get_signed_headers(self):
        client = _make_client()
        mock_resp = _mock_response(_bybit_response({"list": []}))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            await client._request(
                "GET", "/v5/order/realtime", params={"category": "spot"}, signed=True
            )

            call_kwargs = mock_http.request.call_args[1]
            headers = call_kwargs["headers"]
            assert headers["X-BAPI-API-KEY"] == "test-key"
            assert headers["X-BAPI-RECV-WINDOW"] == RECV_WINDOW
            assert "X-BAPI-SIGN" in headers
            assert "X-BAPI-TIMESTAMP" in headers

    async def test_request_post_body_signed(self):
        client = _make_client()
        mock_resp = _mock_response(_bybit_response({"orderId": "123"}))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            body = {"symbol": "BTCUSDT", "side": "Buy"}
            result = await client._request("POST", "/v5/order/create", body=body, signed=True)

            call_kwargs = mock_http.request.call_args[1]
            assert json.loads(call_kwargs["content"]) == body
            assert call_kwargs["headers"]["X-BAPI-API-KEY"] == "test-key"
            assert result == {"orderId": "123"}

    async def test_request_returns_result_payload(self):
        """Bybit _request returns the 'result' field, not the full envelope."""
        client = _make_client()
        result_payload = {"list": [{"symbol": "BTCUSDT"}]}
        mock_resp = _mock_response(_bybit_response(result_payload))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            result = await client._request("GET", "/v5/market/tickers")
            assert result == result_payload

    async def test_request_api_error_nonzero_retcode(self):
        """retCode != 0 raises BybitAPIError (wrapped in RetryError by tenacity)."""
        client = _make_client()
        mock_resp = _mock_response(_bybit_response(ret_code=10001, ret_msg="Invalid symbol"))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with pytest.raises(tenacity.RetryError) as exc_info:
                await client._request("GET", "/v5/market/tickers")

            last_exc = exc_info.value.last_attempt.exception()
            assert isinstance(last_exc, BybitAPIError)
            assert last_exc.code == "10001"
            assert "Invalid symbol" in last_exc.message

    async def test_request_missing_retcode_treated_as_error(self):
        """Missing retCode defaults to -1 → error."""
        client = _make_client()
        mock_resp = _mock_response({"retMsg": "malformed"})

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with pytest.raises(tenacity.RetryError) as exc_info:
                await client._request("GET", "/v5/market/tickers")

            last_exc = exc_info.value.last_attempt.exception()
            assert isinstance(last_exc, BybitAPIError)
            assert last_exc.code == "-1"


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


class TestPublicEndpoints:
    async def test_get_instruments(self):
        client = _make_client()
        result_payload = {"list": [{"symbol": "BTCUSDT"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_instruments()
            assert result["list"][0]["symbol"] == "BTCUSDT"

    async def test_get_ticker(self):
        client = _make_client()
        result_payload = {"list": [{"symbol": "BTCUSDT", "lastPrice": "50000"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_ticker("BTCUSDT")
            assert result["list"][0]["lastPrice"] == "50000"

    async def test_get_orderbook(self):
        client = _make_client()
        result_payload = {"b": [["50000", "1"]], "a": [["50001", "2"]]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_orderbook("BTCUSDT", depth=5)
            assert result["b"][0][0] == "50000"

    async def test_get_candles(self):
        client = _make_client()
        result_payload = {"list": [["1691841600000", "50000", "51000", "49000", "50500", "100"]]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_candles("BTCUSDT", interval="60")
            assert len(result["list"]) == 1

    async def test_get_candles_params(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.get_candles("BTCUSDT", interval="60", limit=50)
            params = mock_req.call_args[1]["params"]
            assert params["symbol"] == "BTCUSDT"
            assert params["interval"] == "60"
            assert params["limit"] == "50"
            assert params["category"] == "spot"


# ---------------------------------------------------------------------------
# Private endpoints
# ---------------------------------------------------------------------------


class TestPrivateEndpoints:
    async def test_get_wallet_balance(self):
        client = _make_client()
        result_payload = {"list": [{"totalEquity": "1000"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_wallet_balance()
            assert result["list"][0]["totalEquity"] == "1000"

    async def test_get_wallet_balance_is_signed(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.get_wallet_balance()
            assert mock_req.call_args[1]["signed"] is True

    async def test_place_order_limit(self):
        client = _make_client()
        result_payload = {"orderId": "123", "orderLinkId": "my-order"}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Limit",
                qty="0.001",
                price="50000",
                order_link_id="my-order",
            )
            assert result["orderId"] == "123"

    async def test_place_order_body_construction(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.place_order(
                symbol="BTCUSDT",
                side="Buy",
                order_type="Limit",
                qty="0.001",
                price="50000",
            )
            body = mock_req.call_args[1]["body"]
            assert body["category"] == "spot"
            assert body["symbol"] == "BTCUSDT"
            assert body["side"] == "Buy"
            assert body["orderType"] == "Limit"
            assert body["price"] == "50000"

    async def test_place_order_market_no_price(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.place_order(symbol="BTCUSDT", side="Buy", order_type="Market", qty="0.001")
            body = mock_req.call_args[1]["body"]
            assert "price" not in body

    async def test_cancel_order(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"orderId": "123"}
            await client.cancel_order("BTCUSDT", "123")
            body = mock_req.call_args[1]["body"]
            assert body["symbol"] == "BTCUSDT"
            assert body["orderId"] == "123"
            assert body["category"] == "spot"

    async def test_get_order_from_realtime(self):
        client = _make_client()
        realtime_result = {"list": [{"orderId": "123", "orderStatus": "New"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=realtime_result):
            result = await client.get_order("BTCUSDT", "123")
            assert result["orderId"] == "123"

    async def test_get_order_fallback_to_history(self):
        """Empty realtime list → fallback to history endpoint."""
        client = _make_client()
        realtime_result = {"list": []}
        history_result = {"list": [{"orderId": "123", "orderStatus": "Filled"}]}

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [realtime_result, history_result]
            result = await client.get_order("BTCUSDT", "123")
            assert result["orderStatus"] == "Filled"
            assert mock_req.call_count == 2
            # Second call should be history endpoint
            assert mock_req.call_args_list[1][0][1] == "/v5/order/history"

    async def test_get_order_fallback_on_api_error(self):
        """BybitAPIError from realtime → fallback to history."""
        client = _make_client()
        history_result = {"list": [{"orderId": "123", "orderStatus": "Filled"}]}

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [
                BybitAPIError(code="10001", message="Not found"),
                history_result,
            ]
            result = await client.get_order("BTCUSDT", "123")
            assert result["orderStatus"] == "Filled"

    async def test_get_order_not_found_raises(self):
        """Both realtime and history empty → ORDER_NOT_FOUND."""
        client = _make_client()

        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.side_effect = [{"list": []}, {"list": []}]
            with pytest.raises(BybitAPIError) as exc_info:
                await client.get_order("BTCUSDT", "999")
            assert exc_info.value.code == "ORDER_NOT_FOUND"

    async def test_get_open_orders(self):
        client = _make_client()
        result_payload = {"list": [{"orderId": "1"}, {"orderId": "2"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_open_orders()
            assert len(result) == 2

    async def test_get_open_orders_empty(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock, return_value={}):
            result = await client.get_open_orders()
            assert result == []

    async def test_get_fills(self):
        client = _make_client()
        result_payload = {"list": [{"execId": "e1", "symbol": "BTCUSDT"}]}
        with patch.object(client, "_request", new_callable=AsyncMock, return_value=result_payload):
            result = await client.get_fills(symbol="BTCUSDT")
            assert len(result) == 1

    async def test_get_fills_params(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {}
            await client.get_fills(symbol="ETHUSDT")
            params = mock_req.call_args[1]["params"]
            assert params["symbol"] == "ETHUSDT"
            assert params["category"] == "spot"


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------


class TestBybitAPIError:
    def test_error_str_format(self):
        err = BybitAPIError(code="10001", message="Invalid symbol")
        assert str(err) == "Bybit API Error 10001: Invalid symbol"

    def test_error_data_default_empty(self):
        err = BybitAPIError(code="1", message="test")
        assert err.data == {}

    def test_error_data_preserved(self):
        err = BybitAPIError(code="1", message="test", data={"retCode": 1})
        assert err.data["retCode"] == 1

    def test_recv_window_constant(self):
        assert RECV_WINDOW == "5000"
