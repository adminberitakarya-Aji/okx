"""
OKX Exchange Adapter.

This module provides the main adapter that:
- Combines REST and WebSocket clients
- Maps OKX responses to domain models
- Handles reconciliation after disconnects
- Provides unified interface for execution engine

Security rules:
1. Reconciliation required after any disconnect
2. Ambiguous order state → reconcile before retry
3. DEMO and LIVE use separate credentials
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from trading_grid.config.settings import OKXSettings
from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.domain.execution.models import Fill, Order, Position
from trading_grid.domain.market.models import Candle, Market, OrderBook, OrderBookLevel
from trading_grid.domain.shared.types import ExchangeId, ExecutionMode, MarketId
from trading_grid.infrastructure.okx.rest_client import OKXAPIError, OKXRestClient
from trading_grid.infrastructure.okx.websocket_client import OKXWebSocketClient

logger = structlog.get_logger()


class OKXAdapter(ExchangeAdapter):
    """
    OKX Exchange Adapter.

    Implements ExchangeAdapter interface for OKX API v5.
    """

    def __init__(self, settings: OKXSettings) -> None:
        """
        Initialize OKX adapter.

        Args:
            settings: OKX API settings
        """
        self._settings = settings
        self._rest = OKXRestClient(settings)
        self._public_ws: OKXWebSocketClient | None = None
        self._private_ws: OKXWebSocketClient | None = None
        self._public_ws_task: asyncio.Task[None] | None = None
        self._private_ws_task: asyncio.Task[None] | None = None
        self._needs_reconciliation = False
        self._order_update_handlers: list[Callable[[dict[str, Any]], None]] = []
        self._ticker_handlers: list[Callable[[dict[str, Any]], None]] = []

    @property
    def exchange_id(self) -> ExchangeId:
        """Get the exchange identifier."""
        return "OKX"

    @property
    def mode(self) -> ExecutionMode:
        """Get execution mode based on demo setting."""
        return "DEMO" if self._settings.demo_mode else "LIVE"

    @property
    def needs_reconciliation(self) -> bool:
        """Check if reconciliation is needed."""
        return self._needs_reconciliation

    # =========================================================================
    # Connection management
    # =========================================================================

    async def connect(self) -> None:
        """Connect to OKX."""
        logger.info("okx_adapter_connected", mode=self.mode)
        # WebSocket connections are started separately as needed

    async def disconnect(self) -> None:
        """Disconnect from OKX."""
        if self._public_ws:
            await self._public_ws.disconnect()
        if self._public_ws_task and not self._public_ws_task.done():
            self._public_ws_task.cancel()
        if self._private_ws:
            await self._private_ws.disconnect()
        if self._private_ws_task and not self._private_ws_task.done():
            self._private_ws_task.cancel()
        await self._rest.close()
        logger.info("okx_adapter_disconnected")

    async def start_market_data_ws(self) -> None:
        """Start public WebSocket for market data."""
        if self._public_ws is None:
            self._public_ws = OKXWebSocketClient(self._settings, private=False)
            self._public_ws.on_message(self._handle_public_message)
            self._public_ws.on_disconnect(self._handle_disconnect)
        if self._public_ws_task is None or self._public_ws_task.done():
            self._public_ws_task = asyncio.create_task(self._public_ws.connect())

    async def start_private_ws(self) -> None:
        """Start private WebSocket for order updates."""
        if self._private_ws is None:
            self._private_ws = OKXWebSocketClient(self._settings, private=True)
            self._private_ws.on_message(self._handle_private_message)
            self._private_ws.on_disconnect(self._handle_disconnect)
        if self._private_ws_task is None or self._private_ws_task.done():
            self._private_ws_task = asyncio.create_task(self._private_ws.connect())

    def _handle_disconnect(self) -> None:
        """Handle WebSocket disconnect - mark for reconciliation."""
        logger.warning("okx_ws_disconnected", needs_reconciliation=True)
        self._needs_reconciliation = True

    def _handle_public_message(self, data: dict[str, Any]) -> None:
        """Handle public WebSocket message."""
        arg = data.get("arg", {})
        channel = arg.get("channel")

        if channel == "tickers":
            for handler in self._ticker_handlers:
                try:
                    handler(data)
                except Exception as e:
                    logger.error("ticker_handler_error", error=str(e))

    def _handle_private_message(self, data: dict[str, Any]) -> None:
        """Handle private WebSocket message."""
        arg = data.get("arg", {})
        channel = arg.get("channel")

        if channel == "orders":
            for handler in self._order_update_handlers:
                try:
                    handler(data)
                except Exception as e:
                    logger.error("order_handler_error", error=str(e))

    def on_order_update(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register order update handler."""
        self._order_update_handlers.append(handler)

    def on_ticker(self, handler: Callable[[dict[str, Any]], None]) -> None:
        """Register ticker update handler."""
        self._ticker_handlers.append(handler)

    # =========================================================================
    # Market data
    # =========================================================================

    async def get_instruments(self) -> list[Market]:
        """Get available spot instruments."""
        data = await self._rest.get_instruments(inst_type="SPOT")
        markets = []
        for item in data:
            try:
                market = Market(
                    market_id=item["instId"],
                    base_currency=item["baseCcy"],
                    quote_currency=item["quoteCcy"],
                    min_order_size=Decimal(item.get("minSz", "0") or "0"),
                    max_order_size=Decimal(item.get("maxSz", "0")) if item.get("maxSz") else None,
                    tick_size=Decimal(item.get("tickSz", "0.01") or "0.01"),
                    lot_size=Decimal(item.get("lotSz", "0.000001") or "0.000001"),
                    is_active=item.get("state") == "live",
                )
                markets.append(market)
            except (KeyError, ValueError) as e:
                logger.warning("skip_instrument", inst_id=item.get("instId"), error=str(e))
        return markets

    async def get_ticker(self, market_id: MarketId) -> dict[str, Any]:
        """Get ticker for market."""
        return await self._rest.get_ticker(market_id)

    async def get_orderbook(self, market_id: MarketId, depth: int = 20) -> OrderBook:
        """Get order book for market."""
        from datetime import UTC, datetime

        data = await self._rest.get_orderbook(market_id, depth)

        bids = tuple(
            OrderBookLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty, *_ in data.get("bids", [])
        )
        asks = tuple(
            OrderBookLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty, *_ in data.get("asks", [])
        )

        return OrderBook(
            market_id=market_id,
            timestamp=datetime.now(UTC),
            bids=bids,
            asks=asks,
        )

    async def get_candles(
        self,
        market_id: MarketId,
        interval: str = "1H",
        limit: int = 100,
    ) -> list[Candle]:
        """Get candlestick data."""
        from datetime import UTC, datetime

        data = await self._rest.get_candles(market_id, bar=interval, limit=limit)
        candles = []
        for row in data:
            try:
                # OKX returns timestamp in milliseconds
                ts_ms = int(row[0])
                timestamp = datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
                candle = Candle(
                    market_id=market_id,
                    timestamp=timestamp,
                    open=Decimal(row[1]),
                    high=Decimal(row[2]),
                    low=Decimal(row[3]),
                    close=Decimal(row[4]),
                    volume=Decimal(row[5]),
                )
                candles.append(candle)
            except (IndexError, ValueError) as e:
                logger.warning("skip_candle", error=str(e))
        return candles

    # =========================================================================
    # Account
    # =========================================================================

    async def get_balance(self, currency: str | None = None) -> dict[str, Decimal]:
        """Get account balances."""
        data = await self._rest.get_account_balance(currency)
        balances: dict[str, Decimal] = {}

        for detail in data.get("details", []):
            ccy = detail.get("ccy", "")
            available = Decimal(detail.get("availBal", "0") or "0")
            frozen = Decimal(detail.get("frozenBal", "0") or "0")
            balances[ccy] = available + frozen

        return balances

    async def get_positions(self) -> list[Position]:
        """Get current positions."""
        data = await self._rest.get_positions(inst_type="SPOT")
        positions = []

        for item in data:
            try:
                qty = Decimal(item.get("pos", "0") or "0")
                if qty > 0:
                    position = Position(
                        position_id=f"{item['instId']}-spot",
                        market_id=item["instId"],
                        quantity=qty,
                        average_entry_price=Decimal(item.get("avgPx", "0") or "0"),
                    )
                    positions.append(position)
            except (KeyError, ValueError) as e:
                logger.warning("skip_position", error=str(e))

        return positions

    # =========================================================================
    # Order management
    # =========================================================================

    async def place_order(self, order: Order) -> str:
        """
        Place order on exchange.

        Args:
            order: Order to place

        Returns:
            Exchange order ID

        Raises:
            OKXAPIError: If order placement fails
        """
        logger.info(
            "placing_order",
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            quantity=str(order.quantity),
            mode=self.mode,
        )

        result = await self._rest.place_order(
            inst_id=order.market_id,
            side=order.side.lower(),
            ord_type=order.order_type.lower(),
            sz=str(order.quantity),
            px=str(order.price) if order.price else None,
            cl_ord_id=order.order_id,
        )

        exchange_order_id: str = result.get("ordId", "")
        if not exchange_order_id:
            error_msg = result.get("sMsg", "Order placement failed")
            raise OKXAPIError(code="ORDER_FAILED", message=error_msg)

        logger.info(
            "order_placed",
            order_id=order.order_id,
            exchange_order_id=exchange_order_id,
        )
        return exchange_order_id

    async def cancel_order(self, market_id: MarketId, exchange_order_id: str) -> bool:
        """Cancel order."""
        try:
            await self._rest.cancel_order(market_id, exchange_order_id)
            logger.info("order_cancelled", exchange_order_id=exchange_order_id)
            return True
        except OKXAPIError as e:
            logger.error("cancel_failed", exchange_order_id=exchange_order_id, error=str(e))
            return False

    async def get_order_status(self, market_id: MarketId, exchange_order_id: str) -> dict[str, Any]:
        """
        Get NORMALIZED order status from OKX.

        Translates OKX-specific fields into the normalized shape defined by
        the ExchangeAdapter interface:
        - "status": normalized OrderStatus string
        - "filled_quantity": str decimal filled quantity
        - "average_price": str decimal average fill price or None
        - "raw": original OKX payload
        """
        raw = await self._rest.get_order(market_id, exchange_order_id)

        # OKX state values: live, partially_filled, filled, canceled, mmp_canceled
        state = raw.get("state", "")
        status_map = {
            "live": "SUBMITTED",
            "partially_filled": "PARTIALLY_FILLED",
            "filled": "FILLED",
            "canceled": "CANCELLED",
            "cancelled": "CANCELLED",
            "mmp_canceled": "CANCELLED",
        }

        return {
            "status": status_map.get(state, "SUBMITTED"),
            "filled_quantity": raw.get("accFillSz", "0") or "0",
            "average_price": raw.get("avgPx") or None,
            "raw": raw,
        }

    async def get_pending_orders(self) -> list[dict[str, Any]]:
        """Get all pending orders."""
        return await self._rest.get_pending_orders()

    async def get_fills(self, market_id: MarketId | None = None) -> list[Fill]:
        """Get recent fills."""
        data = await self._rest.get_fills(inst_id=market_id)
        fills = []

        for item in data:
            try:
                fill = Fill(
                    trade_id=item.get("tradeId", ""),
                    order_id=item.get("clOrdId", item.get("ordId", "")),
                    market_id=item["instId"],
                    side="BUY" if item.get("side") == "buy" else "SELL",
                    price=Decimal(item.get("fillPx", "0")),
                    quantity=Decimal(item.get("fillSz", "0")),
                    fee=Decimal(item.get("fee", "0") or "0").copy_abs(),
                    fee_currency=item.get("feeCcy", "USDT"),
                )
                fills.append(fill)
            except (KeyError, ValueError) as e:
                logger.warning("skip_fill", error=str(e))

        return fills

    # =========================================================================
    # Reconciliation
    # =========================================================================

    async def reconcile(self) -> dict[str, Any]:
        """
        Reconcile local state with exchange state.

        Called after disconnect or when state is ambiguous.

        Returns:
            Reconciliation result summary
        """
        logger.info("starting_reconciliation", mode=self.mode)

        # Get pending orders from exchange
        pending_orders = await self.get_pending_orders()

        # Get positions from exchange
        positions = await self.get_positions()

        # Get balances
        balances = await self.get_balance()

        self._needs_reconciliation = False

        result = {
            "pending_orders": len(pending_orders),
            "positions": len(positions),
            "balances": len(balances),
            "reconciled_at": datetime.now(UTC).isoformat(),
        }

        logger.info("reconciliation_complete", **result)
        return result
