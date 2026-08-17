"""
Tests for TenantLimitsService (Phase 5: Multi-Tenant Beta).

Verifies:
1. Per-user risk limits (defaults from RiskSettings, overridable per-user)
2. Rate limiting per-user (sliding window)
3. Max concurrent grids per-user enforcement
4. Emergency stop per-user (kill switch)
5. Combined check_can_trade
"""

from decimal import Decimal

import pytest

from trading_grid.application.services.tenant_limits import (
    MaxGridsExceededError,
    RateLimitExceededError,
    TenantLimitsService,
    UserEmergencyStoppedError,
)
from trading_grid.config.settings import Settings


@pytest.fixture
def settings() -> Settings:
    """Build a Settings instance with default risk limits."""
    return Settings(_env_file=None)


@pytest.fixture
def service(settings: Settings) -> TenantLimitsService:
    """Build a TenantLimitsService."""
    return TenantLimitsService(settings)


class TestGetUserLimits:
    """Tests for get_user_limits."""

    def test_returns_defaults_from_settings(
        self, service: TenantLimitsService, settings: Settings
    ) -> None:
        """User without overrides gets system defaults."""
        limits = service.get_user_limits("usr_1")

        assert limits.user_id == "usr_1"
        assert limits.limits.max_capital_per_grid == Decimal(
            str(settings.risk.max_capital_per_grid)
        )
        assert limits.limits.max_total_capital == Decimal(str(settings.risk.max_total_capital))
        assert limits.max_concurrent_grids == settings.risk.max_concurrent_grids
        assert limits.is_emergency_stopped is False
        assert limits.overrides == {}

    def test_overrides_applied(self, service: TenantLimitsService) -> None:
        """Per-user overrides change effective limits."""
        service.set_user_overrides(
            "usr_1",
            {"max_capital_per_grid": "50", "max_concurrent_grids": 2},
        )
        limits = service.get_user_limits("usr_1")

        assert limits.limits.max_capital_per_grid == Decimal("50")
        assert limits.max_concurrent_grids == 2
        # Non-overridden fields keep defaults
        assert limits.limits.max_drawdown_pct == Decimal("10")

    def test_clear_overrides_reverts_to_defaults(
        self, service: TenantLimitsService, settings: Settings
    ) -> None:
        """clear_user_overrides reverts to system defaults."""
        service.set_user_overrides("usr_1", {"max_capital_per_grid": "50"})
        service.clear_user_overrides("usr_1")
        limits = service.get_user_limits("usr_1")

        assert limits.limits.max_capital_per_grid == Decimal(
            str(settings.risk.max_capital_per_grid)
        )

    def test_users_are_isolated(self, service: TenantLimitsService) -> None:
        """Overrides for one user do not affect another."""
        service.set_user_overrides("usr_1", {"max_concurrent_grids": 1})

        limits_1 = service.get_user_limits("usr_1")
        limits_2 = service.get_user_limits("usr_2")

        assert limits_1.max_concurrent_grids == 1
        assert limits_2.max_concurrent_grids == 5  # default


class TestRateLimiting:
    """Tests for check_rate_limit."""

    def test_allows_requests_under_limit(self, service: TenantLimitsService) -> None:
        """Requests under the limit pass."""
        for i in range(5):
            service.check_rate_limit("usr_1", now=float(i))

    def test_blocks_requests_over_limit(self, service: TenantLimitsService) -> None:
        """Requests over the limit raise RateLimitExceededError."""
        # Default rate limit is 30/min
        for i in range(30):
            service.check_rate_limit("usr_1", now=float(i))

        with pytest.raises(RateLimitExceededError) as exc_info:
            service.check_rate_limit("usr_1", now=30.0)

        assert exc_info.value.user_id == "usr_1"
        assert exc_info.value.retry_after_seconds > 0

    def test_sliding_window_expires_old_requests(self, service: TenantLimitsService) -> None:
        """Requests older than 60s are pruned from the window."""
        # Fill the window at t=0..29
        for i in range(30):
            service.check_rate_limit("usr_1", now=float(i))

        # At t=61, the first request (t=0) has expired
        service.check_rate_limit("usr_1", now=61.0)  # should not raise

    def test_rate_limits_are_per_user(self, service: TenantLimitsService) -> None:
        """Rate limit windows are independent per user."""
        for i in range(30):
            service.check_rate_limit("usr_1", now=float(i))

        # usr_2 is unaffected
        service.check_rate_limit("usr_2", now=30.0)

    def test_custom_rate_limit_override(self, service: TenantLimitsService) -> None:
        """Per-user rate_limit_per_minute override is respected."""
        service.set_user_overrides("usr_1", {"rate_limit_per_minute": 2})

        service.check_rate_limit("usr_1", now=0.0)
        service.check_rate_limit("usr_1", now=1.0)

        with pytest.raises(RateLimitExceededError):
            service.check_rate_limit("usr_1", now=2.0)


