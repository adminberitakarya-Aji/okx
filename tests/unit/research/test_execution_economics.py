"""
Unit tests for Execution Economics Feature Layer (F-EXE).

Tests cover:
1. Microstructure: bid, ask, spread, mid price
2. Liquidity: depth, volume, liquidity score
3. Fees: buy/sell fee estimation
4. Buy-side economics: execution price, slippage, effective cost
5. Sell-side economics: execution price, slippage, effective proceeds
6. Round-trip economics: fees, costs, net P&L
7. Break-even: break-even price, minimum profitable exit
8. Execution burden ratios
9. Grid economic viability
10. Stress economics
11. Order size and liquidity ratios
12. Price impact
13. Liquidity stress
14. Opportunity margin
15. Execution quality
16. Historical features
17. to_dict serialization
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from okx_trading.research.features.execution_economics import (
    ExecutionEconomicsExtractor,
    ExecutionEconomicsFeatures,
    GridEconomicViability,
    LiquidityStressLevel,
)


class TestMicrostructure:
    """Tests for microstructure features (F-EXE-001 to F-EXE-005)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_bid_ask_extracted(self) -> None:
        """Bid and ask prices should be extracted with availability flags."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
        )
        assert features.microstructure.bid_price == Decimal("49990")
        assert features.microstructure.ask_price == Decimal("50010")
        assert features.microstructure.bid_available is True
        assert features.microstructure.ask_available is True

    def test_spread_absolute(self) -> None:
        """Spread absolute should be ask - bid."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
        )
        assert features.microstructure.spread_absolute == Decimal("20")

    def test_spread_pct(self) -> None:
        """Spread pct should be spread / mid price."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
        )
        # spread = 20, mid = 50000, pct = 0.0004
        assert features.microstructure.spread_pct == pytest.approx(0.0004)

    def test_mid_price(self) -> None:
        """Mid price should be (bid + ask) / 2."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
        )
        assert features.microstructure.mid_price == Decimal("50000")

    def test_missing_bid_flagged(self) -> None:
        """Missing bid should set availability flag to False."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50010"),
        )
        assert features.microstructure.bid_available is False
        assert features.microstructure.spread_absolute is None


class TestLiquidity:
    """Tests for liquidity features (F-EXE-006 to F-EXE-010)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_depth_extracted(self) -> None:
        """Depth values should be extracted."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_depth_top=Decimal("10"),
            ask_depth_top=Decimal("15"),
            depth_near_price=Decimal("100000"),
        )
        assert features.liquidity.bid_depth_top == Decimal("10")
        assert features.liquidity.ask_depth_top == Decimal("15")
        assert features.liquidity.depth_near_price == Decimal("100000")
        assert features.liquidity.depth_available is True

    def test_liquidity_score(self) -> None:
        """Liquidity score should be normalized 0-1."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            depth_near_price=Decimal("1000000"),
        )
        # log10(1000000) / 6 = 1.0
        assert features.liquidity.liquidity_score == pytest.approx(1.0)

    def test_liquidity_score_low_depth(self) -> None:
        """Low depth should give low liquidity score."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            depth_near_price=Decimal("1000"),
        )
        # log10(1000) / 6 = 0.5
        assert features.liquidity.liquidity_score == pytest.approx(0.5)

    def test_volume_extracted(self) -> None:
        """Recent volume should be extracted."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            recent_volume=Decimal("5000000"),
        )
        assert features.liquidity.recent_volume == Decimal("5000000")
        assert features.liquidity.volume_available is True


class TestFees:
    """Tests for fee features (F-EXE-011 to F-EXE-014)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_fee_rates_stored(self) -> None:
        """Fee rates should be stored."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
        )
        assert features.fees.buy_fee_rate == 0.001
        assert features.fees.sell_fee_rate == 0.001

    def test_estimated_buy_fee(self) -> None:
        """Estimated buy fee should be notional * fee rate."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.001,
        )
        assert features.fees.estimated_buy_fee == Decimal("10")

    def test_estimated_sell_fee(self) -> None:
        """Estimated sell fee should be sell notional * fee rate."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            sell_order_size=Decimal("0.2"),
            sell_fee_rate=0.001,
        )
        # sell notional = 0.2 * 50000 = 10000, fee = 10
        assert features.fees.estimated_sell_fee == Decimal("10")


