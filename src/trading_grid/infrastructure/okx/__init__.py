"""
OKX Exchange Adapter infrastructure.

This package provides:
- OKXAdapter: Main adapter combining REST and WebSocket
- OKXRestClient: REST API v5 client
- OKXWebSocketClient: WebSocket client for real-time data

Security rules:
1. API keys: Read + Trade only, Withdraw DISABLED
2. DEMO and LIVE use separate credentials
3. Secrets never in logs
4. Reconciliation required after any disconnect
"""

from trading_grid.infrastructure.okx.adapter import OKXAdapter
from trading_grid.infrastructure.okx.rest_client import OKXAPIError, OKXRestClient
from trading_grid.infrastructure.okx.websocket_client import OKXWebSocketClient

__all__ = [
    "OKXAPIError",
    "OKXAdapter",
    "OKXRestClient",
    "OKXWebSocketClient",
]
