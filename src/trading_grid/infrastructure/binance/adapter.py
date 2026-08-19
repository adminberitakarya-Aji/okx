"""
Binance Exchange Adapter.

This module provides the Binance adapter that:
- Combines REST and WebSocket clients
- Maps Binance responses to domain models
- Converts between normalized market IDs ("BTC-USDT") and Binance symbols ("BTCUSDT")
- Handles reconciliation after disconnects
- Implements the exchange-agnostic ExchangeAdapter interface

Security rules:
1. Reconciliation required after any disconnect
2. Ambiguous order state → reconcile before retry
3. Testnet and Live use separate credentials

Known limitations (documented per domain rule "Assuming demo = live behavior"):
- Spot positions are derived from account balances (Binance has no spot
  positions endpoint). average_entry_price is not available from balances
  and defaults to 0.
- get_fills(market_id=None) returns an empty list because Binance's
  myTrades endpoint requires a symbol. Always pass market_id.
"""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from trading_grid.config.settings import BinanceSettings
from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.domain.execution.models import Fill, Order, Position
from trading_grid.domain.market.models import Candle, Market, OrderBook, OrderBookLevel, Ticker
from trading_grid.domain.shared.types import ExchangeId, ExecutionMode, MarketId
from trading_grid.infrastructure.binance.rest_client import BinanceAPIError, BinanceRestClient
from trading_grid.infrastructure.binance.websocket_client import BinanceWebSocketClient
from trading_grid.domain.market.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)

logger = structlog.get_logger()

# Binance order status → normalized OrderStatus
_BINANCE_STATUS_MAP = {
    "NEW": "SUBMITTED",
    "PARTIALLY_FILLED": "PARTIALLY_FILLED",
    "FILLED": "FILLED",
    "CANCELED": "CANCELLED",
    "PENDING_CANCEL": "SUBMITTED",
    "REJECTED": "REJECTED",
    "EXPIRED": "CANCELLED",
}