class TestBuySide:
    """Tests for buy-side features (F-EXE-015 to F-EXE-020)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_buy_notional(self) -> None:
        """Buy notional should be stored."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
        )
        assert features.buy_side.buy_notional == Decimal("10000")

    def test_buy_execution_price_without_slippage(self) -> None:
        """Without slippage, execution price equals ask."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
        )
        assert features.buy_side.estimated_buy_execution_price == Decimal("50000")
        assert features.buy_side.buy_slippage_available is False

    def test_buy_execution_price_with_slippage(self) -> None:
        """With slippage, execution price is ask * (1 + slippage)."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            estimated_buy_slippage_pct=0.001,
        )
        # 50000 * 1.001 = 50050
        assert features.buy_side.estimated_buy_execution_price == Decimal("50050")
        assert features.buy_side.buy_slippage_available is True
        assert features.buy_side.estimated_buy_slippage_pct == 0.001

    def test_effective_buy_cost(self) -> None:
        """Effective buy cost includes slippage and fee."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.001,
            estimated_buy_slippage_pct=0.001,
        )
        # quantity = 10000 / 50000 = 0.2
        # execution value = 0.2 * 50050 = 10010
        # fee = 10010 * 0.001 = 10.01
        # effective cost = 10010 + 10.01 = 10020.01
        assert features.buy_side.effective_buy_cost == pytest.approx(Decimal("10020.01"))

    def test_effective_buy_cost_pct(self) -> None:
        """Effective buy cost pct should be cost / notional."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.001,
        )
        # No slippage: cost = 10000 + 10 = 10010, pct = 1.001
        assert features.buy_side.effective_buy_cost_pct == pytest.approx(1.001)


class TestSellSide:
    """Tests for sell-side features (F-EXE-021 to F-EXE-026)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_sell_notional(self) -> None:
        """Sell notional should be quantity * bid."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            sell_order_size=Decimal("0.2"),
        )
        assert features.sell_side.sell_notional == Decimal("10000")

    def test_sell_execution_price_with_slippage(self) -> None:
        """With slippage, execution price is bid * (1 - slippage)."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            sell_order_size=Decimal("0.2"),
            estimated_sell_slippage_pct=0.001,
        )
        # 50000 * 0.999 = 49950
        assert features.sell_side.estimated_sell_execution_price == Decimal("49950")
        assert features.sell_side.sell_slippage_available is True

    def test_effective_sell_proceeds(self) -> None:
        """Effective sell proceeds = execution value - fee."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            sell_order_size=Decimal("0.2"),
            sell_fee_rate=0.001,
            estimated_sell_slippage_pct=0.001,
        )
        # execution value = 0.2 * 49950 = 9990
        # fee = 9990 * 0.001 = 9.99
        # proceeds = 9990 - 9.99 = 9980.01
        assert features.sell_side.effective_sell_proceeds == pytest.approx(Decimal("9980.01"))


class TestRoundTrip:
    """Tests for round-trip features (F-EXE-027 to F-EXE-031)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_round_trip_fee(self) -> None:
        """Round-trip fee should be buy fee + sell fee."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            sell_order_size=Decimal("0.2"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
        )
        # buy fee = 10, sell fee = 10, total = 20
        assert features.round_trip.round_trip_fee == Decimal("20")

    def test_expected_net_pnl(self) -> None:
        """Expected net P&L should be sell proceeds - buy cost."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("51000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            sell_order_size=Decimal("0.2"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
        )
        # buy cost = 10010
        # sell proceeds = 0.2 * 51000 * 0.999 = 10189.8
        # net pnl = 10189.8 - 10010 = 179.8
        assert features.round_trip.expected_net_pnl is not None
        assert features.round_trip.expected_net_pnl > 0

    def test_expected_gross_move(self) -> None:
        """Expected gross move should be mid * pct."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            buy_order_size=Decimal("10000"),
            expected_gross_move_pct=0.02,
        )
        # mid = 50000, gross move = 1000
        assert features.round_trip.expected_gross_move == Decimal("1000")


