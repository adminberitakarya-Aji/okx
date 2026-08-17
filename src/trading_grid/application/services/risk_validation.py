"""
Risk Validation Service — Deterministic risk limit enforcement.

This module wires the domain ``RiskLimits`` model into the real order
execution path. It provides:

- ``RiskValidationService``: Validates every order against deterministic
  risk limits BEFORE the order is submitted to the exchange.

Key domain rules enforced here:
1. All orders go through risk validation (deny-by-default).
2. Spot-only: no shorting — a SELL must be covered by an open position.
3. Maximum drawdown triggers an emergency stop (blocks new BUY orders).
4. Capital, exposure and concurrency limits are enforced deterministically.

The service is deterministic: the same inputs always produce the same
validation result. It never fetches future data and never double-counts
spread/slippage (those are modeled by the execution economics layer).
"""

from decimal import Decimal
from typing import Protocol

import structlog

from trading_grid.domain.execution.models import Position
from trading_grid.domain.risk.models import (
    PortfolioRisk,
    RiskLimits,
    RiskValidationResult,
    RiskViolation,
)
from trading_grid.domain.shared.types import MarketId, OrderSide

logger = structlog.get_logger()

_HUNDRED = Decimal("100")


class RiskSettingsLike(Protocol):
    """Structural type for config.settings.RiskSettings (duck-typed)."""

    max_capital_per_grid: Decimal
    max_total_capital: Decimal
    max_drawdown_pct: Decimal
    max_concurrent_grids: int
    max_position_pct: Decimal
    min_profitable_exit_pct: Decimal
    max_slippage_pct: Decimal
    max_execution_cost_pct: Decimal
    min_reserve_pct: Decimal
    max_exposure_pct: Decimal