class BinanceAdapter(ExchangeAdapter):
    """
    Binance Exchange Adapter.

    Implements the exchange-agnostic ExchangeAdapter interface for Binance Spot.

    Provides unified interface for:
    - Market data queries
    - Account queries
    - Order placement and management
    - Real-time updates via WebSocket
    - Reconciliation after disconnects
    """

    def __init__(self, settings: BinanceSettings, default_quote_currency: str = "USDT") -> None:
        """
        Initialize Binance adapter.

        Args:
            settings: Binance API settings
            default_quote_currency: [I-M6] Default quote currency for balance-derived
                positions. Binance spot has no positions endpoint, so positions are
                derived from balances. The actual trading pair quote currency is not
                available from balances alone; this parameter provides a configurable
                default instead of hardcoding "USDT".
        """
        self._settings = settings
        self._default_quote_currency = default_quote_currency
        self._rest = BinanceRestClient(settings)
        self._public_ws: BinanceWebSocketClient | None = None
        self._private_ws: BinanceWebSocketClient | None = None
        self._public_ws_task: asyncio.Task[None] | None = None
        self._private_ws_task: asyncio.Task[None] | None = None
        self._needs_reconciliation = False
        self._order_update_handlers: list[Callable[[dict[str, Any]], None]] = []
        self._ticker_handlers: list[Callable[[dict[str, Any]], None]] = []
        # Cache of base_asset -> quote_currency from exchange info (populated lazily)
        self._quote_currency_map: dict[str, str] = {}

    @property
    def exchange_id(self) -> ExchangeId:
        """Get the exchange identifier."""
        return "BINANCE"

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
        """Connect to Binance (REST is stateless, WebSocket connects)."""
        logger.info("binance_adapter_connecting", mode=self.mode)

    async def disconnect(self) -> None:
        """Disconnect from Binance."""
        if self._public_ws:
            await self._public_ws.disconnect()
        if self._public_ws_task and not self._public_ws_task.done():
            self._public_ws_task.cancel()
        if self._private_ws:
            await self._private_ws.disconnect()
        if self._private_ws_task and not self._private_ws_task.done():
            self._private_ws_task.cancel()
        await self._rest.close()
        logger.info("binance_adapter_disconnected")

    async def start_market_data_ws(
        self, market_ids: list[MarketId] | None = None
    ) -> None:
        """
        Start public WebSocket for market data.

        Args:
            market_ids: Optional list of market IDs to subscribe immediately
                (e.g., ["BTC-USDT", "ETH-USDT"]). If provided, ticker and
                1H kline streams are subscribed for each market after the
                connection is established.

        [NEW-CR-1] Without market_ids, only the connection is opened but no
        subscriptions are made. Call subscribe_market_ids() to subscribe
        markets at a later time.
        """
        if self._public_ws is None:
            self._public_ws = BinanceWebSocketClient(self._settings, private=False)
            self._public_ws.on_message(self._handle_public_message)
            self._public_ws.on_disconnect(self._handle_disconnect)
        if self._public_ws_task is None or self._public_ws_task.done():
            self._public_ws_task = asyncio.create_task(self._public_ws.connect())

        # [NEW-CR-1] Wait for connection then subscribe to streams
        if market_ids:
            await self._public_ws._wait_for_connected()
            await self.subscribe_market_ids(market_ids)

    async def subscribe_market_ids(self, market_ids: list[MarketId]) -> None:
        """
        [NEW-CR-1] Subscribe to ticker and 1H kline streams for given markets.

        Sends a single SUBSCRIBE message with all streams. The WS client
        tracks them for automatic re-subscription after reconnect.

        Args:
            market_ids: List of market IDs, e.g. ["BTC-USDT", "ETH-USDT"]
        """
        if self._public_ws is None:
            raise RuntimeError(
                "Public WebSocket not initialized. Call start_market_data_ws() first."
            )
        await self._public_ws._wait_for_connected()
        streams: list[str] = []
        for mid in market_ids:
            symbol = to_concatenated_symbol(mid).lower()
            streams.append(f"{symbol}@ticker")
            streams.append(f"{symbol}@kline_1h")
        await self._public_ws.subscribe(streams)
        logger.info("binance_subscribed_market_data", markets=len(market_ids))

    async def start_private_ws(self) -> None:
        """Start private WebSocket for order updates (user data stream)."""
        if self._private_ws is None:
            self._private_ws = BinanceWebSocketClient(self._settings, private=True)
            self._private_ws.on_message(self._handle_private_message)
            self._private_ws.on_disconnect(self._handle_disconnect)
        if self._private_ws_task is None or self._private_ws_task.done():
            self._private_ws_task = asyncio.create_task(self._private_ws.connect())

    def _handle_disconnect(self) -> None:
        """Handle WebSocket disconnect - mark for reconciliation."""
        logger.warning("binance_ws_disconnected", needs_reconciliation=True)
        self._needs_reconciliation = True

    def _handle_public_message(self, data: dict[str, Any]) -> None:
        """Handle public WebSocket message (ticker events)."""
        event = data.get("e")
        if event == "24hrTicker":
            for handler in self._ticker_handlers:
                try:
                    handler(data)
                except Exception as e:
                    logger.error("binance_ticker_handler_error", error=str(e))

    def _handle_private_message(self, data: dict[str, Any]) -> None:
        """
        Handle user data stream message (execution reports).

        Normalizes Binance executionReport events into the common shape
        used by the application layer.
        """
        event = data.get("e")
        if event != "executionReport":
            return

        symbol = data.get("s", "")
        try:
            market_id = to_normalized_market_id(symbol) if symbol else ""
        except ValueError:
            market_id = symbol

        normalized = {
            "event": "order_update",
            "market_id": market_id,
            "exchange_order_id": str(data.get("i", "")),
            "client_order_id": data.get("c", ""),
            "status": _BINANCE_STATUS_MAP.get(data.get("X", ""), "SUBMITTED"),
            "filled_quantity": data.get("z", "0"),
            "average_price": data.get("Z") if data.get("Z") not in (None, "", "0") else None,
            "raw": data,
        }

        for handler in self._order_update_handlers:
            try:
                handler(normalized)
            except Exception as e:
                logger.error("binance_order_handler_error", error=str(e))

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
        data = await self._rest.get_exchange_info()
        markets = []

        for item in data.get("symbols", []):
            try:
                if item.get("status") != "TRADING":
                    continue
                symbol = item["symbol"]
                market_id = to_normalized_market_id(symbol)

                # Parse filters
                min_qty = Decimal("0.00000001")
                max_qty: Decimal | None = None
                lot_size = Decimal("0.00000001")
                tick_size = Decimal("0.00000001")
                min_notional: Decimal | None = None

                for f in item.get("filters", []):
                    filter_type = f.get("filterType")
                    if filter_type == "LOT_SIZE":
                        min_qty = Decimal(f.get("minQty", "0.00000001"))
                        max_qty_str = f.get("maxQty")
                        max_qty = Decimal(max_qty_str) if max_qty_str else None
                        lot_size = Decimal(f.get("stepSize", "0.00000001"))
                    elif filter_type == "PRICE_FILTER":
                        tick_size = Decimal(f.get("tickSize", "0.00000001"))
                    elif filter_type in ("MIN_NOTIONAL", "NOTIONAL"):
                        min_notional_str = f.get("minNotional") or f.get("notional")
                        if min_notional_str:
                            min_notional = Decimal(min_notional_str)

                market = Market(
                    market_id=market_id,
                    base_currency=item["baseAsset"],
                    quote_currency=item["quoteAsset"],
                    min_order_size=min_qty,
                    max_order_size=max_qty,
                    tick_size=tick_size,
                    lot_size=lot_size,
                    is_active=True,
                )
                # min_notional is informational; Market model uses min_order_size
                _ = min_notional
                markets.append(market)
            except (KeyError, ValueError) as e:
                logger.warning("binance_skip_instrument", symbol=item.get("symbol"), error=str(e))

        return markets

    async def get_ticker(self, market_id: MarketId) -> Ticker:
        """Get ticker for market. [D-M8] Returns normalized domain Ticker model."""
        symbol = to_concatenated_symbol(market_id)
        raw = await self._rest.get_ticker(symbol)
        return Ticker(
            market_id=market_id,
            timestamp=datetime.now(UTC),
            last_price=Decimal(str(raw.get("lastPrice") or "0")),
            bid_price=Decimal(str(raw["bidPrice"])) if raw.get("bidPrice") else None,
            ask_price=Decimal(str(raw["askPrice"])) if raw.get("askPrice") else None,
            volume_24h=Decimal(str(raw.get("volume") or "0")),
            quote_volume_24h=Decimal(str(raw.get("quoteVolume") or "0")),
            high_24h=Decimal(str(raw["highPrice"])) if raw.get("highPrice") else None,
        )

    async def get_orderbook(self, market_id: MarketId, depth: int = 20) -> OrderBook:
        """Get order book for market."""
        symbol = to_concatenated_symbol(market_id)
        data = await self._rest.get_orderbook(symbol, depth)

        bids = tuple(
            OrderBookLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in data.get("bids", [])
        )
        asks = tuple(
            OrderBookLevel(price=Decimal(price), quantity=Decimal(qty))
            for price, qty in data.get("asks", [])
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
        # Normalize interval: domain uses "1H", Binance uses "1h"
        binance_interval = interval.lower()
        data = await self._rest.get_candles(symbol, interval=binance_interval, limit=limit)

        candles = []
        for row in data:
            try:
                # Binance kline: [open_time, open, high, low, close, volume,
                #                 close_time, quote_volume, trades, ...]
                timestamp = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
                candle = Candle(
                    market_id=market_id,
                    timestamp=timestamp,
                    open=Decimal(row[1]),
                    high=Decimal(row[2]),
                    low=Decimal(row[3]),
                    close=Decimal(row[4]),
                    volume=Decimal(row[5]),
                    quote_volume=Decimal(row[7]),
                    trade_count=int(row[8]),
                )
                candles.append(candle)
            except (IndexError, ValueError) as e:
                logger.warning("binance_skip_candle", error=str(e))

        return candles

    # =========================================================================
    # Account
    # =========================================================================

    async def get_balance(self, currency: str | None = None) -> dict[str, Decimal]:
        """Get account balances."""
        data = await self._rest.get_account()
        balances: dict[str, Decimal] = {}

        for item in data.get("balances", []):
            ccy = item.get("asset", "")
            free = Decimal(item.get("free", "0") or "0")
            locked = Decimal(item.get("locked", "0") or "0")
            total = free + locked
            if total > 0 and (currency is None or ccy == currency):
                balances[ccy] = total

        return balances

    async def _ensure_quote_currency_map(self) -> None:
        """
        [I-M6] Lazily populate the base_asset -> quote_currency map from exchange info.

        This allows get_positions() to use the actual quote currency for each
        asset instead of hardcoding "USDT".
        """
        if self._quote_currency_map:
            return
        try:
            data = await self._rest.get_exchange_info()
            for item in data.get("symbols", []):
                if item.get("status") == "TRADING":
                    base = item.get("baseAsset", "")
                    quote = item.get("quoteAsset", "")
                    if base and quote and base not in self._quote_currency_map:
                        self._quote_currency_map[base] = quote
        except Exception as e:
            logger.warning("binance_quote_map_populate_failed", error=str(e))

    async def get_positions(self) -> list[Position]:
        """
        Get current spot positions.

        Binance spot has no positions endpoint — positions are derived from
        account balances. Average entry price is NOT available from balances
        and defaults to 0 (documented limitation).

        [I-M6] The quote currency for each position is resolved dynamically
        from exchange info instead of hardcoding "USDT". Falls back to
        the configured default_quote_currency if the asset is not found.
        """
        await self._ensure_quote_currency_map()
        data = await self._rest.get_account()
        positions = []

        # Determine quote assets to exclude (they are not positions)
        quote_assets = {"USDT", "USDC", "BUSD", "FDUSD", "TUSD", "DAI", "BTC", "ETH", "BNB", "EUR"}

        for item in data.get("balances", []):
            try:
                asset = item.get("asset", "")
                free = Decimal(item.get("free", "0") or "0")
                locked = Decimal(item.get("locked", "0") or "0")
                qty = free + locked

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
                logger.warning("binance_skip_position", error=str(e))

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
            BinanceAPIError: If order placement fails
        """
        symbol = to_concatenated_symbol(order.market_id)

        logger.info(
            "binance_placing_order",
            order_id=order.order_id,
            market_id=order.market_id,
            side=order.side,
            quantity=str(order.quantity),
            mode=self.mode,
        )

        result = await self._rest.place_order(
            symbol=symbol,
            side=order.side,
            order_type=order.order_type,
            quantity=str(order.quantity),
            price=str(order.price) if order.price else None,
            new_client_order_id=order.order_id,
        )

        order_id_value = result.get("orderId")
        if order_id_value is None:
            raise BinanceAPIError(code="ORDER_FAILED", message="Order placement failed: no orderId")

        exchange_order_id = str(order_id_value)
        logger.info(
            "binance_order_placed",
            order_id=order.order_id,
            exchange_order_id=exchange_order_id,
        )
        return exchange_order_id

    async def cancel_order(self, market_id: MarketId, exchange_order_id: str) -> bool:
        """Cancel order."""
        try:
            symbol = to_concatenated_symbol(market_id)
            await self._rest.cancel_order(symbol, exchange_order_id)
            logger.info("binance_order_cancelled", exchange_order_id=exchange_order_id)
            return True
        except BinanceAPIError as e:
            logger.error("binance_cancel_failed", exchange_order_id=exchange_order_id, error=str(e))
            return False

    async def get_order_status(self, market_id: MarketId, exchange_order_id: str) -> dict[str, Any]:
        """
        Get NORMALIZED order status from Binance.

        Translates Binance-specific fields into the normalized shape defined
        by the ExchangeAdapter interface.
        """
        symbol = to_concatenated_symbol(market_id)
        raw = await self._rest.get_order(symbol, exchange_order_id)

        # Binance status: NEW, PARTIALLY_FILLED, FILLED, CANCELED, REJECTED, EXPIRED
        status = raw.get("status", "")
        avg_price = raw.get("avgPrice") or raw.get("price")

        return {
            "status": _BINANCE_STATUS_MAP.get(status, "SUBMITTED"),
            "filled_quantity": raw.get("executedQty", "0") or "0",
            "average_price": avg_price if avg_price not in (None, "", "0") else None,
            "raw": raw,
        }

    async def get_pending_orders(self) -> list[dict[str, Any]]:
        """Get all open orders."""
        return await self._rest.get_open_orders()

    async def get_fills(self, market_id: MarketId | None = None) -> list[Fill]:
        """
        Get recent fills.

        Note: Binance's myTrades endpoint requires a symbol. If market_id is
        None, returns an empty list (documented limitation).
        """
        if market_id is None:
            logger.warning("binance_get_fills_requires_market_id")
            return []

        symbol = to_concatenated_symbol(market_id)
        data = await self._rest.get_my_trades(symbol)
        fills = []

        for item in data:
            try:
                fill = Fill(
                    trade_id=str(item.get("id", "")),
                    order_id=str(item.get("orderId", "")),
                    market_id=market_id,
                    side="BUY" if item.get("isBuyer") else "SELL",
                    price=Decimal(item.get("price", "0")),
                    quantity=Decimal(item.get("qty", "0")),
                    fee=Decimal(item.get("commission", "0") or "0"),
                    fee_currency=item.get("commissionAsset", "USDT"),
                )
                fills.append(fill)
            except (KeyError, ValueError) as e:
                logger.warning("binance_skip_fill", error=str(e))

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
        logger.info("binance_starting_reconciliation", mode=self.mode)

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

        logger.info("binance_reconciliation_complete", **result)
        return result
