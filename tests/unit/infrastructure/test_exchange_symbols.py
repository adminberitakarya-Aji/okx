"""
Tests for market symbol normalization helpers.

Verifies:
1. Domain format "BTC-USDT" converts to "BTCUSDT"
2. Concatenated format "BTCUSDT" converts back to "BTC-USDT"
3. Round-trip conversion is lossless
4. Invalid inputs raise ValueError
"""

import pytest

from okx_trading.infrastructure.exchange.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)


class TestToConcatenatedSymbol:
    """Tests for to_concatenated_symbol."""

    def test_btc_usdt(self) -> None:
        """BTC-USDT → BTCUSDT."""
        assert to_concatenated_symbol("BTC-USDT") == "BTCUSDT"

    def test_eth_usdt(self) -> None:
        """ETH-USDT → ETHUSDT."""
        assert to_concatenated_symbol("ETH-USDT") == "ETHUSDT"

    def test_lowercase_normalized(self) -> None:
        """Lowercase input is uppercased."""
        assert to_concatenated_symbol("btc-usdt") == "BTCUSDT"

    def test_invalid_no_dash(self) -> None:
        """Symbol without dash raises ValueError."""
        with pytest.raises(ValueError, match="expected 'BASE-QUOTE'"):
            to_concatenated_symbol("BTCUSDT")

    def test_invalid_empty_base(self) -> None:
        """Empty base raises ValueError."""
        with pytest.raises(ValueError, match="expected 'BASE-QUOTE'"):
            to_concatenated_symbol("-USDT")

    def test_invalid_empty_quote(self) -> None:
        """Empty quote raises ValueError."""
        with pytest.raises(ValueError, match="expected 'BASE-QUOTE'"):
            to_concatenated_symbol("BTC-")

    def test_invalid_multiple_dashes(self) -> None:
        """Multiple dashes raise ValueError."""
        with pytest.raises(ValueError, match="expected 'BASE-QUOTE'"):
            to_concatenated_symbol("BTC-USDT-EXTRA")


class TestToNormalizedMarketId:
    """Tests for to_normalized_market_id."""

    def test_btcusdt(self) -> None:
        """BTCUSDT → BTC-USDT."""
        assert to_normalized_market_id("BTCUSDT") == "BTC-USDT"

    def test_ethbtc(self) -> None:
        """ETHBTC → ETH-BTC."""
        assert to_normalized_market_id("ETHBTC") == "ETH-BTC"

    def test_ethusdc(self) -> None:
        """ETHUSDC → ETH-USDC."""
        assert to_normalized_market_id("ETHUSDC") == "ETH-USDC"

    def test_lowercase_input(self) -> None:
        """Lowercase input is handled."""
        assert to_normalized_market_id("btcusdt") == "BTC-USDT"

    def test_unknown_quote_raises(self) -> None:
        """Symbol with unknown quote raises ValueError."""
        with pytest.raises(ValueError, match="Cannot split symbol"):
            to_normalized_market_id("XYZABC")

    def test_quote_only_raises(self) -> None:
        """Symbol that is only a quote currency raises ValueError."""
        with pytest.raises(ValueError, match="Cannot split symbol"):
            to_normalized_market_id("USDT")


class TestRoundTrip:
    """Tests for round-trip conversion."""

    @pytest.mark.parametrize(
        "market_id",
        ["BTC-USDT", "ETH-USDT", "SOL-USDT", "ETH-BTC", "BNB-USDT"],
    )
    def test_round_trip(self, market_id: str) -> None:
        """normalize(to_concatenated(x)) == x."""
        concatenated = to_concatenated_symbol(market_id)
        normalized = to_normalized_market_id(concatenated)
        assert normalized == market_id
