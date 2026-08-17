"""
Exchange domain package.

This package defines the exchange-agnostic contracts:
- ExchangeAdapter: Abstract interface implemented by all exchange adapters
- ExchangeAPIError: Base exception for exchange API errors

Dependency rule: this package MUST NOT import from infrastructure/.
Concrete adapters (OKX, Binance, Bybit) live in infrastructure/<exchange>/.
"""

from trading_grid.domain.exchange.errors import (
    ExchangeAPIError,
    ExchangeAuthError,
    ExchangeConnectionError,
    ExchangeError,
    ExchangeNotConfiguredError,
)
from trading_grid.domain.exchange.interface import ExchangeAdapter

__all__ = [
    "ExchangeAPIError",
    "ExchangeAdapter",
    "ExchangeAuthError",
    "ExchangeConnectionError",
    "ExchangeError",
    "ExchangeNotConfiguredError",
]
