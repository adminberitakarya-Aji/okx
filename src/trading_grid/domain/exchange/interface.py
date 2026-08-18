"""
Exchange Adapter interface.

This module defines the abstract interface that every exchange adapter
(OKX, Binance, Bybit, ...) must implement. The application layer
(ExecutionEngine, GridEngine, DemoTradingService) depends ONLY on this
interface — never on a concrete exchange implementation.

Dependency rule:
    domain/exchange/ MUST NOT import from infrastructure/.
    Concrete adapters in infrastructure/<exchange>/ implement this protocol.

Key domain rules preserved by this interface:
1. Reconciliation required after any disconnect (needs_reconciliation)
2. Ambiguous order state → reconcile before retry
3. DEMO and LIVE use separate credentials (mode property)
4. Spot-only: adapters expose spot instruments/positions only
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from decimal import Decimal
from typing import Any

from trading_grid.domain.execution.models import Fill, Order, Position
from trading_grid.domain.market.models import Candle, Market, OrderBook
from trading_grid.domain.shared.types import ExchangeId, ExecutionMode, MarketId


class ExchangeAdapter(ABC):
    """
    Abstract exchange adapter interface.

    Provides the unified contract for:
    - Connection management
    - Market data queries
    - Account queries
    - Order placement and management
    - Real-time updates via WebSocket
    - Reconciliation after disconnects

    All market identifiers use the normalized domain format (e.g., "BTC-USDT").
    Concrete adapters are responsible for converting to/from the exchange's
    native symbol format (e.g., Binance/Bybit "BTCUSDT").
    """

    # =========================================================================
    # Identity & state
    # =========================================================================

    @property
    @abstractmethod
    def exchange_id(self) -> ExchangeId:
        """Get the exchange identifier (e.g., 'OKX', 'BINANCE', 'BYBIT')."""

    @property
    @abstractmethod
    def mode(self) -> ExecutionMode:
        """Get execution mode ('DEMO' or 'LIVE') based on configuration."""

    @property
    @abstractmethod
    def needs_reconciliation(self) -> bool:
        """Check if reconciliation is needed after disconnect."""

    # =========================================================================
    # Connection management
    # =========================================================================

    @abstractmethod
    async def connect(self) -> None:
        """Connect to the exchange (REST is typically stateless)."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect from the exchange (close REST session and WebSockets)."""

    @abstractmethod
    async def start_market_data_ws(self) -> None:
        """Start public WebSocket for market data."""

    @abstractmethod
    async def start_private_ws(self) -> None:
        """Start private WebSocket for order updates."""

    @abstractmethod
    def on_order_update(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Register order update handler (supports sync and async callables)."""

    @abstractmethod
    def on_ticker(self, handler: Callable[[dict[str, Any]], Any]) -> None:
        """Register ticker update handler (supports sync and async callables)."""

    # =========================================================================
    # Market data
    # =========================================================================

    @abstractmethod
    async def get_instruments(self) -> list[Market]:
        """Get available spot instruments."""

    @abstractmethod
    async def get_ticker(self, market_id: MarketId) -> dict[str, Any]:
        """Get ticker for market."""

    @abstractmethod
    async def get_orderbook(self, market_id: MarketId, depth: int = 20) -> OrderBook:
        """Get order book for market."""

    @abstractmethod
    async def get_candles(
        self,
        market_id: MarketId,
        interval: str = "1H",
        limit: int = 100,
    ) -> list[Candle]:
        """Get candlestick data."""

    # =========================================================================
    # Account
    # =========================================================================

    @abstractmethod
    async def get_balance(self, currency: str | None = None) -> dict[str, Decimal]:
        """Get account balances keyed by currency."""

    @abstractmethod
    async def get_positions(self) -> list[Position]:
        """Get current spot positions."""

    # =========================================================================
    # Order management
    # =========================================================================

    @abstractmethod
    async def place_order(self, order: Order) -> str:
        """
        Place order on exchange.

        Args:
            order: Order to place

        Returns:
            Exchange order ID

        Raises:
            ExchangeAPIError: If order placement fails (or subclass thereof)
        """

    @abstractmethod
    async def cancel_order(self, market_id: MarketId, exchange_order_id: str) -> bool:
        """Cancel order. Returns True if cancellation succeeded."""

    @abstractmethod
    async def get_order_status(self, market_id: MarketId, exchange_order_id: str) -> dict[str, Any]:
        """
        Get NORMALIZED order status from exchange.

        Concrete adapters MUST translate exchange-specific fields into this
        normalized shape so the application layer stays exchange-agnostic:

        Returns:
            dict with keys:
            - "status": OrderStatus string
              (one of SUBMITTED / PARTIALLY_FILLED / FILLED / CANCELLED / REJECTED)
            - "filled_quantity": str decimal of quantity filled so far (e.g. "0.5")
            - "average_price": str decimal average fill price, or None if unfilled
            - "raw": the original exchange payload (for debugging/audit only)
        """

    @abstractmethod
    async def get_pending_orders(self) -> list[dict[str, Any]]:
        """Get all pending/open orders."""

    @abstractmethod
    async def get_fills(self, market_id: MarketId | None = None) -> list[Fill]:
        """Get recent fills, optionally filtered by market."""

    # =========================================================================
    # Reconciliation
    # =========================================================================

    @abstractmethod
    async def reconcile(self) -> dict[str, Any]:
        """
        Reconcile local state with exchange state.

        MUST be called after any disconnect or when order state is ambiguous.

        Returns:
            Reconciliation result summary
        """
