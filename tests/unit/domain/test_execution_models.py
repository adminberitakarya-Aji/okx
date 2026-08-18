"""
Unit tests for execution domain models.

Tests verify key domain rules:
1. Buy cost and sell cost are modeled separately
2. Spread and slippage are never double-counted
3. Net P&L = truth (fees + spread + slippage always modeled)
"""

from decimal import Decimal

import pytest

from trading_grid.domain.execution.models import (
    ExecutionEconomics,
    Fill,
    MinimumProfitableExit,
    Order,
    Position,
)


class TestOrder:
    """Tests for Order."""

    def test_valid_order(self) -> None:
        """Order with valid values should be created."""
        order = Order(
            order_id="ord-001",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("0.1"),
        )
        assert order.status == "PENDING"
        assert order.order_type == "MARKET"
        assert order.is_active
        assert not order.is_filled

    def test_zero_quantity_raises_error(self) -> None:
        """Zero quantity should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            Order(
                order_id="ord-001",
                market_id="BTC-USDT",
                side="BUY",
                quantity=Decimal("0"),
            )

    def test_remaining_quantity(self) -> None:
        """Remaining quantity should calculate correctly."""
        order = Order(
            order_id="ord-001",
            market_id="BTC-USDT",
            side="BUY",
            quantity=Decimal("1.0"),
            filled_quantity=Decimal("0.3"),
        )
        assert order.remaining_quantity == Decimal("0.7")
        assert order.fill_ratio == Decimal("0.3")


class TestFill:
    """Tests for Fill."""

    def test_buy_fill_effective_cost(self) -> None:
        """Buy fill effective cost should include fees."""
        fill = Fill(
            trade_id="trade-001",
            order_id="ord-001",
            market_id="BTC-USDT",
            side="BUY",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            fee=Decimal("5"),
        )
        assert fill.notional_value == Decimal("5000")
        assert fill.effective_cost == Decimal("5005")

    def test_sell_fill_effective_cost(self) -> None:
        """Sell fill effective proceeds should subtract fees."""
        fill = Fill(
            trade_id="trade-002",
            order_id="ord-002",
            market_id="BTC-USDT",
            side="SELL",
            price=Decimal("51000"),
            quantity=Decimal("0.1"),
            fee=Decimal("5.1"),
        )
        assert fill.notional_value == Decimal("5100")
        assert fill.effective_cost == Decimal("5094.9")

    def test_buy_fill_effective_cost_base_currency_fee(self) -> None:
        """Buy fill with fee in base currency converts fee to quote notional."""
        fill = Fill(
            trade_id="trade-003",
            order_id="ord-003",
            market_id="BTC-USDT",
            side="BUY",
            price=Decimal("50000"),
            quantity=Decimal("0.1"),
            fee=Decimal("0.0001"),  # 0.0001 BTC fee
            fee_currency="BTC",
        )
        # Notional: $5,000 + (0.0001 BTC * $50,000 = $5) = $5,005
        assert fill.notional_value == Decimal("5000")
        assert fill.effective_cost == Decimal("5005")


class TestPosition:
    """Tests for Position."""

    def test_unrealized_pnl_profit(self) -> None:
        """Unrealized P&L should be positive when price increases."""
        position = Position(
            position_id="pos-001",
            market_id="BTC-USDT",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000"),
        )
        pnl = position.unrealized_pnl(Decimal("51000"))
        assert pnl == Decimal("100")

    def test_unrealized_pnl_loss(self) -> None:
        """Unrealized P&L should be negative when price decreases."""
        position = Position(
            position_id="pos-001",
            market_id="BTC-USDT",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000"),
        )
        pnl = position.unrealized_pnl(Decimal("49000"))
        assert pnl == Decimal("-100")

    def test_total_pnl(self) -> None:
        """Total P&L should include realized and unrealized."""
        position = Position(
            position_id="pos-001",
            market_id="BTC-USDT",
            quantity=Decimal("0.1"),
            average_entry_price=Decimal("50000"),
            realized_pnl=Decimal("50"),
        )
        total = position.total_pnl(Decimal("51000"))
        assert total == Decimal("150")


class TestExecutionEconomics:
    """Tests for ExecutionEconomics."""

    def test_profitable_trade(self) -> None:
        """Trade should be profitable when sell > buy + costs."""
        economics = ExecutionEconomics(
            buy_price=Decimal("100"),
            buy_fee=Decimal("0.1"),
            sell_price=Decimal("102"),
            sell_fee=Decimal("0.102"),
            quantity=Decimal("1"),
        )
        # Buy cost: 100 + 0.1 = 100.1
        # Sell proceeds: 102 - 0.102 = 101.898
        # Net P&L: 101.898 - 100.1 = 1.798
        assert economics.effective_buy_cost == Decimal("100.1")
        assert economics.effective_sell_proceeds == Decimal("101.898")
        assert economics.net_pnl == Decimal("1.798")
        assert economics.is_profitable

    def test_unprofitable_trade_due_to_fees(self) -> None:
        """Trade with small price gain but high fees should be unprofitable."""
        economics = ExecutionEconomics(
            buy_price=Decimal("100"),
            buy_fee=Decimal("1"),  # 1% fee
            sell_price=Decimal("100.5"),  # 0.5% gain
            sell_fee=Decimal("1.005"),  # 1% fee
            quantity=Decimal("1"),
        )
        # Buy cost: 100 + 1 = 101
        # Sell proceeds: 100.5 - 1.005 = 99.495
        # Net P&L: 99.495 - 101 = -1.505
        assert not economics.is_profitable
        assert economics.net_pnl < 0

    def test_slippage_included_once(self) -> None:
        """Slippage should be included in costs, not double-counted."""
        economics = ExecutionEconomics(
            buy_price=Decimal("100"),
            buy_fee=Decimal("0.1"),
            sell_price=Decimal("102"),
            sell_fee=Decimal("0.1"),
            quantity=Decimal("1"),
            buy_slippage=Decimal("0.05"),
            sell_slippage=Decimal("0.05"),
        )
        # Buy cost: 100 + 0.1 + 0.05 = 100.15
        # Sell proceeds: 102 - 0.1 - 0.05 = 101.85
        assert economics.effective_buy_cost == Decimal("100.15")
        assert economics.effective_sell_proceeds == Decimal("101.85")
        assert economics.total_slippage == Decimal("0.1")

    def test_net_pnl_pct(self) -> None:
        """Net P&L percentage should calculate correctly."""
        economics = ExecutionEconomics(
            buy_price=Decimal("100"),
            buy_fee=Decimal("0"),
            sell_price=Decimal("110"),
            sell_fee=Decimal("0"),
            quantity=Decimal("1"),
        )
        assert economics.net_pnl_pct == Decimal("10")


class TestMinimumProfitableExit:
    """Tests for MinimumProfitableExit."""

    def test_minimum_exit_price_no_fees(self) -> None:
        """With no fees, minimum exit equals entry."""
        exit_calc = MinimumProfitableExit(
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            buy_fee=Decimal("0"),
            estimated_sell_fee_pct=Decimal("0"),
        )
        assert exit_calc.minimum_exit_price == Decimal("100")

    def test_minimum_exit_price_with_fees(self) -> None:
        """With fees, minimum exit should be above entry."""
        exit_calc = MinimumProfitableExit(
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            buy_fee=Decimal("0.1"),  # 0.1% buy fee
            estimated_sell_fee_pct=Decimal("0.1"),  # 0.1% sell fee
        )
        # Cost basis: 100.1
        # Minimum exit: 100.1 / (1 - 0.001) = 100.2002...
        assert exit_calc.minimum_exit_price > Decimal("100.1")
        assert exit_calc.is_profitable_at(Decimal("100.3"))
        assert not exit_calc.is_profitable_at(Decimal("100.1"))

    def test_position_not_profitable_just_above_entry(self) -> None:
        """Position should not be profitable just above entry due to fees."""
        exit_calc = MinimumProfitableExit(
            entry_price=Decimal("100"),
            quantity=Decimal("1"),
            buy_fee=Decimal("0.55"),  # 0.55% total cost as in spec example
            estimated_sell_fee_pct=Decimal("0"),
        )
        # As per spec: Entry $100, costs 0.55%, minimum exit > $100.55
        assert not exit_calc.is_profitable_at(Decimal("100.30"))
        assert exit_calc.is_profitable_at(Decimal("101.00"))
