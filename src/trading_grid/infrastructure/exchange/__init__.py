"""
Shared exchange infrastructure utilities.

[TD-1] Symbol normalization is now imported directly from domain.market.symbols.
The infrastructure/exchange/symbols.py re-export module has been removed.

Concrete exchange adapters live in their own packages:
- infrastructure/okx/
- infrastructure/binance/
- infrastructure/bybit/
"""

from trading_grid.domain.market.symbols import (
    to_concatenated_symbol,
    to_normalized_market_id,
)

__all__ = [
    "to_concatenated_symbol",
    "to_normalized_market_id",
]
