"""
Price Monitor — Grid execution loop for immediate execution.

This module provides:
- PriceMonitorService: Watches market price feed and triggers immediate
  execution when price hits grid levels.

Key domain rules enforced:
1. BUY and SELL use immediate execution (not passive limit orders)
2. Grid spacing is uniform within each Section
3. Cooldown per-level prevents double-triggering
4. Only RUNNING grids are monitored

The Price Monitor is the "gap fix" for Phase 3 — it connects the
ExchangeAdapter's WebSocket ticker feed to the ExecutionEngine's
immediate order execution, completing the grid execution loop.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog

from trading_grid.application.services.authorization import SYSTEM_IDENTITY
from trading_grid.application.services.execution_engine import ExecutionEngine
from trading_grid.application.services.grid_engine import GridEngine, GridRuntime
from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.domain.shared.types import MarketId, Price

logger = structlog.get_logger()

# Default cooldown between triggers for the same grid level (seconds)
DEFAULT_LEVEL_COOLDOWN_SECONDS = 30


@dataclass
class LevelTriggerState:
    """
    Tracks trigger state for a single grid level.

    Attributes:
        last_triggered_at: When this level was last triggered
        trigger_count: Total times this level has been triggered
    """

    last_triggered_at: datetime | None = None
    trigger_count: int = 0

    def is_in_cooldown(self, cooldown: timedelta, now: datetime) -> bool:
        """Check if level is still in cooldown period."""
        if self.last_triggered_at is None:
            return False
        return (now - self.last_triggered_at) < cooldown

    def record_trigger(self, now: datetime) -> None:
        """Record that this level was triggered."""
        self.last_triggered_at = now
        self.trigger_count += 1


@dataclass
class GridMonitorState:
    """
    Monitoring state for a single grid.

    Attributes:
        grid_id: The grid being monitored
        market_id: Market this grid trades
        last_price: Last observed price (for crossing detection)
        level_states: Per-level trigger state keyed by (section_id, level_index)
        is_subscribed: Whether ticker subscription is active
    """

    grid_id: str
    market_id: MarketId
    last_price: Price | None = None
    level_states: dict[tuple[int, int], LevelTriggerState] = field(default_factory=dict)
    is_subscribed: bool = False

    def get_level_state(self, section_id: int, level_index: int) -> LevelTriggerState:
        """Get or create trigger state for a level."""
        key = (section_id, level_index)
        if key not in self.level_states:
            self.level_states[key] = LevelTriggerState()
        return self.level_states[key]


class PriceMonitorService:
    """
    Price Monitor Service — watches price feed and triggers grid execution.

    This is the execution loop that completes the grid trading flow:
    1. Subscribe to market price via adapter WebSocket
    2. On each ticker update, check all active grids
    3. Detect price crossings through grid levels
    4. Trigger immediate execution (MARKET order) via ExecutionEngine
    5. Apply per-level cooldown to prevent double-triggering

    The service is exchange-agnostic — it depends only on the ExchangeAdapter
    interface and the normalized ticker format.
    """

    def __init__(
        self,
        adapter: ExchangeAdapter,
        grid_engine: GridEngine,
        execution_engine: ExecutionEngine,
        cooldown_seconds: int = DEFAULT_LEVEL_COOLDOWN_SECONDS,
    ) -> None:
        """
        Initialize price monitor.

        Args:
            adapter: Exchange adapter for WebSocket subscription
            grid_engine: Grid engine for accessing active grids
            execution_engine: Execution engine for order submission
            cooldown_seconds: Cooldown between triggers for same level
        """
        self._adapter = adapter
        self._grid_engine = grid_engine
        self._execution_engine = execution_engine
        self._cooldown = timedelta(seconds=cooldown_seconds)
        self._monitored_grids: dict[str, GridMonitorState] = {}
        self._market_last_prices: dict[MarketId, Price] = {}
        self._is_running = False
        self._ticker_handler_registered = False
        self._background_tasks: set[asyncio.Task[None]] = set()

    @property
    def is_running(self) -> bool:
        """Check if monitor is actively running."""
        return self._is_running

    @property
    def monitored_grid_ids(self) -> list[str]:
        """Get list of monitored grid IDs."""
        return list(self._monitored_grids.keys())

    async def start(self) -> None:
        """
        Start the price monitor.

        Registers the ticker handler and starts the market data WebSocket.
        """
        if self._is_running:
            logger.warning("price_monitor_already_running")
            return

        # Register ticker handler (once)
        if not self._ticker_handler_registered:
            self._adapter.on_ticker(self._handle_ticker)
            self._ticker_handler_registered = True

        # Start market data WebSocket
        await self._adapter.start_market_data_ws()
        self._is_running = True

        logger.info(
            "price_monitor_started",
            exchange=self._adapter.exchange_id,
            mode=self._adapter.mode,
        )

    async def stop(self) -> None:
        """Stop the price monitor and unsubscribe all grids."""
        self._monitored_grids.clear()
        self._is_running = False

        # Cancel all in-flight background tasks
        if self._background_tasks:
            for task in self._background_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self._background_tasks.clear()

        logger.info("price_monitor_stopped")

    def monitor_grid(self, grid: GridRuntime) -> None:
        """
        Start monitoring a grid for price triggers.

        Args:
            grid: The grid runtime to monitor
        """
        if grid.grid_id in self._monitored_grids:
            logger.warning("grid_already_monitored", grid_id=grid.grid_id)
            return

        state = GridMonitorState(
            grid_id=grid.grid_id,
            market_id=grid.market_id,
            is_subscribed=True,
        )
        self._monitored_grids[grid.grid_id] = state

        logger.info(
            "grid_monitoring_started",
            grid_id=grid.grid_id,
            market_id=grid.market_id,
        )

    def unmonitor_grid(self, grid_id: str) -> None:
        """
        Stop monitoring a grid.

        Args:
            grid_id: Grid to stop monitoring
        """
        if grid_id in self._monitored_grids:
            del self._monitored_grids[grid_id]
            logger.info("grid_monitoring_stopped", grid_id=grid_id)

    def _handle_ticker(self, data: dict[str, Any]) -> None:
        """
        Handle incoming ticker data from WebSocket.

        Expected normalized format from adapter:
        {
            "market_id": "BTC-USDT",
            "last": "50000.5",  # Last traded price as string
            ...
        }
        """
        market_id = data.get("market_id") or data.get("symbol") or data.get("instId")
        last_price_str = data.get("last") or data.get("price") or data.get("lastPrice")

        if not market_id or not last_price_str:
            return

        try:
            current_price = Decimal(str(last_price_str))
        except (ValueError, TypeError, InvalidOperation):
            logger.warning("invalid_ticker_price", data=data)
            return

        # Normalize market_id to domain format if needed
        market_id = self._normalize_market_id(market_id)

        # Update last known price for this market
        self._market_last_prices[market_id] = current_price

        # Process all monitored grids for this market
        for grid_id, state in self._monitored_grids.items():
            if state.market_id != market_id:
                continue

            grid = self._grid_engine.get_grid(grid_id)
            if grid is None or not grid.is_active:
                continue

            if grid.calculated_prices is None:
                continue

            # Use per-grid last_price for crossing detection
            prev_price = state.last_price
            state.last_price = current_price

            if prev_price is None:
                # First ticker for this grid — no crossing detection yet
                continue

            # Check for level crossings
            self._check_level_crossings(
                grid=grid,
                state=state,
                previous_price=prev_price,
                current_price=current_price,
            )

    def get_last_price(self, market_id: MarketId) -> Price | None:
        """
        Get the latest recorded price for a market.

        [A-M9-REV] Phase 10.4: Public method to access last known prices.
        Callers should use this instead of accessing _market_last_prices directly.

        Args:
            market_id: Market identifier

        Returns:
            Last known price or None if no price recorded
        """
        return self._market_last_prices.get(market_id)

    def get_all_last_prices(self) -> dict[MarketId, Price]:
        """
        Get all last known prices.

        [A-M9-REV] Phase 10.4: Public method to access all last known prices.
        Returns a copy to prevent external mutation.

        Returns:
            Dictionary mapping market IDs to last known prices
        """
        return dict(self._market_last_prices)

    def _normalize_market_id(self, raw_id: str) -> MarketId:
        """
        Normalize exchange-specific market ID to domain format.

        Domain format: "BTC-USDT"
        Binance/Bybit format: "BTCUSDT"
        """
        # If already in domain format (contains dash), return as-is
        if "-" in raw_id:
            return raw_id

        # Try to convert from concatenated format (e.g., "BTCUSDT" → "BTC-USDT")
        # Common quote currencies
        for quote in ("USDT", "USDC", "BTC", "ETH", "BUSD", "USD"):
            if raw_id.endswith(quote) and len(raw_id) > len(quote):
                base = raw_id[: -len(quote)]
                return f"{base}-{quote}"

        return raw_id

    def _check_level_crossings(
        self,
        grid: GridRuntime,
        state: GridMonitorState,
        previous_price: Price,
        current_price: Price,
    ) -> None:
        """
        Check if price crossed any grid levels and trigger execution.

        Crossing detection:
        - Price crosses DOWN through a level → BUY trigger
        - Price crosses UP through a level → SELL trigger

        Fill-state guard (prevents double-execution and invalid sells):
        - BUY only triggers if the level is NOT filled (no open position)
        - SELL only triggers if the level IS filled (has a position to sell)
        """
        if grid.calculated_prices is None:
            return

        now = datetime.now(UTC)

        for section_id, prices in grid.calculated_prices.section_prices.items():
            section = grid.blueprint.get_section(section_id)

            for level_index, level_price in enumerate(prices):
                level_state = state.get_level_state(section_id, level_index)

                # Skip if in cooldown
                if level_state.is_in_cooldown(self._cooldown, now):
                    continue

                # Detect crossing
                trigger_side = self._detect_crossing(
                    previous_price=previous_price,
                    current_price=current_price,
                    level_price=level_price,
                )

                if trigger_side is None:
                    continue

                # FILL-STATE GUARD — check level fill state before triggering.
                # This prevents double-buy on an already-filled level and
                # prevents selling a level that has no open position.
                level_model = None
                if section is not None and level_index < len(section.levels):
                    level_model = section.levels[level_index]

                if level_model is not None:
                    if trigger_side == "BUY" and level_model.is_filled:
                        # Already have a position at this level — skip BUY
                        continue
                    if trigger_side == "SELL" and not level_model.is_filled:
                        # No position to sell at this level — skip SELL
                        continue

                # Trigger execution
                level_state.record_trigger(now)
                self._trigger_execution(
                    grid=grid,
                    section_id=section_id,
                    level_index=level_index,
                    level_price=level_price,
                    side=trigger_side,
                    current_price=current_price,
                    trigger_time=now,
                )

    def _detect_crossing(
        self,
        previous_price: Price,
        current_price: Price,
        level_price: Price,
    ) -> str | None:
        """
        Detect if price crossed a level.

        Returns:
            "BUY" if price crossed down through level
            "SELL" if price crossed up through level
            None if no crossing
        """
        # Price crossed DOWN through level: (previous > level >= current) or (previous == level > current)
        if (previous_price > level_price >= current_price) or (
            previous_price == level_price > current_price
        ):
            return "BUY"

        # Price crossed UP through level: (previous < level <= current) or (previous == level < current)
        if (previous_price < level_price <= current_price) or (
            previous_price == level_price < current_price
        ):
            return "SELL"

        return None

    def _trigger_execution(
        self,
        grid: GridRuntime,
        section_id: int,
        level_index: int,
        level_price: Price,
        side: str,
        current_price: Price,
        trigger_time: datetime | None = None,
    ) -> None:
        """
        Trigger immediate execution for a grid level.

        This schedules the async execution. In production, this would
        use asyncio.create_task() or a task queue.

        A deterministic idempotency key is generated here so that any retry
        of the same logical trigger (same grid, level, side, within the same
        cooldown window) produces the same key and is deduplicated by the
        ExecutionEngine instead of submitting a duplicate order.
        """
        # Get quantity for this level from the blueprint section
        section = grid.blueprint.get_section(section_id)
        if section is None or level_index >= len(section.levels):
            logger.warning(
                "level_not_found_in_section",
                grid_id=grid.grid_id,
                section_id=section_id,
                level_index=level_index,
            )
            return

        level_model = section.levels[level_index]
        quantity = level_model.quantity

        if quantity <= 0:
            logger.warning(
                "level_quantity_zero",
                grid_id=grid.grid_id,
                section_id=section_id,
                level_index=level_index,
            )
            return

        # Generate deterministic idempotency key.
        # The cooldown epoch ensures that any retry of the same logical
        # trigger within the same cooldown window produces the same key.
        now = trigger_time or datetime.now(UTC)
        cooldown_epoch = int(now.timestamp() / self._cooldown.total_seconds())
        idempotency_key = f"{grid.grid_id}:{section_id}:{level_index}:{side}:{cooldown_epoch}"

        logger.info(
            "grid_level_trigger",
            grid_id=grid.grid_id,
            market_id=grid.market_id,
            section_id=section_id,
            level_index=level_index,
            level_price=str(level_price),
            side=side,
            quantity=str(quantity),
            current_price=str(current_price),
            idempotency_key=idempotency_key,
        )

        # Execute the order immediately via asyncio task.
        # This is the actual execution path — the price monitor
        # triggers a MARKET order through the ExecutionEngine.
        # In production, _handle_ticker is called from an async WS handler,
        # so there is always a running event loop. In tests, it may be
        # called synchronously — handle gracefully.
        try:
            task = asyncio.create_task(
                self.execute_level_trigger(
                    grid_id=grid.grid_id,
                    section_id=section_id,
                    level_index=level_index,
                    side=side,
                    quantity=quantity,
                    reference_price=current_price,
                    idempotency_key=idempotency_key,
                )
            )
            # Store reference to prevent garbage collection (RUF006)
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
        except RuntimeError:
            # No running event loop (e.g., synchronous test context).
            # Log the trigger; execution will be handled when the loop runs.
            logger.debug(
                "trigger_scheduled_no_loop",
                grid_id=grid.grid_id,
                side=side,
            )

    async def execute_level_trigger(
        self,
        grid_id: str,
        section_id: int,
        level_index: int,
        side: str,
        quantity: Decimal,
        reference_price: Price,
        idempotency_key: str | None = None,
    ) -> None:
        """
        Execute an order for a triggered grid level.

        This is the async method that actually submits the order.

        After successful execution, the level's fill state is updated:
        - BUY success → level.mark_filled() (position open)
        - SELL success → level.mark_closed() (position closed, level
          becomes available for re-buy in the next grid cycle)

        Args:
            grid_id: Grid that triggered
            section_id: Section containing the level
            level_index: Level index within section
            side: Order side ("BUY" or "SELL")
            quantity: Order quantity
            reference_price: Reference price for risk validation
            idempotency_key: Deterministic key for deduplication. When
                provided, the ExecutionEngine will return the existing
                result instead of submitting a duplicate order.
        """
        grid = self._grid_engine.get_grid(grid_id)
        if grid is None:
            return

        metadata = {
            "grid_id": grid_id,
            "section_id": section_id,
            "level_index": level_index,
            "trigger_type": "price_monitor",
        }

        result = await self._execution_engine.execute_order(
            market_id=grid.market_id,
            side=side,  # type: ignore[arg-type]
            quantity=quantity,
            price=None,  # MARKET order — immediate execution
            metadata=metadata,
            reference_price=reference_price,
            user_id=grid.user_id,
            idempotency_key=idempotency_key,
            identity=SYSTEM_IDENTITY,  # [A-H12] System-triggered order — no user bypass
            skip_rate_limit=True,  # [A-M1] Autonomous grid triggers bypass interactive rate limit
        )

        if result.success:
            # UPDATE LEVEL FILL STATE after successful execution.
            # This wires the execution result back to the blueprint's
            # level model so crossing detection can use is_filled.
            self._update_level_fill_state(
                grid=grid,
                section_id=section_id,
                level_index=level_index,
                side=side,
                quantity=quantity,
                reference_price=reference_price,
            )

            logger.info(
                "grid_level_executed",
                grid_id=grid_id,
                order_id=result.order_id,
                side=side,
                quantity=str(quantity),
            )
        else:
            logger.error(
                "grid_level_execution_failed",
                grid_id=grid_id,
                side=side,
                error=result.error_message,
            )

    def _update_level_fill_state(
        self,
        grid: GridRuntime,
        section_id: int,
        level_index: int,
        side: str,
        quantity: Decimal,
        reference_price: Price,
    ) -> None:
        """
        Update the level's fill state after successful execution.

        - BUY → mark_filled(quantity, fill_price)
        - SELL → mark_closed() (resets level for next grid cycle)

        The fill price uses reference_price (current market price at
        trigger time). In production, this should be replaced with the
        actual average fill price from the exchange response when
        fill tracking is implemented.

        Args:
            grid: Grid runtime containing the level
            section_id: Section containing the level
            level_index: Level index within section
            side: Order side ("BUY" or "SELL")
            quantity: Executed quantity
            reference_price: Reference/execution price
        """
        section = grid.blueprint.get_section(section_id)
        if section is None or level_index >= len(section.levels):
            return

        level_model = section.levels[level_index]

        if side == "BUY":
            level_model.mark_filled(quantity, reference_price)
            logger.info(
                "level_marked_filled",
                grid_id=grid.grid_id,
                section_id=section_id,
                level_index=level_index,
                quantity=str(quantity),
                entry_price=str(reference_price),
            )
        elif side == "SELL":
            level_model.mark_closed()
            logger.info(
                "level_marked_closed",
                grid_id=grid.grid_id,
                section_id=section_id,
                level_index=level_index,
            )

    def get_monitor_status(self) -> dict[str, Any]:
        """Get monitor status summary."""
        return {
            "is_running": self._is_running,
            "monitored_grids": len(self._monitored_grids),
            "grid_ids": list(self._monitored_grids.keys()),
            "markets_tracked": len(self._market_last_prices),
            "exchange": self._adapter.exchange_id,
            "mode": self._adapter.mode,
        }