class TestGridCapacity:
    """Tests for check_grid_capacity and grid tracking."""

    def test_allows_under_capacity(self, service: TenantLimitsService) -> None:
        """Grid count under max passes."""
        service.check_grid_capacity("usr_1", active_grid_count=4)  # max 5

    def test_blocks_at_capacity(self, service: TenantLimitsService) -> None:
        """Grid count at max raises MaxGridsExceededError."""
        with pytest.raises(MaxGridsExceededError):
            service.check_grid_capacity("usr_1", active_grid_count=5)

    def test_blocks_over_capacity(self, service: TenantLimitsService) -> None:
        """Grid count over max raises MaxGridsExceededError."""
        with pytest.raises(MaxGridsExceededError):
            service.check_grid_capacity("usr_1", active_grid_count=6)

    def test_override_max_grids(self, service: TenantLimitsService) -> None:
        """Per-user max_concurrent_grids override is respected."""
        service.set_user_overrides("usr_1", {"max_concurrent_grids": 1})

        service.check_grid_capacity("usr_1", active_grid_count=0)
        with pytest.raises(MaxGridsExceededError):
            service.check_grid_capacity("usr_1", active_grid_count=1)

    def test_grid_count_tracking(self, service: TenantLimitsService) -> None:
        """register_grid_started/stopped tracks active count."""
        assert service.get_active_grid_count("usr_1") == 0

        service.register_grid_started("usr_1")
        service.register_grid_started("usr_1")
        assert service.get_active_grid_count("usr_1") == 2

        service.register_grid_stopped("usr_1")
        assert service.get_active_grid_count("usr_1") == 1

    def test_grid_count_never_negative(self, service: TenantLimitsService) -> None:
        """Stopping more grids than started floors at zero."""
        service.register_grid_stopped("usr_1")
        assert service.get_active_grid_count("usr_1") == 0


class TestEmergencyStop:
    """Tests for emergency stop per-user."""

    def test_emergency_stop_activates(self, service: TenantLimitsService) -> None:
        """emergency_stop_user sets the flag with reason."""
        service.emergency_stop_user("usr_1", reason="Max drawdown")

        assert service.is_emergency_stopped("usr_1") is True
        limits = service.get_user_limits("usr_1")
        assert limits.is_emergency_stopped is True
        assert limits.emergency_stop_reason == "Max drawdown"

    def test_check_not_emergency_stopped_raises(self, service: TenantLimitsService) -> None:
        """check_not_emergency_stopped raises when stopped."""
        service.emergency_stop_user("usr_1", reason="Manual stop")

        with pytest.raises(UserEmergencyStoppedError, match="Manual stop"):
            service.check_not_emergency_stopped("usr_1")

    def test_check_not_emergency_stopped_passes_when_clear(
        self, service: TenantLimitsService
    ) -> None:
        """check_not_emergency_stopped passes when not stopped."""
        service.check_not_emergency_stopped("usr_1")  # should not raise

    def test_clear_emergency_stop(self, service: TenantLimitsService) -> None:
        """clear_emergency_stop removes the flag."""
        service.emergency_stop_user("usr_1", reason="Test")
        service.clear_emergency_stop("usr_1")

        assert service.is_emergency_stopped("usr_1") is False
        service.check_not_emergency_stopped("usr_1")  # should not raise

    def test_emergency_stop_is_per_user(self, service: TenantLimitsService) -> None:
        """Emergency stop for one user does not affect others."""
        service.emergency_stop_user("usr_1", reason="Test")

        assert service.is_emergency_stopped("usr_1") is True
        assert service.is_emergency_stopped("usr_2") is False

    def test_get_all_emergency_stopped_users(self, service: TenantLimitsService) -> None:
        """get_all_emergency_stopped_users returns all stopped users."""
        service.emergency_stop_user("usr_1", reason="Drawdown")
        service.emergency_stop_user("usr_2", reason="Manual")

        stopped = service.get_all_emergency_stopped_users()
        assert stopped == {"usr_1": "Drawdown", "usr_2": "Manual"}


class TestCheckCanTrade:
    """Tests for the combined check_can_trade."""

    def test_passes_when_all_clear(self, service: TenantLimitsService) -> None:
        """check_can_trade returns limits when all checks pass."""
        limits = service.check_can_trade("usr_1", active_grid_count=0, now=0.0)
        assert limits.user_id == "usr_1"

    def test_fails_on_emergency_stop(self, service: TenantLimitsService) -> None:
        """check_can_trade raises when user is emergency stopped."""
        service.emergency_stop_user("usr_1", reason="Stop")

        with pytest.raises(UserEmergencyStoppedError):
            service.check_can_trade("usr_1", active_grid_count=0, now=0.0)

    def test_fails_on_rate_limit(self, service: TenantLimitsService) -> None:
        """check_can_trade raises when rate limited."""
        service.set_user_overrides("usr_1", {"rate_limit_per_minute": 1})
        service.check_can_trade("usr_1", active_grid_count=0, now=0.0)

        with pytest.raises(RateLimitExceededError):
            service.check_can_trade("usr_1", active_grid_count=0, now=1.0)

    def test_fails_on_grid_capacity(self, service: TenantLimitsService) -> None:
        """check_can_trade raises when grid capacity exceeded."""
        with pytest.raises(MaxGridsExceededError):
            service.check_can_trade("usr_1", active_grid_count=5, now=0.0)

    def test_skip_rate_limit_for_emergency_ops(self, service: TenantLimitsService) -> None:
        """skip_rate_limit bypasses rate check but not other checks."""
        service.set_user_overrides("usr_1", {"rate_limit_per_minute": 1})
        service.check_can_trade("usr_1", active_grid_count=0, now=0.0)

        # Would be rate-limited, but skip_rate_limit=True
        limits = service.check_can_trade(
            "usr_1", active_grid_count=0, skip_rate_limit=True, now=1.0
        )
        assert limits.user_id == "usr_1"

    def test_emergency_stop_checked_before_rate_limit(self, service: TenantLimitsService) -> None:
        """Emergency stop takes precedence over rate limit."""
        service.emergency_stop_user("usr_1", reason="Stop")

        with pytest.raises(UserEmergencyStoppedError):
            service.check_can_trade("usr_1", active_grid_count=0, skip_rate_limit=True, now=0.0)
