"""
Bybit Exchange Adapter.

This module provides the Bybit adapter that:
- Combines REST and WebSocket clients (API v5)
- Maps Bybit responses to domain models
- Converts between normalized market IDs ("BTC-USDT") and Bybit symbols ("BTCUSDT")
- Handles reconciliation after disconnects
- Implements the exchange-agnostic ExchangeAdapter interface

Security rules:
1. Reconciliation required after any disconnect
2. Ambiguous order state → reconcile before retry
3. Testnet and Live use separate credentials

Known limitations (documented per domain rule "Assuming demo = live behavior"):
- Spot positions are derived from wallet balances (Bybit spot has no
  positions endpoint). average_entry_price is not available from balances
  and defaults to 0.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from trading_grid.config.settings import BybitSettings
from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.domain.execution.models import Fill, Order, Position
from trading_grid.domain.market.models import Candle, Market, OrderBook, OrderBookLevel, Ticker
from trading_grid.domain.shared.types import ExchangeId, ExecutionMode, MarketId
from trading_grid.infrastructure.bybit.rest_client import BybitAPIError, BybitRestClient
from trading_grid.infrastructure.bybit.websocket_client import BybitWebSocketClient
from trading_grid.infrastructure.exchange.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)

logger = structlog.get_logger()

# Bybit order status → normalized OrderStatus
_BYBIT_STATUS_MAP = {
    "New": "SUBMITTED",
    "PartiallyFilled": "PARTIALLY_FILLED",
    "Filled": "FILLED",
    "Cancelled": "CANCELLED",
    "Rejected": "REJECTED",
    "Deactivated": "CANCELLED",
    "Untriggered": "SUBMITTED",
    "Triggered": "SUBMITTED",
}

# Domain interval → Bybit interval (minutes as string)
_INTERVAL_MAP = {
    "1M": "1",
    "3M": "3",
    "5M": "5",
    "15M": "15",
    "30M": "30",
    "1H": "60",
    "2H": "120",
    "4H": "240",
    "6H": "360",
    "12H": "720",
    "1D": "D",
    "1W": "W",
}


class BybitAdapter(ExchangeAdapter):
    """
    Bybit Exchange Adapter.

    Implements the exchange-agnostic ExchangeAdapter interface for Bybit Spot (API v5).

    Provides unified interface for:
    - Market data queries
    - Account queries
    - Order placement and management
    - Real-time updates via WebSocket
    - Reconciliation after disconnects
    """

    def __init__(self, settings: BybitSettings, default_quote_currency: str = "USDT") -> None:
        """
        Initialize Bybit adapter.

        Args:
            settings: Bybit API settings
            default_quote_currency: [I-M6] Default quote currency for balance-derived
                positions. Bybit spot has no positions endpoint, so positions are
                derived from wallet balances. The actual trading pair quote currency
                is not available from balances alone; this parameter provides a
                configurable default instead of hardcoding "USDT".
        """
        self._settings = settings
        self._default_quote_currency = default_quote_currency
        self._rest = BybitRestClient(settings)
        self._public_ws: BybitWebSocketClient | None = None
        self._private_ws: BybitWebSocketClient | None = None
        self._public_ws_task: asyncio.Task[None] | None = None
        self._private_ws_task: asyncio.Task[None] | None = None
        self._needs_reconciliation = False
        self._order_update_handlers: list[Callable[[dict[str, Any]], None]] = []
        self._ticker_handlers: list[Callable[[dict[str, Any]], None]] = []
        # Cache of base_asset -> quote_currency from instruments (populated lazily)
        self._quote_currency_map: dict[str, str] = {}

    @property
    def exchange_id(self) -> ExchangeId:
        """Get the exchange identifier."""
        return "BYBIT"

    @property
    def mode(self) -> ExecutionMode:
        """Get execution mode based on testnet setting."""
        return "DEMO" if self._settings.testnet_mode else "LIVE"

    @property
    def needs_reconciliation(self) -> bool:
        """Check if reconciliation is needed after disconnect."""
        return self._needs_reconciliation

    # =========================================================================
    # Connection management
    # =========================================================================

    async def connect(self) -> None:
        """Connect to Bybit (REST is stateless, WebSocket connects)."""
        logger.info("bybit_adapter_connecting", mode=self.mode)

    async def disconnect(self) -> None:
        """Disconnect from Bybit."""
        if self._public_ws:
            await self._public_ws.disconnect()
        if self._public_ws_task and not self._public_ws_task.done():
            self._public_ws_task.cancel()
        if self._private_ws:
            await self._private_ws.disconnect()
        if self._private_ws_task and not self._private_ws_task.done():
            self._private_ws_task.cancel()
        await self._rest.close()
        logger.info("bybit_adapter_disconnected")

    async def start_market_data_ws(self) -> None:
        """Start public WebSocket for market data."""
        if self._public_ws is None:
            self._public_ws = BybitWebSocketClient(self._settings, private=False)
            self._public_ws.on_message(self._handle_public_message)
            self._public_ws.on_disconnect(self._handle_disconnect)
        if self._public_ws_task is None or self._public_ws_task.done():
            self._public_ws_task = asyncio.create_task(self._public_ws.connect())

    async def start_private_ws(self) -> None:
        """Start private WebSocket for order updates."""
        if self._private_ws is None:
            self._private_ws = BybitWebSocketClient(self._settings, private=True)
            self._private_ws.on_message(self._handle_private_message)
            self._private_ws.on_disconnect(self._handle_disconnect)
        if self._private_ws_task is None or self._private_ws_task.done():
            self._private_ws_task = asyncio.create_task(self._private_ws.connect())

    def _handle_disconnect(self) -> None:
        """Handle WebSocket disconnect - mark for reconciliation."""
        logger.warning("bybit_ws_disconnected", needs_reconciliation=True)
        self._needs_reconciliation = True

    def _handle_public_message(self, data: dict[str, Any]) -> None:
        """Handle public WebSocket message (tickers)."""
        topic = data.get("topic", "")
        if topic.startswith("tickers."):
            for handler in self._ticker_handlers:
                try:
                    handler(data)
                except Exception as e:
                    logger.error("bybit_ticker_handler_error", error=str(e))

    def _handle_private_message(self, data: dict[str, Any]) -> None:
        """
        Handle private WebSocket message (order updates).

        Normalizes Bybit order events into the common shape used by the
        application layer.
        """
        topic = data.get("topic", "")
        if topic != "order":
            return

        for item in data.get("data", []):
            symbol = item.get("symbol", "")
            try:
                market_id = to_normalized_market_id(symbol) if symbol else ""
            except ValueError:
                market_id = symbol

            normalized = {
                "event": "order_update",
                "market_id": market_id,
                "exchange_order_id": item.get("orderId", ""),
                "client_order_id": item.get("orderLinkId", ""),
                "status": _BYBIT_STATUS_MAP.get(item.get("orderStatus", ""), "SUBMITTED"),
                "filled_quantity": item.get("cumExecQty", "0"),
                "average_price": item.get("avgPrice")
                if item.get("avgPrice") not in (None, "", "0")
                else None,
                "raw": item,
            }

            for handler in self._order_update_handlers:
                try:
                    handler(normalized)
                except Exception as e:
                    logger.error("bybit_order_handler_error", error=str(e))

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
        data = await self._rest.get_instruments(category="spot")
        markets = []

        for item in data.get("list", []):
            try:
                if item.get("status") != "Trading":
                    continue
                symbol = item["symbol"]
                market_id = to_normalized_market_id(symbol)

                market = Market(
                    market_id=market_id,
                    base_currency=item.get("baseCoin", ""),
                    quote_currency=item.get("quoteCoin", ""),
                    min_order_size=Decimal(
                        item.get("lotSizeFilter", {}).get("minOrderQty", "0.00000001")
                    ),
                    max_order_size=Decimal(item["lotSizeFilter"]["maxOrderQty"])
                    if item.get("lotSizeFilter", {}).get("maxOrderQty")
                    else None,
                    tick_size=Decimal(item.get("priceFilter", {}).get("tickSize", "0.00000001")),
                    lot_size=Decimal(item.get("lotSizeFilter", {}).get("qtyStep", "0.00000001")),
                    is_active=True,
                )
                markets.append(market)
            except (KeyError, ValueError) as e:
                logger.warning("bybit_skip_instrument", symbol=item.get("symbol"), error=str(e))

        return markets

    async def get_ticker(self, market_id: MarketId) -> Ticker:
        """Get ticker for market. [D-M8] Returns normalized domain Ticker model."""
        symbol = to_concatenated_symbol(market_id)
        data = await self._rest.get_ticker(symbol, category="spot")
        ticker_list = data.get("list", [])
        raw = ticker_list[0] if ticker_list else {}
        return Ticker(
            market_id=market_id,
            timestamp=datetime.now(UTC),
            last_price=Decimal(str(raw.get("lastPrice") or "0")),
            bid_price=Decimal(str(raw["bid1Price"])) if raw.get("bid1Price") else None,
            ask_price=Decimal(str(raw["ask1Price"])) if raw.get("ask1Price") else None,
            volume_24h=Decimal(str(raw.get("volume24h") or "0")),
            quote_volume_24h=Decimal(str(raw.get("turnover24h") or "0")),
            high_24h=Decimal(str(raw["highPrice24h"])) if raw.get("highPrice24h") else None,
        )

    async def get_orderbook(self, market_id: MarketId, depth: int = 20) -> OrderBook:
        """Get order book for market."""
        symbol = to_concatenated_symbol(market_id)
        data = await self._rest.get_orderbook(symbol, depth, category="spot")

        bids = tuple(
            OrderBookLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in data.get("b", [])
        )
        asks = tuple(
            OrderBookLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in data.get("a", [])
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
        symbol = to_concatenated_symbol(market_id)
        bybit_interval = _INTERVAL_MAP.get(interval.upper(), "60")
        data = await self._rest.get_candles(
            symbol, interval=bybit_interval, limit=limit, category="spot"
        )

        candles = []
        for row in data.get("list", []):
            try:
                # Bybit kline: [start, open, high, low, close, volume, turnover]
                timestamp = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
                candle = Candle(
                    market_id=market_id,
                    timestamp=timestamp,
                    open=Decimal(row[1]),
                    high=Decimal(row[2]),
                    low=Decimal(row[3]),
                    close=Decimal(row[4]),
                    volume=Decimal(row[5]),
                    quote_volume=Decimal(row[6]),
                )
                candles.append(candle)
            except (IndexError, ValueError) as e:
                logger.warning("bybit_skip_candle", error=str(e))

        # Bybit returns newest first — reverse to chronological order
        candles.reverse()
        return candles

    # =========================================================================
    # Account
    # =========================================================================

    async def get_balance(self, currency: str | None = None) -> dict[str, Decimal]:
        """Get account balances."""
        data = await self._rest.get_wallet_balance()
        balances: dict[str, Decimal] = {}

        for account in data.get("list", []):
            for coin in account.get("coin", []):
                ccy = coin.get("coin", "")
                wallet_balance = Decimal(coin.get("walletBalance", "0") or "0")
                if wallet_balance > 0 and (currency is None or ccy == currency):
                    balances[ccy] = wallet_balance

        return balances

    async def _ensure_quote_currency_map(self) -> None:
        """
        [I-M6] Lazily populate the base_asset -> quote_currency map from instruments.

        This allows get_positions() to use the actual quote currency for each
        asset instead of hardcoding "USDT".
        """
        if self._quote_currency_map:
            return
        try:
            data = await self._rest.get_instruments(category="spot")
            for item in data.get("list", []):
                if item.get("status") == "Trading":
                    base = item.get("baseCoin", "")
                    quote = item.get("quoteCoin", "")
                    if base and quote and base not in self._quote_currency_map:
                        self._quote_currency_map[base] = quote
        except Exception as e:
            logger.warning("bybit_quote_map_populate_failed", error=str(e))

    async def get_positions(self) -> list[Position]:
        """
        Get current spot positions.

        Bybit spot has no positions endpoint — positions are derived from
        wallet balances. Average entry price is NOT available from balances
        and defaults to 0 (documented limitation).

        [I-M6] The quote currency for each position is resolved dynamically
        from instruments instead of hardcoding "USDT". Falls back to
        the configured default_quote_currency if the asset is not found.
        """
        await self._ensure_quote_currency_map()
        data = await self._rest.get_wallet_balance()
        positions = []

        # Quote assets are not positions
        quote_assets = {"USDT", "USDC", "DAI", "BTC", "ETH", "EUR"}

        for account in data.get("list", []):
            for coin in account.get("coin", []):
                try:
                    asset = coin.get("coin", "")
                    qty = Decimal(coin.get("walletBalance", "0") or "0")

                    if qty > 0 and asset not in quote_assets:
                        # [I-M6] Resolve quote currency dynamically
                        quote_ccy = self._quote_currency_map.get(asset, self._default_quote_currency)
                        position = Position(
                            position_id=f"{asset}-spot",
                            market_id=f"{asset}-{quote_ccy}",
                            quantity=qty,
                            average_entry_price=Decimal("0"),
                        )
                        positions.append(position)
                except (KeyError, ValueError) as e:
                    logger.warning("bybit_skip_position", error=str(e))

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
            BybitAPIError: If order placement fails
        """
        symbol = to_concatenated_symbol(order.market_id)

        logger.info(
            "bybit_placing_order",
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            quantity=str(order.quantity),
            mode=self.mode,
        )

        # Bybit uses "Buy"/"Sell" and "Market"/"Limit"
        side = "Buy" if order.side == "BUY" else "Sell"
        order_type = "Market" if order.order_type == "MARKET" else "Limit"

        result = await self._rest.place_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            qty=str(order.quantity),
            price=str(order.price) if order.price else None,
            order_link_id=order.order_id,
            category="spot",
        )

        exchange_order_id = str(result.get("orderId", ""))
        if not exchange_order_id:
            raise BybitAPIError(code="ORDER_FAILED", message="Order placement failed: no orderId")

        logger.info(
            "bybit_order_placed",
            order_id=order.order_id,
            exchange_order_id=exchange_order_id,
        )
        return exchange_order_id

    async def cancel_order(self, market_id: MarketId, exchange_order_id: str) -> bool:
        """Cancel order."""
        try:
            symbol = to_concatenated_symbol(market_id)
            await self._rest.cancel_order(symbol, exchange_order_id, category="spot")
            logger.info("bybit_order_cancelled", exchange_order_id=exchange_order_id)
            return True
        except BybitAPIError as e:
            logger.error("bybit_cancel_failed", exchange_order_id=exchange_order_id, error=str(e))
            return False

    async def get_order_status(self, market_id: MarketId, exchange_order_id: str) -> dict[str, Any]:
        """
        Get NORMALIZED order status from Bybit.

        Translates Bybit-specific fields into the normalized shape defined
        by the ExchangeAdapter interface.
        """
        symbol = to_concatenated_symbol(market_id)
        raw = await self._rest.get_order(symbol, exchange_order_id, category="spot")

        # Bybit orderStatus: New, PartiallyFilled, Filled, Cancelled, Rejected, Deactivated
        status = raw.get("orderStatus", "")
        avg_price = raw.get("avgPrice")

        return {
            "status": _BYBIT_STATUS_MAP.get(status, "SUBMITTED"),
            "filled_quantity": raw.get("cumExecQty", "0") or "0",
            "average_price": avg_price if avg_price not in (None, "", "0") else None,
            "raw": raw,
        }

    async def get_pending_orders(self) -> list[dict[str, Any]]:
        """Get all open orders."""
        return await self._rest.get_open_orders(category="spot")

    async def get_fills(self, market_id: MarketId | None = None) -> list[Fill]:
        """Get recent fills."""
        symbol = to_concatenated_symbol(market_id) if market_id else None
        data = await self._rest.get_fills(symbol=symbol, category="spot")
        fills = []

        for item in data:
            try:
                fill_market_id = to_normalized_market_id(item.get("symbol", ""))
                fill = Fill(
                    trade_id=item.get("execId", ""),
                    order_id=item.get("orderId", ""),
                    market_id=fill_market_id,
                    side="BUY" if item.get("side") == "Buy" else "SELL",
                    price=Decimal(item.get("execPrice", "0")),
                    quantity=Decimal(item.get("execQty", "0")),
                    fee=Decimal(item.get("execFee", "0") or "0"),
                    fee_currency=item.get("feeCurrency", "USDT"),
                )
                fills.append(fill)
            except (KeyError, ValueError) as e:
                logger.warning("bybit_skip_fill", error=str(e))

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
        logger.info("bybit_starting_reconciliation", mode=self.mode)

        pending_orders = await self.get_pending_orders()
        positions = await self.get_positions()
        balances = await self.get_balance()

        self._needs_reconciliation = False

        result = {
            "pending_orders": len(pending_orders),
            "positions": len(positions),
            "balances": len(balances),
            "reconciled_at": datetime.now(UTC).isoformat(),
        }

        logger.info("bybit_reconciliation_complete", **result)
        return result
