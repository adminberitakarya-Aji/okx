"""
Unit tests for Market State Feature Layer (F-MKT).

Tests cover:
1. CandleStructure: range, body, wicks, body-to-range ratio
2. MarketStateFeatureExtractor: realtime prices, candle structures,
   price position, proximity, monthly low context, trend, volatility
3. MarketStateFeatures.to_dict: serialization
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from okx_trading.domain.market.models import Candle
from okx_trading.research.features.market_state import (
    CandleStructure,
    MarketStateFeatureExtractor,
    MarketStateFeatures,
    MonthlyLowRecoveryState,
    MonthlyLowStatus,
    RefinementPriority,
    StructuralAlignment,
    TrendDirection,
    VolatilityRegime,
)


def make_candle(
    timestamp: datetime,
    market_id: str = "BTC-USDT",
    open_price: Decimal = Decimal("50000"),
    high_price: Decimal = Decimal("51000"),
    low_price: Decimal = Decimal("49000"),
    close_price: Decimal = Decimal("50500"),
) -> Candle:
    """Create a test candle."""
    return Candle(
        market_id=market_id,
        timestamp=timestamp,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=Decimal("100"),
        quote_volume=Decimal("5000000"),
    )


class TestCandleStructure:
    """Tests for CandleStructure."""

    def test_range(self) -> None:
        """Range should be high - low."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
        )
        assert cs.range == Decimal("20")

    def test_range_pct(self) -> None:
        """Range % should be (high - low) / low."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("100"),
            close=Decimal("105"),
        )
        assert cs.range_pct == Decimal("0.1")

    def test_range_pct_zero_low(self) -> None:
        """Range % should be 0 when low is 0."""
        cs = CandleStructure(
            open=Decimal("0"),
            high=Decimal("10"),
            low=Decimal("0"),
            close=Decimal("5"),
        )
        assert cs.range_pct == Decimal("0")

    def test_body(self) -> None:
        """Body should be abs(close - open)."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
        )
        assert cs.body == Decimal("5")

    def test_body_bearish(self) -> None:
        """Body should be positive even for bearish candles."""
        cs = CandleStructure(
            open=Decimal("105"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
        )
        assert cs.body == Decimal("5")

    def test_upper_wick(self) -> None:
        """Upper wick should be high - max(open, close)."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
        )
        assert cs.upper_wick == Decimal("5")

    def test_lower_wick(self) -> None:
        """Lower wick should be min(open, close) - low."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
        )
        assert cs.lower_wick == Decimal("10")

    def test_body_to_range(self) -> None:
        """Body-to-range ratio should be body / range."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("110"),
        )
        assert cs.body_to_range == Decimal("0.5")

    def test_body_to_range_zero_range(self) -> None:
        """Body-to-range should be None when range is zero."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("100"),
            low=Decimal("100"),
            close=Decimal("100"),
        )
        assert cs.body_to_range is None

    def test_is_bullish(self) -> None:
        """is_bullish should be True when close > open."""
        cs = CandleStructure(
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("105"),
        )
        assert cs.is_bullish is True

    def test_is_bearish(self) -> None:
        """is_bullish should be False when close < open."""
        cs = CandleStructure(
            open=Decimal("105"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100"),
        )
        assert cs.is_bullish is False


class TestRealtimePrices:
    """Tests for realtime price extraction (F-MKT-004 to F-MKT-007)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_last_price_extracted(self) -> None:
        """Last price should be extracted with availability flag."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("50000"),
        )
        assert features.last_price == Decimal("50000")
        assert features.last_price_available is True

    def test_missing_last_price_flagged(self) -> None:
        """Missing last price should set availability flag to False."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
        )
        assert features.last_price is None
        assert features.last_price_available is False

    def test_mid_price_calculated(self) -> None:
        """Mid price should be (bid + ask) / 2."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            best_bid=Decimal("49990"),
            best_ask=Decimal("50010"),
        )
        assert features.mid_price == Decimal("50000")

    def test_mid_price_none_without_bid_ask(self) -> None:
        """Mid price should be None without both bid and ask."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            best_bid=Decimal("49990"),
        )
        assert features.mid_price is None


class TestCandleStructures:
    """Tests for candle structure extraction (F-MKT-008 to F-MKT-040)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_monthly_structure_extracted(self) -> None:
        """Monthly candle structure should be extracted."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            open_price=Decimal("48000"),
            high_price=Decimal("52000"),
            low_price=Decimal("47000"),
            close_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            monthly_candles=[monthly],
        )
        assert features.monthly is not None
        assert features.monthly.open == Decimal("48000")
        assert features.monthly.high == Decimal("52000")
        assert features.monthly.low == Decimal("47000")
        assert features.monthly.close == Decimal("50000")
        assert features.monthly_available is True

    def test_daily_structure_extracted(self) -> None:
        """Daily candle structure should be extracted."""
        daily = make_candle(
            datetime(2024, 6, 15, tzinfo=UTC),
            open_price=Decimal("49500"),
            high_price=Decimal("50500"),
            low_price=Decimal("49000"),
            close_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=[daily],
        )
        assert features.daily is not None
        assert features.daily_available is True

    def test_no_candles_means_unavailable(self) -> None:
        """No candles should mean structures are unavailable."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
        )
        assert features.monthly is None
        assert features.monthly_available is False
        assert features.weekly is None
        assert features.weekly_available is False
        assert features.daily is None
        assert features.daily_available is False


