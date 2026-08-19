"""
WebSocket reconnect backoff helper.

Provides exponential backoff with jitter for WebSocket reconnection
to prevent reconnect storms during network issues.

Usage:
    from trading_grid.infrastructure._common.ws_backoff import ws_reconnect_delay

    delay = ws_reconnect_delay(attempt)
    await asyncio.sleep(delay)
"""

import random


def ws_reconnect_delay(attempt: int, base: float = 1.0, max_delay: float = 60.0) -> float:
    """
    Calculate exponential backoff delay with jitter for WS reconnect.

    Args:
        attempt: Number of consecutive failed reconnect attempts (0-based)
        base: Base delay in seconds (default 1.0)
        max_delay: Maximum delay in seconds (default 60.0)

    Returns:
        Delay in seconds with jitter added

    Example:
        attempt 0: ~1.0s
        attempt 1: ~2.0s
        attempt 2: ~4.0s
        attempt 3: ~8.0s
        ...
        attempt 6+: capped at ~60.0s
    """
    delay = float(min(base * (2**attempt), max_delay))
    jitter = float(random.uniform(0, delay * 0.1))
    return delay + jitter