class TestBreakEven:
    """Tests for break-even features (F-EXE-032 to F-EXE-034)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_break_even_price(self) -> None:
        """Break-even price should recover effective buy cost after sell fees."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
        )
        # quantity = 0.2, effective buy cost = 10010
        # break_even = 10010 / (0.2 * 0.999) = 50100.1...
        assert features.break_even.break_even_price is not None
        assert features.break_even.break_even_price > Decimal("50000")

    def test_minimum_profitable_exit(self) -> None:
        """Minimum profitable exit should be break-even + profit requirement."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
            minimum_profit_requirement=Decimal("100"),
        )
        assert features.break_even.minimum_profitable_exit is not None
        assert features.break_even.break_even_price is not None
        assert features.break_even.minimum_profitable_exit == (
            features.break_even.break_even_price + Decimal("100")
        )


class TestExecutionBurden:
    """Tests for execution burden features (F-EXE-035 to F-EXE-039)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_spread_burden_ratio(self) -> None:
        """Spread burden ratio should be spread pct / gross move pct."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            buy_order_size=Decimal("10000"),
            expected_gross_move_pct=0.02,
        )
        # spread pct = 0.0004, gross move = 0.02
        # ratio = 0.0004 / 0.02 = 0.02
        assert features.execution_burden.spread_burden_ratio == pytest.approx(0.02)

    def test_slippage_burden_ratio(self) -> None:
        """Slippage burden ratio should be total slippage / gross move."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            sell_order_size=Decimal("0.2"),
            estimated_buy_slippage_pct=0.001,
            estimated_sell_slippage_pct=0.001,
            expected_gross_move_pct=0.02,
        )
        # total slippage 0.002 vs gross move 0.02 gives ratio 0.1
        assert features.execution_burden.slippage_burden_ratio == pytest.approx(0.1)


class TestGridViability:
    """Tests for grid viability features (F-EXE-040 to F-EXE-043)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_not_viable_when_costs_exceed_movement(self) -> None:
        """Grid should be NOT_VIABLE when costs exceed expected movement."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.01,  # 1% fee
            sell_fee_rate=0.01,
            expected_gross_move_pct=0.005,  # 0.5% movement
        )
        assert features.grid_viability.grid_economic_viability == GridEconomicViability.NOT_VIABLE

    def test_strong_viability_when_low_costs(self) -> None:
        """Grid should be STRONG when costs are low relative to movement."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.0005,  # 0.05% fee
            sell_fee_rate=0.0005,
            expected_gross_move_pct=0.02,  # 2% movement
        )
        assert features.grid_viability.grid_economic_viability == GridEconomicViability.STRONG


class TestStress:
    """Tests for stress features (F-EXE-044 to F-EXE-047)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_stress_costs_scaled(self) -> None:
        """Stress and extreme costs should be scaled from normal."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            sell_order_size=Decimal("0.2"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
        )
        assert features.stress.normal_execution_cost is not None
        assert features.stress.stress_execution_cost is not None
        assert features.stress.extreme_execution_cost is not None

        normal = features.stress.normal_execution_cost
        assert features.stress.stress_execution_cost == normal * Decimal("1.5")
        assert features.stress.extreme_execution_cost == normal * Decimal("2.5")

    def test_stress_multiplier(self) -> None:
        """Stress multiplier should be 1.5."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            sell_order_size=Decimal("0.2"),
        )
        assert features.stress.execution_cost_stress_multiplier == pytest.approx(1.5)


class TestOrderSize:
    """Tests for order size features (F-EXE-048 to F-EXE-051)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_order_size_liquidity_ratio(self) -> None:
        """Order size / liquidity ratio should be calculated."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            depth_near_price=Decimal("100000"),
        )
        # 10000 / 100000 = 0.1
        assert features.order_size.buy_order_size_liquidity_ratio == pytest.approx(0.1)


class TestPriceImpact:
    """Tests for price impact features (F-EXE-052 to F-EXE-054)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_price_impact_asymmetry(self) -> None:
        """Impact asymmetry should be buy impact - sell impact."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            estimated_buy_slippage_pct=0.002,
            estimated_sell_slippage_pct=0.001,
        )
        assert features.price_impact.execution_impact_asymmetry == pytest.approx(0.001)


