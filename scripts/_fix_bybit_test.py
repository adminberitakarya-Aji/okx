"""One-off fix: Bybit empty-list ticker test matches zeroed Ticker domain model."""
from pathlib import Path

p = Path("tests/integration/bybit/test_bybit_adapter_integration.py")
text = p.read_text(encoding="utf-8")

old = '''    async def test_get_ticker_empty_list(self):
        """get_ticker returns empty dict when no data."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {"list": []}

        ticker = await adapter.get_ticker("BTC-USDT")
        assert ticker == {}'''

new = '''    async def test_get_ticker_empty_list(self):
        """get_ticker returns an empty Ticker model when no data."""
        adapter = _make_adapter()
        adapter._rest.get_ticker.return_value = {"list": []}

        ticker = await adapter.get_ticker("BTC-USDT")
        # [D-M8] Adapter always returns a Ticker domain model (zeroed on empty)
        assert ticker.market_id == "BTC-USDT"
        assert ticker.last_price == Decimal("0")'''

if old in text:
    text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")
    print("REPLACED")
else:
    print("NOT_FOUND")