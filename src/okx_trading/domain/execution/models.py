"""
Execution domain models.

This module defines execution-related models:
- Order: Order representation
- Fill: Order fill/execution details
- Position: Open position tracking
- ExecutionEconomics: Buy/sell cost calculations

Key domain rules:
1. BUY and SELL use immediate execution (not passive limit orders)
2. Buy cost and sell cost are modeled separately
3. Spread and slippage are never double-counted
4. Net P&L = truth (fees + spread + slippage always modeled)
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from okx_trading.domain.shared.types import (
    ExecutionMode,
    MarketId,
    OrderId,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionId,
    Price,
    Quantity,
    Timestamp,
    TradeId,
)


@dataclass
class Order:
    """
    Order representation.

    Attributes:
        order_id: Internal order ID
        exchange_order_id: Exchange-assigned order ID (after submission)
        market_id: Market identifier
        side: Order side (BUY/SELL)
        order_type: Order type (MARKET for immediate execution)
        quantity: Order quantity
        price: Limit price (None for market orders)
        status: Order status
        filled_quantity: Quantity filled so far
        average_fill_price: Average fill price
        fee: Total fees paid
        created_at: Order creation timestamp
        updated_at: Last update timestamp
        metadata: Additional metadata (grid level, section, etc.)
    """

    order_id: OrderId
    market_id: MarketId
    side: OrderSide
    order_type: OrderType = "MARKET"
    quantity: Quantity = Decimal("0")
    price: Price | None = None
    status: OrderStatus = "PENDING"
    exchange_order_id: str | None = None
    filled_quantity: Quantity = Decimal("0")
    average_fill_price: Price | None = None
    fee: Decimal = Decimal("0")
    created_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    updated_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = field(default_factory=dict)
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        """Validate order constraints."""
        if self.quantity <= 0:
            raise ValueError(f"Order quantity must be positive, got {self.quantity}")

    @property
    def is_filled(self) -> bool:
        """Check if order is completely filled."""
        return self.status == "FILLED"

    @property
    def is_active(self) -> bool:
        """Check if order is still active."""
        return self.status in ("PENDING", "SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED")

    @property
    def remaining_quantity(self) -> Quantity:
        """Get remaining quantity to fill."""
        return self.quantity - self.filled_quantity

    @property
    def fill_ratio(self) -> Decimal:
        """Get fill ratio (0-1)."""
        if self.quantity == 0:
            return Decimal("0")
        return self.filled_quantity / self.quantity


@dataclass(frozen=True)
class Fill:
    """
    Order fill/execution details.

    Attributes:
        trade_id: Exchange trade ID
        order_id: Internal order ID
        market_id: Market identifier
        side: Trade side
        price: Execution price
        quantity: Executed quantity
        fee: Fee paid
        fee_currency: Fee currency
        slippage: Slippage vs expected price
        timestamp: Execution timestamp
    """

    trade_id: TradeId
    order_id: OrderId
    market_id: MarketId
    side: OrderSide
    price: Price
    quantity: Quantity
    fee: Decimal = Decimal("0")
    fee_currency: str = "USDT"
    slippage: Decimal = Decimal("0")
    timestamp: Timestamp = field(default_factory=lambda: datetime.now(UTC))

    @property
    def notional_value(self) -> Decimal:
        """Calculate notional value (price * quantity)."""
        return self.price * self.quantity

    @property
    def effective_cost(self) -> Decimal:
        """Calculate effective cost including fees."""
        if self.side == "BUY":
            return self.notional_value + self.fee
        return self.notional_value - self.fee


@dataclass
class Position:
    """
    Open position tracking.

    Spot-only: no shorting, no leverage.
    Position quantity is always >= 0.

    Attributes:
        position_id: Position identifier
        market_id: Market identifier
        quantity: Position quantity (base currency)
        average_entry_price: Average entry price
        cost_basis: Total cost basis (including fees)
        realized_pnl: Realized P&L from partial sells
        opened_at: Position open timestamp
        updated_at: Last update timestamp
        grid_level: Associated grid level (if any)
        section_id: Associated section (if any)
    """

    position_id: PositionId
    market_id: MarketId
    quantity: Quantity = Decimal("0")
    average_entry_price: Price = Decimal("0")
    cost_basis: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    opened_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    updated_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    grid_level: int | None = None
    section_id: int | None = None

    @property
    def is_open(self) -> bool:
        """Check if position is open."""
        return self.quantity > 0

    def unrealized_pnl(self, current_price: Price) -> Decimal:
        """Calculate unrealized P&L at current price."""
        if self.quantity == 0:
            return Decimal("0")
        return (current_price - self.average_entry_price) * self.quantity

    def total_pnl(self, current_price: Price) -> Decimal:
        """Calculate total P&L (realized + unrealized)."""
        return self.realized_pnl + self.unrealized_pnl(current_price)


@dataclass(frozen=True)
class ExecutionEconomics:
    """
    Execution economics for a trade.

    Models buy-side and sell-side costs separately.
    Never double-counts spread or slippage.

    Attributes:
        buy_price: Actual buy execution price
        buy_fee: Buy-side fee
        buy_slippage: Buy-side slippage cost
        sell_price: Actual/expected sell execution price
        sell_fee: Sell-side fee
        sell_slippage: Sell-side slippage cost
        quantity: Trade quantity
    """

    buy_price: Price
    buy_fee: Decimal
    sell_price: Price
    sell_fee: Decimal
    quantity: Quantity
    buy_slippage: Decimal = Decimal("0")
    sell_slippage: Decimal = Decimal("0")

    @property
    def effective_buy_cost(self) -> Decimal:
        """
        Calculate effective buy cost.

        = (buy_price * quantity) + buy_fee + buy_slippage
        """
        return (self.buy_price * self.quantity) + self.buy_fee + self.buy_slippage

    @property
    def effective_sell_proceeds(self) -> Decimal:
        """
        Calculate effective sell proceeds.

        = (sell_price * quantity) - sell_fee - sell_slippage
        """
        return (self.sell_price * self.quantity) - self.sell_fee - self.sell_slippage

    @property
    def net_pnl(self) -> Decimal:
        """
        Calculate net P&L.

        = effective_sell_proceeds - effective_buy_cost
        """
        return self.effective_sell_proceeds - self.effective_buy_cost

    @property
    def net_pnl_pct(self) -> Decimal:
        """Calculate net P&L percentage."""
        if self.effective_buy_cost == 0:
            return Decimal("0")
        return (self.net_pnl / self.effective_buy_cost) * 100

    @property
    def total_fees(self) -> Decimal:
        """Calculate total fees."""
        return self.buy_fee + self.sell_fee

    @property
    def total_slippage(self) -> Decimal:
        """Calculate total slippage cost."""
        return self.buy_slippage + self.sell_slippage

    @property
    def is_profitable(self) -> bool:
        """Check if trade is profitable after all costs."""
        return self.net_pnl > 0


@dataclass(frozen=True)
class MinimumProfitableExit:
    """
    Minimum profitable exit price calculation.

    The minimum price at which selling would result in positive net P&L
    after all execution costs.

    Attributes:
        entry_price: Actual entry price
        quantity: Position quantity
        buy_fee: Buy-side fee paid
        estimated_sell_fee_pct: Estimated sell fee percentage
        estimated_slippage_pct: Estimated total slippage percentage
    """

    entry_price: Price
    quantity: Quantity
    buy_fee: Decimal
    estimated_sell_fee_pct: Decimal
    estimated_slippage_pct: Decimal = Decimal("0")

    @property
    def cost_basis(self) -> Decimal:
        """Calculate total cost basis."""
        return (self.entry_price * self.quantity) + self.buy_fee

    @property
    def minimum_exit_price(self) -> Price:
        """
        Calculate minimum profitable exit price.

        Solves for sell_price where:
        (sell_price * qty) - (sell_price * qty * fee_pct) - slippage >= cost_basis
        """
        if self.quantity == 0:
            return self.entry_price

        total_cost_pct = (self.estimated_sell_fee_pct + self.estimated_slippage_pct) / 100
        effective_ratio = Decimal("1") - total_cost_pct

        if effective_ratio <= 0:
            # Fees exceed 100%, no profitable exit possible
            return Price("Infinity")

        return self.cost_basis / (self.quantity * effective_ratio)

    def is_profitable_at(self, current_price: Price) -> bool:
        """Check if selling at current price would be profitable."""
        return current_price > self.minimum_exit_price


@dataclass
class ExecutionRecord:
    """
    Complete execution record for audit trail.

    Attributes:
        record_id: Record identifier
        order: The order
        fills: List of fills
        economics: Execution economics
        mode: Execution mode (DEMO/LIVE)
        executed_at: Execution timestamp
    """

    record_id: str
    order: Order
    fills: list[Fill] = field(default_factory=list)
    economics: ExecutionEconomics | None = None
    mode: ExecutionMode = "DEMO"
    executed_at: Timestamp = field(default_factory=lambda: datetime.now(UTC))

    @property
    def total_filled_quantity(self) -> Quantity:
        """Get total filled quantity."""
        return sum((fill.quantity for fill in self.fills), Decimal("0"))

    @property
    def total_fees(self) -> Decimal:
        """Get total fees from all fills."""
        return sum((fill.fee for fill in self.fills), Decimal("0"))