class TestPricePositionAndProximity:
    """Tests for price position and proximity (F-MKT-041 to F-MKT-049)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_monthly_price_position(self) -> None:
        """Monthly price position should be (price - low) / range."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            open_price=Decimal("48000"),
            high_price=Decimal("52000"),
            low_price=Decimal("48000"),
            close_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("50000"),
            monthly_candles=[monthly],
        )
        # (50000 - 48000) / (52000 - 48000) = 0.5
        assert features.monthly_price_position == pytest.approx(0.5)

    def test_price_position_at_low(self) -> None:
        """Price position at low should be 0."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("48000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("48000"),
            monthly_candles=[monthly],
        )
        assert features.monthly_price_position == pytest.approx(0.0)

    def test_price_position_at_high(self) -> None:
        """Price position at high should be 1."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("48000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("52000"),
            monthly_candles=[monthly],
        )
        assert features.monthly_price_position == pytest.approx(1.0)

    def test_distance_to_monthly_low_pct(self) -> None:
        """Distance to monthly low should be (price - low) / low."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("51000"),
            monthly_candles=[monthly],
        )
        # (51000 - 50000) / 50000 = 0.02
        assert features.distance_to_monthly_low_pct == pytest.approx(0.02)

    def test_distance_to_monthly_high_pct(self) -> None:
        """Distance to monthly high should be (price - high) / high."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("48000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("51000"),
            monthly_candles=[monthly],
        )
        # (51000 - 52000) / 52000 = -0.0192...
        assert features.distance_to_monthly_high_pct == pytest.approx(-0.01923, rel=1e-3)

    def test_no_price_means_no_position(self) -> None:
        """No last price should mean no position features."""
        monthly = make_candle(datetime(2024, 6, 1, tzinfo=UTC))
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            monthly_candles=[monthly],
        )
        assert features.monthly_price_position is None


