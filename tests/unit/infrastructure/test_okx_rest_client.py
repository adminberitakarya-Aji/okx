"""Tests for OKX REST client — full request/response lifecycle.

Mocks httpx.AsyncClient to test:
- Client creation (demo/live headers)
- Request construction (auth headers, query params, body)
- Response parsing for all endpoints
- Error handling (API errors, HTTP errors)
- Context manager
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import tenacity

from trading_grid.config.settings import OKXSettings
from trading_grid.infrastructure.okx.rest_client import OKXAPIError, OKXRestClient


def _make_settings(demo: bool = True) -> OKXSettings:
    return OKXSettings(
        api_key="test-key",
        api_secret="test-secret",
        passphrase="test-pass",
        demo_mode=demo,
        _env_file=None,
    )


def _make_client(demo: bool = True) -> OKXRestClient:
    return OKXRestClient(_make_settings(demo))


def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _okx_response(data: list | dict | None = None, code: str = "0", msg: str = "") -> dict:
    """Build a standard OKX API response envelope."""
    return {"code": code, "msg": msg, "data": data if data is not None else []}


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

    async def test_ensure_client_demo_header(self):
        client = _make_client(demo=True)
        http_client = await client._ensure_client()
        assert http_client.headers.get("x-simulated-trading") == "1"
        await client.close()

    async def test_ensure_client_live_no_demo_header(self):
        client = _make_client(demo=False)
        http_client = await client._ensure_client()
        assert "x-simulated-trading" not in http_client.headers
        await client.close()

    async def test_close_resets_client(self):
        client = _make_client()
        await client._ensure_client()
        assert client._client is not None
        await client.close()
        assert client._client is None

    async def test_close_idempotent(self):
        client = _make_client()
        await client.close()  # No client yet — should not raise
        await client.close()

    async def test_context_manager(self):
        async with _make_client() as client:
            assert client._client is not None
        assert client._client is None


# ---------------------------------------------------------------------------
# _request() internals
# ---------------------------------------------------------------------------


class TestRequestInternals:
    async def test_request_get_with_params(self):
        client = _make_client()
        mock_resp = _mock_response(_okx_response([{"instId": "BTC-USDT"}]))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            result = await client._request(
                "GET",
                "/api/v5/public/instruments",
                params={"instType": "SPOT"},
                authenticated=False,
            )

            mock_http.request.assert_called_once()
            call_kwargs = mock_http.request.call_args[1]
            assert call_kwargs["method"] == "GET"
            assert "instType=SPOT" in call_kwargs["url"]
            assert result["code"] == "0"

    async def test_request_post_with_body(self):
        client = _make_client()
        mock_resp = _mock_response(_okx_response([{"ordId": "123"}]))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            body = {"instId": "BTC-USDT", "side": "buy"}
            await client._request("POST", "/api/v5/trade/order", body=body)

            call_kwargs = mock_http.request.call_args[1]
            assert call_kwargs["method"] == "POST"
            assert json.loads(call_kwargs["content"]) == body
            # Auth headers should be present
            assert "OK-ACCESS-KEY" in call_kwargs["headers"]

    async def test_request_unauthenticated_no_auth_headers(self):
        client = _make_client()
        mock_resp = _mock_response(_okx_response([]))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            await client._request("GET", "/api/v5/public/instruments", authenticated=False)

            call_kwargs = mock_http.request.call_args[1]
            assert "OK-ACCESS-KEY" not in call_kwargs.get("headers", {})

    async def test_request_api_error_raises(self):
        """API errors are retried by tenacity, then wrapped in RetryError."""
        client = _make_client()
        mock_resp = _mock_response(_okx_response(code="51000", msg="Parameter error"))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with pytest.raises(tenacity.RetryError) as exc_info:
                await client._request("GET", "/api/v5/account/balance")

            # The underlying exception is OKXAPIError
            last_exc = exc_info.value.last_attempt.exception()
            assert isinstance(last_exc, OKXAPIError)
            assert last_exc.code == "51000"
            assert "Parameter error" in str(last_exc)

    async def test_request_http_error_propagates(self):
        """HTTP errors are retried by tenacity, then wrapped in RetryError."""
        client = _make_client()
        mock_resp = _mock_response({}, status_code=500)

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with pytest.raises(tenacity.RetryError) as exc_info:
                await client._request("GET", "/api/v5/account/balance")

            last_exc = exc_info.value.last_attempt.exception()
            assert isinstance(last_exc, httpx.HTTPStatusError)

    async def test_request_query_string_in_signed_path(self):
        """Query params must be included in the signed path."""
        client = _make_client()
        mock_resp = _mock_response(_okx_response([]))

        with patch.object(client, "_ensure_client", new_callable=AsyncMock) as mock_ensure:
            mock_http = AsyncMock()
            mock_http.request.return_value = mock_resp
            mock_ensure.return_value = mock_http

            with patch.object(client, "_get_auth_headers", return_value={}) as mock_auth:
                await client._request(
                    "GET", "/api/v5/trade/order", params={"instId": "BTC-USDT", "ordId": "1"}
                )
                # The full_path passed to auth should include query string
                call_args = mock_auth.call_args
                full_path = call_args[0][1]  # second positional arg
                assert "instId=BTC-USDT" in full_path
                assert "ordId=1" in full_path


# ---------------------------------------------------------------------------
# Public endpoints
# ---------------------------------------------------------------------------


class TestPublicEndpoints:
    async def test_get_instruments(self):
        client = _make_client()
        instruments = [{"instId": "BTC-USDT"}, {"instId": "ETH-USDT"}]

        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(instruments)
        ):
            result = await client.get_instruments()
            assert len(result) == 2
            assert result[0]["instId"] == "BTC-USDT"

    async def test_get_instruments_custom_type(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([])
            await client.get_instruments(inst_type="MARGIN")
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["instType"] == "MARGIN"

    async def test_get_ticker(self):
        client = _make_client()
        ticker_data = [{"instId": "BTC-USDT", "last": "50000"}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(ticker_data)
        ):
            result = await client.get_ticker("BTC-USDT")
            assert result["instId"] == "BTC-USDT"
            assert result["last"] == "50000"

    async def test_get_ticker_empty(self):
        client = _make_client()
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response([])
        ):
            result = await client.get_ticker("BTC-USDT")
            assert result == {}

    async def test_get_orderbook(self):
        client = _make_client()
        ob_data = [{"bids": [["50000", "1"]], "asks": [["50001", "2"]]}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(ob_data)
        ):
            result = await client.get_orderbook("BTC-USDT", depth=5)
            assert result["bids"][0][0] == "50000"

    async def test_get_candles(self):
        client = _make_client()
        candle_data = [["1691841600000", "50000", "51000", "49000", "50500", "100"]]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(candle_data)
        ):
            result = await client.get_candles("BTC-USDT", bar="1H", limit=10)
            assert len(result) == 1
            assert result[0][0] == "1691841600000"

    async def test_get_candles_with_after(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([])
            await client.get_candles("BTC-USDT", after="1691841600000")
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["after"] == "1691841600000"


# ---------------------------------------------------------------------------
# Private endpoints
# ---------------------------------------------------------------------------


class TestPrivateEndpoints:
    async def test_get_account_balance(self):
        client = _make_client()
        balance_data = [{"details": [{"ccy": "USDT", "availBal": "1000"}]}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(balance_data)
        ):
            result = await client.get_account_balance()
            assert result["details"][0]["ccy"] == "USDT"

    async def test_get_account_balance_with_ccy(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([{}])
            await client.get_account_balance(ccy="USDT")
            call_kwargs = mock_req.call_args[1]
            assert call_kwargs["params"]["ccy"] == "USDT"

    async def test_get_positions(self):
        client = _make_client()
        pos_data = [{"instId": "BTC-USDT", "pos": "0.5"}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(pos_data)
        ):
            result = await client.get_positions()
            assert len(result) == 1
            assert result[0]["instId"] == "BTC-USDT"

    async def test_place_order_limit(self):
        client = _make_client()
        order_data = [{"ordId": "12345", "sCode": "0"}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(order_data)
        ):
            result = await client.place_order(
                inst_id="BTC-USDT",
                side="buy",
                ord_type="limit",
                sz="0.001",
                px="50000",
                cl_ord_id="my-order-1",
            )
            assert result["ordId"] == "12345"

    async def test_place_order_body_construction(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([{}])
            await client.place_order(
                inst_id="BTC-USDT",
                side="BUY",
                ord_type="LIMIT",
                sz="0.001",
                px="50000",
            )
            call_kwargs = mock_req.call_args[1]
            body = call_kwargs["body"]
            assert body["instId"] == "BTC-USDT"
            assert body["side"] == "buy"  # lowercased
            assert body["ordType"] == "limit"  # lowercased
            assert body["tdMode"] == "cash"
            assert body["px"] == "50000"

    async def test_place_order_market_no_price(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([{}])
            await client.place_order(inst_id="BTC-USDT", side="buy", ord_type="market", sz="0.001")
            body = mock_req.call_args[1]["body"]
            assert "px" not in body

    async def test_cancel_order(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([{"ordId": "123"}])
            await client.cancel_order("BTC-USDT", "123")
            body = mock_req.call_args[1]["body"]
            assert body["instId"] == "BTC-USDT"
            assert body["ordId"] == "123"

    async def test_get_order(self):
        client = _make_client()
        order_data = [{"ordId": "123", "state": "filled"}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(order_data)
        ):
            result = await client.get_order("BTC-USDT", "123")
            assert result["state"] == "filled"

    async def test_get_pending_orders(self):
        client = _make_client()
        orders_data = [{"ordId": "1"}, {"ordId": "2"}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(orders_data)
        ):
            result = await client.get_pending_orders()
            assert len(result) == 2

    async def test_get_fills(self):
        client = _make_client()
        fills_data = [{"tradeId": "t1", "instId": "BTC-USDT"}]
        with patch.object(
            client, "_request", new_callable=AsyncMock, return_value=_okx_response(fills_data)
        ):
            result = await client.get_fills(inst_id="BTC-USDT")
            assert len(result) == 1

    async def test_get_fills_with_inst_id_param(self):
        client = _make_client()
        with patch.object(client, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = _okx_response([])
            await client.get_fills(inst_id="ETH-USDT", limit=50)
            params = mock_req.call_args[1]["params"]
            assert params["instId"] == "ETH-USDT"
            assert params["limit"] == "50"


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------


class TestOKXAPIError:
    def test_error_str_format(self):
        err = OKXAPIError(code="51000", message="Parameter error")
        assert str(err) == "OKX API Error 51000: Parameter error"

    def test_error_data_default_empty(self):
        err = OKXAPIError(code="1", message="test")
        assert err.data == {}

    def test_error_data_preserved(self):
        err = OKXAPIError(code="1", message="test", data={"detail": "x"})
        assert err.data["detail"] == "x"
