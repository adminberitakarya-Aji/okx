"""One-off fix: OKX ticker test matches Ticker domain model per [D-M8]."""
from pathlib import Path

p = Path("tests/integration/okx/test_okx_adapter_integration.py")
text = p.read_text(encoding="utf-8")

old = '''    async def test_get_ticker_returns_raw_dict(self):
        """get_ticker returns the raw ticker dict from OKX."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {
            "instId": "BTC-USDT",
            "last": "50000.00",
            "bidPx": "49999.00",
            "askPx": "50001.00",
            "vol24h": "1234.56",
        }

        ticker = await adapter.get_ticker("BTC-USDT")

        assert ticker["instId"] == "BTC-USDT"
        assert ticker["last"] == "50000.00"
        adapter._rest.get_ticker.assert_called_once_with("BTC-USDT")'''

new = '''    async def test_get_ticker_returns_domain_model(self):
        """get_ticker returns a domain Ticker model (not a raw dict) per [D-M8]."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {
            "instId": "BTC-USDT",
            "last": "50000.00",
            "bidPx": "49999.00",
            "askPx": "50001.00",
            "vol24h": "1234.56",
        }

        ticker = await adapter.get_ticker("BTC-USDT")

        # [D-M8] Adapter returns a normalized Ticker domain model
        assert ticker.market_id == "BTC-USDT"
        assert ticker.last_price == Decimal("50000.00")
        assert ticker.bid_price == Decimal("49999.00")
        assert ticker.ask_price == Decimal("50001.00")
        adapter._rest.get_ticker.assert_called_once_with("BTC-USDT")'''

if old in text:
    text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
    print("REPLACED")
else:
    print("NOT_FOUND")