class TestLiquidityStress:
    """Tests for liquidity stress features (F-EXE-055 to F-EXE-056)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_spread_stress(self) -> None:
        """Spread stress should be current spread / historical average."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49900"),
            ask_price=Decimal("50100"),
            historical_spreads=[0.001, 0.001, 0.001],
        )
        # current spread pct 0.004 vs historical avg 0.001 gives stress 4.0
        assert features.liquidity_stress.spread_stress == pytest.approx(4.0)
        assert features.liquidity_stress.liquidity_stress_score == LiquidityStressLevel.EXTREME

    def test_low_stress(self) -> None:
        """Normal spread should give LOW stress."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            historical_spreads=[0.0004, 0.0004],
        )
        # current = 0.0004, historical = 0.0004, stress = 1.0
        assert features.liquidity_stress.liquidity_stress_score == LiquidityStressLevel.LOW


class TestOpportunityMargin:
    """Tests for opportunity margin features (F-EXE-057 to F-EXE-058)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_opportunity_margin_pct(self) -> None:
        """Opportunity margin pct should be net / gross."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.001,
            sell_fee_rate=0.001,
            expected_gross_move_pct=0.02,
        )
        # cost pct ~ 0.002, net pct = 0.018
        # margin = 0.018 / 0.02 = 0.9
        assert features.opportunity_margin.economic_opportunity_margin_pct == pytest.approx(
            0.9, rel=0.1
        )


class TestExecutionQuality:
    """Tests for execution quality features (F-EXE-059 to F-EXE-060)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_execution_quality_score(self) -> None:
        """Execution quality score should be normalized 0-1."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
            depth_near_price=Decimal("1000000"),
            estimated_buy_slippage_pct=0.0001,
        )
        assert features.execution_quality.execution_quality_score is not None
        assert 0.0 <= features.execution_quality.execution_quality_score <= 1.0

    def test_execution_cost_stability(self) -> None:
        """Cost stability should be coefficient of variation."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            historical_round_trip_costs=[0.002, 0.002, 0.002],
        )
        # All same => variance = 0 => stability = 0
        assert features.execution_quality.execution_cost_stability == pytest.approx(0.0)


class TestHistorical:
    """Tests for historical features (F-EXE-061 to F-EXE-065)."""

    def setup_method(self) -> None:
        self.extractor = ExecutionEconomicsExtractor()
        self.obs_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_historical_averages(self) -> None:
        """Historical averages should be calculated."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
            historical_buy_slippages=[0.001, 0.002, 0.003],
            historical_sell_slippages=[0.001, 0.001, 0.001],
            historical_spreads=[0.0004, 0.0006],
            historical_round_trip_costs=[0.002, 0.004],
        )
        assert features.historical.historical_average_buy_slippage == pytest.approx(0.002)
        assert features.historical.historical_average_sell_slippage == pytest.approx(0.001)
        assert features.historical.historical_average_spread == pytest.approx(0.0005)
        assert features.historical.historical_average_round_trip_cost == pytest.approx(0.003)
        assert features.historical.historical_data_available is True

    def test_no_historical_data(self) -> None:
        """No historical data should flag availability as False."""
        features = self.extractor.extract(
            market_id="BTC-USDT",
            observation_time=self.obs_time,
        )
        assert features.historical.historical_data_available is False


class TestToDict:
    """Tests for ExecutionEconomicsFeatures.to_dict serialization."""

    def test_to_dict_includes_identity(self) -> None:
        """to_dict should include identity fields."""
        features = ExecutionEconomicsFeatures(market_id="BTC-USDT")
        d = features.to_dict()
        assert d["market_id"] == "BTC-USDT"
        assert d["exchange_id"] == "okx"
        assert "observation_timestamp" in d

    def test_to_dict_includes_microstructure(self) -> None:
        """to_dict should include microstructure fields."""
        extractor = ExecutionEconomicsExtractor()
        features = extractor.extract(
            market_id="BTC-USDT",
            observation_time=datetime(2024, 6, 15, tzinfo=UTC),
            bid_price=Decimal("49990"),
            ask_price=Decimal("50010"),
        )
        d = features.to_dict()
        assert d["bid_price"] == 49990.0
        assert d["ask_price"] == 50010.0
        assert d["spread_absolute"] == 20.0
        assert d["mid_price"] == 50000.0

    def test_to_dict_includes_enums_as_strings(self) -> None:
        """to_dict should convert enums to string values."""
        extractor = ExecutionEconomicsExtractor()
        features = extractor.extract(
            market_id="BTC-USDT",
            observation_time=datetime(2024, 6, 15, tzinfo=UTC),
            bid_price=Decimal("50000"),
            ask_price=Decimal("50000"),
            buy_order_size=Decimal("10000"),
            buy_fee_rate=0.0005,
            sell_fee_rate=0.0005,
            expected_gross_move_pct=0.02,
        )
        d = features.to_dict()
        assert d["grid_economic_viability"] == "STRONG"

    def test_to_dict_none_handling(self) -> None:
        """to_dict should handle None values."""
        features = ExecutionEconomicsFeatures(market_id="BTC-USDT")
        d = features.to_dict()
        assert d["bid_price"] is None
        assert d["liquidity_score"] is None
        assert d["grid_economic_viability"] is None
