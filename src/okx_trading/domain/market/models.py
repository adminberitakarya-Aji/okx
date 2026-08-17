"""
Market domain models.

This module defines market-related models:
- Market: Trading pair information
- Candle: OHLCV candlestick data
- OrderBook: Order book snapshot
- Ticker: Current market ticker
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from okx_trading.domain.shared.types import MarketId, Price, Quantity, Timestamp


@dataclass(frozen=True)
class Market:
    """
    Trading market/pair information.

    Attributes:
        market_id: Market identifier (e.g., 'BTC-USDT')
        base_currency: Base currency (e.g., 'BTC')
        quote_currency: Quote currency (e.g., 'USDT')
        min_order_size: Minimum order size in base currency
        max_order_size: Maximum order size in base currency
        min_price: Minimum price
        max_price: Maximum price
        tick_size: Price tick size (minimum price increment)
        lot_size: Quantity lot size (minimum quantity increment)
        maker_fee_pct: Maker fee percentage
        taker_fee_pct: Taker fee percentage
        is_active: Whether the market is active/tradable
    """

    market_id: MarketId
    base_currency: str
    quote_currency: str
    min_order_size: Quantity = Decimal("0")
    max_order_size: Quantity | None = None
    min_price: Price | None = None
    max_price: Price | None = None
    tick_size: Price = Decimal("0.00000001")
    lot_size: Quantity = Decimal("0.00000001")
    maker_fee_pct: Decimal = Decimal("0.1")
    taker_fee_pct: Decimal = Decimal("0.1")
    is_active: bool = True

    def __post_init__(self) -> None:
        """Validate market constraints."""
        if not self.market_id:
            raise ValueError("Market ID cannot be empty")
        if self.tick_size <= 0:
            raise ValueError(f"Tick size must be positive, got {self.tick_size}")
        if self.lot_size <= 0:
            raise ValueError(f"Lot size must be positive, got {self.lot_size}")

    def round_price(self, price: Price) -> Price:
        """Round price to tick size."""
        return (price / self.tick_size).quantize(Decimal("1")) * self.tick_size

    def round_quantity(self, quantity: Quantity) -> Quantity:
        """Round quantity to lot size."""
        return (quantity / self.lot_size).quantize(Decimal("1")) * self.lot_size

    def validate_order(self, price: Price, quantity: Quantity) -> list[str]:
        """
        Validate an order against market constraints.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []

        if quantity < self.min_order_size:
            errors.append(f"Quantity {quantity} below minimum {self.min_order_size}")
        if self.max_order_size and quantity > self.max_order_size:
            errors.append(f"Quantity {quantity} above maximum {self.max_order_size}")
        if self.min_price and price < self.min_price:
            errors.append(f"Price {price} below minimum {self.min_price}")
        if self.max_price and price > self.max_price:
            errors.append(f"Price {price} above maximum {self.max_price}")
        if not self.is_active:
            errors.append(f"Market {self.market_id} is not active")

        return errors


@dataclass(frozen=True)
class Candle:
    """
    OHLCV candlestick data.

    Attributes:
        market_id: Market identifier
        timestamp: Candle open time (UTC)
        open: Opening price
        high: Highest price
        low: Lowest price
        close: Closing price
        volume: Trading volume (base currency)
        quote_volume: Trading volume (quote currency)
        trade_count: Number of trades
    """

    market_id: MarketId
    timestamp: Timestamp
    open: Price
    high: Price
    low: Price
    close: Price
    volume: Quantity
    quote_volume: Quantity = Decimal("0")
    trade_count: int = 0

    def __post_init__(self) -> None:
        """Validate candle constraints."""
        if self.high < self.low:
            raise ValueError(f"High ({self.high}) cannot be less than low ({self.low})")
        if self.high < self.open or self.high < self.close:
            raise ValueError("High must be >= open and close")
        if self.low > self.open or self.low > self.close:
            raise ValueError("Low must be <= open and close")
        if self.volume < 0:
            raise ValueError(f"Volume cannot be negative, got {self.volume}")

    @property
    def is_bullish(self) -> bool:
        """Check if candle is bullish (close > open)."""
        return self.close > self.open

    @property
    def is_bearish(self) -> bool:
        """Check if candle is bearish (close < open)."""
        return self.close < self.open

    @property
    def body_size(self) -> Price:
        """Get the candle body size."""
        return abs(self.close - self.open)

    @property
    def range_size(self) -> Price:
        """Get the candle range size (high - low)."""
        return self.high - self.low