class RiskValidationService:
    """
    Validates orders against deterministic risk limits.

    The service holds a ``RiskLimits`` configuration and a ``PortfolioRisk``
    snapshot. Callers update the portfolio snapshot as positions/equity change
    via :meth:`update_portfolio`. Every order must pass
    :meth:`validate_order` before being submitted to the exchange.
    """

    def __init__(
        self,
        limits: RiskLimits,
        portfolio: PortfolioRisk | None = None,
    ) -> None:
        """
        Initialize the risk validation service.

        Args:
            limits: The deterministic risk limits to enforce.
            portfolio: Current portfolio risk snapshot. If omitted, a
                conservative snapshot is created using ``max_total_capital``
                as the available capital.
        """
        self._limits = limits
        self._portfolio = portfolio or PortfolioRisk(
            total_capital=limits.max_total_capital,
            available_capital=limits.max_total_capital,
        )

    @property
    def limits(self) -> RiskLimits:
        """Get the enforced risk limits."""
        return self._limits

    @property
    def portfolio(self) -> PortfolioRisk:
        """Get the current portfolio risk snapshot."""
        return self._portfolio

    def update_portfolio(self, portfolio: PortfolioRisk) -> None:
        """
        Update the portfolio risk snapshot.

        Call this whenever positions, equity, drawdown or active grid count
        change so subsequent validations use current state.
        """
        self._portfolio = portfolio

    @classmethod
    def from_risk_settings(cls, risk_settings: RiskSettingsLike) -> "RiskValidationService":
        """
        Build a service from ``config.settings.RiskSettings``.

        Accepts the settings object structurally (duck-typed) to avoid a
        dependency from the application layer on the config layer's concrete
        type while still allowing convenient construction.
        """
        limits = RiskLimits(
            max_capital_per_grid=risk_settings.max_capital_per_grid,
            max_total_capital=risk_settings.max_total_capital,
            max_drawdown_pct=risk_settings.max_drawdown_pct,
            max_concurrent_grids=risk_settings.max_concurrent_grids,
            max_position_pct=risk_settings.max_position_pct,
            min_profitable_exit_pct=risk_settings.min_profitable_exit_pct,
            max_slippage_pct=risk_settings.max_slippage_pct,
            max_execution_cost_pct=risk_settings.max_execution_cost_pct,
            min_reserve_pct=risk_settings.min_reserve_pct,
            max_exposure_pct=risk_settings.max_exposure_pct,
        )
        return cls(limits=limits)

    def validate_order(
        self,
        market_id: MarketId,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal | None = None,
        reference_price: Decimal | None = None,
        positions: dict[str, Position] | None = None,
    ) -> RiskValidationResult:
        """
        Validate an order against the risk limits.

        Args:
            market_id: Market to trade.
            side: Order side (BUY/SELL).
            quantity: Order quantity (base currency).
            price: Limit price (None for market orders).
            reference_price: Estimated execution price used for notional
                calculations when ``price`` is None (market orders).
            positions: Current open positions keyed by market id, used to
                enforce the no-shorting rule for SELL orders.

        Returns:
            RiskValidationResult. ``is_passed`` is False if any limit is
            violated; the order MUST NOT be submitted in that case.
        """
        result = RiskValidationResult()
        limits = self._limits
        portfolio = self._portfolio

        if quantity <= 0:
            result.add_violation(
                RiskViolation(
                    rule="POSITIVE_QUANTITY",
                    message="Order quantity must be positive",
                    value=quantity,
                    severity="HIGH",
                )
            )
            return result

        estimated_price = price if price is not None else reference_price

        if side == "BUY":
            self._validate_buy(
                result=result,
                market_id=market_id,
                quantity=quantity,
                estimated_price=estimated_price,
                portfolio=portfolio,
                limits=limits,
            )
        else:  # SELL
            self._validate_sell(
                result=result,
                market_id=market_id,
                quantity=quantity,
                positions=positions,
            )

        if result.is_passed:
            logger.debug(
                "risk_validation_passed",
                market_id=market_id,
                side=side,
                quantity=str(quantity),
            )
        else:
            logger.warning(
                "risk_validation_failed",
                market_id=market_id,
                side=side,
                quantity=str(quantity),
                violations=[v.rule for v in result.violations],
            )

        return result

    def _validate_buy(
        self,
        *,
        result: RiskValidationResult,
        market_id: MarketId,
        quantity: Decimal,
        estimated_price: Decimal | None,
        portfolio: PortfolioRisk,
        limits: RiskLimits,
    ) -> None:
        """Apply BUY-side risk checks (opening new exposure)."""
        # Emergency stop: max drawdown blocks all new BUY orders.
        if portfolio.drawdown_pct >= limits.max_drawdown_pct:
            result.add_violation(
                RiskViolation(
                    rule="MAX_DRAWDOWN",
                    message=(
                        f"Max drawdown breached: {portfolio.drawdown_pct}% "
                        f"(limit {limits.max_drawdown_pct}%). New buys blocked."
                    ),
                    value=portfolio.drawdown_pct,
                    limit=limits.max_drawdown_pct,
                    severity="CRITICAL",
                )
            )

        # Concurrency limit: cap the number of active grids.
        if portfolio.active_grids >= limits.max_concurrent_grids:
            result.add_violation(
                RiskViolation(
                    rule="MAX_CONCURRENT_GRIDS",
                    message=(
                        f"Max concurrent grids reached: {portfolio.active_grids} "
                        f"(limit {limits.max_concurrent_grids})"
                    ),
                    value=portfolio.active_grids,
                    limit=limits.max_concurrent_grids,
                    severity="HIGH",
                )
            )

        # Notional-based checks require an estimated price.
        if estimated_price is None:
            result.add_warning(
                RiskViolation(
                    rule="MISSING_PRICE",
                    message=(
                        "No price/reference_price provided for BUY; "
                        "capital and exposure limits could not be verified."
                    ),
                    severity="MEDIUM",
                )
            )
            return

        order_notional = quantity * estimated_price

        # Capital per grid limit.
        if order_notional > limits.max_capital_per_grid:
            result.add_violation(
                RiskViolation(
                    rule="MAX_CAPITAL_PER_GRID",
                    message=(
                        f"Order notional {order_notional} exceeds max capital "
                        f"per grid {limits.max_capital_per_grid}"
                    ),
                    value=order_notional,
                    limit=limits.max_capital_per_grid,
                    severity="HIGH",
                )
            )

        # Total capital limit across all grids.
        projected_deployed = portfolio.deployed_capital + order_notional
        if projected_deployed > limits.max_total_capital:
            result.add_violation(
                RiskViolation(
                    rule="MAX_TOTAL_CAPITAL",
                    message=(
                        f"Projected deployed capital {projected_deployed} exceeds "
                        f"max total capital {limits.max_total_capital}"
                    ),
                    value=projected_deployed,
                    limit=limits.max_total_capital,
                    severity="HIGH",
                )
            )

        # Exposure limit as a percentage of total capital.
        if portfolio.total_capital > 0:
            max_exposure = portfolio.total_capital * limits.max_exposure_pct / _HUNDRED
            projected_exposure = portfolio.total_exposure + order_notional
            if projected_exposure > max_exposure:
                result.add_violation(
                    RiskViolation(
                        rule="MAX_EXPOSURE",
                        message=(
                            f"Projected exposure {projected_exposure} exceeds max "
                            f"exposure {max_exposure} "
                            f"({limits.max_exposure_pct}% of capital)"
                        ),
                        value=projected_exposure,
                        limit=max_exposure,
                        severity="HIGH",
                    )
                )

    def _validate_sell(
        self,
        *,
        result: RiskValidationResult,
        market_id: MarketId,
        quantity: Decimal,
        positions: dict[str, Position] | None,
    ) -> None:
        """Apply SELL-side risk checks (spot-only: no shorting)."""
        position = positions.get(market_id) if positions else None
        held_quantity = position.quantity if position is not None else Decimal("0")

        # Spot-only rule: cannot sell more than is held (no shorting).
        if quantity > held_quantity:
            result.add_violation(
                RiskViolation(
                    rule="NO_SHORTING",
                    message=(
                        f"Cannot sell {quantity} of {market_id}: only "
                        f"{held_quantity} held. Spot trading forbids shorting."
                    ),
                    value=quantity,
                    limit=held_quantity,
                    severity="HIGH",
                )
            )
