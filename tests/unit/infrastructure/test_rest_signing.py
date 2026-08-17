"""Tests for REST API request signing across all exchanges.

Verifies that HMAC-SHA256 signatures are computed correctly per each
exchange's specification:
- OKX: base64(HMAC_SHA256(secret, timestamp + method + path + body))
- Binance: hex(HMAC_SHA256(secret, query_string))
- Bybit: hex(HMAC_SHA256(secret, timestamp + api_key + recv_window + params_str))
"""

import base64
import hashlib
import hmac

from okx_trading.config.settings import BinanceSettings, BybitSettings, OKXSettings
from okx_trading.infrastructure.binance.rest_client import BinanceRestClient
from okx_trading.infrastructure.bybit.rest_client import RECV_WINDOW, BybitRestClient
from okx_trading.infrastructure.okx.rest_client import OKXRestClient

# ---------------------------------------------------------------------------
# OKX Signing
# ---------------------------------------------------------------------------


class TestOKXSigning:
    """OKX signature: base64(HMAC_SHA256(secret, timestamp + method + path + body))."""

    def _make_client(self) -> OKXRestClient:
        settings = OKXSettings(
            api_key="test-api-key",
            api_secret="test-secret-key",
            passphrase="test-passphrase",
            demo_mode=True,
            _env_file=None,
        )
        return OKXRestClient(settings)

    def test_sign_request_get_no_body(self):
        """GET request with empty body."""
        client = self._make_client()
        timestamp = "2026-08-16T08:00:00.000Z"
        method = "GET"
        path = "/api/v5/account/balance"
        body = ""

        signature = client._sign_request(timestamp, method, path, body)

        # Verify independently
        message = f"{timestamp}{method}{path}{body}"
        expected = base64.b64encode(
            hmac.new(
                b"test-secret-key",
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        assert signature == expected

    def test_sign_request_post_with_body(self):
        """POST request with JSON body."""
        client = self._make_client()
        timestamp = "2026-08-16T08:00:00.000Z"
        method = "POST"
        path = "/api/v5/trade/order"
        body = '{"instId":"BTC-USDT","side":"buy","sz":"0.001"}'

        signature = client._sign_request(timestamp, method, path, body)

        message = f"{timestamp}{method}{path}{body}"
        expected = base64.b64encode(
            hmac.new(
                b"test-secret-key",
                message.encode("utf-8"),
                hashlib.sha256,
            ).digest()
        ).decode("utf-8")
        assert signature == expected

    def test_sign_request_deterministic(self):
        """Same inputs produce same signature."""
        client = self._make_client()
        ts = "2026-08-16T08:00:00.000Z"
        sig1 = client._sign_request(ts, "GET", "/api/v5/account/balance", "")
        sig2 = client._sign_request(ts, "GET", "/api/v5/account/balance", "")
        assert sig1 == sig2

    def test_sign_request_different_timestamp_different_signature(self):
        """Different timestamps produce different signatures."""
        client = self._make_client()
        sig1 = client._sign_request(
            "2026-08-16T08:00:00.000Z", "GET", "/api/v5/account/balance", ""
        )
        sig2 = client._sign_request(
            "2026-08-16T08:00:01.000Z", "GET", "/api/v5/account/balance", ""
        )
        assert sig1 != sig2

    def test_sign_request_different_method_different_signature(self):
        """Different methods produce different signatures."""
        client = self._make_client()
        ts = "2026-08-16T08:00:00.000Z"
        sig1 = client._sign_request(ts, "GET", "/api/v5/trade/order", "")
        sig2 = client._sign_request(ts, "POST", "/api/v5/trade/order", "")
        assert sig1 != sig2

    def test_auth_headers_contain_required_keys(self):
        """Auth headers include all OKX-required fields."""
        client = self._make_client()
        headers = client._get_auth_headers("GET", "/api/v5/account/balance")
        assert "OK-ACCESS-KEY" in headers
        assert "OK-ACCESS-SIGN" in headers
        assert "OK-ACCESS-TIMESTAMP" in headers
        assert "OK-ACCESS-PASSPHRASE" in headers
        assert headers["OK-ACCESS-KEY"] == "test-api-key"
        assert headers["OK-ACCESS-PASSPHRASE"] == "test-passphrase"

    def test_timestamp_format(self):
        """Timestamp is ISO 8601 with milliseconds and Z suffix."""
        client = self._make_client()
        ts = client._get_timestamp()
        assert ts.endswith("Z")
        assert "T" in ts
        # Format: YYYY-MM-DDTHH:MM:SS.mmmZ
        assert len(ts) == 24


# ---------------------------------------------------------------------------
# Binance Signing
# ---------------------------------------------------------------------------


class TestBinanceSigning:
    """Binance signature: hex(HMAC_SHA256(secret, query_string))."""

    def _make_client(self) -> BinanceRestClient:
        settings = BinanceSettings(
            api_key="test-api-key",
            api_secret="test-secret-key",
            testnet_mode=True,
            _env_file=None,
        )
        return BinanceRestClient(settings)

    def test_sign_query_simple(self):
        """Simple query string signing."""
        client = self._make_client()
        query = "symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=0.001"

        signature = client._sign_query(query)

        expected = hmac.new(
            b"test-secret-key",
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_query_with_timestamp(self):
        """Query string with timestamp parameter."""
        client = self._make_client()
        query = "timestamp=1691841600000&symbol=BTCUSDT"

        signature = client._sign_query(query)

        expected = hmac.new(
            b"test-secret-key",
            query.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_query_empty(self):
        """Empty query string."""
        client = self._make_client()
        signature = client._sign_query("")

        expected = hmac.new(
            b"test-secret-key",
            b"",
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_query_deterministic(self):
        """Same query produces same signature."""
        client = self._make_client()
        query = "symbol=BTCUSDT&side=BUY"
        sig1 = client._sign_query(query)
        sig2 = client._sign_query(query)
        assert sig1 == sig2

    def test_sign_query_different_query_different_signature(self):
        """Different queries produce different signatures."""
        client = self._make_client()
        sig1 = client._sign_query("symbol=BTCUSDT")
        sig2 = client._sign_query("symbol=ETHUSDT")
        assert sig1 != sig2

    def test_sign_query_is_hex_not_base64(self):
        """Binance uses hex encoding, not base64."""
        client = self._make_client()
        signature = client._sign_query("symbol=BTCUSDT")
        # Hex is 64 chars for SHA256, base64 would be 44
        assert len(signature) == 64
        # Hex only contains 0-9a-f
        assert all(c in "0123456789abcdef" for c in signature)

    def test_auth_headers_contain_api_key(self):
        """Auth headers include X-MBX-APIKEY."""
        client = self._make_client()
        headers = client._get_auth_headers()
        assert headers["X-MBX-APIKEY"] == "test-api-key"


# ---------------------------------------------------------------------------
# Bybit Signing
# ---------------------------------------------------------------------------


class TestBybitSigning:
    """Bybit v5 signature: hex(HMAC_SHA256(secret, timestamp + api_key + recv_window + params_str))."""

    def _make_client(self) -> BybitRestClient:
        settings = BybitSettings(
            api_key="test-api-key",
            api_secret="test-secret-key",
            testnet_mode=True,
            _env_file=None,
        )
        return BybitRestClient(settings)

    def test_sign_get_params(self):
        """GET request with query params as string."""
        client = self._make_client()
        timestamp = "1691841600000"
        params_str = "symbol=BTCUSDT&limit=10"

        signature = client._sign(timestamp, params_str)

        message = f"{timestamp}test-api-key{RECV_WINDOW}{params_str}"
        expected = hmac.new(
            b"test-secret-key",
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_post_json_body(self):
        """POST request with JSON body as params string."""
        client = self._make_client()
        timestamp = "1691841600000"
        params_str = '{"symbol":"BTCUSDT","side":"Buy","orderType":"Limit","qty":"0.001"}'

        signature = client._sign(timestamp, params_str)

        message = f"{timestamp}test-api-key{RECV_WINDOW}{params_str}"
        expected = hmac.new(
            b"test-secret-key",
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_empty_params(self):
        """Empty params string."""
        client = self._make_client()
        timestamp = "1691841600000"
        params_str = ""

        signature = client._sign(timestamp, params_str)

        message = f"{timestamp}test-api-key{RECV_WINDOW}{params_str}"
        expected = hmac.new(
            b"test-secret-key",
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert signature == expected

    def test_sign_deterministic(self):
        """Same inputs produce same signature."""
        client = self._make_client()
        ts = "1691841600000"
        params = "symbol=BTCUSDT"
        sig1 = client._sign(ts, params)
        sig2 = client._sign(ts, params)
        assert sig1 == sig2

    def test_sign_different_timestamp_different_signature(self):
        """Different timestamps produce different signatures."""
        client = self._make_client()
        params = "symbol=BTCUSDT"
        sig1 = client._sign("1691841600000", params)
        sig2 = client._sign("1691841600001", params)
        assert sig1 != sig2

    def test_sign_includes_api_key_in_message(self):
        """Bybit signature includes API key in the signed message (unlike OKX/Binance)."""
        client = self._make_client()
        ts = "1691841600000"
        params = "symbol=BTCUSDT"

        # The signature should match a message that includes the API key
        message_with_key = f"{ts}test-api-key{RECV_WINDOW}{params}"
        expected = hmac.new(
            b"test-secret-key",
            message_with_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert client._sign(ts, params) == expected

        # And should NOT match a message without the API key
        message_without_key = f"{ts}{RECV_WINDOW}{params}"
        wrong = hmac.new(
            b"test-secret-key",
            message_without_key.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        assert client._sign(ts, params) != wrong

    def test_auth_headers_contain_required_keys(self):
        """Auth headers include all Bybit-required fields."""
        client = self._make_client()
        headers = client._get_auth_headers("1691841600000", "symbol=BTCUSDT")
        assert headers["X-BAPI-API-KEY"] == "test-api-key"
        assert headers["X-BAPI-TIMESTAMP"] == "1691841600000"
        assert headers["X-BAPI-RECV-WINDOW"] == RECV_WINDOW
        assert "X-BAPI-SIGN" in headers
        assert headers["Content-Type"] == "application/json"

    def test_recv_window_constant(self):
        """RECV_WINDOW is 5000 as per Bybit spec."""
        assert RECV_WINDOW == "5000"


# ---------------------------------------------------------------------------
# Cross-exchange signing differences
# ---------------------------------------------------------------------------


class TestCrossExchangeSigningDifferences:
    """Verify that each exchange uses its correct signing scheme."""

    def test_okx_uses_base64_binance_bybit_use_hex(self):
        """OKX uses base64 encoding; Binance and Bybit use hex."""
        okx_settings = OKXSettings(
            api_key="k", api_secret="s", passphrase="p", demo_mode=True, _env_file=None
        )
        binance_settings = BinanceSettings(
            api_key="k", api_secret="s", testnet_mode=True, _env_file=None
        )
        bybit_settings = BybitSettings(
            api_key="k", api_secret="s", testnet_mode=True, _env_file=None
        )

        okx_client = OKXRestClient(okx_settings)
        binance_client = BinanceRestClient(binance_settings)
        bybit_client = BybitRestClient(bybit_settings)

        okx_sig = okx_client._sign_request("ts", "GET", "/path", "")
        binance_sig = binance_client._sign_query("query")
        bybit_sig = bybit_client._sign("ts", "params")

        # OKX base64: ends with = or contains +/ chars, length ~44
        assert okx_sig.endswith("=") or "+" in okx_sig or "/" in okx_sig or len(okx_sig) == 44

        # Binance/Bybit hex: 64 chars, only hex digits
        assert len(binance_sig) == 64
        assert len(bybit_sig) == 64
        assert all(c in "0123456789abcdef" for c in binance_sig)
        assert all(c in "0123456789abcdef" for c in bybit_sig)

    def test_same_secret_different_schemes_different_signatures(self):
        """Even with the same secret, different signing schemes produce different results."""
        secret = "shared-secret"

        okx_settings = OKXSettings(
            api_key="k", api_secret=secret, passphrase="p", demo_mode=True, _env_file=None
        )
        binance_settings = BinanceSettings(
            api_key="k", api_secret=secret, testnet_mode=True, _env_file=None
        )

        okx_client = OKXRestClient(okx_settings)
        binance_client = BinanceRestClient(binance_settings)

        # Sign the same logical message
        okx_sig = okx_client._sign_request("msg", "", "", "")
        binance_sig = binance_client._sign_query("msg")

        # base64 vs hex → different strings
        assert okx_sig != binance_sig
