"""
Binance exchange adapter package.

Implements the exchange-agnostic ExchangeAdapter interface for Binance Spot.

Security rules:
1. API keys: Read + Trade only, Withdraw DISABLED
2. Testnet and Live use separate credentials
3. Secrets never in logs
"""

from okx_trading.infrastructure.binance.adapter import BinanceAdapter
from okx_trading.infrastructure.binance.rest_client import BinanceAPIError, BinanceRestClient
from okx_trading.infrastructure.binance.websocket_client import BinanceWebSocketClient

__all__ = [
    "BinanceAPIError",
    "BinanceAdapter",
    "BinanceRestClient",
    "BinanceWebSocketClient",
]