class TestMonthlyLowContext:
    """Tests for monthly low context (F-MKT-056 to F-MKT-059)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def _extract_with_price(self, price: Decimal, low: Decimal) -> MarketStateFeatures:
        """Helper to extract features with given price and monthly low."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=low + Decimal("5000"),
            low_price=low,
        )
        return self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=price,
            monthly_candles=[monthly],
        )

    def test_status_above(self) -> None:
        """Price well above monthly low should be ABOVE."""
        features = self._extract_with_price(Decimal("55000"), Decimal("50000"))
        assert features.monthly_low_status == MonthlyLowStatus.ABOVE
        assert features.monthly_low_break_flag is False

    def test_status_near(self) -> None:
        """Price 1% above monthly low should be NEAR."""
        features = self._extract_with_price(Decimal("50500"), Decimal("50000"))
        assert features.monthly_low_status == MonthlyLowStatus.NEAR

    def test_status_breaking(self) -> None:
        """Price 0.3% above monthly low should be BREAKING."""
        features = self._extract_with_price(Decimal("50150"), Decimal("50000"))
        assert features.monthly_low_status == MonthlyLowStatus.BREAKING

    def test_status_below(self) -> None:
        """Price below monthly low should be BELOW with break flag."""
        features = self._extract_with_price(Decimal("49000"), Decimal("50000"))
        assert features.monthly_low_status == MonthlyLowStatus.BELOW
        assert features.monthly_low_break_flag is True
        assert features.monthly_low_recovery_state == MonthlyLowRecoveryState.BELOW

    def test_distance_below_monthly_low(self) -> None:
        """Distance below should be negative when below, 0 when above."""
        features_below = self._extract_with_price(Decimal("49000"), Decimal("50000"))
        assert features_below.distance_below_monthly_low_pct == pytest.approx(-0.02)

        features_above = self._extract_with_price(Decimal("51000"), Decimal("50000"))
        assert features_above.distance_below_monthly_low_pct == pytest.approx(0.0)


class TestPreviousMonthlyReference:
    """Tests for previous monthly reference (F-MKT-060 to F-MKT-063)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_previous_monthly_extracted(self) -> None:
        """Previous monthly high/low should be extracted."""
        prev_monthly = make_candle(
            datetime(2024, 5, 1, tzinfo=UTC),
            high_price=Decimal("55000"),
            low_price=Decimal("45000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("50000"),
            previous_monthly_candle=prev_monthly,
        )
        assert features.previous_monthly_high == Decimal("55000")
        assert features.previous_monthly_low == Decimal("45000")

    def test_distance_to_previous_monthly_low(self) -> None:
        """Distance to previous monthly low should be calculated."""
        prev_monthly = make_candle(
            datetime(2024, 5, 1, tzinfo=UTC),
            high_price=Decimal("55000"),
            low_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("51000"),
            previous_monthly_candle=prev_monthly,
        )
        assert features.distance_to_previous_monthly_low_pct == pytest.approx(0.02)


class TestMultiTimeframeRelationships:
    """Tests for multi-timeframe relationships (F-MKT-064 to F-MKT-067)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_monthly_weekly_position_diff(self) -> None:
        """Monthly-weekly position difference should be calculated."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("48000"),
        )
        weekly = make_candle(
            datetime(2024, 6, 10, tzinfo=UTC),
            high_price=Decimal("51000"),
            low_price=Decimal("49000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("50000"),
            monthly_candles=[monthly],
            weekly_candles=[weekly],
        )
        # Monthly position 0.5 vs weekly position 0.5 gives diff 0.0
        assert features.monthly_weekly_position_diff == pytest.approx(0.0)


class TestTrendFeatures:
    """Tests for trend features (F-MKT-068 to F-MKT-074)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_bullish_trend_detected(self) -> None:
        """Bullish trend should be detected when close > prev close."""
        daily_candles = [
            make_candle(
                datetime(2024, 6, 13, tzinfo=UTC),
                close_price=Decimal("49000"),
            ),
            make_candle(
                datetime(2024, 6, 14, tzinfo=UTC),
                close_price=Decimal("50000"),
            ),
        ]
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=daily_candles,
        )
        assert features.daily_trend_direction == TrendDirection.BULLISH

    def test_bearish_trend_detected(self) -> None:
        """Bearish trend should be detected when close < prev close."""
        daily_candles = [
            make_candle(
                datetime(2024, 6, 13, tzinfo=UTC),
                close_price=Decimal("51000"),
            ),
            make_candle(
                datetime(2024, 6, 14, tzinfo=UTC),
                close_price=Decimal("50000"),
            ),
        ]
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=daily_candles,
        )
        assert features.daily_trend_direction == TrendDirection.BEARISH

    def test_trend_strength_normalized(self) -> None:
        """Trend strength should be normalized to 0-1."""
        daily_candles = [
            make_candle(
                datetime(2024, 6, 13, tzinfo=UTC),
                close_price=Decimal("50000"),
            ),
            make_candle(
                datetime(2024, 6, 14, tzinfo=UTC),
                close_price=Decimal("52500"),  # 5% change
                high_price=Decimal("53000"),
            ),
        ]
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=daily_candles,
        )
        assert features.daily_trend_strength == pytest.approx(1.0)

    def test_aligned_bullish_trend(self) -> None:
        """All timeframes bullish should give ALIGNED_BULLISH."""
        monthly_candles = [
            make_candle(
                datetime(2024, 5, 1, tzinfo=UTC),
                close_price=Decimal("48000"),
                low_price=Decimal("47000"),
            ),
            make_candle(datetime(2024, 6, 1, tzinfo=UTC), close_price=Decimal("50000")),
        ]
        weekly_candles = [
            make_candle(
                datetime(2024, 6, 3, tzinfo=UTC),
                close_price=Decimal("49000"),
                low_price=Decimal("48000"),
            ),
            make_candle(datetime(2024, 6, 10, tzinfo=UTC), close_price=Decimal("50000")),
        ]
        daily_candles = [
            make_candle(
                datetime(2024, 6, 13, tzinfo=UTC),
                close_price=Decimal("49500"),
                low_price=Decimal("49000"),
            ),
            make_candle(datetime(2024, 6, 14, tzinfo=UTC), close_price=Decimal("50000")),
        ]
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            monthly_candles=monthly_candles,
            weekly_candles=weekly_candles,
            daily_candles=daily_candles,
        )
        assert features.trend_alignment == "ALIGNED_BULLISH"

    def test_mixed_trend(self) -> None:
        """Mixed timeframes should give MIXED."""
        monthly_candles = [
            make_candle(
                datetime(2024, 5, 1, tzinfo=UTC),
                close_price=Decimal("52000"),
                high_price=Decimal("53000"),
            ),
            make_candle(datetime(2024, 6, 1, tzinfo=UTC), close_price=Decimal("50000")),
        ]
        daily_candles = [
            make_candle(
                datetime(2024, 6, 13, tzinfo=UTC),
                close_price=Decimal("49500"),
                low_price=Decimal("49000"),
            ),
            make_candle(datetime(2024, 6, 14, tzinfo=UTC), close_price=Decimal("50000")),
        ]
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            monthly_candles=monthly_candles,
            daily_candles=daily_candles,
        )
        assert features.trend_alignment == "MIXED"


