"""
Deterministic Historical Grid Simulator.

Implements the AI Research Grid Simulator per AI_RESEARCH_GRID_SIMULATOR_SPEC.md.

This simulator answers:
> What would our actual Section-based, uniform-grid, adaptive-Section-Gap,
> immediate-execution Grid Strategy have done if applied to historical data?

Key principles:
- Deterministic: same inputs produce same outputs
- Immediate execution model (not passive limit orders)
- Spot-only: no shorting, no leverage
- Buy and sell costs modeled separately, never double-counted
- All events are logged and auditable
- OHLC ambiguity handled via explicit conservative intrabar policy
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

import structlog

from trading_grid.domain.grid.calculator import (
    calculate_grid_prices,
    calculate_section_capital,
)

if TYPE_CHECKING:
    from datetime import datetime

    from trading_grid.domain.grid.models import Blueprint, Section
    from trading_grid.domain.market.models import Candle
    from trading_grid.domain.shared.types import MarketId

logger = structlog.get_logger()

# Simulator version — bump when execution logic changes
SIMULATOR_VERSION = "1.0.0"
STRATEGY_RULE_VERSION = "1.0.0"
EXECUTION_MODEL_VERSION = "1.0.0"


class SectionState(StrEnum):
    """Section lifecycle states."""

    INACTIVE = "INACTIVE"
    ARMED = "ARMED"
    ACTIVE = "ACTIVE"
    PARTIALLY_DEPLOYED = "PARTIALLY_DEPLOYED"
    FULLY_DEPLOYED = "FULLY_DEPLOYED"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"


class GridLevelState(StrEnum):
    """Grid level lifecycle states."""

    INACTIVE = "INACTIVE"
    ELIGIBLE = "ELIGIBLE"
    TRIGGERED = "TRIGGERED"
    EXECUTED = "EXECUTED"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class EventType(StrEnum):
    """Simulation event types."""

    MARKET_UPDATE = "MARKET_UPDATE"
    SECTION_ACTIVATED = "SECTION_ACTIVATED"
    SECTION_TRANSITION = "SECTION_TRANSITION"
    GRID_TRIGGERED = "GRID_TRIGGERED"
    BUY_EXECUTED = "BUY_EXECUTED"
    SELL_EXECUTED = "SELL_EXECUTED"
    BUY_REJECTED = "BUY_REJECTED"
    SELL_REJECTED = "SELL_REJECTED"
    CAPITAL_RESERVED = "CAPITAL_RESERVED"
    CAPITAL_RELEASED = "CAPITAL_RELEASED"
    RISK_BLOCK = "RISK_BLOCK"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    CAPITAL_EXHAUSTED = "CAPITAL_EXHAUSTED"
    SIMULATION_TERMINATED = "SIMULATION_TERMINATED"


class TerminalCondition(StrEnum):
    """Simulation terminal conditions."""

    HORIZON_END = "HORIZON_END"
    CAPITAL_EXHAUSTED = "CAPITAL_EXHAUSTED"
    RISK_LIMIT_REACHED = "RISK_LIMIT_REACHED"
    STRATEGY_STOP = "STRATEGY_STOP"
    DATA_END = "DATA_END"
    INVALID_STATE = "INVALID_STATE"


class ScenarioMode(StrEnum):
    """Simulation scenario modes."""

    BASELINE = "BASELINE"
    STRESS = "STRESS"
    EXTREME = "EXTREME"


class IntrabarPolicy(StrEnum):
    """Intrabar price path policy for OHLC ambiguity resolution."""

    # Bullish candle: Open -> Low -> High -> Close
    # Bearish candle: Open -> High -> Low -> Close
    CONSERVATIVE_DIRECTIONAL = "CONSERVATIVE_DIRECTIONAL"


@dataclass
class SimulationConfig:
    """Configuration for a simulation run."""

    market_id: MarketId
    observation_timestamp: datetime
    simulation_horizon_candles: int
    starting_capital: Decimal
    starting_asset_balance: Decimal = Decimal("0")
    buy_fee_rate: float = 0.001
    sell_fee_rate: float = 0.001
    slippage_pct: float = 0.0
    scenario_mode: ScenarioMode = ScenarioMode.BASELINE
    intrabar_policy: IntrabarPolicy = IntrabarPolicy.CONSERVATIVE_DIRECTIONAL
    minimum_profit_requirement: Decimal = Decimal("0")
    valuation_method: str = "close"  # "close", "bid", "mid"

    # Stress multipliers
    stress_slippage_multiplier: float = 2.0
    extreme_slippage_multiplier: float = 4.0

    def effective_slippage(self) -> float:
        """Get effective slippage based on scenario mode."""
        if self.scenario_mode == ScenarioMode.STRESS:
            return self.slippage_pct * self.stress_slippage_multiplier
        if self.scenario_mode == ScenarioMode.EXTREME:
            return self.slippage_pct * self.extreme_slippage_multiplier
        return self.slippage_pct


@dataclass
class PositionLot:
    """A single BUY lot for lot-linked cycle tracking."""

    lot_id: int
    section_id: int
    grid_level: int
    buy_price: Decimal
    quantity: Decimal
    buy_fee: Decimal
    buy_slippage_cost: Decimal
    effective_buy_cost: Decimal
    target_sell_price: Decimal
    timestamp: datetime
    status: str = "OPEN"  # OPEN, SOLD
    sell_price: Decimal | None = None
    sell_fee: Decimal | None = None
    realized_pnl: Decimal | None = None


@dataclass
class SimulationEvent:
    """A single simulation event."""

    event_id: int
    timestamp: datetime
    event_type: EventType
    market_price: Decimal | None = None
    section_id: int | None = None
    grid_level: int | None = None
    action: str | None = None
    requested_quantity: Decimal | None = None
    executed_quantity: Decimal | None = None
    execution_price: Decimal | None = None
    fee: Decimal | None = None
    slippage_cost: Decimal | None = None
    capital_before: Decimal | None = None
    capital_after: Decimal | None = None
    asset_before: Decimal | None = None
    asset_after: Decimal | None = None
    realized_pnl: Decimal | None = None
    unrealized_pnl: Decimal | None = None
    reason: str | None = None


@dataclass
class SectionSimState:
    """Runtime state for a section during simulation."""

    section_id: int
    state: SectionState = SectionState.INACTIVE
    capital_allocated: Decimal = Decimal("0")
    capital_used: Decimal = Decimal("0")
    activation_timestamp: datetime | None = None
    activation_price: Decimal | None = None
    grid_states: dict[int, GridLevelState] = field(default_factory=dict)
    grid_prices: list[Decimal] = field(default_factory=list)


@dataclass
class SimulationResult:
    """Complete simulation result."""

    # Identity
    simulation_run_id: str
    market_id: str
    observation_timestamp: datetime
    blueprint_id: str
    simulator_version: str = SIMULATOR_VERSION
    strategy_rule_version: str = STRATEGY_RULE_VERSION
    execution_model_version: str = EXECUTION_MODEL_VERSION
    scenario_mode: ScenarioMode = ScenarioMode.BASELINE
    intrabar_policy: IntrabarPolicy = IntrabarPolicy.CONSERVATIVE_DIRECTIONAL

    # Initial state
    initial_capital: Decimal = Decimal("0")
    initial_asset_balance: Decimal = Decimal("0")

    # Final state
    final_quote_balance: Decimal = Decimal("0")
    final_asset_quantity: Decimal = Decimal("0")
    final_equity: Decimal = Decimal("0")

    # Performance
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    total_pnl: Decimal = Decimal("0")
    net_pnl_return_pct: float = 0.0
    max_drawdown: Decimal = Decimal("0")
    max_drawdown_pct: float = 0.0

    # Grid behavior
    total_buy_count: int = 0
    total_sell_count: int = 0
    total_buy_rejected: int = 0
    total_sell_rejected: int = 0
    completed_cycles: int = 0
    open_lots: int = 0
    total_fees_paid: Decimal = Decimal("0")
    total_slippage_cost: Decimal = Decimal("0")

    # Capital
    peak_capital_utilization: float = 0.0
    capital_exhausted: bool = False

    # Sections
    max_section_depth: int = 0
    sections_activated: int = 0

    # Coin accumulation
    coin_accumulated: Decimal = Decimal("0")
    average_acquisition_price: Decimal | None = None

    # Events
    events: list[SimulationEvent] = field(default_factory=list)

    # Terminal
    terminal_condition: TerminalCondition | None = None
    simulation_status: str = "PENDING"  # PENDING, COMPLETED, FAILED

    # Data quality
    candles_processed: int = 0
    data_granularity: str = "OHLC"

    def to_dict(self) -> dict[str, object]:
        """Convert to flat dictionary for storage/ML pipeline."""
        return {
            "simulation_run_id": self.simulation_run_id,
            "market_id": self.market_id,
            "observation_timestamp": self.observation_timestamp.isoformat(),
            "blueprint_id": self.blueprint_id,
            "simulator_version": self.simulator_version,
            "strategy_rule_version": self.strategy_rule_version,
            "execution_model_version": self.execution_model_version,
            "scenario_mode": self.scenario_mode.value,
            "intrabar_policy": self.intrabar_policy.value,
            "initial_capital": float(self.initial_capital),
            "initial_asset_balance": float(self.initial_asset_balance),
            "final_quote_balance": float(self.final_quote_balance),
            "final_asset_quantity": float(self.final_asset_quantity),
            "final_equity": float(self.final_equity),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "total_pnl": float(self.total_pnl),
            "net_pnl_return_pct": self.net_pnl_return_pct,
            "max_drawdown": float(self.max_drawdown),
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_buy_count": self.total_buy_count,
            "total_sell_count": self.total_sell_count,
            "total_buy_rejected": self.total_buy_rejected,
            "total_sell_rejected": self.total_sell_rejected,
            "completed_cycles": self.completed_cycles,
            "open_lots": self.open_lots,
            "total_fees_paid": float(self.total_fees_paid),
            "total_slippage_cost": float(self.total_slippage_cost),
            "peak_capital_utilization": self.peak_capital_utilization,
            "capital_exhausted": self.capital_exhausted,
            "max_section_depth": self.max_section_depth,
            "sections_activated": self.sections_activated,
            "coin_accumulated": float(self.coin_accumulated),
            "average_acquisition_price": (
                float(self.average_acquisition_price) if self.average_acquisition_price else None
            ),
            "terminal_condition": self.terminal_condition.value
            if self.terminal_condition
            else None,
            "simulation_status": self.simulation_status,
            "candles_processed": self.candles_processed,
            "data_granularity": self.data_granularity,
            "event_count": len(self.events),
        }


class GridSimulator:
    """
    Deterministic historical grid simulator.

    Processes historical candles through a Section-based grid strategy,
    modeling immediate execution with realistic economics.

    Usage:
        config = SimulationConfig(
            market_id="BTC-USDT",
            observation_timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            simulation_horizon_candles=100,
            starting_capital=Decimal("10000"),
        )
        simulator = GridSimulator(config)
        result = simulator.run(blueprint, candles)
    """

    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self._event_counter = 0
        self._lot_counter = 0

    def run(self, blueprint: Blueprint, candles: list[Candle]) -> SimulationResult:
        """
        Run a deterministic simulation.

        Args:
            blueprint: Validated candidate blueprint
            candles: Historical candles covering the simulation horizon

        Returns:
            SimulationResult with all events and metrics
        """
        # Initialize result
        result = SimulationResult(
            simulation_run_id=f"sim_{self.config.market_id}_{self.config.observation_timestamp.isoformat()}_{blueprint.blueprint_id}",
            market_id=self.config.market_id,
            observation_timestamp=self.config.observation_timestamp,
            blueprint_id=blueprint.blueprint_id,
            scenario_mode=self.config.scenario_mode,
            intrabar_policy=self.config.intrabar_policy,
            initial_capital=self.config.starting_capital,
            initial_asset_balance=self.config.starting_asset_balance,
        )

        # Initialize portfolio state
        quote_balance = self.config.starting_capital
        asset_quantity = self.config.starting_asset_balance
        realized_pnl = Decimal("0")
        total_fees = Decimal("0")
        total_slippage = Decimal("0")
        peak_equity = quote_balance + (
            asset_quantity * candles[0].open if candles else Decimal("0")
        )
        max_drawdown = Decimal("0")
        max_drawdown_pct = 0.0
        peak_utilization = 0.0

        # Compute all grid prices once (deterministic domain calculator)
        calculated_prices = calculate_grid_prices(blueprint, spacing_mode="geometric")

        # Initialize section states
        section_states: dict[int, SectionSimState] = {}
        for section in blueprint.sections:
            ss = SectionSimState(
                section_id=section.section_id,
                capital_allocated=self._section_capital(blueprint, section),
            )
            ss.grid_prices = calculated_prices.get_prices(section.section_id)
            for i in range(len(ss.grid_prices)):
                ss.grid_states[i] = GridLevelState.INACTIVE
            section_states[section.section_id] = ss

        # Position lots (lot-linked tracking)
        open_lots: list[PositionLot] = []

        # Track counters
        buy_count = 0
        sell_count = 0
        buy_rejected = 0
        sell_rejected = 0
        completed_cycles = 0
        max_section_depth = 0
        sections_activated = 0

        # Process candles
        prev_close: Decimal | None = None
        candles_processed = 0

        for candle in candles[: self.config.simulation_horizon_candles]:
            candles_processed += 1

            # Record market update event
            self._add_event(
                result,
                candle.timestamp,
                EventType.MARKET_UPDATE,
                market_price=candle.close,
            )

            # Determine intrabar price path
            price_path = self._get_price_path(candle)

            # Process each price point in the path
            for price in price_path:
                # Evaluate sections and grid levels
                for section in blueprint.sections:
                    ss = section_states[section.section_id]

                    # Check section activation
                    if ss.state == SectionState.INACTIVE and self._should_activate_section(
                        section, price, prev_close
                    ):
                        ss.state = SectionState.ACTIVE
                        ss.activation_timestamp = candle.timestamp
                        ss.activation_price = price
                        sections_activated += 1
                        depth = section.section_id
                        if depth > max_section_depth:
                            max_section_depth = depth
                        self._add_event(
                            result,
                            candle.timestamp,
                            EventType.SECTION_ACTIVATED,
                            market_price=price,
                            section_id=section.section_id,
                            reason="price_entered_section_range",
                        )

                    if ss.state not in (SectionState.ACTIVE, SectionState.PARTIALLY_DEPLOYED):
                        continue

                    # Evaluate grid levels
                    for level_idx, grid_price in enumerate(ss.grid_prices):
                        state = ss.grid_states.get(level_idx, GridLevelState.INACTIVE)

                        if state in (GridLevelState.EXECUTED, GridLevelState.COMPLETED):
                            continue

                        # BUY trigger: price crosses down through grid level
                        if prev_close is not None and prev_close > grid_price >= price:
                            # Check if we already have an open lot for this level
                            has_open_lot = any(
                                lot.section_id == section.section_id
                                and lot.grid_level == level_idx
                                and lot.status == "OPEN"
                                for lot in open_lots
                            )
                            if has_open_lot:
                                continue

                            # Execute BUY
                            capital_before = quote_balance
                            asset_before = asset_quantity

                            buy_result = self._execute_buy(
                                section, ss, level_idx, grid_price, price, quote_balance
                            )

                            if buy_result is not None:
                                qty, exec_price, fee, slip_cost, eff_cost = buy_result
                                quote_balance -= eff_cost
                                asset_quantity += qty
                                realized_pnl -= Decimal("0")  # BUY doesn't realize PnL
                                total_fees += fee
                                total_slippage += slip_cost
                                buy_count += 1

                                # Create lot
                                self._lot_counter += 1
                                target_sell = self._compute_target_sell(
                                    section, ss, level_idx, grid_price
                                )
                                lot = PositionLot(
                                    lot_id=self._lot_counter,
                                    section_id=section.section_id,
                                    grid_level=level_idx,
                                    buy_price=grid_price,
                                    quantity=qty,
                                    buy_fee=fee,
                                    buy_slippage_cost=slip_cost,
                                    effective_buy_cost=eff_cost,
                                    target_sell_price=target_sell,
                                    timestamp=candle.timestamp,
                                )
                                open_lots.append(lot)
                                ss.grid_states[level_idx] = GridLevelState.EXECUTED
                                ss.capital_used += eff_cost

                                self._add_event(
                                    result,
                                    candle.timestamp,
                                    EventType.BUY_EXECUTED,
                                    market_price=price,
                                    section_id=section.section_id,
                                    grid_level=level_idx,
                                    action="BUY",
                                    requested_quantity=qty,
                                    executed_quantity=qty,
                                    execution_price=exec_price,
                                    fee=fee,
                                    slippage_cost=slip_cost,
                                    capital_before=capital_before,
                                    capital_after=quote_balance,
                                    asset_before=asset_before,
                                    asset_after=asset_quantity,
                                )
                            else:
                                buy_rejected += 1
                                ss.grid_states[level_idx] = GridLevelState.BLOCKED
                                self._add_event(
                                    result,
                                    candle.timestamp,
                                    EventType.BUY_REJECTED,
                                    market_price=price,
                                    section_id=section.section_id,
                                    grid_level=level_idx,
                                    action="BUY",
                                    reason="insufficient_capital",
                                )

                        # SELL trigger: price crosses up through target sell price
                        elif prev_close is not None and prev_close < price:
                            # Find matching open lot for this section/level
                            matching_lot = None
                            for lot in open_lots:
                                if (
                                    lot.section_id == section.section_id
                                    and lot.grid_level == level_idx
                                    and lot.status == "OPEN"
                                    and price >= lot.target_sell_price
                                ):
                                    matching_lot = lot
                                    break

                            if matching_lot is not None:
                                # Check minimum profitable exit
                                sell_price_val = lot.target_sell_price
                                sell_proceeds = matching_lot.quantity * sell_price_val
                                sell_fee = sell_proceeds * Decimal(str(self.config.sell_fee_rate))
                                slippage = self.config.effective_slippage()
                                sell_slip_cost = sell_proceeds * Decimal(str(slippage))
                                net_proceeds = sell_proceeds - sell_fee - sell_slip_cost
                                lot_pnl = net_proceeds - matching_lot.effective_buy_cost

                                if lot_pnl < self.config.minimum_profit_requirement:
                                    continue  # SELL not economically valid

                                # Execute SELL
                                capital_before = quote_balance
                                asset_before = asset_quantity

                                quote_balance += net_proceeds
                                asset_quantity -= matching_lot.quantity
                                realized_pnl += lot_pnl
                                total_fees += sell_fee
                                total_slippage += sell_slip_cost
                                sell_count += 1
                                completed_cycles += 1

                                matching_lot.status = "SOLD"
                                matching_lot.sell_price = sell_price_val
                                matching_lot.sell_fee = sell_fee
                                matching_lot.realized_pnl = lot_pnl
                                ss.grid_states[level_idx] = GridLevelState.COMPLETED

                                self._add_event(
                                    result,
                                    candle.timestamp,
                                    EventType.SELL_EXECUTED,
                                    market_price=price,
                                    section_id=section.section_id,
                                    grid_level=level_idx,
                                    action="SELL",
                                    requested_quantity=matching_lot.quantity,
                                    executed_quantity=matching_lot.quantity,
                                    execution_price=sell_price_val,
                                    fee=sell_fee,
                                    slippage_cost=sell_slip_cost,
                                    capital_before=capital_before,
                                    capital_after=quote_balance,
                                    asset_before=asset_before,
                                    asset_after=asset_quantity,
                                    realized_pnl=lot_pnl,
                                )

            # Update equity and drawdown
            equity = quote_balance + asset_quantity * candle.close
            if equity > peak_equity:
                peak_equity = equity
            drawdown = peak_equity - equity
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                if peak_equity > 0:
                    max_drawdown_pct = float(drawdown / peak_equity)

            # Update capital utilization
            deployed = sum(lot.effective_buy_cost for lot in open_lots if lot.status == "OPEN")
            if self.config.starting_capital > 0:
                utilization = float(deployed / self.config.starting_capital)
                if utilization > peak_utilization:
                    peak_utilization = utilization

            prev_close = candle.close

        # Final valuation
        final_price = candles[-1].close if candles else Decimal("0")
        final_equity = quote_balance + asset_quantity * final_price

        # Unrealized PnL on open lots
        unrealized_pnl = Decimal("0")
        open_lot_count = 0
        for lot in open_lots:
            if lot.status == "OPEN":
                open_lot_count += 1
                current_value = lot.quantity * final_price
                unrealized_pnl += current_value - lot.effective_buy_cost

        total_pnl = realized_pnl + unrealized_pnl
        net_return = (
            float(total_pnl / self.config.starting_capital)
            if self.config.starting_capital > 0
            else 0.0
        )

        # Coin accumulation
        coin_accumulated = asset_quantity
        avg_acquisition: Decimal | None = None
        total_cost = sum(lot.effective_buy_cost for lot in open_lots if lot.status == "OPEN")
        if asset_quantity > 0 and total_cost > 0:
            avg_acquisition = total_cost / asset_quantity

        # Populate result
        result.final_quote_balance = quote_balance
        result.final_asset_quantity = asset_quantity
        result.final_equity = final_equity
        result.realized_pnl = realized_pnl
        result.unrealized_pnl = unrealized_pnl
        result.total_pnl = total_pnl
        result.net_pnl_return_pct = net_return
        result.max_drawdown = max_drawdown
        result.max_drawdown_pct = max_drawdown_pct
        result.total_buy_count = buy_count
        result.total_sell_count = sell_count
        result.total_buy_rejected = buy_rejected
        result.total_sell_rejected = sell_rejected
        result.completed_cycles = completed_cycles
        result.open_lots = open_lot_count
        result.total_fees_paid = total_fees
        result.total_slippage_cost = total_slippage
        result.peak_capital_utilization = peak_utilization
        result.capital_exhausted = quote_balance <= Decimal("0")
        result.max_section_depth = max_section_depth
        result.sections_activated = sections_activated
        result.coin_accumulated = coin_accumulated
        result.average_acquisition_price = avg_acquisition
        result.terminal_condition = TerminalCondition.HORIZON_END
        result.simulation_status = "COMPLETED"
        result.candles_processed = candles_processed

        self._add_event(
            result,
            candles[-1].timestamp if candles else self.config.observation_timestamp,
            EventType.SIMULATION_TERMINATED,
            reason=TerminalCondition.HORIZON_END.value,
        )

        return result

    def _section_capital(self, blueprint: Blueprint, section: Section) -> Decimal:
        """Calculate capital allocated to a section using domain calculator."""
        return calculate_section_capital(blueprint, section.section_id)

    def _get_price_path(self, candle: Candle) -> list[Decimal]:
        """
        Determine intrabar price path based on policy.

        Conservative directional policy:
        - Bullish (close >= open): Open -> Low -> High -> Close
        - Bearish (close < open): Open -> High -> Low -> Close
        """
        if candle.close >= candle.open:
            return [candle.open, candle.low, candle.high, candle.close]
        return [candle.open, candle.high, candle.low, candle.close]

    def _should_activate_section(
        self, section: Section, price: Decimal, prev_close: Decimal | None
    ) -> bool:
        """Check if price has entered the section range."""
        return section.lower_price <= price <= section.upper_price

    def _execute_buy(
        self,
        section: Section,
        ss: SectionSimState,
        level_idx: int,
        grid_price: Decimal,
        market_price: Decimal,
        available_capital: Decimal,
    ) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal] | None:
        """
        Execute a BUY at the grid level.

        Returns:
            (quantity, execution_price, fee, slippage_cost, effective_cost) or None if rejected
        """
        # Calculate order size from section capital allocation
        section_capital = ss.capital_allocated
        grid_count = len(ss.grid_prices)
        if grid_count == 0:
            return None

        capital_per_grid = section_capital / Decimal(grid_count)

        # Check available capital
        if capital_per_grid > available_capital:
            return None

        # Execution price: ask approximation with slippage
        slippage = Decimal(str(self.config.effective_slippage()))
        execution_price = grid_price * (1 + slippage)

        # Quantity
        if execution_price <= 0:
            return None
        quantity = capital_per_grid / execution_price

        # Costs
        buy_value = quantity * execution_price
        fee = buy_value * Decimal(str(self.config.buy_fee_rate))
        slippage_cost = quantity * (execution_price - grid_price)
        effective_cost = buy_value + fee

        if effective_cost > available_capital:
            return None

        return (quantity, execution_price, fee, slippage_cost, effective_cost)

    def _compute_target_sell(
        self, section: Section, ss: SectionSimState, level_idx: int, buy_price: Decimal
    ) -> Decimal:
        """
        Compute target sell price for a grid level.

        Default: one grid spacing above the buy price.
        """
        if level_idx > 0 and level_idx < len(ss.grid_prices):
            # Sell at the next grid level up
            return ss.grid_prices[level_idx - 1]
        # If at top level, sell at one spacing above
        if len(ss.grid_prices) >= 2:
            spacing = ss.grid_prices[0] - ss.grid_prices[1]
            return buy_price + spacing
        return buy_price * Decimal("1.01")  # fallback: 1% above

    def _add_event(
        self,
        result: SimulationResult,
        timestamp: datetime,
        event_type: EventType,
        **kwargs: object,
    ) -> None:
        """Add an event to the result."""
        self._event_counter += 1
        event = SimulationEvent(
            event_id=self._event_counter,
            timestamp=timestamp,
            event_type=event_type,
            **kwargs,  # type: ignore[arg-type]
        )
        result.events.append(event)
