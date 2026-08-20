"""Tests for WebSocket reconnect exponential backoff helper.

Verifies that ws_reconnect_delay produces:
- Exponential growth with attempt number
- Jitter added to delay
- Capped at max_delay
"""

from unittest.mock import patch

from trading_grid.infrastructure._common.ws_backoff import ws_reconnect_delay


class TestWsReconnectDelay:
    """Tests for ws_reconnect_delay function."""

    def test_attempt_zero_returns_base(self):
        """Attempt 0 should return ~base delay."""
        with patch(
            "trading_grid.infrastructure._common.ws_backoff.random.uniform", return_value=0.0
        ):
            delay = ws_reconnect_delay(0)
        assert delay == 1.0

    def test_exponential_growth(self):
        """Delay should grow exponentially with attempt."""
        with patch(
            "trading_grid.infrastructure._common.ws_backoff.random.uniform", return_value=0.0
        ):
            d0 = ws_reconnect_delay(0)
            d1 = ws_reconnect_delay(1)
            d2 = ws_reconnect_delay(2)
            d3 = ws_reconnect_delay(3)
        assert d0 == 1.0
        assert d1 == 2.0
        assert d2 == 4.0
        assert d3 == 8.0

    def test_capped_at_max_delay(self):
        """Delay should be capped at max_delay."""
        with patch(
            "trading_grid.infrastructure._common.ws_backoff.random.uniform", return_value=0.0
        ):
            d6 = ws_reconnect_delay(6)
            d7 = ws_reconnect_delay(7)
            d10 = ws_reconnect_delay(10)
        assert d6 == 60.0
        assert d7 == 60.0
        assert d10 == 60.0

    def test_custom_base(self):
        """Custom base should scale delays."""
        with patch(
            "trading_grid.infrastructure._common.ws_backoff.random.uniform", return_value=0.0
        ):
            d0 = ws_reconnect_delay(0, base=2.0)
            d1 = ws_reconnect_delay(1, base=2.0)
        assert d0 == 2.0
        assert d1 == 4.0

    def test_custom_max_delay(self):
        """Custom max_delay should cap earlier."""
        with patch(
            "trading_grid.infrastructure._common.ws_backoff.random.uniform", return_value=0.0
        ):
            d3 = ws_reconnect_delay(3, max_delay=5.0)
            d4 = ws_reconnect_delay(4, max_delay=5.0)
        assert d3 == 5.0
        assert d4 == 5.0

    def test_jitter_added(self):
        """Jitter should be added to the delay."""
        with patch(
            "trading_grid.infrastructure._common.ws_backoff.random.uniform", return_value=0.05
        ):
            delay = ws_reconnect_delay(0)
        # base=1.0, jitter=0.05*1.0=0.05 → 1.05
        assert delay == 1.05

    def test_jitter_within_10_percent(self):
        """Jitter should be within 10% of the base delay."""
        for attempt in range(0, 8):
            delay = ws_reconnect_delay(attempt)
            base = min(1.0 * (2**attempt), 60.0)
            assert base <= delay <= base * 1.1

    def test_delay_always_positive(self):
        """Delay should always be positive."""
        for attempt in range(0, 10):
            delay = ws_reconnect_delay(attempt)
            assert delay > 0
