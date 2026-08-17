"""Tests for market domain models."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trading_grid.domain.market.models import (
    Candle,
    Market,
    MarketState,
    OrderBook,
    OrderBookLevel,
    Ticker,
)


class TestMarket:
    """Tests for Market."""

    def test_valid_market(self):
        """Should create a valid market."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
        )
        assert market.market_id == "BTC-USDT"
        assert market.base_currency == "BTC"
        assert market.quote_currency == "USDT"
        assert market.is_active

    def test_empty_market_id_raises(self):
        """Empty market_id should raise ValueError."""
        with pytest.raises(ValueError, match="Market ID cannot be empty"):
            Market(market_id="", base_currency="BTC", quote_currency="USDT")

    def test_zero_tick_size_raises(self):
        """Zero tick_size should raise ValueError."""
        with pytest.raises(ValueError, match="Tick size must be positive"):
            Market(
                market_id="BTC-USDT",
                base_currency="BTC",
                quote_currency="USDT",
                tick_size=Decimal("0"),
            )

    def test_zero_lot_size_raises(self):
        """Zero lot_size should raise ValueError."""
        with pytest.raises(ValueError, match="Lot size must be positive"):
            Market(
                market_id="BTC-USDT",
                base_currency="BTC",
                quote_currency="USDT",
                lot_size=Decimal("0"),
            )

    def test_round_price(self):
        """Price should be rounded to tick size."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            tick_size=Decimal("0.1"),
        )
        # Uses banker's rounding (ROUND_HALF_EVEN)
        assert market.round_price(Decimal("100.14")) == Decimal("100.1")
        assert market.round_price(Decimal("100.16")) == Decimal("100.2")
        assert market.round_price(Decimal("100.20")) == Decimal("100.2")

    def test_round_quantity(self):
        """Quantity should be rounded to lot size."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            lot_size=Decimal("0.001"),
        )
        assert market.round_quantity(Decimal("0.12345")) == Decimal("0.123")

    def test_validate_order_valid(self):
        """Valid order should produce no errors."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            min_order_size=Decimal("0.001"),
        )
        errors = market.validate_order(Decimal("50000"), Decimal("0.01"))
        assert errors == []

    def test_validate_order_below_min_size(self):
        """Order below min size should produce error."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            min_order_size=Decimal("0.001"),
        )
        errors = market.validate_order(Decimal("50000"), Decimal("0.0001"))
        assert len(errors) == 1
        assert "below minimum" in errors[0]

    def test_validate_order_above_max_size(self):
        """Order above max size should produce error."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            min_order_size=Decimal("0.001"),
            max_order_size=Decimal("1"),
        )
        errors = market.validate_order(Decimal("50000"), Decimal("2"))
        assert len(errors) == 1
        assert "above maximum" in errors[0]

    def test_validate_order_price_below_min(self):
        """Price below min should produce error."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            min_order_size=Decimal("0"),
            min_price=Decimal("100"),
        )
        errors = market.validate_order(Decimal("50"), Decimal("1"))
        assert len(errors) == 1
        assert "below minimum" in errors[0]

    def test_validate_order_price_above_max(self):
        """Price above max should produce error."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            min_order_size=Decimal("0"),
            max_price=Decimal("100000"),
        )
        errors = market.validate_order(Decimal("200000"), Decimal("1"))
        assert len(errors) == 1
        assert "above maximum" in errors[0]

    def test_validate_order_inactive_market(self):
        """Inactive market should produce error."""
        market = Market(
            market_id="BTC-USDT",
            base_currency="BTC",
            quote_currency="USDT",
            min_order_size=Decimal("0"),
            is_active=False,
        )
        errors = market.validate_order(Decimal("50000"), Decimal("1"))
        assert len(errors) == 1
        assert "not active" in errors[0]


class TestCandle:
    """Tests for Candle."""

    def test_valid_candle(self):
        """Should create a valid candle."""
        candle = Candle(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        )
        assert candle.open == Decimal("100")
        assert candle.high == Decimal("110")
        assert candle.low == Decimal("90")
        assert candle.close == Decimal("105")

    def test_high_less_than_low_raises(self):
        """High < low should raise ValueError."""
        with pytest.raises(ValueError, match="cannot be less than low"):
            Candle(
                market_id="BTC-USDT",
                timestamp=datetime.now(UTC),
                open=Decimal("100"),
                high=Decimal("90"),
                low=Decimal("110"),
                close=Decimal("105"),
                volume=Decimal("1000"),
            )

    def test_high_less_than_open_raises(self):
        """High < open should raise ValueError."""
        with pytest.raises(ValueError, match="High must be >= open and close"):
            Candle(
                market_id="BTC-USDT",
                timestamp=datetime.now(UTC),
                open=Decimal("100"),
                high=Decimal("95"),
                low=Decimal("90"),
                close=Decimal("95"),
                volume=Decimal("1000"),
            )

    def test_low_greater_than_open_raises(self):
        """Low > open should raise ValueError."""
        with pytest.raises(ValueError, match="Low must be <= open and close"):
            Candle(
                market_id="BTC-USDT",
                timestamp=datetime.now(UTC),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("105"),
                close=Decimal("108"),
                volume=Decimal("1000"),
            )

    def test_negative_volume_raises(self):
        """Negative volume should raise ValueError."""
        with pytest.raises(ValueError, match="Volume cannot be negative"):
            Candle(
                market_id="BTC-USDT",
                timestamp=datetime.now(UTC),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=Decimal("-1"),
            )

    def test_is_bullish(self):
        """Bullish candle should have close > open."""
        candle = Candle(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        )
        assert candle.is_bullish
        assert not candle.is_bearish

    def test_is_bearish(self):
        """Bearish candle should have close < open."""
        candle = Candle(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("95"),
            volume=Decimal("1000"),
        )
        assert candle.is_bearish
        assert not candle.is_bullish

    def test_body_size(self):
        """Body size should be abs(close - open)."""
        candle = Candle(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("95"),
            volume=Decimal("1000"),
        )
        assert candle.body_size == Decimal("5")

    def test_range_size(self):
        """Range size should be high - low."""
        candle = Candle(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
            volume=Decimal("1000"),
        )
        assert candle.range_size == Decimal("20")


class TestOrderBook:
    """Tests for OrderBook."""

    def test_empty_orderbook(self):
        """Empty order book should have None prices."""
        ob = OrderBook(market_id="BTC-USDT", timestamp=datetime.now(UTC))
        assert ob.best_bid is None
        assert ob.best_ask is None
        assert ob.mid_price is None
        assert ob.spread is None
        assert ob.spread_pct is None

    def test_best_bid_ask(self):
        """Best bid/ask should be first levels."""
        ob = OrderBook(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            bids=(
                OrderBookLevel(price=Decimal("100"), quantity=Decimal("1")),
                OrderBookLevel(price=Decimal("99"), quantity=Decimal("2")),
            ),
            asks=(
                OrderBookLevel(price=Decimal("101"), quantity=Decimal("1")),
                OrderBookLevel(price=Decimal("102"), quantity=Decimal("2")),
            ),
        )
        assert ob.best_bid == Decimal("100")
        assert ob.best_ask == Decimal("101")

    def test_mid_price(self):
        """Mid price should be average of best bid/ask."""
        ob = OrderBook(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            bids=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1")),),
            asks=(OrderBookLevel(price=Decimal("102"), quantity=Decimal("1")),),
        )
        assert ob.mid_price == Decimal("101")

    def test_spread(self):
        """Spread should be ask - bid."""
        ob = OrderBook(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            bids=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1")),),
            asks=(OrderBookLevel(price=Decimal("102"), quantity=Decimal("1")),),
        )
        assert ob.spread == Decimal("2")

    def test_spread_pct(self):
        """Spread percentage should be calculated."""
        ob = OrderBook(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            bids=(OrderBookLevel(price=Decimal("100"), quantity=Decimal("1")),),
            asks=(OrderBookLevel(price=Decimal("102"), quantity=Decimal("1")),),
        )
        # spread=2, mid=101, pct = 2/101*100
        assert ob.spread_pct is not None
        assert abs(ob.spread_pct - Decimal("1.98")) < Decimal("0.01")

    def test_bid_depth(self):
        """Bid depth should sum quantities."""
        ob = OrderBook(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            bids=(
                OrderBookLevel(price=Decimal("100"), quantity=Decimal("1")),
                OrderBookLevel(price=Decimal("99"), quantity=Decimal("2")),
                OrderBookLevel(price=Decimal("98"), quantity=Decimal("3")),
            ),
        )
        assert ob.bid_depth(levels=2) == Decimal("3")
        assert ob.bid_depth(levels=10) == Decimal("6")

    def test_ask_depth(self):
        """Ask depth should sum quantities."""
        ob = OrderBook(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            asks=(
                OrderBookLevel(price=Decimal("101"), quantity=Decimal("1")),
                OrderBookLevel(price=Decimal("102"), quantity=Decimal("2")),
            ),
        )
        assert ob.ask_depth(levels=2) == Decimal("3")


class TestTicker:
    """Tests for Ticker."""

    def test_ticker_mid_price_with_bid_ask(self):
        """Mid price should use bid/ask when available."""
        ticker = Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("100"),
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        )
        assert ticker.mid_price == Decimal("100")

    def test_ticker_mid_price_without_bid_ask(self):
        """Mid price should fall back to last price."""
        ticker = Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("100"),
        )
        assert ticker.mid_price == Decimal("100")

    def test_ticker_spread(self):
        """Spread should be calculated."""
        ticker = Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("100"),
            bid_price=Decimal("99"),
            ask_price=Decimal("101"),
        )
        assert ticker.spread == Decimal("2")

    def test_ticker_spread_none_without_bid_ask(self):
        """Spread should be None without bid/ask."""
        ticker = Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("100"),
        )
        assert ticker.spread is None


class TestMarketState:
    """Tests for MarketState."""

    def test_current_price_from_ticker(self):
        """Current price should come from ticker."""
        ticker = Ticker(
            market_id="BTC-USDT",
            timestamp=datetime.now(UTC),
            last_price=Decimal("50000"),
        )
        state = MarketState(market_id="BTC-USDT", ticker=ticker)
        assert state.current_price == Decimal("50000")

    def test_current_price_none_without_ticker(self):
        """Current price should be None without ticker."""
        state = MarketState(market_id="BTC-USDT")
        assert state.current_price is None

    def test_is_data_complete_true(self):
        """Data complete when all flags are True."""
        state = MarketState(
            market_id="BTC-USDT",
            data_quality={"ticker": True, "orderbook": True},
        )
        assert state.is_data_complete

    def test_is_data_complete_false_when_missing(self):
        """Data incomplete when any flag is False."""
        state = MarketState(
            market_id="BTC-USDT",
            data_quality={"ticker": True, "orderbook": False},
        )
        assert not state.is_data_complete

    def test_is_data_complete_false_when_empty(self):
        """Data incomplete when no flags."""
        state = MarketState(market_id="BTC-USDT")
        assert not state.is_data_complete