class TestVolatilityFeatures:
    """Tests for volatility features (F-MKT-075 to F-MKT-081)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_current_volatility_calculated(self) -> None:
        """Current volatility should be daily range percentage."""
        daily = make_candle(
            datetime(2024, 6, 14, tzinfo=UTC),
            high_price=Decimal("51000"),
            low_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=[daily, daily],
        )
        # (51000 - 50000) / 50000 = 0.02
        assert features.current_volatility == pytest.approx(0.02)

    def test_volatility_regime_low(self) -> None:
        """Low volatility should give LOW regime."""
        daily = make_candle(
            datetime(2024, 6, 14, tzinfo=UTC),
            open_price=Decimal("50100"),
            high_price=Decimal("50400"),
            low_price=Decimal("50000"),
            close_price=Decimal("50200"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=[daily, daily],
        )
        assert features.volatility_regime == VolatilityRegime.LOW

    def test_volatility_regime_extreme(self) -> None:
        """Very high volatility should give EXTREME regime."""
        daily = make_candle(
            datetime(2024, 6, 14, tzinfo=UTC),
            high_price=Decimal("55000"),
            low_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=[daily, daily],
        )
        assert features.volatility_regime == VolatilityRegime.EXTREME

    def test_volatility_expansion(self) -> None:
        """Current vol > 1.2x average should flag expansion."""
        # Create history with low volatility
        history = [
            make_candle(
                datetime(2024, 6, i + 1, tzinfo=UTC),
                high_price=Decimal("50500"),
                low_price=Decimal("50000"),
            )
            for i in range(13)
        ]
        # Current candle with high volatility
        current = make_candle(
            datetime(2024, 6, 14, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("50000"),
        )
        history.append(current)

        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            daily_candles=history,
        )
        assert features.volatility_expansion is True


class TestStructuralFeatures:
    """Tests for structural features (F-MKT-082 to F-MKT-087)."""

    def setup_method(self) -> None:
        """Set up extractor."""
        self.extractor = MarketStateFeatureExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_multi_timeframe_low_pressure(self) -> None:
        """Low pressure should be average of low distances."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("51000"),
            monthly_candles=[monthly],
        )
        # Only monthly available: (51000-50000)/50000 = 0.02
        assert features.multi_timeframe_low_pressure == pytest.approx(0.02)

    def test_structural_alignment_aligned(self) -> None:
        """Similar positions should give ALIGNED."""
        monthly = make_candle(
            datetime(2024, 6, 1, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("48000"),
        )
        weekly = make_candle(
            datetime(2024, 6, 10, tzinfo=UTC),
            high_price=Decimal("51000"),
            low_price=Decimal("49000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("50000"),
            monthly_candles=[monthly],
            weekly_candles=[weekly],
        )
        assert features.structural_alignment == StructuralAlignment.ALIGNED

    def test_weekly_refinement_priority_high(self) -> None:
        """Near weekly low should give HIGH refinement priority."""
        weekly = make_candle(
            datetime(2024, 6, 10, tzinfo=UTC),
            high_price=Decimal("52000"),
            low_price=Decimal("50000"),
        )
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            last_price=Decimal("50500"),  # 1% above low
            weekly_candles=[weekly],
        )
        assert features.weekly_refinement_priority == RefinementPriority.HIGH


class TestMarketStateFeaturesToDict:
    """Tests for MarketStateFeatures.to_dict serialization."""

    def test_to_dict_includes_identity(self) -> None:
        """to_dict should include identity fields."""
        features = MarketStateFeatures(market_id="BTC-USDT")
        d = features.to_dict()
        assert d["market_id"] == "BTC-USDT"
        assert d["exchange_id"] == "okx"
        assert "observation_timestamp" in d

    def test_to_dict_includes_prices(self) -> None:
        """to_dict should include price fields."""
        features = MarketStateFeatures(
            market_id="BTC-USDT",
            last_price=Decimal("50000"),
            best_bid=Decimal("49990"),
            best_ask=Decimal("50010"),
        )
        features.last_price_available = True
        d = features.to_dict()
        assert d["last_price"] == 50000.0
        assert d["best_bid"] == 49990.0
        assert d["best_ask"] == 50010.0
        assert d["last_price_available"] is True

    def test_to_dict_none_prices(self) -> None:
        """to_dict should handle None prices."""
        features = MarketStateFeatures(market_id="BTC-USDT")
        d = features.to_dict()
        assert d["last_price"] is None
        assert d["last_price_available"] is False

    def test_to_dict_includes_monthly_structure(self) -> None:
        """to_dict should include monthly structure when available."""
        features = MarketStateFeatures(
            market_id="BTC-USDT",
            monthly=CandleStructure(
                open=Decimal("48000"),
                high=Decimal("52000"),
                low=Decimal("47000"),
                close=Decimal("50000"),
            ),
        )
        features.monthly_available = True
        d = features.to_dict()
        assert d["monthly_open"] == 48000.0
        assert d["monthly_high"] == 52000.0
        assert d["monthly_low"] == 47000.0
        assert d["monthly_close"] == 50000.0
        assert d["monthly_available"] is True

    def test_to_dict_includes_enums_as_strings(self) -> None:
        """to_dict should convert enums to string values."""
        features = MarketStateFeatures(
            market_id="BTC-USDT",
            monthly_low_status=MonthlyLowStatus.NEAR,
            volatility_regime=VolatilityRegime.HIGH,
            weekly_refinement_priority=RefinementPriority.MEDIUM,
        )
        d = features.to_dict()
        assert d["monthly_low_status"] == "NEAR"
        assert d["volatility_regime"] == "HIGH"
        assert d["weekly_refinement_priority"] == "MEDIUM"
