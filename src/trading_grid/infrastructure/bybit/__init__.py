"""
Bybit exchange adapter package.

Implements the exchange-agnostic ExchangeAdapter interface for Bybit Spot (API v5).

Security rules:
1. API keys: Read + Trade only, Withdraw DISABLED
2. Testnet and Live use separate credentials
3. Secrets never in logs
"""

from trading_grid.infrastructure.bybit.adapter import BybitAdapter
from trading_grid.infrastructure.bybit.rest_client import BybitAPIError, BybitRestClient
from trading_grid.infrastructure.bybit.websocket_client import BybitWebSocketClient

__all__ = [
    "BybitAPIError",
    "BybitAdapter",
    "BybitRestClient",
    "BybitWebSocketClient",
]
