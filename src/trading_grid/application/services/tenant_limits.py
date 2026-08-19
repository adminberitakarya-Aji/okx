"""
Per-tenant (per-user) limits service (Phase 5: Multi-Tenant Beta).

Provides:
1. Per-user risk limits (default from RiskSettings, overridable per-user)
2. Rate limiting per-user (sliding window, in-memory)
3. Max concurrent grids per-user enforcement
4. Emergency stop per-user (kill switch)

Design decisions:
- In-memory rate limiter is sufficient for beta scale (10 users).
  For production scale, migrate to Redis-backed sliding window.
- Emergency stop flags are in-memory for immediate effect;
  persistent state is handled by GridEngine/DemoTradingService.
- Per-user risk limit overrides are stored in-memory with defaults
  from settings. For persistence, add a user_risk_limits table.

Security rules:
- Rate limit decisions are audit-logged when they block an action
- Emergency stop is always allowed (never rate-limited)

[A-M1-REV] Phase 10.3: Tenant Limits Auto-Fetch.
- GridEngine can be injected for auto-fetching active grid count
- `check_can_trade` auto-fetches count if not provided
- Eliminates manual `active_grid_count` parameter passing
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

import structlog

from trading_grid.domain.risk.models import RiskLimits

if TYPE_CHECKING:
    from trading_grid.application.services.grid_engine import GridEngine
    from trading_grid.config.settings import Settings

logger = structlog.get_logger()


class RateLimitExceededError(Exception):
    """Raised when a user exceeds their rate limit."""

    def __init__(self, user_id: str, retry_after_seconds: float) -> None:
        self.user_id = user_id
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Rate limit exceeded for user {user_id}. Retry after {retry_after_seconds:.1f}s"
        )


class MaxGridsExceededError(Exception):
    """Raised when a user exceeds their max concurrent grids."""


class UserEmergencyStoppedError(Exception):
    """Raised when a user is under emergency stop."""


@dataclass
class UserRiskLimits:
    """
    Effective risk limits for a specific user.

    Combines system defaults with per-user overrides.
    """

    user_id: str
    limits: RiskLimits
    max_concurrent_grids: int
    rate_limit_per_minute: int
    is_emergency_stopped: bool = False
    emergency_stop_reason: str | None = None
    overrides: dict[str, object] = field(default_factory=dict)


class TenantLimitsService:
    """
    Per-user limits enforcement service.

    [A-M1-REV] Phase 10.3: GridEngine can be injected for auto-fetching
    active grid count. This eliminates manual `active_grid_count` parameter
    passing and reduces the risk of stale counts.

    Usage:
        # Without GridEngine (manual count):
        service = TenantLimitsService(settings)
        service.check_can_trade("usr_1", active_grid_count=2)

        # With GridEngine (auto-fetch):
        service = TenantLimitsService(settings, grid_engine=engine)
        service.check_can_trade("usr_1")  # count auto-fetched
    """

    def __init__(
        self,
        settings: Settings,
        grid_engine: GridEngine | None = None,
    ) -> None:
        """
        Initialize tenant limits service.

        Args:
            settings: Application settings (uses risk defaults)
            grid_engine: [A-M1-REV] Optional GridEngine for auto-fetching
                active grid count. If provided, `check_can_trade` will
                auto-fetch the count when not explicitly provided.
        """
        self._settings = settings
        self._grid_engine = grid_engine
        # Per-user overrides: user_id -> partial overrides dict
        self._user_overrides: dict[str, dict[str, object]] = {}
        # Rate limiter: user_id -> list of request timestamps
        self._rate_windows: dict[str, list[float]] = {}
        # Emergency stop flags: user_id -> reason
        self._emergency_stops: dict[str, str] = {}
        # Active grid counts: user_id -> count (fallback when no GridEngine)
        self._active_grids: dict[str, int] = {}

    @property
    def grid_engine(self) -> GridEngine | None:
        """[A-M1-REV] Get the injected GridEngine (if any)."""
        return self._grid_engine

    def set_grid_engine(self, grid_engine: GridEngine) -> None:
        """
        [A-M1-REV] Set the GridEngine for auto-fetching.

        Useful for late wiring when GridEngine is created after
        TenantLimitsService.

        Args:
            grid_engine: GridEngine instance
        """
        self._grid_engine = grid_engine
        logger.info("tenant_limits_grid_engine_set")

    def _default_limits(self) -> RiskLimits:
        """Build default RiskLimits from settings."""
        risk = self._settings.risk
        return RiskLimits(
            max_capital_per_grid=Decimal(str(risk.max_capital_per_grid)),
            max_total_capital=Decimal(str(risk.max_total_capital)),
            max_drawdown_pct=Decimal(str(risk.max_drawdown_pct)),
            max_concurrent_grids=risk.max_concurrent_grids,
            max_position_pct=Decimal(str(risk.max_position_pct)),
            min_profitable_exit_pct=Decimal(str(risk.min_profitable_exit_pct)),
            max_slippage_pct=Decimal(str(risk.max_slippage_pct)),
            max_execution_cost_pct=Decimal(str(risk.max_execution_cost_pct)),
            min_reserve_pct=Decimal(str(risk.min_reserve_pct)),
            max_exposure_pct=Decimal(str(risk.max_exposure_pct)),
        )

    def get_user_limits(self, user_id: str) -> UserRiskLimits:
        """
        Get effective risk limits for a user.

        Merges system defaults with per-user overrides.

        Args:
            user_id: User identifier

        Returns:
            UserRiskLimits with effective limits
        """
        defaults = self._default_limits()
        overrides = self._user_overrides.get(user_id, {})

        if overrides:
            # Apply overrides to create user-specific limits
            limit_fields = {
                "max_capital_per_grid": Decimal,
                "max_total_capital": Decimal,
                "max_drawdown_pct": Decimal,
                "max_concurrent_grids": int,
                "max_position_pct": Decimal,
                "min_profitable_exit_pct": Decimal,
                "max_slippage_pct": Decimal,
                "max_execution_cost_pct": Decimal,
                "min_reserve_pct": Decimal,
                "max_exposure_pct": Decimal,
            }
            merged = {}
            for field_name, converter in limit_fields.items():
                if field_name in overrides:
                    merged[field_name] = converter(str(overrides[field_name]))
                else:
                    merged[field_name] = getattr(defaults, field_name)
            limits = RiskLimits(**merged)
        else:
            limits = defaults

        max_grids = int(str(overrides.get("max_concurrent_grids", limits.max_concurrent_grids)))
        rate_limit = int(str(overrides.get("rate_limit_per_minute", 30)))  # default 30 req/min

        return UserRiskLimits(
            user_id=user_id,
            limits=limits,
            max_concurrent_grids=max_grids,
            rate_limit_per_minute=rate_limit,
            is_emergency_stopped=user_id in self._emergency_stops,
            emergency_stop_reason=self._emergency_stops.get(user_id),
            overrides=dict(overrides),
        )

    def set_user_overrides(self, user_id: str, overrides: dict[str, object]) -> None:
        """
        Set per-user limit overrides.

        Args:
            user_id: User identifier
            overrides: Dict of limit overrides (e.g., {"max_concurrent_grids": 3})
        """
        self._user_overrides[user_id] = dict(overrides)
        logger.info(
            "user_limits_overridden",
            user_id=user_id,
            override_keys=list(overrides.keys()),
        )

    def clear_user_overrides(self, user_id: str) -> None:
        """Clear per-user overrides, reverting to defaults."""
        self._user_overrides.pop(user_id, None)

    # =========================================================================
    # RATE LIMITING
    # =========================================================================

    def check_rate_limit(self, user_id: str, *, now: float | None = None) -> None:
        """
        Check if user is within rate limit.

        Uses sliding window (60 seconds).

        Args:
            user_id: User identifier
            now: Current timestamp (injectable for testing)

        Raises:
            RateLimitExceededError: If rate limit exceeded
        """
        current_time = now if now is not None else time.monotonic()
        window_start = current_time - 60.0

        # Get or create window
        if user_id not in self._rate_windows:
            self._rate_windows[user_id] = []

        # Prune old entries
        window = self._rate_windows[user_id]
        self._rate_windows[user_id] = [t for t in window if t > window_start]
        window = self._rate_windows[user_id]

        user_limits = self.get_user_limits(user_id)
        max_requests = user_limits.rate_limit_per_minute

        if len(window) >= max_requests:
            # Calculate retry-after
            oldest = min(window)
            retry_after = oldest + 60.0 - current_time
            logger.warning(
                "rate_limit_exceeded",
                user_id=user_id,
                requests_in_window=len(window),
                limit=max_requests,
            )
            raise RateLimitExceededError(user_id, max(0.0, retry_after))

        # Record this request
        window.append(current_time)

    # =========================================================================
    # GRID CAPACITY
    # =========================================================================

    def check_grid_capacity(self, user_id: str, active_grid_count: int) -> None:
        """
        Check if user can start another grid.

        Args:
            user_id: User identifier
            active_grid_count: Current number of active grids

        Raises:
            MaxGridsExceededError: If max concurrent grids exceeded
        """
        user_limits = self.get_user_limits(user_id)

        if active_grid_count >= user_limits.max_concurrent_grids:
            logger.warning(
                "max_grids_exceeded",
                user_id=user_id,
                active_grids=active_grid_count,
                max_grids=user_limits.max_concurrent_grids,
            )
            raise MaxGridsExceededError(
                f"User {user_id} has {active_grid_count} active grids "
                f"(max: {user_limits.max_concurrent_grids})"
            )

    def register_grid_started(self, user_id: str) -> None:
        """Register that a user started a grid."""
        self._active_grids[user_id] = self._active_grids.get(user_id, 0) + 1

    def register_grid_stopped(self, user_id: str) -> None:
        """Register that a user stopped a grid."""
        count = self._active_grids.get(user_id, 0)
        self._active_grids[user_id] = max(0, count - 1)

    def get_active_grid_count(self, user_id: str) -> int:
        """
        Get active grid count for a user.

        [A-M1-REV] If GridEngine is injected, auto-fetches the count from
        the engine (counting grids owned by the user). Otherwise, falls back
        to the internally tracked count.

        Args:
            user_id: User identifier

        Returns:
            Number of active grids for the user
        """
        if self._grid_engine is not None:
            # Auto-fetch from GridEngine
            return self._fetch_grid_count_from_engine(user_id)
        return self._active_grids.get(user_id, 0)

    def _fetch_grid_count_from_engine(self, user_id: str) -> int:
        """
        [A-M1-REV] Fetch active grid count from GridEngine.

        Counts grids where user_id matches. Grids with user_id=None
        (system grids) are not counted toward user limits.

        Args:
            user_id: User identifier

        Returns:
            Number of active grids owned by the user
        """
        if self._grid_engine is None:
            return 0

        active_grids = self._grid_engine.get_active_grids()
        count = sum(
            1
            for grid in active_grids
            if getattr(grid, "user_id", None) == user_id
        )
        return count

    # =========================================================================
    # EMERGENCY STOP
    # =========================================================================

    def emergency_stop_user(self, user_id: str, reason: str) -> None:
        """
        Activate emergency stop for a user.

        This blocks all new actions for the user.

        Args:
            user_id: User identifier
            reason: Reason for emergency stop
        """
        self._emergency_stops[user_id] = reason
        logger.critical(
            "user_emergency_stop_activated",
            user_id=user_id,
            reason=reason,
        )

    def clear_emergency_stop(self, user_id: str) -> None:
        """Clear emergency stop for a user."""
        removed = self._emergency_stops.pop(user_id, None)
        if removed is not None:
            logger.info(
                "user_emergency_stop_cleared",
                user_id=user_id,
                previous_reason=removed,
            )

    def is_emergency_stopped(self, user_id: str) -> bool:
        """Check if a user is under emergency stop."""
        return user_id in self._emergency_stops

    def check_not_emergency_stopped(self, user_id: str) -> None:
        """
        Verify user is not under emergency stop.

        Args:
            user_id: User identifier

        Raises:
            UserEmergencyStoppedError: If user is emergency stopped
        """
        if user_id in self._emergency_stops:
            raise UserEmergencyStoppedError(
                f"User {user_id} is under emergency stop: {self._emergency_stops[user_id]}"
            )

    def get_all_emergency_stopped_users(self) -> dict[str, str]:
        """Get all users under emergency stop with reasons."""
        return dict(self._emergency_stops)

    # =========================================================================
    # COMBINED CHECK
    # =========================================================================

    def check_can_place_order(
        self,
        user_id: str,
        *,
        skip_rate_limit: bool = False,
        now: float | None = None,
    ) -> UserRiskLimits:
        """
        Check whether an order can be placed for an already running grid.

        Checks:
        1. Emergency stop status
        2. Rate limit (unless skipped)
        (Grid capacity is checked when initiating/starting a grid, not per-order).

        Args:
            user_id: User identifier
            skip_rate_limit: Skip rate limit check (for emergency ops)
            now: Injectable timestamp for testing

        Returns:
            UserRiskLimits if checks pass

        Raises:
            UserEmergencyStoppedError: If emergency stopped
            RateLimitExceededError: If rate limited
        """
        self.check_not_emergency_stopped(user_id)

        if not skip_rate_limit:
            self.check_rate_limit(user_id, now=now)

        return self.get_user_limits(user_id)

    def check_can_trade(
        self,
        user_id: str,
        active_grid_count: int | None = None,
        *,
        skip_rate_limit: bool = False,
        now: float | None = None,
    ) -> UserRiskLimits:
        """
        Combined pre-trade check for a user.

        Checks:
        1. Emergency stop status
        2. Rate limit (unless skipped, e.g., for emergency operations)
        3. Grid capacity

        [A-M1-REV] If `active_grid_count` is not provided and GridEngine is
        injected, the count is auto-fetched from the engine. This eliminates
        the need for callers to manually track and pass the count.

        Args:
            user_id: User identifier
            active_grid_count: Current active grid count. If None, auto-fetched
                from GridEngine (if injected) or defaults to 0.
            skip_rate_limit: Skip rate limit check (for emergency ops)
            now: Injectable timestamp for testing

        Returns:
            UserRiskLimits if all checks pass

        Raises:
            UserEmergencyStoppedError: If emergency stopped
            RateLimitExceededError: If rate limited
            MaxGridsExceededError: If grid capacity exceeded
        """
        self.check_can_place_order(user_id, skip_rate_limit=skip_rate_limit, now=now)

        # [A-M1-REV] Auto-fetch count if not provided
        if active_grid_count is None:
            active_grid_count = self.get_active_grid_count(user_id)

        self.check_grid_capacity(user_id, active_grid_count)

        return self.get_user_limits(user_id)
