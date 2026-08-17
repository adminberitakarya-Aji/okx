"""
Execution Economics Feature Layer (F-EXE).

Implements F-EXE-001 through F-EXE-065 from AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md.

This layer answers:
> Is this market economically suitable for our immediate-execution Grid Strategy
> after accounting for the real cost of BUY and SELL execution?

Key principles:
- BUY and SELL execution economics are modeled independently
- Spread and slippage must never be double-counted
- Net P&L is the economic truth
- Missing execution data must not be silently interpreted as zero cost
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from okx_trading.domain.shared.types import MarketId

logger = structlog.get_logger()


class GridEconomicViability(StrEnum):
    """Grid economic viability states."""

    NOT_VIABLE = "NOT_VIABLE"
    MARGINAL = "MARGINAL"
    VIABLE = "VIABLE"
    STRONG = "STRONG"


class LiquidityStressLevel(StrEnum):
    """Liquidity stress levels."""

    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class MicrostructureFeatures:
    """Market microstructure features (F-EXE-001 to F-EXE-005)."""

    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    spread_absolute: Decimal | None = None
    spread_pct: float | None = None
    mid_price: Decimal | None = None

    # Availability flags
    bid_available: bool = False
    ask_available: bool = False


@dataclass
class LiquidityFeatures:
    """Liquidity features (F-EXE-006 to F-EXE-010)."""

    bid_depth_top: Decimal | None = None
    ask_depth_top: Decimal | None = None
    depth_near_price: Decimal | None = None
    recent_volume: Decimal | None = None
    liquidity_score: float | None = None

    # Availability flags
    depth_available: bool = False
    volume_available: bool = False


@dataclass
class FeeFeatures:
    """Fee model features (F-EXE-011 to F-EXE-014)."""

    buy_fee_rate: float = 0.0
    sell_fee_rate: float = 0.0
    estimated_buy_fee: Decimal | None = None
    estimated_sell_fee: Decimal | None = None


@dataclass
class BuySideFeatures:
    """Buy-side economics features (F-EXE-015 to F-EXE-020)."""

    buy_notional: Decimal | None = None
    estimated_buy_execution_price: Decimal | None = None
    estimated_buy_slippage_pct: float | None = None
    estimated_buy_slippage_cost: Decimal | None = None
    effective_buy_cost: Decimal | None = None
    effective_buy_cost_pct: float | None = None

    # Availability flags
    buy_slippage_available: bool = False


@dataclass
class SellSideFeatures:
    """Sell-side economics features (F-EXE-021 to F-EXE-026)."""

    sell_notional: Decimal | None = None
    estimated_sell_execution_price: Decimal | None = None
    estimated_sell_slippage_pct: float | None = None
    estimated_sell_slippage_cost: Decimal | None = None
    effective_sell_proceeds: Decimal | None = None
    effective_sell_proceeds_pct: float | None = None

    # Availability flags
    sell_slippage_available: bool = False


@dataclass
class RoundTripFeatures:
    """Round-trip economics features (F-EXE-027 to F-EXE-031)."""

    round_trip_fee: Decimal | None = None
    round_trip_execution_cost: Decimal | None = None
    expected_gross_move: Decimal | None = None
    expected_net_move: Decimal | None = None
    expected_net_pnl: Decimal | None = None


@dataclass
class BreakEvenFeatures:
    """Break-even features (F-EXE-032 to F-EXE-034)."""

    break_even_price: Decimal | None = None
    minimum_profitable_exit: Decimal | None = None
    required_gross_move: Decimal | None = None


@dataclass
class ExecutionBurdenFeatures:
    """Execution cost ratio and burden features (F-EXE-035 to F-EXE-039)."""

    execution_cost_ratio: float | None = None
    fee_burden_ratio: float | None = None
    spread_burden_ratio: float | None = None
    slippage_burden_ratio: float | None = None
    total_execution_burden_ratio: float | None = None


@dataclass
class GridViabilityFeatures:
    """Grid economic viability features (F-EXE-040 to F-EXE-043)."""

    expected_grid_movement: Decimal | None = None
    expected_grid_round_trip_cost: Decimal | None = None
    expected_grid_net_opportunity: Decimal | None = None
    grid_economic_viability: GridEconomicViability | None = None


@dataclass
class StressFeatures:
    """Stress execution economics features (F-EXE-044 to F-EXE-047)."""

    normal_execution_cost: Decimal | None = None
    stress_execution_cost: Decimal | None = None
    extreme_execution_cost: Decimal | None = None
    execution_cost_stress_multiplier: float | None = None


@dataclass
class OrderSizeFeatures:
    """Order size and liquidity ratio features (F-EXE-048 to F-EXE-051)."""

    buy_order_size: Decimal | None = None
    sell_order_size: Decimal | None = None
    buy_order_size_liquidity_ratio: float | None = None
    sell_order_size_liquidity_ratio: float | None = None


@dataclass
class PriceImpactFeatures:
    """Execution price impact features (F-EXE-052 to F-EXE-054)."""

    expected_buy_price_impact: float | None = None
    expected_sell_price_impact: float | None = None
    execution_impact_asymmetry: float | None = None


@dataclass
class LiquidityStressFeatures:
    """Liquidity stress features (F-EXE-055 to F-EXE-056)."""

    liquidity_stress_score: LiquidityStressLevel | None = None
    spread_stress: float | None = None


@dataclass
class OpportunityMarginFeatures:
    """Economic opportunity margin features (F-EXE-057 to F-EXE-058)."""

    economic_opportunity_margin: Decimal | None = None
    economic_opportunity_margin_pct: float | None = None


@dataclass
class ExecutionQualityFeatures:
    """Execution quality features (F-EXE-059 to F-EXE-060)."""

    execution_quality_score: float | None = None
    execution_cost_stability: float | None = None


@dataclass
class HistoricalExecutionFeatures:
    """Historical execution economics features (F-EXE-061 to F-EXE-065)."""

    historical_average_buy_slippage: float | None = None
    historical_average_sell_slippage: float | None = None
    historical_average_spread: float | None = None
    historical_average_round_trip_cost: float | None = None
    historical_execution_cost_volatility: float | None = None

    # Availability flags
    historical_data_available: bool = False


@dataclass
class ExecutionEconomicsFeatures:
    """
    Complete Execution Economics feature set (F-EXE-001 through F-EXE-065).

    All price-based features use Decimal for precision.
    Normalized features (percentages, ratios) use float for ML compatibility.
    """

    # Identity
    market_id: str
    exchange_id: str = "okx"
    observation_timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Feature groups
    microstructure: MicrostructureFeatures = field(default_factory=MicrostructureFeatures)
    liquidity: LiquidityFeatures = field(default_factory=LiquidityFeatures)
    fees: FeeFeatures = field(default_factory=FeeFeatures)
    buy_side: BuySideFeatures = field(default_factory=BuySideFeatures)
    sell_side: SellSideFeatures = field(default_factory=SellSideFeatures)
    round_trip: RoundTripFeatures = field(default_factory=RoundTripFeatures)
    break_even: BreakEvenFeatures = field(default_factory=BreakEvenFeatures)
    execution_burden: ExecutionBurdenFeatures = field(default_factory=ExecutionBurdenFeatures)
    grid_viability: GridViabilityFeatures = field(default_factory=GridViabilityFeatures)
    stress: StressFeatures = field(default_factory=StressFeatures)
    order_size: OrderSizeFeatures = field(default_factory=OrderSizeFeatures)
    price_impact: PriceImpactFeatures = field(default_factory=PriceImpactFeatures)
    liquidity_stress: LiquidityStressFeatures = field(default_factory=LiquidityStressFeatures)
    opportunity_margin: OpportunityMarginFeatures = field(default_factory=OpportunityMarginFeatures)
    execution_quality: ExecutionQualityFeatures = field(default_factory=ExecutionQualityFeatures)
    historical: HistoricalExecutionFeatures = field(default_factory=HistoricalExecutionFeatures)

    def to_dict(self) -> dict[str, object]:
        """Convert to flat dictionary for ML pipeline."""
        result: dict[str, object] = {
            "market_id": self.market_id,
            "exchange_id": self.exchange_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
        }

        # Microstructure
        ms = self.microstructure
        result["bid_price"] = float(ms.bid_price) if ms.bid_price else None
        result["ask_price"] = float(ms.ask_price) if ms.ask_price else None
        result["spread_absolute"] = float(ms.spread_absolute) if ms.spread_absolute else None
        result["spread_pct"] = ms.spread_pct
        result["mid_price"] = float(ms.mid_price) if ms.mid_price else None
        result["bid_available"] = ms.bid_available
        result["ask_available"] = ms.ask_available

        # Liquidity
        liq = self.liquidity
        result["bid_depth_top"] = float(liq.bid_depth_top) if liq.bid_depth_top else None
        result["ask_depth_top"] = float(liq.ask_depth_top) if liq.ask_depth_top else None
        result["depth_near_price"] = float(liq.depth_near_price) if liq.depth_near_price else None
        result["recent_volume"] = float(liq.recent_volume) if liq.recent_volume else None
        result["liquidity_score"] = liq.liquidity_score
        result["depth_available"] = liq.depth_available
        result["volume_available"] = liq.volume_available

        # Fees
        fees = self.fees
        result["buy_fee_rate"] = fees.buy_fee_rate
        result["sell_fee_rate"] = fees.sell_fee_rate
        result["estimated_buy_fee"] = (
            float(fees.estimated_buy_fee) if fees.estimated_buy_fee else None
        )
        result["estimated_sell_fee"] = (
            float(fees.estimated_sell_fee) if fees.estimated_sell_fee else None
        )

        # Buy side
        buy = self.buy_side
        result["buy_notional"] = float(buy.buy_notional) if buy.buy_notional else None
        result["estimated_buy_execution_price"] = (
            float(buy.estimated_buy_execution_price) if buy.estimated_buy_execution_price else None
        )
        result["estimated_buy_slippage_pct"] = buy.estimated_buy_slippage_pct
        result["estimated_buy_slippage_cost"] = (
            float(buy.estimated_buy_slippage_cost) if buy.estimated_buy_slippage_cost else None
        )
        result["effective_buy_cost"] = (
            float(buy.effective_buy_cost) if buy.effective_buy_cost else None
        )
        result["effective_buy_cost_pct"] = buy.effective_buy_cost_pct
        result["buy_slippage_available"] = buy.buy_slippage_available

        # Sell side
        sell = self.sell_side
        result["sell_notional"] = float(sell.sell_notional) if sell.sell_notional else None
        result["estimated_sell_execution_price"] = (
            float(sell.estimated_sell_execution_price)
            if sell.estimated_sell_execution_price
            else None
        )
        result["estimated_sell_slippage_pct"] = sell.estimated_sell_slippage_pct
        result["estimated_sell_slippage_cost"] = (
            float(sell.estimated_sell_slippage_cost) if sell.estimated_sell_slippage_cost else None
        )
        result["effective_sell_proceeds"] = (
            float(sell.effective_sell_proceeds) if sell.effective_sell_proceeds else None
        )
        result["effective_sell_proceeds_pct"] = sell.effective_sell_proceeds_pct
        result["sell_slippage_available"] = sell.sell_slippage_available

        # Round trip
        rt = self.round_trip
        result["round_trip_fee"] = float(rt.round_trip_fee) if rt.round_trip_fee else None
        result["round_trip_execution_cost"] = (
            float(rt.round_trip_execution_cost) if rt.round_trip_execution_cost else None
        )
        result["expected_gross_move"] = (
            float(rt.expected_gross_move) if rt.expected_gross_move else None
        )
        result["expected_net_move"] = float(rt.expected_net_move) if rt.expected_net_move else None
        result["expected_net_pnl"] = float(rt.expected_net_pnl) if rt.expected_net_pnl else None

        # Break even
        be = self.break_even
        result["break_even_price"] = float(be.break_even_price) if be.break_even_price else None
        result["minimum_profitable_exit"] = (
            float(be.minimum_profitable_exit) if be.minimum_profitable_exit else None
        )
        result["required_gross_move"] = (
            float(be.required_gross_move) if be.required_gross_move else None
        )

        # Execution burden
        eb = self.execution_burden
        result["execution_cost_ratio"] = eb.execution_cost_ratio
        result["fee_burden_ratio"] = eb.fee_burden_ratio
        result["spread_burden_ratio"] = eb.spread_burden_ratio
        result["slippage_burden_ratio"] = eb.slippage_burden_ratio
        result["total_execution_burden_ratio"] = eb.total_execution_burden_ratio

        # Grid viability
        gv = self.grid_viability
        result["expected_grid_movement"] = (
            float(gv.expected_grid_movement) if gv.expected_grid_movement else None
        )
        result["expected_grid_round_trip_cost"] = (
            float(gv.expected_grid_round_trip_cost) if gv.expected_grid_round_trip_cost else None
        )
        result["expected_grid_net_opportunity"] = (
            float(gv.expected_grid_net_opportunity) if gv.expected_grid_net_opportunity else None
        )
        result["grid_economic_viability"] = (
            gv.grid_economic_viability.value if gv.grid_economic_viability else None
        )

        # Stress
        st = self.stress
        result["normal_execution_cost"] = (
            float(st.normal_execution_cost) if st.normal_execution_cost else None
        )
        result["stress_execution_cost"] = (
            float(st.stress_execution_cost) if st.stress_execution_cost else None
        )
        result["extreme_execution_cost"] = (
            float(st.extreme_execution_cost) if st.extreme_execution_cost else None
        )
        result["execution_cost_stress_multiplier"] = st.execution_cost_stress_multiplier

        # Order size
        os_ = self.order_size
        result["buy_order_size"] = float(os_.buy_order_size) if os_.buy_order_size else None
        result["sell_order_size"] = float(os_.sell_order_size) if os_.sell_order_size else None
        result["buy_order_size_liquidity_ratio"] = os_.buy_order_size_liquidity_ratio
        result["sell_order_size_liquidity_ratio"] = os_.sell_order_size_liquidity_ratio

        # Price impact
        pi = self.price_impact
        result["expected_buy_price_impact"] = pi.expected_buy_price_impact
        result["expected_sell_price_impact"] = pi.expected_sell_price_impact
        result["execution_impact_asymmetry"] = pi.execution_impact_asymmetry

        # Liquidity stress
        ls = self.liquidity_stress
        result["liquidity_stress_score"] = (
            ls.liquidity_stress_score.value if ls.liquidity_stress_score else None
        )
        result["spread_stress"] = ls.spread_stress

        # Opportunity margin
        om = self.opportunity_margin
        result["economic_opportunity_margin"] = (
            float(om.economic_opportunity_margin) if om.economic_opportunity_margin else None
        )
        result["economic_opportunity_margin_pct"] = om.economic_opportunity_margin_pct

        # Execution quality
        eq = self.execution_quality
        result["execution_quality_score"] = eq.execution_quality_score
        result["execution_cost_stability"] = eq.execution_cost_stability

        # Historical
        hist = self.historical
        result["historical_average_buy_slippage"] = hist.historical_average_buy_slippage
        result["historical_average_sell_slippage"] = hist.historical_average_sell_slippage
        result["historical_average_spread"] = hist.historical_average_spread
        result["historical_average_round_trip_cost"] = hist.historical_average_round_trip_cost
        result["historical_execution_cost_volatility"] = hist.historical_execution_cost_volatility
        result["historical_data_available"] = hist.historical_data_available

        return result


class ExecutionEconomicsExtractor:
    """
    Extracts Execution Economics features from market data.

    This extractor enforces:
    - Independent BUY and SELL modeling
    - No double-counting of spread/slippage
    - Missing data explicitly flagged, never silently zero

    Usage:
        extractor = ExecutionEconomicsExtractor()
        features = extractor.extract(
            market_id="BTC-USDT",
            observation_time=datetime.now(UTC),
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
        )
    """

    # Default thresholds for grid viability
    VIABILITY_MARGINAL_THRESHOLD = 0.0  # Net opportunity > 0
    VIABILITY_VIABLE_THRESHOLD = 0.002  # Net opportunity > 0.2%
    VIABILITY_STRONG_THRESHOLD = 0.005  # Net opportunity > 0.5%

    # Stress multipliers (implementation-dependent defaults)
    STRESS_MULTIPLIER = 1.5
    EXTREME_MULTIPLIER = 2.5

    def extract(
        self,
        market_id: MarketId,
        observation_time: datetime,
        bid_price: Decimal | None = None,
        ask_price: Decimal | None = None,
        bid_depth_top: Decimal | None = None,
        ask_depth_top: Decimal | None = None,
        depth_near_price: Decimal | None = None,
        recent_volume: Decimal | None = None,
        buy_fee_rate: float = 0.001,
        sell_fee_rate: float = 0.001,
        buy_order_size: Decimal | None = None,
        sell_order_size: Decimal | None = None,
        estimated_buy_slippage_pct: float | None = None,
        estimated_sell_slippage_pct: float | None = None,
        expected_gross_move_pct: float | None = None,
        minimum_profit_requirement: Decimal | None = None,
        historical_spreads: list[float] | None = None,
        historical_buy_slippages: list[float] | None = None,
        historical_sell_slippages: list[float] | None = None,
        historical_round_trip_costs: list[float] | None = None,
    ) -> ExecutionEconomicsFeatures:
        """
        Extract Execution Economics features.

        Args:
            market_id: Market identifier
            observation_time: Observation timestamp (causal cutoff)
            bid_price: Current best bid
            ask_price: Current best ask
            bid_depth_top: Quantity at best bid
            ask_depth_top: Quantity at best ask
            depth_near_price: Executable liquidity within price band
            recent_volume: Recent trading volume
            buy_fee_rate: Buy fee rate (decimal, e.g., 0.001 = 0.1%)
            sell_fee_rate: Sell fee rate (decimal)
            buy_order_size: Intended buy order size (quote currency)
            sell_order_size: Intended sell order size (base currency)
            estimated_buy_slippage_pct: Estimated buy slippage as decimal
            estimated_sell_slippage_pct: Estimated sell slippage as decimal
            expected_gross_move_pct: Expected gross price movement as decimal
            minimum_profit_requirement: Minimum profit required above break-even
            historical_spreads: Historical spread percentages
            historical_buy_slippages: Historical buy slippage percentages
            historical_sell_slippages: Historical sell slippage percentages
            historical_round_trip_costs: Historical round-trip cost percentages

        Returns:
            ExecutionEconomicsFeatures with all computed features
        """
        features = ExecutionEconomicsFeatures(
            market_id=market_id,
            observation_timestamp=observation_time,
        )

        # F-EXE-001 to F-EXE-005: Microstructure
        self._extract_microstructure(features, bid_price, ask_price)

        # F-EXE-006 to F-EXE-010: Liquidity
        self._extract_liquidity(
            features, bid_depth_top, ask_depth_top, depth_near_price, recent_volume
        )

        # F-EXE-011 to F-EXE-014: Fees
        self._extract_fees(features, buy_fee_rate, sell_fee_rate, buy_order_size, sell_order_size)

        # F-EXE-015 to F-EXE-020: Buy side
        self._extract_buy_side(
            features, ask_price, buy_order_size, buy_fee_rate, estimated_buy_slippage_pct
        )

        # F-EXE-021 to F-EXE-026: Sell side
        self._extract_sell_side(
            features, bid_price, sell_order_size, sell_fee_rate, estimated_sell_slippage_pct
        )

        # F-EXE-027 to F-EXE-031: Round trip
        self._extract_round_trip(features, expected_gross_move_pct)

        # F-EXE-032 to F-EXE-034: Break even
        self._extract_break_even(features, minimum_profit_requirement)

        # F-EXE-035 to F-EXE-039: Execution burden
        self._extract_execution_burden(features, expected_gross_move_pct)

        # F-EXE-040 to F-EXE-043: Grid viability
        self._extract_grid_viability(features, expected_gross_move_pct)

        # F-EXE-044 to F-EXE-047: Stress
        self._extract_stress(features)

        # F-EXE-048 to F-EXE-051: Order size
        self._extract_order_size(features, buy_order_size, sell_order_size, depth_near_price)

        # F-EXE-052 to F-EXE-054: Price impact
        self._extract_price_impact(
            features, estimated_buy_slippage_pct, estimated_sell_slippage_pct
        )

        # F-EXE-055 to F-EXE-056: Liquidity stress
        self._extract_liquidity_stress(features, historical_spreads)

        # F-EXE-057 to F-EXE-058: Opportunity margin
        self._extract_opportunity_margin(features, expected_gross_move_pct)

        # F-EXE-059 to F-EXE-060: Execution quality
        self._extract_execution_quality(features, historical_round_trip_costs)

        # F-EXE-061 to F-EXE-065: Historical
        self._extract_historical(
            features,
            historical_spreads,
            historical_buy_slippages,
            historical_sell_slippages,
            historical_round_trip_costs,
        )

        return features

    def _extract_microstructure(
        self,
        features: ExecutionEconomicsFeatures,
        bid_price: Decimal | None,
        ask_price: Decimal | None,
    ) -> None:
        """Extract microstructure features (F-EXE-001 to F-EXE-005)."""
        ms = features.microstructure

        ms.bid_price = bid_price
        ms.bid_available = bid_price is not None

        ms.ask_price = ask_price
        ms.ask_available = ask_price is not None

        if bid_price is not None and ask_price is not None:
            # F-EXE-003: Spread Absolute
            ms.spread_absolute = ask_price - bid_price

            # F-EXE-005: Mid Price
            ms.mid_price = (bid_price + ask_price) / 2

            # F-EXE-004: Spread Percentage
            if ms.mid_price > 0:
                ms.spread_pct = float(ms.spread_absolute / ms.mid_price)

    def _extract_liquidity(
        self,
        features: ExecutionEconomicsFeatures,
        bid_depth_top: Decimal | None,
        ask_depth_top: Decimal | None,
        depth_near_price: Decimal | None,
        recent_volume: Decimal | None,
    ) -> None:
        """Extract liquidity features (F-EXE-006 to F-EXE-010)."""
        liq = features.liquidity

        liq.bid_depth_top = bid_depth_top
        liq.ask_depth_top = ask_depth_top
        liq.depth_near_price = depth_near_price
        liq.depth_available = depth_near_price is not None

        liq.recent_volume = recent_volume
        liq.volume_available = recent_volume is not None

        # F-EXE-010: Liquidity Score (normalized 0-1)
        # Simple scoring based on depth near price
        if depth_near_price is not None and depth_near_price > 0:
            # Log-scale normalization: score = min(log10(depth) / 6, 1.0)
            # depth of 1,000,000 => score 1.0
            import math

            liq.liquidity_score = min(math.log10(float(depth_near_price)) / 6.0, 1.0)

    def _extract_fees(
        self,
        features: ExecutionEconomicsFeatures,
        buy_fee_rate: float,
        sell_fee_rate: float,
        buy_order_size: Decimal | None,
        sell_order_size: Decimal | None,
    ) -> None:
        """Extract fee features (F-EXE-011 to F-EXE-014)."""
        fees = features.fees

        fees.buy_fee_rate = buy_fee_rate
        fees.sell_fee_rate = sell_fee_rate

        # F-EXE-013: Estimated Buy Fee
        if buy_order_size is not None:
            fees.estimated_buy_fee = buy_order_size * Decimal(str(buy_fee_rate))

        # F-EXE-014: Estimated Sell Fee
        if sell_order_size is not None and features.microstructure.bid_price is not None:
            sell_notional = sell_order_size * features.microstructure.bid_price
            fees.estimated_sell_fee = sell_notional * Decimal(str(sell_fee_rate))

    def _extract_buy_side(
        self,
        features: ExecutionEconomicsFeatures,
        ask_price: Decimal | None,
        buy_order_size: Decimal | None,
        buy_fee_rate: float,
        estimated_buy_slippage_pct: float | None,
    ) -> None:
        """Extract buy-side features (F-EXE-015 to F-EXE-020)."""
        buy = features.buy_side

        buy.buy_notional = buy_order_size

        if ask_price is None or buy_order_size is None:
            return

        # F-EXE-016: Estimated Buy Execution Price
        if estimated_buy_slippage_pct is not None:
            buy.buy_slippage_available = True
            slippage_factor = Decimal(str(1 + estimated_buy_slippage_pct))
            buy.estimated_buy_execution_price = ask_price * slippage_factor

            # F-EXE-017: Buy Slippage Percentage
            buy.estimated_buy_slippage_pct = estimated_buy_slippage_pct

            # F-EXE-018: Buy Slippage Cost (per unit)
            buy.estimated_buy_slippage_cost = buy.estimated_buy_execution_price - ask_price
        else:
            buy.estimated_buy_execution_price = ask_price
            buy.buy_slippage_available = False

        # F-EXE-019: Effective Buy Cost
        # = Buy Execution Value + Buy Fee
        # (slippage already reflected in execution price, not added again)
        quantity = buy_order_size / ask_price if ask_price > 0 else Decimal("0")
        execution_value = quantity * buy.estimated_buy_execution_price
        buy_fee = execution_value * Decimal(str(buy_fee_rate))
        buy.effective_buy_cost = execution_value + buy_fee

        # F-EXE-020: Effective Buy Cost Percentage
        if buy_order_size > 0:
            buy.effective_buy_cost_pct = float(buy.effective_buy_cost / buy_order_size)

    def _extract_sell_side(
        self,
        features: ExecutionEconomicsFeatures,
        bid_price: Decimal | None,
        sell_order_size: Decimal | None,
        sell_fee_rate: float,
        estimated_sell_slippage_pct: float | None,
    ) -> None:
        """Extract sell-side features (F-EXE-021 to F-EXE-026)."""
        sell = features.sell_side

        if bid_price is None or sell_order_size is None:
            return

        sell.sell_notional = sell_order_size * bid_price

        # F-EXE-022: Estimated Sell Execution Price
        if estimated_sell_slippage_pct is not None:
            sell.sell_slippage_available = True
            slippage_factor = Decimal(str(1 - estimated_sell_slippage_pct))
            sell.estimated_sell_execution_price = bid_price * slippage_factor

            # F-EXE-023: Sell Slippage Percentage
            sell.estimated_sell_slippage_pct = estimated_sell_slippage_pct

            # F-EXE-024: Sell Slippage Cost (per unit)
            sell.estimated_sell_slippage_cost = bid_price - sell.estimated_sell_execution_price
        else:
            sell.estimated_sell_execution_price = bid_price
            sell.sell_slippage_available = False

        # F-EXE-025: Effective Sell Proceeds
        # = Sell Execution Value - Sell Fee
        # (slippage already reflected in execution price, not subtracted again)
        execution_value = sell_order_size * sell.estimated_sell_execution_price
        sell_fee = execution_value * Decimal(str(sell_fee_rate))
        sell.effective_sell_proceeds = execution_value - sell_fee

        # F-EXE-026: Effective Sell Proceeds Percentage
        if sell.sell_notional is not None and sell.sell_notional > 0:
            sell.effective_sell_proceeds_pct = float(
                sell.effective_sell_proceeds / sell.sell_notional
            )

    def _extract_round_trip(
        self,
        features: ExecutionEconomicsFeatures,
        expected_gross_move_pct: float | None,
    ) -> None:
        """Extract round-trip features (F-EXE-027 to F-EXE-031)."""
        rt = features.round_trip

        # F-EXE-027: Round-Trip Fee
        buy_fee = features.fees.estimated_buy_fee
        sell_fee = features.fees.estimated_sell_fee
        if buy_fee is not None and sell_fee is not None:
            rt.round_trip_fee = buy_fee + sell_fee

        # F-EXE-028: Round-Trip Execution Cost
        # = Effective Buy Cost - Buy Notional + (Sell Notional - Effective Sell Proceeds)
        buy = features.buy_side
        sell = features.sell_side
        if buy.effective_buy_cost is not None and buy.buy_notional is not None:
            buy_burden = buy.effective_buy_cost - buy.buy_notional
            sell_burden = Decimal("0")
            if sell.sell_notional is not None and sell.effective_sell_proceeds is not None:
                sell_burden = sell.sell_notional - sell.effective_sell_proceeds
            rt.round_trip_execution_cost = buy_burden + sell_burden

        # F-EXE-029: Expected Gross Move
        if expected_gross_move_pct is not None and features.microstructure.mid_price is not None:
            rt.expected_gross_move = features.microstructure.mid_price * Decimal(
                str(expected_gross_move_pct)
            )

        # F-EXE-030: Expected Net Move
        if (
            rt.expected_gross_move is not None
            and rt.round_trip_execution_cost is not None
            and features.buy_side.buy_notional is not None
            and features.buy_side.buy_notional > 0
        ):
            # Convert cost to price movement equivalent
            cost_pct = rt.round_trip_execution_cost / features.buy_side.buy_notional
            rt.expected_net_move = rt.expected_gross_move - (
                features.microstructure.mid_price * cost_pct
                if features.microstructure.mid_price
                else Decimal("0")
            )

        # F-EXE-031: Expected Net P&L
        if sell.effective_sell_proceeds is not None and buy.effective_buy_cost is not None:
            rt.expected_net_pnl = sell.effective_sell_proceeds - buy.effective_buy_cost

    def _extract_break_even(
        self,
        features: ExecutionEconomicsFeatures,
        minimum_profit_requirement: Decimal | None,
    ) -> None:
        """Extract break-even features (F-EXE-032 to F-EXE-034)."""
        be = features.break_even
        buy = features.buy_side

        if buy.effective_buy_cost is None or buy.buy_notional is None or buy.buy_notional == 0:
            return

        # F-EXE-032: Break-Even Price
        # The sell price at which Net P&L equals zero.
        # We solve for the sell price that recovers the effective buy cost after sell fees.
        quantity = (
            buy.buy_notional / features.microstructure.ask_price
            if (features.microstructure.ask_price and features.microstructure.ask_price > 0)
            else Decimal("0")
        )

        if quantity > 0:
            sell_fee_rate = Decimal(str(features.fees.sell_fee_rate))
            be.break_even_price = buy.effective_buy_cost / (quantity * (1 - sell_fee_rate))

            # F-EXE-033: Minimum Profitable Exit
            profit_req = minimum_profit_requirement or Decimal("0")
            be.minimum_profitable_exit = be.break_even_price + profit_req

            # F-EXE-034: Required Gross Move
            if features.microstructure.ask_price and features.microstructure.ask_price > 0:
                be.required_gross_move = (
                    be.minimum_profitable_exit - features.microstructure.ask_price
                )

    def _extract_execution_burden(
        self,
        features: ExecutionEconomicsFeatures,
        expected_gross_move_pct: float | None,
    ) -> None:
        """Extract execution burden features (F-EXE-035 to F-EXE-039)."""
        eb = features.execution_burden
        rt = features.round_trip

        if expected_gross_move_pct is None or expected_gross_move_pct == 0:
            return

        gross_move = Decimal(str(expected_gross_move_pct))

        # F-EXE-035: Execution Cost Ratio
        if rt.round_trip_execution_cost is not None and features.buy_side.buy_notional:
            cost_pct = rt.round_trip_execution_cost / features.buy_side.buy_notional
            if gross_move > 0:
                eb.execution_cost_ratio = float(cost_pct / gross_move)

        # F-EXE-036: Fee Burden Ratio
        if rt.round_trip_fee is not None and features.buy_side.buy_notional:
            fee_pct = rt.round_trip_fee / features.buy_side.buy_notional
            eb.fee_burden_ratio = float(fee_pct / gross_move)

        # F-EXE-037: Spread Burden Ratio
        if features.microstructure.spread_pct is not None:
            eb.spread_burden_ratio = features.microstructure.spread_pct / expected_gross_move_pct

        # F-EXE-038: Slippage Burden Ratio
        buy_slip = features.buy_side.estimated_buy_slippage_pct or 0.0
        sell_slip = features.sell_side.estimated_sell_slippage_pct or 0.0
        total_slippage = buy_slip + sell_slip
        eb.slippage_burden_ratio = total_slippage / expected_gross_move_pct

        # F-EXE-039: Total Execution Burden Ratio
        if eb.execution_cost_ratio is not None:
            eb.total_execution_burden_ratio = eb.execution_cost_ratio

    def _extract_grid_viability(
        self,
        features: ExecutionEconomicsFeatures,
        expected_gross_move_pct: float | None,
    ) -> None:
        """Extract grid viability features (F-EXE-040 to F-EXE-043)."""
        gv = features.grid_viability
        rt = features.round_trip

        # F-EXE-040: Expected Grid Movement
        gv.expected_grid_movement = rt.expected_gross_move

        # F-EXE-041: Expected Grid Round-Trip Cost
        gv.expected_grid_round_trip_cost = rt.round_trip_execution_cost

        # F-EXE-042: Expected Grid Net Opportunity
        if gv.expected_grid_movement is not None and gv.expected_grid_round_trip_cost is not None:
            gv.expected_grid_net_opportunity = (
                gv.expected_grid_movement - gv.expected_grid_round_trip_cost
            )

        # F-EXE-043: Grid Economic Viability
        if expected_gross_move_pct is not None and features.buy_side.buy_notional:
            rt_cost = rt.round_trip_execution_cost or Decimal("0")
            cost_pct = float(rt_cost / features.buy_side.buy_notional)
            net_opportunity_pct = expected_gross_move_pct - cost_pct

            if net_opportunity_pct <= self.VIABILITY_MARGINAL_THRESHOLD:
                gv.grid_economic_viability = GridEconomicViability.NOT_VIABLE
            elif net_opportunity_pct <= self.VIABILITY_VIABLE_THRESHOLD:
                gv.grid_economic_viability = GridEconomicViability.MARGINAL
            elif net_opportunity_pct <= self.VIABILITY_STRONG_THRESHOLD:
                gv.grid_economic_viability = GridEconomicViability.VIABLE
            else:
                gv.grid_economic_viability = GridEconomicViability.STRONG

    def _extract_stress(self, features: ExecutionEconomicsFeatures) -> None:
        """Extract stress features (F-EXE-044 to F-EXE-047)."""
        st = features.stress
        rt = features.round_trip

        # F-EXE-044: Normal Execution Cost
        st.normal_execution_cost = rt.round_trip_execution_cost

        # F-EXE-045/046: Stress and Extreme Execution Cost
        if st.normal_execution_cost is not None:
            st.stress_execution_cost = st.normal_execution_cost * Decimal(
                str(self.STRESS_MULTIPLIER)
            )
            st.extreme_execution_cost = st.normal_execution_cost * Decimal(
                str(self.EXTREME_MULTIPLIER)
            )

            # F-EXE-047: Execution Cost Stress Multiplier
            if st.normal_execution_cost > 0:
                st.execution_cost_stress_multiplier = float(
                    st.stress_execution_cost / st.normal_execution_cost
                )

    def _extract_order_size(
        self,
        features: ExecutionEconomicsFeatures,
        buy_order_size: Decimal | None,
        sell_order_size: Decimal | None,
        depth_near_price: Decimal | None,
    ) -> None:
        """Extract order size features (F-EXE-048 to F-EXE-051)."""
        os_ = features.order_size

        os_.buy_order_size = buy_order_size
        os_.sell_order_size = sell_order_size

        # F-EXE-050/051: Order Size / Liquidity Ratio
        if depth_near_price is not None and depth_near_price > 0:
            if buy_order_size is not None:
                os_.buy_order_size_liquidity_ratio = float(buy_order_size / depth_near_price)
            if sell_order_size is not None and features.microstructure.mid_price:
                sell_notional = sell_order_size * features.microstructure.mid_price
                os_.sell_order_size_liquidity_ratio = float(sell_notional / depth_near_price)

    def _extract_price_impact(
        self,
        features: ExecutionEconomicsFeatures,
        estimated_buy_slippage_pct: float | None,
        estimated_sell_slippage_pct: float | None,
    ) -> None:
        """Extract price impact features (F-EXE-052 to F-EXE-054)."""
        pi = features.price_impact

        # F-EXE-052/053: Expected Buy/Sell Price Impact
        pi.expected_buy_price_impact = estimated_buy_slippage_pct
        pi.expected_sell_price_impact = estimated_sell_slippage_pct

        # F-EXE-054: Execution Impact Asymmetry
        if estimated_buy_slippage_pct is not None and estimated_sell_slippage_pct is not None:
            pi.execution_impact_asymmetry = estimated_buy_slippage_pct - estimated_sell_slippage_pct

    def _extract_liquidity_stress(
        self,
        features: ExecutionEconomicsFeatures,
        historical_spreads: list[float] | None,
    ) -> None:
        """Extract liquidity stress features (F-EXE-055 to F-EXE-056)."""
        ls = features.liquidity_stress

        # F-EXE-056: Spread Stress
        if historical_spreads and features.microstructure.spread_pct is not None:
            avg_spread = sum(historical_spreads) / len(historical_spreads)
            if avg_spread > 0:
                ls.spread_stress = features.microstructure.spread_pct / avg_spread

                # F-EXE-055: Liquidity Stress Score
                if ls.spread_stress < 1.2:
                    ls.liquidity_stress_score = LiquidityStressLevel.LOW
                elif ls.spread_stress < 2.0:
                    ls.liquidity_stress_score = LiquidityStressLevel.NORMAL
                elif ls.spread_stress < 3.0:
                    ls.liquidity_stress_score = LiquidityStressLevel.HIGH
                else:
                    ls.liquidity_stress_score = LiquidityStressLevel.EXTREME

    def _extract_opportunity_margin(
        self,
        features: ExecutionEconomicsFeatures,
        expected_gross_move_pct: float | None,
    ) -> None:
        """Extract opportunity margin features (F-EXE-057 to F-EXE-058)."""
        om = features.opportunity_margin
        rt = features.round_trip

        # F-EXE-057: Economic Opportunity Margin
        if rt.expected_gross_move is not None and rt.round_trip_execution_cost is not None:
            om.economic_opportunity_margin = rt.expected_gross_move - rt.round_trip_execution_cost

        # F-EXE-058: Economic Opportunity Margin %
        if (
            expected_gross_move_pct is not None
            and expected_gross_move_pct > 0
            and features.buy_side.buy_notional
            and rt.round_trip_execution_cost is not None
        ):
            cost_pct = float(rt.round_trip_execution_cost / features.buy_side.buy_notional)
            net_pct = expected_gross_move_pct - cost_pct
            om.economic_opportunity_margin_pct = net_pct / expected_gross_move_pct

    def _extract_execution_quality(
        self,
        features: ExecutionEconomicsFeatures,
        historical_round_trip_costs: list[float] | None,
    ) -> None:
        """Extract execution quality features (F-EXE-059 to F-EXE-060)."""
        eq = features.execution_quality

        # F-EXE-059: Execution Quality Score (normalized 0-1)
        # Combines spread, liquidity, and slippage
        components: list[float] = []

        if features.microstructure.spread_pct is not None:
            # Lower spread = higher quality (spread < 0.1% = 1.0, > 1% = 0.0)
            spread_score = max(0.0, min(1.0, 1.0 - features.microstructure.spread_pct / 0.01))
            components.append(spread_score)

        if features.liquidity.liquidity_score is not None:
            components.append(features.liquidity.liquidity_score)

        if features.buy_side.estimated_buy_slippage_pct is not None:
            # Lower slippage = higher quality
            slip_score = max(
                0.0, min(1.0, 1.0 - features.buy_side.estimated_buy_slippage_pct / 0.01)
            )
            components.append(slip_score)

        if components:
            eq.execution_quality_score = sum(components) / len(components)

        # F-EXE-060: Execution Cost Stability
        if historical_round_trip_costs and len(historical_round_trip_costs) >= 2:
            mean = sum(historical_round_trip_costs) / len(historical_round_trip_costs)
            if mean > 0:
                variance = sum((c - mean) ** 2 for c in historical_round_trip_costs) / len(
                    historical_round_trip_costs
                )
                std_dev = variance**0.5
                # Coefficient of variation (lower = more stable)
                eq.execution_cost_stability = std_dev / mean

    def _extract_historical(
        self,
        features: ExecutionEconomicsFeatures,
        historical_spreads: list[float] | None,
        historical_buy_slippages: list[float] | None,
        historical_sell_slippages: list[float] | None,
        historical_round_trip_costs: list[float] | None,
    ) -> None:
        """Extract historical features (F-EXE-061 to F-EXE-065)."""
        hist = features.historical

        has_data = False

        if historical_buy_slippages:
            hist.historical_average_buy_slippage = sum(historical_buy_slippages) / len(
                historical_buy_slippages
            )
            has_data = True

        if historical_sell_slippages:
            hist.historical_average_sell_slippage = sum(historical_sell_slippages) / len(
                historical_sell_slippages
            )
            has_data = True

        if historical_spreads:
            hist.historical_average_spread = sum(historical_spreads) / len(historical_spreads)
            has_data = True

        if historical_round_trip_costs:
            hist.historical_average_round_trip_cost = sum(historical_round_trip_costs) / len(
                historical_round_trip_costs
            )
            has_data = True

            # F-EXE-065: Historical Execution Cost Volatility
            if len(historical_round_trip_costs) >= 2:
                mean = hist.historical_average_round_trip_cost
                if mean and mean > 0:
                    variance = sum((c - mean) ** 2 for c in historical_round_trip_costs) / len(
                        historical_round_trip_costs
                    )
                    hist.historical_execution_cost_volatility = (variance**0.5) / mean

        hist.historical_data_available = has_data
