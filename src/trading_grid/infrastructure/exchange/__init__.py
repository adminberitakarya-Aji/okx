"""
Shared exchange infrastructure utilities.

This package contains helpers shared by all exchange adapters:
- symbols: Market ID normalization between domain format ("BTC-USDT")
  and concatenated exchange format ("BTCUSDT")

Concrete exchange adapters live in their own packages:
- infrastructure/okx/
- infrastructure/binance/
- infrastructure/bybit/
"""

from trading_grid.infrastructure.exchange.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)

__all__ = [
    "to_concatenated_symbol",
    "to_normalized_market_id",
]