@dataclass(frozen=True)
class OrderBookLevel:
    """
    A single order book level.

    Attributes:
        price: Price level
        quantity: Total quantity at this level
    """

    price: Price
    quantity: Quantity


@dataclass(frozen=True)
class OrderBook:
    """
    Order book snapshot.

    Attributes:
        market_id: Market identifier
        timestamp: Snapshot timestamp (UTC)
        bids: Bid levels (highest first)
        asks: Ask levels (lowest first)
    """

    market_id: MarketId
    timestamp: Timestamp
    bids: tuple[OrderBookLevel, ...] = ()
    asks: tuple[OrderBookLevel, ...] = ()

    @property
    def best_bid(self) -> Price | None:
        """Get the best (highest) bid price."""
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Price | None:
        """Get the best (lowest) ask price."""
        return self.asks[0].price if self.asks else None

    @property
    def mid_price(self) -> Price | None:
        """Get the mid price ((best_bid + best_ask) / 2)."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2

    @property
    def spread(self) -> Price | None:
        """Get the spread (best_ask - best_bid)."""
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    @property
    def spread_pct(self) -> Decimal | None:
        """Get the spread percentage."""
        if self.spread is None or self.mid_price is None or self.mid_price == 0:
            return None
        return (self.spread / self.mid_price) * 100

    def bid_depth(self, levels: int = 10) -> Quantity:
        """Get total bid depth for top N levels."""
        return sum((level.quantity for level in self.bids[:levels]), Decimal("0"))

    def ask_depth(self, levels: int = 10) -> Quantity:
        """Get total ask depth for top N levels."""
        return sum((level.quantity for level in self.asks[:levels]), Decimal("0"))


@dataclass(frozen=True)
class Ticker:
    """
    Current market ticker.

    Attributes:
        market_id: Market identifier
        timestamp: Ticker timestamp (UTC)
        last_price: Last traded price
        bid_price: Best bid price
        ask_price: Best ask price
        volume_24h: 24-hour volume (base currency)
        quote_volume_24h: 24-hour volume (quote currency)
        high_24h: 24-hour high
        low_24h: 24-hour low
        price_change_24h: 24-hour price change
        price_change_pct_24h: 24-hour price change percentage
    """

    market_id: MarketId
    timestamp: Timestamp
    last_price: Price
    bid_price: Price | None = None
    ask_price: Price | None = None
    volume_24h: Quantity = Decimal("0")
    quote_volume_24h: Quantity = Decimal("0")
    high_24h: Price | None = None
    low_24h: Price | None = None
    price_change_24h: Price | None = None
    price_change_pct_24h: Decimal | None = None

    @property
    def mid_price(self) -> Price | None:
        """Get the mid price."""
        if self.bid_price is None or self.ask_price is None:
            return self.last_price
        return (self.bid_price + self.ask_price) / 2

    @property
    def spread(self) -> Price | None:
        """Get the spread."""
        if self.bid_price is None or self.ask_price is None:
            return None
        return self.ask_price - self.bid_price


@dataclass
class MarketState:
    """
    Aggregated market state for strategy decisions.

    This is the output of market intelligence,
    combining multiple data sources.

    Attributes:
        market_id: Market identifier
        timestamp: State timestamp (UTC)
        ticker: Current ticker
        order_book: Current order book
        volatility_pct: Current volatility percentage
        atr: Average True Range
        liquidity_score: Liquidity score (0-1)
        momentum_score: Momentum score (-1 to 1)
        regime: Detected market regime
        data_quality: Data quality flags
    """

    market_id: MarketId
    timestamp: Timestamp = field(default_factory=lambda: datetime.now(UTC))
    ticker: Ticker | None = None
    order_book: OrderBook | None = None
    volatility_pct: Decimal | None = None
    atr: Decimal | None = None
    liquidity_score: Decimal | None = None
    momentum_score: Decimal | None = None
    regime: str | None = None
    data_quality: dict[str, bool] = field(default_factory=dict)

    @property
    def current_price(self) -> Price | None:
        """Get the current price."""
        if self.ticker:
            return self.ticker.last_price
        return None

    @property
    def is_data_complete(self) -> bool:
        """Check if all required data is available."""
        return all(self.data_quality.values()) if self.data_quality else False
