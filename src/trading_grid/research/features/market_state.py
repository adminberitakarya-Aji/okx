"""
Market State Feature Layer (F-MKT).

Implements F-MKT-001 through F-MKT-087 from AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md.

This layer answers:
> What is happening in the market now, and where is realtime price relative
> to multi-timeframe market structure?

Key principles:
- Causal integrity: only use data available at observation time
- Missing data ≠ zero (use availability flags)
- Normalized representations for cross-market ML
- Candle state policy: CLOSED vs IN_PROGRESS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from trading_grid.domain.market.models import Candle
    from trading_grid.domain.shared.types import MarketId

logger = structlog.get_logger()


class TrendDirection(StrEnum):
    """Trend direction states."""

    BULLISH = "BULLISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"


class VolatilityRegime(StrEnum):
    """Volatility regime states."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


class MonthlyLowStatus(StrEnum):
    """Monthly low proximity status."""

    ABOVE = "ABOVE"
    NEAR = "NEAR"
    BREAKING = "BREAKING"
    BELOW = "BELOW"
    RECOVERING = "RECOVERING"


class MonthlyLowRecoveryState(StrEnum):
    """Monthly low recovery state."""

    NO_BREAK = "NO_BREAK"
    BREAKING = "BREAKING"
    BELOW = "BELOW"
    RECOVERING_ABOVE = "RECOVERING_ABOVE"


class StructuralAlignment(StrEnum):
    """Structural alignment state."""

    ALIGNED = "ALIGNED"
    MIXED = "MIXED"
    TRANSITION = "TRANSITION"


