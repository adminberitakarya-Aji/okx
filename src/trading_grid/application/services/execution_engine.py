"""
Execution Engine — Order management and execution.

This module provides:
- ExecutionEngine: Coordinates order execution
- Order tracking and state management
- Integration with any exchange adapter implementing ExchangeAdapter
  (OKX, Binance, Bybit)
- Reconciliation after disconnects

Key domain rules:
1. BUY and SELL use immediate execution (not passive limit orders)
2. All orders go through risk validation BEFORE submission (enforced here)
3. Ambiguous order state → reconcile before retry
4. Spot-only: no shorting, no leverage

IMPORTANT: The risk validation gate is mandatory and exchange-agnostic.
Every order must pass deterministic risk validation BEFORE it reaches any
exchange. Swapping the exchange adapter must never bypass or reorder this gate.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

import structlog

from trading_grid.application.services.authorization import (
    AuthorizationResult,
    Identity,
    PermissionLevel,
)
from trading_grid.application.services.risk_validation import RiskValidationService
from trading_grid.application.services.tenant_limits import (
    MaxGridsExceededError,
    RateLimitExceededError,
    TenantLimitsService,
    UserEmergencyStoppedError,
)
from trading_grid.domain.exchange.errors import ExchangeAPIError
from trading_grid.domain.exchange.interface import ExchangeAdapter
from trading_grid.domain.execution.models import Fill, Order, Position
from trading_grid.domain.shared.types import ExecutionMode, MarketId, OrderId, OrderSide

logger = structlog.get_logger()


@dataclass
class ExecutionResult:
    """
    Result of an order execution.

    Attributes:
        success: Whether execution succeeded
        order_id: Internal order ID
        exchange_order_id: Exchange-assigned order ID
        error_message: Error message if failed
        fills: List of fills
    """

    success: bool
    order_id: OrderId
    exchange_order_id: str | None = None
    error_message: str | None = None
    fills: list[Fill] = field(default_factory=list)


class ExecutionEngine:
    """
    Execution Engine for order management.

    Responsibilities:
    - Validate every order against risk limits BEFORE submission
    - Submit orders to exchange via adapter
    - Track order state
    - Handle fills and position updates
    - Reconcile after disconnects
    """

    def __init__(
        self,
        adapter: ExchangeAdapter,
        risk_validator: RiskValidationService,
        tenant_limits: TenantLimitsService | None = None,
    ) -> None:
        """
        Initialize execution engine.

        Args:
            adapter: Exchange adapter (OKX, Binance, Bybit, ...) implementing
                the ExchangeAdapter interface
            risk_validator: Risk validation service. REQUIRED — every order
                must pass deterministic risk validation before submission.
                This gate is exchange-agnostic and must never be bypassed.
            tenant_limits: Per-user limits service (rate limit, max grids,
                emergency stop). When provided, every order is checked against
                the user's limits BEFORE risk validation. This gate is
                exchange-agnostic and must never be bypassed.
        """
        self._adapter = adapter
        self._risk_validator = risk_validator
        self._tenant_limits = tenant_limits
        self._orders: dict[OrderId, Order] = {}
        self._positions: dict[str, Position] = {}

    @property
    def mode(self) -> ExecutionMode:
        """Get execution mode."""
        return self._adapter.mode

    @property
    def risk_validator(self) -> RiskValidationService:
        """Get the risk validation service used by this engine."""
        return self._risk_validator

    async def execute_order(
        self,
        market_id: MarketId,
        side: OrderSide,
        quantity: Decimal,
        price: Decimal | None = None,
        metadata: dict[str, Any] | None = None,
        reference_price: Decimal | None = None,
        user_id: str | None = None,
        active_grid_count: int = 0,
        idempotency_key: str | None = None,
        identity: Identity = None,  # type: ignore[assignment]  # [A-H12] Required — no default
        skip_rate_limit: bool = False,
    ) -> ExecutionResult:
        """
        Execute an order with immediate execution.

        Every order is validated against deterministic risk limits BEFORE
        being submitted to the exchange. If validation fails, the order is
        rejected locally and never reaches the exchange.

        When a TenantLimitsService is configured and a user_id is provided,
        the order is first checked against per-user limits (emergency stop,
        rate limit, max concurrent grids) BEFORE risk validation. If any
        per-user check fails, the order is rejected locally and never reaches
        the exchange.

        [A-H7] Authorization: [A-H12] identity is REQUIRED (no default).
        The engine verifies:
        1. The identity can access the current environment (DEMO/LIVE)
        2. The identity has sufficient permission level:
           - DEMO mode: DEMO_OPERATOR (Level 2)
           - LIVE mode: LIVE_OPERATOR (Level 3)
        If authorization fails, the order is rejected locally.

        Idempotency: When an idempotency_key is provided, the engine checks
        whether an order with the same key already exists. If it does and is
        in an active or filled state, the existing result is returned without
        submitting a duplicate order. This prevents double-execution when a
        network timeout causes a retry of the same logical trigger.

        Args:
            market_id: Market to trade
            side: Order side (BUY/SELL)
            quantity: Order quantity
            price: Limit price (None for market orders)
            metadata: Additional metadata (grid level, section, etc.)
            reference_price: Estimated execution price for market orders,
                used by risk validation for notional calculations
            user_id: User identifier for per-user limits enforcement.
                Required when tenant_limits is configured.
            active_grid_count: Current active grid count for the user,
                used by max-concurrent-grids enforcement.
            idempotency_key: Deterministic key for deduplication. If an
                order with this key already exists in an active/filled
                state, the existing result is returned (no duplicate submit).
            identity: [A-H12] REQUIRED authenticated identity for RBAC
                authorization. Must be provided by every caller. System-level
                callers (price monitor, background tasks) must provide a
                SYSTEM identity.
            skip_rate_limit: [A-M1] Skip the per-user interactive rate limit
                check. Used by autonomous grid triggers (PriceMonitorService)
                so that machine-generated orders are not throttled by the
                interactive rate limit. Emergency stop and max-grid checks
                are still enforced.

        Returns:
            ExecutionResult with order details

        Raises:
            ValueError: If identity is None (belt-and-suspenders — mypy
                enforces this statically, this covers runtime edge cases).
        """
        # [A-H12] Belt and suspenders — identity must never be None.
        # mypy enforces this at compile time; this guards runtime edge cases.
        if identity is None:
            logger.error(
                "execute_order_missing_identity",
                market_id=market_id,
                side=side,
            )
            raise ValueError("identity is required for execute_order")

        # [A-H7] AUTHORIZATION CHECK — verify identity can execute in this environment.
        # [A-H12] This is now UNCONDITIONAL — no caller can bypass authorization.
        auth_result = self._check_execution_authorization(identity)
        if not auth_result.is_authorized:
            logger.warning(
                "execute_order_unauthorized",
                identity_id=identity.identity_id,
                role=identity.role.name,
                environment=self.mode,
                reason=auth_result.reason,
                market_id=market_id,
                side=side,
            )
            return ExecutionResult(
                success=False,
                order_id="UNAUTHORIZED",
                error_message=f"Authorization denied: {auth_result.reason}",
            )
        # IDEMPOTENCY CHECK — return existing result if this key was already
        # processed. This is the primary defense against double-execution
        # caused by network timeouts + retries. The DB unique constraint on
        # idempotency_key is the last-resort safety net for race conditions.
        if idempotency_key:
            existing = self._find_order_by_idempotency_key(idempotency_key)
            if existing is not None and existing.status in (
                "SUBMITTED",
                "ACKNOWLEDGED",
                "PARTIALLY_FILLED",
                "FILLED",
            ):
                logger.info(
                    "idempotent_order_deduplicated",
                    idempotency_key=idempotency_key,
                    existing_order_id=existing.order_id,
                    existing_status=existing.status,
                    market_id=market_id,
                    side=side,
                )
                return ExecutionResult(
                    success=True,
                    order_id=existing.order_id,
                    exchange_order_id=existing.exchange_order_id,
                )

        order_id = f"ORD-{uuid4().hex[:12].upper()}"

        meta = dict(metadata or {})
        if user_id is not None and "user_id" not in meta:
            meta["user_id"] = user_id

        order = Order(
            order_id=order_id,
            market_id=market_id,
            side=side,
            order_type="MARKET" if price is None else "LIMIT",
            quantity=quantity,
            price=price,
            metadata=meta,
            idempotency_key=idempotency_key,
        )

        # PER-USER LIMITS CHECK — mandatory before risk validation when
        # tenant_limits is configured. This enforces rate limits, max
        # concurrent grids, and emergency stop per-user. If any check fails,
        # the order is rejected locally and never reaches the exchange.
        #
        # IMPORTANT: If tenant_limits is configured but user_id is None, the
        # per-user protection is silently skipped. This is a "loud skip" —
        # we log a warning so the gap is visible in monitoring, rather than
        # failing silently (the is_configured lesson).
        if self._tenant_limits is not None and user_id is None:
            logger.warning(
                "tenant_limits_skipped_missing_user_id",
                order_id=order_id,
                market_id=market_id,
                side=side,
                quantity=str(quantity),
            )

        if self._tenant_limits is not None and user_id is not None:
            try:
                self._tenant_limits.check_can_trade(
                    user_id=user_id,
                    active_grid_count=active_grid_count,
                    skip_rate_limit=skip_rate_limit,  # [A-M1] autonomous triggers bypass rate limit
                )
            except UserEmergencyStoppedError as e:
                order.status = "REJECTED"
                order.updated_at = datetime.now(UTC)
                self._orders[order_id] = order

                logger.warning(
                    "order_rejected_by_user_emergency_stop",
                    order_id=order_id,
                    user_id=user_id,
                    market_id=market_id,
                    side=side,
                    quantity=str(quantity),
                )

                return ExecutionResult(
                    success=False,
                    order_id=order_id,
                    error_message=f"User emergency stopped: {e}",
                )
            except RateLimitExceededError as e:
                order.status = "REJECTED"
                order.updated_at = datetime.now(UTC)
                self._orders[order_id] = order

                logger.warning(
                    "order_rejected_by_rate_limit",
                    order_id=order_id,
                    user_id=user_id,
                    market_id=market_id,
                    side=side,
                    quantity=str(quantity),
                    retry_after_seconds=e.retry_after_seconds,
                )

                return ExecutionResult(
                    success=False,
                    order_id=order_id,
                    error_message=f"Rate limit exceeded: {e}",
                )
            except MaxGridsExceededError as e:
                order.status = "REJECTED"
                order.updated_at = datetime.now(UTC)
                self._orders[order_id] = order

                logger.warning(
                    "order_rejected_by_max_grids",
                    order_id=order_id,
                    user_id=user_id,
                    market_id=market_id,
                    side=side,
                    quantity=str(quantity),
                )

                return ExecutionResult(
                    success=False,
                    order_id=order_id,
                    error_message=f"Max grids exceeded: {e}",
                )

        # RISK VALIDATION — mandatory before any order reaches the exchange.
        risk_result = self._risk_validator.validate_order(
            market_id=market_id,
            side=side,
            quantity=quantity,
            price=price,
            reference_price=reference_price,
            positions=self._positions,
        )
        if not risk_result.is_passed:
            order.status = "REJECTED"
            order.updated_at = datetime.now(UTC)
            self._orders[order_id] = order

            violation_summary = "; ".join(v.message for v in risk_result.violations)
            logger.warning(
                "order_rejected_by_risk_validation",
                order_id=order_id,
                market_id=market_id,
                side=side,
                quantity=str(quantity),
                violations=[v.rule for v in risk_result.violations],
            )

            return ExecutionResult(
                success=False,
                order_id=order_id,
                error_message=f"Risk validation failed: {violation_summary}",
            )

        # Check if reconciliation is needed before executing
        if self._adapter.needs_reconciliation:
            logger.warning("reconciliation_needed_before_order", order_id=order_id)
            await self.reconcile()

        try:
            # Submit order to exchange
            exchange_order_id = await self._adapter.place_order(order)
            order.exchange_order_id = exchange_order_id
            order.status = "SUBMITTED"
            order.updated_at = datetime.now(UTC)

            self._orders[order_id] = order

            logger.info(
                "order_submitted",
                order_id=order_id,
                exchange_order_id=exchange_order_id,
                market_id=market_id,
                side=side,
                quantity=str(quantity),
                mode=self.mode,
            )

            return ExecutionResult(
                success=True,
                order_id=order_id,
                exchange_order_id=exchange_order_id,
            )

        except ExchangeAPIError as e:
            # Exchange-specific error — preserve code & detail for debugging.
            # This path is separate from the risk rejection path above.
            order.status = "REJECTED"
            order.updated_at = datetime.now(UTC)
            self._orders[order_id] = order

            logger.error(
                "order_rejected",
                order_id=order_id,
                error=str(e),
                code=e.code,
                exchange=self._adapter.exchange_id,
            )

            return ExecutionResult(
                success=False,
                order_id=order_id,
                error_message=str(e),
            )

        except Exception as e:
            order.status = "REJECTED"
            order.updated_at = datetime.now(UTC)
            self._orders[order_id] = order

            logger.error("order_execution_failed", order_id=order_id, error=str(e))

            return ExecutionResult(
                success=False,
                order_id=order_id,
                error_message=f"Execution failed: {e}",
            )

    async def cancel_order(self, order_id: OrderId, user_id: str | None = None) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order to cancel
            user_id: Optional user identifier for authorization tracking

        Returns:
            True if cancellation succeeded
        """
        order = self._orders.get(order_id)
        if order is None:
            logger.warning("cancel_order_not_found", order_id=order_id, user_id=user_id)
            return False

        # If user_id is specified and order has user_id metadata, verify ownership
        order_user_id = order.metadata.get("user_id") if order.metadata else None
        if user_id is not None and order_user_id is not None and order_user_id != user_id:
            logger.warning(
                "cancel_order_unauthorized",
                order_id=order_id,
                caller_user_id=user_id,
                owner_user_id=order_user_id,
            )
            return False

        if order.exchange_order_id is None:
            logger.warning("cancel_order_no_exchange_id", order_id=order_id, user_id=user_id)
            return False

        if not order.is_active:
            logger.info(
                "cancel_order_not_active", order_id=order_id, status=order.status, user_id=user_id
            )
            return False

        success = await self._adapter.cancel_order(order.market_id, order.exchange_order_id)

        if success:
            order.status = "CANCELLED"
            order.updated_at = datetime.now(UTC)
            logger.info("order_cancelled", order_id=order_id, user_id=user_id)

        return success

    def get_order(self, order_id: OrderId) -> Order | None:
        """Get an order by ID."""
        return self._orders.get(order_id)

    def get_active_orders(self) -> list[Order]:
        """Get all active orders."""
        return [o for o in self._orders.values() if o.is_active]

    def get_orders_for_market(self, market_id: MarketId) -> list[Order]:
        """Get all orders for a market."""
        return [o for o in self._orders.values() if o.market_id == market_id]

    def get_positions(self) -> list[Position]:
        """Get all positions."""
        return list(self._positions.values())

    def get_position(self, market_id: MarketId) -> Position | None:
        """Get position for a market."""
        return self._positions.get(market_id)

    def _find_order_by_idempotency_key(self, key: str) -> Order | None:
        """
        Find an existing order by idempotency key.

        In-memory lookup across all tracked orders. This is the primary
        deduplication mechanism within a single process lifetime. The DB
        unique constraint on idempotency_key provides the safety net for
        cross-process/restart scenarios.

        Args:
            key: The idempotency key to search for

        Returns:
            The existing Order if found, None otherwise
        """
        for order in self._orders.values():
            if order.idempotency_key == key:
                return order
        return None

    async def reconcile(self) -> dict[str, Any]:
        """
        Reconcile local state with exchange state.

        Called after disconnect or when state is ambiguous.

        Returns:
            Reconciliation summary
        """
        logger.info("execution_reconcile_start", mode=self.mode)

        # Reconcile via adapter
        adapter_result = await self._adapter.reconcile()

        # Update positions from exchange
        exchange_positions = await self._adapter.get_positions()
        for pos in exchange_positions:
            self._positions[pos.market_id] = pos

        # Update order states for active orders concurrently
        active_orders = [o for o in self.get_active_orders() if o.exchange_order_id]
        if active_orders:

            async def _check_order_status(ord_obj: Order) -> None:
                try:
                    status_data = await self._adapter.get_order_status(
                        ord_obj.market_id,
                        ord_obj.exchange_order_id,  # type: ignore[arg-type]
                    )
                    self._update_order_from_exchange(ord_obj, status_data)
                except Exception as e:
                    logger.warning(
                        "order_status_check_failed",
                        order_id=ord_obj.order_id,
                        error=str(e),
                    )

            await asyncio.gather(
                *[_check_order_status(o) for o in active_orders], return_exceptions=True
            )

        result = {
            "adapter": adapter_result,
            "local_orders": len(self._orders),
            "active_orders": len(self.get_active_orders()),
            "positions": len(self._positions),
        }

        logger.info("execution_reconcile_complete", **result)
        return result

    def _update_order_from_exchange(self, order: Order, data: dict[str, Any]) -> None:
        """
        Update order state from NORMALIZED exchange data.

        Adapters return the normalized shape defined by the ExchangeAdapter
        interface: {"status", "filled_quantity", "average_price", "raw"}.
        This keeps the engine exchange-agnostic (OKX, Binance, Bybit).
        """
        new_status = data.get("status", order.status)
        if new_status != order.status:
            logger.info(
                "order_status_updated",
                order_id=order.order_id,
                old_status=order.status,
                new_status=new_status,
                exchange=self._adapter.exchange_id,
            )
            order.status = new_status
            order.updated_at = datetime.now(UTC)

        # Update fill information
        filled_qty = data.get("filled_quantity", "0")
        if filled_qty:
            order.filled_quantity = Decimal(filled_qty)

        avg_price = data.get("average_price")
        if avg_price:
            order.average_fill_price = Decimal(avg_price)

    def _check_execution_authorization(self, identity: Identity) -> AuthorizationResult:
        """
        [A-H7] Check if identity is authorized to execute orders.

        Authorization rules:
        1. Identity must be allowed to access the current environment (DEMO/LIVE)
        2. Identity must have sufficient permission level:
           - DEMO mode: DEMO_OPERATOR (Level 2)
           - LIVE mode: LIVE_OPERATOR (Level 3)

        Args:
            identity: The authenticated identity to check

        Returns:
            AuthorizationResult with is_authorized and reason
        """
        # Check environment access
        if not identity.can_access_environment(self.mode):
            return AuthorizationResult(
                is_authorized=False,
                identity=identity,
                operation="LIVE_EXECUTE" if self.mode == "LIVE" else "GRID_START",
                environment=self.mode,
                reason=f"Identity not allowed in {self.mode} environment",
            )

        # Check permission level based on environment
        if self.mode == "LIVE":
            required_level = PermissionLevel.LIVE_OPERATOR
            operation = "LIVE_EXECUTE"
        else:
            required_level = PermissionLevel.DEMO_OPERATOR
            operation = "GRID_START"

        if identity.permission_level < required_level:
            return AuthorizationResult(
                is_authorized=False,
                identity=identity,
                operation=operation,
                environment=self.mode,
                reason=(
                    f"Insufficient permission level: {identity.permission_level.name} "
                    f"(requires {required_level.name})"
                ),
            )

        return AuthorizationResult(
            is_authorized=True,
            identity=identity,
            operation=operation,
            environment=self.mode,
        )