class RefinementPriority(StrEnum):
    """Refinement priority level."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class CandleStructure:
    """
    OHLC structure for a timeframe.

    Represents the candle state at observation time.
    Distinguishes CLOSED vs IN_PROGRESS candles.
    """

    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    is_closed: bool = True
    timestamp: datetime | None = None

    @property
    def range(self) -> Decimal:
        """Candle range (high - low)."""
        return self.high - self.low

    @property
    def range_pct(self) -> Decimal:
        """Candle range as percentage of low."""
        if self.low == 0:
            return Decimal("0")
        return (self.high - self.low) / self.low

    @property
    def body(self) -> Decimal:
        """Candle body size (abs(close - open))."""
        return abs(self.close - self.open)

    @property
    def body_pct(self) -> Decimal:
        """Candle body as percentage of open."""
        if self.open == 0:
            return Decimal("0")
        return abs(self.close - self.open) / self.open

    @property
    def upper_wick(self) -> Decimal:
        """Upper wick size."""
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> Decimal:
        """Lower wick size."""
        return min(self.open, self.close) - self.low

    @property
    def body_to_range(self) -> Decimal | None:
        """Body-to-range ratio. None if range is zero."""
        if self.range == 0:
            return None
        return self.body / self.range

    @property
    def is_bullish(self) -> bool:
        """True if close > open."""
        return self.close > self.open


@dataclass
class MarketStateFeatures:
    """
    Complete Market State feature set (F-MKT-001 through F-MKT-087).

    All price-based features use Decimal for precision.
    Normalized features (percentages, positions) use float for ML compatibility.
    """

    # F-MKT-001 to F-MKT-003: Identity
    market_id: str
    exchange_id: str = "okx"
    observation_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # F-MKT-004 to F-MKT-007: Realtime Price
    last_price: Decimal | None = None
    best_bid: Decimal | None = None
    best_ask: Decimal | None = None
    mid_price: Decimal | None = None

    # Availability flags (missing data ≠ zero)
    last_price_available: bool = False
    best_bid_available: bool = False
    best_ask_available: bool = False

    # F-MKT-008 to F-MKT-018: Monthly Structure
    monthly: CandleStructure | None = None
    monthly_available: bool = False

    # F-MKT-019 to F-MKT-029: Weekly Structure
    weekly: CandleStructure | None = None
    weekly_available: bool = False

    # F-MKT-030 to F-MKT-040: Daily Structure
    daily: CandleStructure | None = None
    daily_available: bool = False

    # F-MKT-041 to F-MKT-043: Price Position (normalized 0-1, can exceed)
    monthly_price_position: float | None = None
    weekly_price_position: float | None = None
    daily_price_position: float | None = None

    # F-MKT-044 to F-MKT-049: Proximity (percentage distance)
    distance_to_monthly_low_pct: float | None = None
    distance_to_monthly_high_pct: float | None = None
    distance_to_weekly_low_pct: float | None = None
    distance_to_weekly_high_pct: float | None = None
    distance_to_daily_low_pct: float | None = None
    distance_to_daily_high_pct: float | None = None

    # F-MKT-050 to F-MKT-055: Volatility-Adjusted Proximity
    monthly_low_distance_vol_adjusted: float | None = None
    monthly_high_distance_vol_adjusted: float | None = None
    weekly_low_distance_vol_adjusted: float | None = None
    weekly_high_distance_vol_adjusted: float | None = None
    daily_low_distance_vol_adjusted: float | None = None
    daily_high_distance_vol_adjusted: float | None = None

    # F-MKT-056 to F-MKT-059: Monthly Low Context
    monthly_low_status: MonthlyLowStatus | None = None
    distance_below_monthly_low_pct: float | None = None
    monthly_low_break_flag: bool = False
    monthly_low_recovery_state: MonthlyLowRecoveryState | None = None

    # F-MKT-060 to F-MKT-063: Previous Closed Monthly Reference
    previous_monthly_high: Decimal | None = None
    previous_monthly_low: Decimal | None = None
    distance_to_previous_monthly_low_pct: float | None = None
    distance_to_previous_monthly_high_pct: float | None = None

    # F-MKT-064 to F-MKT-067: Multi-Timeframe Relationships
    monthly_weekly_position_diff: float | None = None
    monthly_weekly_low_proximity: float | None = None
    weekly_daily_position_diff: float | None = None
    weekly_daily_low_proximity: float | None = None

    # F-MKT-068 to F-MKT-074: Trend
    monthly_trend_direction: TrendDirection | None = None
    weekly_trend_direction: TrendDirection | None = None
    daily_trend_direction: TrendDirection | None = None
    monthly_trend_strength: float | None = None
    weekly_trend_strength: float | None = None
    daily_trend_strength: float | None = None
    trend_alignment: str | None = None

    # F-MKT-075 to F-MKT-081: Volatility
    current_volatility: float | None = None
    monthly_volatility: float | None = None
    weekly_volatility: float | None = None
    daily_volatility: float | None = None
    volatility_regime: VolatilityRegime | None = None
    volatility_expansion: bool = False
    volatility_compression: bool = False

    # F-MKT-082 to F-MKT-084: Structural Pressure
    multi_timeframe_low_pressure: float | None = None
    multi_timeframe_high_pressure: float | None = None
    structural_alignment: StructuralAlignment | None = None

    # F-MKT-085 to F-MKT-087: Refinement Priority
    monthly_context_priority: str | None = None
    weekly_refinement_priority: RefinementPriority | None = None
    daily_refinement_priority: RefinementPriority | None = None

    def to_dict(self) -> dict[str, object]:
        """Convert to dictionary for ML pipeline."""
        result: dict[str, object] = {
            "market_id": self.market_id,
            "exchange_id": self.exchange_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
        }

        # Realtime prices
        result["last_price"] = float(self.last_price) if self.last_price else None
        result["best_bid"] = float(self.best_bid) if self.best_bid else None
        result["best_ask"] = float(self.best_ask) if self.best_ask else None
        result["mid_price"] = float(self.mid_price) if self.mid_price else None
        result["last_price_available"] = self.last_price_available
        result["best_bid_available"] = self.best_bid_available
        result["best_ask_available"] = self.best_ask_available

        # Monthly structure
        if self.monthly:
            result["monthly_open"] = float(self.monthly.open)
            result["monthly_high"] = float(self.monthly.high)
            result["monthly_low"] = float(self.monthly.low)
            result["monthly_close"] = float(self.monthly.close)
            result["monthly_range"] = float(self.monthly.range)
            result["monthly_range_pct"] = float(self.monthly.range_pct)
            result["monthly_body"] = float(self.monthly.body)
            result["monthly_body_pct"] = float(self.monthly.body_pct)
            result["monthly_upper_wick"] = float(self.monthly.upper_wick)
            result["monthly_lower_wick"] = float(self.monthly.lower_wick)
            result["monthly_body_to_range"] = (
                float(self.monthly.body_to_range)
                if self.monthly.body_to_range is not None
                else None
            )
            result["monthly_is_closed"] = self.monthly.is_closed
        result["monthly_available"] = self.monthly_available

        # Weekly structure
        if self.weekly:
            result["weekly_open"] = float(self.weekly.open)
            result["weekly_high"] = float(self.weekly.high)
            result["weekly_low"] = float(self.weekly.low)
            result["weekly_close"] = float(self.weekly.close)
            result["weekly_range"] = float(self.weekly.range)
            result["weekly_range_pct"] = float(self.weekly.range_pct)
            result["weekly_body"] = float(self.weekly.body)
            result["weekly_body_pct"] = float(self.weekly.body_pct)
            result["weekly_upper_wick"] = float(self.weekly.upper_wick)
            result["weekly_lower_wick"] = float(self.weekly.lower_wick)
            result["weekly_body_to_range"] = (
                float(self.weekly.body_to_range) if self.weekly.body_to_range is not None else None
            )
            result["weekly_is_closed"] = self.weekly.is_closed
        result["weekly_available"] = self.weekly_available

        # Daily structure
        if self.daily:
            result["daily_open"] = float(self.daily.open)
            result["daily_high"] = float(self.daily.high)
            result["daily_low"] = float(self.daily.low)
            result["daily_close"] = float(self.daily.close)
            result["daily_range"] = float(self.daily.range)
            result["daily_range_pct"] = float(self.daily.range_pct)
            result["daily_body"] = float(self.daily.body)
            result["daily_body_pct"] = float(self.daily.body_pct)
            result["daily_upper_wick"] = float(self.daily.upper_wick)
            result["daily_lower_wick"] = float(self.daily.lower_wick)
            result["daily_body_to_range"] = (
                float(self.daily.body_to_range) if self.daily.body_to_range is not None else None
            )
            result["daily_is_closed"] = self.daily.is_closed
        result["daily_available"] = self.daily_available

        # Price position
        result["monthly_price_position"] = self.monthly_price_position
        result["weekly_price_position"] = self.weekly_price_position
        result["daily_price_position"] = self.daily_price_position

        # Proximity
        result["distance_to_monthly_low_pct"] = self.distance_to_monthly_low_pct
        result["distance_to_monthly_high_pct"] = self.distance_to_monthly_high_pct
        result["distance_to_weekly_low_pct"] = self.distance_to_weekly_low_pct
        result["distance_to_weekly_high_pct"] = self.distance_to_weekly_high_pct
        result["distance_to_daily_low_pct"] = self.distance_to_daily_low_pct
        result["distance_to_daily_high_pct"] = self.distance_to_daily_high_pct

        # Volatility-adjusted proximity
        result["monthly_low_distance_vol_adjusted"] = self.monthly_low_distance_vol_adjusted
        result["monthly_high_distance_vol_adjusted"] = self.monthly_high_distance_vol_adjusted
        result["weekly_low_distance_vol_adjusted"] = self.weekly_low_distance_vol_adjusted
        result["weekly_high_distance_vol_adjusted"] = self.weekly_high_distance_vol_adjusted
        result["daily_low_distance_vol_adjusted"] = self.daily_low_distance_vol_adjusted
        result["daily_high_distance_vol_adjusted"] = self.daily_high_distance_vol_adjusted

        # Monthly low context
        result["monthly_low_status"] = (
            self.monthly_low_status.value if self.monthly_low_status else None
        )
        result["distance_below_monthly_low_pct"] = self.distance_below_monthly_low_pct
        result["monthly_low_break_flag"] = self.monthly_low_break_flag
        result["monthly_low_recovery_state"] = (
            self.monthly_low_recovery_state.value if self.monthly_low_recovery_state else None
        )

        # Previous monthly reference
        result["previous_monthly_high"] = (
            float(self.previous_monthly_high) if self.previous_monthly_high else None
        )
        result["previous_monthly_low"] = (
            float(self.previous_monthly_low) if self.previous_monthly_low else None
        )
        result["distance_to_previous_monthly_low_pct"] = self.distance_to_previous_monthly_low_pct
        result["distance_to_previous_monthly_high_pct"] = self.distance_to_previous_monthly_high_pct

        # Multi-timeframe relationships
        result["monthly_weekly_position_diff"] = self.monthly_weekly_position_diff
        result["monthly_weekly_low_proximity"] = self.monthly_weekly_low_proximity
        result["weekly_daily_position_diff"] = self.weekly_daily_position_diff
        result["weekly_daily_low_proximity"] = self.weekly_daily_low_proximity

        # Trend
        result["monthly_trend_direction"] = (
            self.monthly_trend_direction.value if self.monthly_trend_direction else None
        )
        result["weekly_trend_direction"] = (
            self.weekly_trend_direction.value if self.weekly_trend_direction else None
        )
        result["daily_trend_direction"] = (
            self.daily_trend_direction.value if self.daily_trend_direction else None
        )
        result["monthly_trend_strength"] = self.monthly_trend_strength
        result["weekly_trend_strength"] = self.weekly_trend_strength
        result["daily_trend_strength"] = self.daily_trend_strength
        result["trend_alignment"] = self.trend_alignment

        # Volatility
        result["current_volatility"] = self.current_volatility
        result["monthly_volatility"] = self.monthly_volatility
        result["weekly_volatility"] = self.weekly_volatility
        result["daily_volatility"] = self.daily_volatility
        result["volatility_regime"] = (
            self.volatility_regime.value if self.volatility_regime else None
        )
        result["volatility_expansion"] = self.volatility_expansion
        result["volatility_compression"] = self.volatility_compression

        # Structural pressure
        result["multi_timeframe_low_pressure"] = self.multi_timeframe_low_pressure
        result["multi_timeframe_high_pressure"] = self.multi_timeframe_high_pressure
        result["structural_alignment"] = (
            self.structural_alignment.value if self.structural_alignment else None
        )

        # Refinement priority
        result["monthly_context_priority"] = self.monthly_context_priority
        result["weekly_refinement_priority"] = (
            self.weekly_refinement_priority.value if self.weekly_refinement_priority else None
        )
        result["daily_refinement_priority"] = (
            self.daily_refinement_priority.value if self.daily_refinement_priority else None
        )

        return result


class MarketStateFeatureExtractor:
    """
    Extracts Market State features from candle data.

    This extractor enforces causal integrity:
    - Only uses data available at observation time
    - Distinguishes CLOSED vs IN_PROGRESS candles
    - Missing data is explicitly flagged, never silently zero

    Usage:
        extractor = MarketStateFeatureExtractor()
        features = extractor.extract(
            market_id="BTC-USDT",
            observation_time=datetime.now(UTC),
            last_price=Decimal("50000"),
            monthly_candles=[...],
            weekly_candles=[...],
            daily_candles=[...],
        )
    """

    # Thresholds for monthly low status (as percentage)
    NEAR_THRESHOLD = 0.02  # 2% above monthly low
    BREAKING_THRESHOLD = 0.005  # 0.5% above monthly low

    # Volatility regime thresholds (as percentage of daily range)
    VOL_LOW_THRESHOLD = 0.01
    VOL_NORMAL_THRESHOLD = 0.03
    VOL_HIGH_THRESHOLD = 0.05

    def extract(
        self,
        market_id: MarketId,
        observation_time: datetime,
        last_price: Decimal | None = None,
        best_bid: Decimal | None = None,
        best_ask: Decimal | None = None,
        monthly_candles: list[Candle] | None = None,
        weekly_candles: list[Candle] | None = None,
        daily_candles: list[Candle] | None = None,
        previous_monthly_candle: Candle | None = None,
    ) -> MarketStateFeatures:
        """
        Extract Market State features.

        Args:
            market_id: Market identifier
            observation_time: Observation timestamp (causal cutoff)
            last_price: Current last price
            best_bid: Current best bid
            best_ask: Current best ask
            monthly_candles: Monthly candles up to observation time
            weekly_candles: Weekly candles up to observation time
            daily_candles: Daily candles up to observation time
            previous_monthly_candle: Previous closed monthly candle

        Returns:
            MarketStateFeatures with all computed features
        """
        features = MarketStateFeatures(
            market_id=market_id,
            observation_timestamp=observation_time,
        )

        # F-MKT-004 to F-MKT-007: Realtime Price
        self._extract_realtime_prices(features, last_price, best_bid, best_ask)

        # F-MKT-008 to F-MKT-040: Candle Structures
        self._extract_candle_structures(
            features, monthly_candles, weekly_candles, daily_candles, observation_time
        )

        # F-MKT-041 to F-MKT-049: Price Position and Proximity
        self._extract_position_and_proximity(features)

        # F-MKT-056 to F-MKT-059: Monthly Low Context
        self._extract_monthly_low_context(features)

        # F-MKT-060 to F-MKT-063: Previous Monthly Reference
        self._extract_previous_monthly_reference(features, previous_monthly_candle)

        # F-MKT-064 to F-MKT-067: Multi-Timeframe Relationships
        self._extract_multi_timeframe_relationships(features)

        # F-MKT-068 to F-MKT-074: Trend
        self._extract_trend_features(features, monthly_candles, weekly_candles, daily_candles)

        # F-MKT-075 to F-MKT-081: Volatility
        self._extract_volatility_features(features, daily_candles)

        # F-MKT-082 to F-MKT-087: Structural Pressure and Refinement
        self._extract_structural_features(features)

        return features

    def _extract_realtime_prices(
        self,
        features: MarketStateFeatures,
        last_price: Decimal | None,
        best_bid: Decimal | None,
        best_ask: Decimal | None,
    ) -> None:
        """Extract realtime price features (F-MKT-004 to F-MKT-007)."""
        features.last_price = last_price
        features.last_price_available = last_price is not None

        features.best_bid = best_bid
        features.best_bid_available = best_bid is not None

        features.best_ask = best_ask
        features.best_ask_available = best_ask is not None

        # F-MKT-007: Mid Price
        if best_bid is not None and best_ask is not None:
            features.mid_price = (best_bid + best_ask) / 2

    def _extract_candle_structures(
        self,
        features: MarketStateFeatures,
        monthly_candles: list[Candle] | None,
        weekly_candles: list[Candle] | None,
        daily_candles: list[Candle] | None,
        observation_time: datetime,
    ) -> None:
        """Extract candle structure features (F-MKT-008 to F-MKT-040)."""
        # Monthly structure
        if monthly_candles:
            current = monthly_candles[-1]
            is_closed = current.timestamp < observation_time.replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            features.monthly = CandleStructure(
                open=current.open,
                high=current.high,
                low=current.low,
                close=current.close,
                is_closed=is_closed,
                timestamp=current.timestamp,
            )
            features.monthly_available = True

        # Weekly structure
        if weekly_candles:
            current = weekly_candles[-1]
            # Weekly candle closes at end of week (Sunday 23:59 UTC)
            is_closed = self._is_weekly_candle_closed(current.timestamp, observation_time)
            features.weekly = CandleStructure(
                open=current.open,
                high=current.high,
                low=current.low,
                close=current.close,
                is_closed=is_closed,
                timestamp=current.timestamp,
            )
            features.weekly_available = True

        # Daily structure
        if daily_candles:
            current = daily_candles[-1]
            # [TD-6] Daily candle closes at end of day (23:59 UTC).
            # Add 1-hour buffer: candle is only considered closed after 01:00 UTC
            # to account for exchange delays in finalizing the previous day's candle.
            is_closed = self._is_daily_candle_closed(current.timestamp, observation_time)
            features.daily = CandleStructure(
                open=current.open,
                high=current.high,
                low=current.low,
                close=current.close,
                is_closed=is_closed,
                timestamp=current.timestamp,
            )
            features.daily_available = True

    def _is_weekly_candle_closed(self, candle_time: datetime, observation_time: datetime) -> bool:
        """Check if weekly candle is closed at observation time.

        Uses full ISO (year, week) tuple comparison to correctly handle
        year-boundary transitions (e.g. week 52 of year N vs week 1 of year N+1).
        """
        # ISO week: Monday=0, Sunday=6
        # Weekly candle closes at end of Sunday
        candle_iso = candle_time.isocalendar()
        obs_iso = observation_time.isocalendar()
        return (candle_iso.year, candle_iso.week) < (obs_iso.year, obs_iso.week)

    def _is_daily_candle_closed(self, candle_time: datetime, observation_time: datetime) -> bool:
        """Check if daily candle is closed at observation time.

        [TD-6] Adds a 1-hour buffer after midnight UTC to account for exchange
        delays in finalizing the previous day's candle. A candle is only
        considered closed after 01:00 UTC on the following day.

        Args:
            candle_time: Timestamp of the candle (start of day)
            observation_time: Current observation time

        Returns:
            True if the candle is definitively closed, False otherwise
        """
        from datetime import timedelta

        # If candle is from a previous day AND we're past 01:00 UTC, it's closed
        if candle_time.date() < observation_time.date():
            # Check if we're past the 1-hour buffer (01:00 UTC)
            midnight = observation_time.replace(hour=0, minute=0, second=0, microsecond=0)
            buffer_end = midnight + timedelta(hours=1)
            return observation_time >= buffer_end

        # Same day or future — not closed
        return False

    def _extract_position_and_proximity(self, features: MarketStateFeatures) -> None:
        """Extract price position and proximity features (F-MKT-041 to F-MKT-049)."""
        price = features.last_price
        if price is None:
            return

        # F-MKT-041: Monthly Price Position
        if features.monthly and features.monthly.range > 0:
            position = (price - features.monthly.low) / features.monthly.range
            features.monthly_price_position = float(position)

        # F-MKT-042: Weekly Price Position
        if features.weekly and features.weekly.range > 0:
            position = (price - features.weekly.low) / features.weekly.range
            features.weekly_price_position = float(position)

        # F-MKT-043: Daily Price Position
        if features.daily and features.daily.range > 0:
            position = (price - features.daily.low) / features.daily.range
            features.daily_price_position = float(position)

        # F-MKT-044 to F-MKT-049: Proximity
        if features.monthly:
            if features.monthly.low > 0:
                features.distance_to_monthly_low_pct = float(
                    (price - features.monthly.low) / features.monthly.low
                )
            if features.monthly.high > 0:
                features.distance_to_monthly_high_pct = float(
                    (price - features.monthly.high) / features.monthly.high
                )

        if features.weekly:
            if features.weekly.low > 0:
                features.distance_to_weekly_low_pct = float(
                    (price - features.weekly.low) / features.weekly.low
                )
            if features.weekly.high > 0:
                features.distance_to_weekly_high_pct = float(
                    (price - features.weekly.high) / features.weekly.high
                )

        if features.daily:
            if features.daily.low > 0:
                features.distance_to_daily_low_pct = float(
                    (price - features.daily.low) / features.daily.low
                )
            if features.daily.high > 0:
                features.distance_to_daily_high_pct = float(
                    (price - features.daily.high) / features.daily.high
                )

    def _extract_monthly_low_context(self, features: MarketStateFeatures) -> None:
        """Extract monthly low context features (F-MKT-056 to F-MKT-059)."""
        if features.distance_to_monthly_low_pct is None:
            return

        dist = features.distance_to_monthly_low_pct

        # F-MKT-056: Monthly Low Status
        if dist < 0:
            features.monthly_low_status = MonthlyLowStatus.BELOW
            features.monthly_low_break_flag = True
            features.monthly_low_recovery_state = MonthlyLowRecoveryState.BELOW
        elif dist < self.BREAKING_THRESHOLD:
            features.monthly_low_status = MonthlyLowStatus.BREAKING
            features.monthly_low_break_flag = False
            features.monthly_low_recovery_state = MonthlyLowRecoveryState.BREAKING
        elif dist < self.NEAR_THRESHOLD:
            features.monthly_low_status = MonthlyLowStatus.NEAR
            features.monthly_low_break_flag = False
            features.monthly_low_recovery_state = MonthlyLowRecoveryState.NO_BREAK
        else:
            features.monthly_low_status = MonthlyLowStatus.ABOVE
            features.monthly_low_break_flag = False
            features.monthly_low_recovery_state = MonthlyLowRecoveryState.NO_BREAK

        # F-MKT-057: Distance Below Monthly Low %
        features.distance_below_monthly_low_pct = min(dist, 0.0)

    def _extract_previous_monthly_reference(
        self, features: MarketStateFeatures, previous_candle: Candle | None
    ) -> None:
        """Extract previous monthly reference features (F-MKT-060 to F-MKT-063)."""
        if previous_candle is None or features.last_price is None:
            return

        features.previous_monthly_high = previous_candle.high
        features.previous_monthly_low = previous_candle.low

        if previous_candle.low > 0:
            features.distance_to_previous_monthly_low_pct = float(
                (features.last_price - previous_candle.low) / previous_candle.low
            )

        if previous_candle.high > 0:
            features.distance_to_previous_monthly_high_pct = float(
                (features.last_price - previous_candle.high) / previous_candle.high
            )

    def _extract_multi_timeframe_relationships(self, features: MarketStateFeatures) -> None:
        """Extract multi-timeframe relationship features (F-MKT-064 to F-MKT-067)."""
        # F-MKT-064: Monthly/Weekly Position Difference
        if (
            features.monthly_price_position is not None
            and features.weekly_price_position is not None
        ):
            features.monthly_weekly_position_diff = (
                features.monthly_price_position - features.weekly_price_position
            )

        # F-MKT-065: Monthly/Weekly Low Proximity
        if (
            features.distance_to_monthly_low_pct is not None
            and features.distance_to_weekly_low_pct is not None
        ):
            features.monthly_weekly_low_proximity = (
                features.distance_to_monthly_low_pct + features.distance_to_weekly_low_pct
            ) / 2

        # F-MKT-066: Weekly/Daily Position Difference
        if features.weekly_price_position is not None and features.daily_price_position is not None:
            features.weekly_daily_position_diff = (
                features.weekly_price_position - features.daily_price_position
            )

        # F-MKT-067: Weekly/Daily Low Proximity
        if (
            features.distance_to_weekly_low_pct is not None
            and features.distance_to_daily_low_pct is not None
        ):
            features.weekly_daily_low_proximity = (
                features.distance_to_weekly_low_pct + features.distance_to_daily_low_pct
            ) / 2

    def _extract_trend_features(
        self,
        features: MarketStateFeatures,
        monthly_candles: list[Candle] | None,
        weekly_candles: list[Candle] | None,
        daily_candles: list[Candle] | None,
    ) -> None:
        """Extract trend features (F-MKT-068 to F-MKT-074)."""
        # Simple trend detection based on recent candle direction
        # More sophisticated methods can be added later

        if monthly_candles and len(monthly_candles) >= 2:
            features.monthly_trend_direction = self._detect_trend(monthly_candles[-2:])
            features.monthly_trend_strength = self._calculate_trend_strength(monthly_candles[-2:])

        if weekly_candles and len(weekly_candles) >= 2:
            features.weekly_trend_direction = self._detect_trend(weekly_candles[-2:])
            features.weekly_trend_strength = self._calculate_trend_strength(weekly_candles[-2:])

        if daily_candles and len(daily_candles) >= 2:
            features.daily_trend_direction = self._detect_trend(daily_candles[-2:])
            features.daily_trend_strength = self._calculate_trend_strength(daily_candles[-2:])

        # F-MKT-074: Trend Alignment
        features.trend_alignment = self._calculate_trend_alignment(
            features.monthly_trend_direction,
            features.weekly_trend_direction,
            features.daily_trend_direction,
        )

    def _detect_trend(self, candles: list[Candle]) -> TrendDirection:
        """Detect trend direction from recent candles."""
        if len(candles) < 2:
            return TrendDirection.NEUTRAL

        prev_close = candles[-2].close
        curr_close = candles[-1].close

        if curr_close > prev_close:
            return TrendDirection.BULLISH
        elif curr_close < prev_close:
            return TrendDirection.BEARISH
        return TrendDirection.NEUTRAL

    def _calculate_trend_strength(self, candles: list[Candle]) -> float:
        """Calculate trend strength (0-1) from recent candles."""
        if len(candles) < 2:
            return 0.0

        prev_close = candles[-2].close
        curr_close = candles[-1].close

        if prev_close == 0:
            return 0.0

        change_pct = abs(float((curr_close - prev_close) / prev_close))
        # Normalize: 5% change = strength 1.0
        return min(change_pct / 0.05, 1.0)

    def _calculate_trend_alignment(
        self,
        monthly: TrendDirection | None,
        weekly: TrendDirection | None,
        daily: TrendDirection | None,
    ) -> str:
        """Calculate trend alignment state."""
        directions = [d for d in [monthly, weekly, daily] if d is not None]

        if not directions:
            return "UNKNOWN"

        if all(d == TrendDirection.BULLISH for d in directions):
            return "ALIGNED_BULLISH"
        if all(d == TrendDirection.BEARISH for d in directions):
            return "ALIGNED_BEARISH"
        if all(d == TrendDirection.NEUTRAL for d in directions):
            return "NEUTRAL"

        return "MIXED"

    def _extract_volatility_features(
        self, features: MarketStateFeatures, daily_candles: list[Candle] | None
    ) -> None:
        """Extract volatility features (F-MKT-075 to F-MKT-081)."""
        if not daily_candles or len(daily_candles) < 2:
            return

        # Current volatility: daily range percentage
        current = daily_candles[-1]
        if current.low > 0:
            features.current_volatility = float((current.high - current.low) / current.low)
            features.daily_volatility = features.current_volatility

        # Historical volatility: average of recent daily ranges
        recent = daily_candles[-14:]  # Last 14 days
        ranges = []
        for c in recent:
            if c.low > 0:
                ranges.append(float((c.high - c.low) / c.low))

        if ranges:
            avg_vol = sum(ranges) / len(ranges)
            features.weekly_volatility = avg_vol

            # F-MKT-079: Volatility Regime
            if features.current_volatility is not None:
                if features.current_volatility < self.VOL_LOW_THRESHOLD:
                    features.volatility_regime = VolatilityRegime.LOW
                elif features.current_volatility < self.VOL_NORMAL_THRESHOLD:
                    features.volatility_regime = VolatilityRegime.NORMAL
                elif features.current_volatility < self.VOL_HIGH_THRESHOLD:
                    features.volatility_regime = VolatilityRegime.HIGH
                else:
                    features.volatility_regime = VolatilityRegime.EXTREME

                # F-MKT-080/081: Expansion/Compression
                if avg_vol > 0:
                    ratio = features.current_volatility / avg_vol
                    features.volatility_expansion = ratio > 1.2
                    features.volatility_compression = ratio < 0.8

    def _extract_structural_features(self, features: MarketStateFeatures) -> None:
        """Extract structural pressure and refinement features (F-MKT-082 to F-MKT-087)."""
        # F-MKT-082: Multi-Timeframe Low Pressure
        low_distances = [
            d
            for d in [
                features.distance_to_monthly_low_pct,
                features.distance_to_weekly_low_pct,
                features.distance_to_daily_low_pct,
            ]
            if d is not None
        ]
        if low_distances:
            features.multi_timeframe_low_pressure = sum(low_distances) / len(low_distances)

        # F-MKT-083: Multi-Timeframe High Pressure
        high_distances = [
            d
            for d in [
                features.distance_to_monthly_high_pct,
                features.distance_to_weekly_high_pct,
                features.distance_to_daily_high_pct,
            ]
            if d is not None
        ]
        if high_distances:
            features.multi_timeframe_high_pressure = sum(high_distances) / len(high_distances)

        # F-MKT-084: Structural Alignment
        positions = [
            p
            for p in [
                features.monthly_price_position,
                features.weekly_price_position,
                features.daily_price_position,
            ]
            if p is not None
        ]
        if len(positions) >= 2:
            # Check if all positions are in similar range
            min_pos = min(positions)
            max_pos = max(positions)
            if max_pos - min_pos < 0.2:
                features.structural_alignment = StructuralAlignment.ALIGNED
            elif max_pos - min_pos < 0.5:
                features.structural_alignment = StructuralAlignment.TRANSITION
            else:
                features.structural_alignment = StructuralAlignment.MIXED

        # F-MKT-085: Monthly Context Priority
        if features.distance_to_monthly_low_pct is not None:
            if abs(features.distance_to_monthly_low_pct) < self.NEAR_THRESHOLD:
                features.monthly_context_priority = "MONTHLY_REFINEMENT_REQUIRED"
            else:
                features.monthly_context_priority = "MONTHLY_DOMINANT"

        # F-MKT-086: Weekly Refinement Priority
        if features.distance_to_weekly_low_pct is not None:
            if abs(features.distance_to_weekly_low_pct) < self.NEAR_THRESHOLD:
                features.weekly_refinement_priority = RefinementPriority.HIGH
            elif abs(features.distance_to_weekly_low_pct) < self.NEAR_THRESHOLD * 2:
                features.weekly_refinement_priority = RefinementPriority.MEDIUM
            else:
                features.weekly_refinement_priority = RefinementPriority.LOW

        # F-MKT-087: Daily Refinement Priority
        if features.distance_to_daily_low_pct is not None:
            if abs(features.distance_to_daily_low_pct) < self.NEAR_THRESHOLD:
                features.daily_refinement_priority = RefinementPriority.HIGH
            elif abs(features.distance_to_daily_low_pct) < self.NEAR_THRESHOLD * 2:
                features.daily_refinement_priority = RefinementPriority.MEDIUM
            else:
                features.daily_refinement_priority = RefinementPriority.LOW
