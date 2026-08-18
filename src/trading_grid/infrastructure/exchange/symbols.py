"""
Market symbol normalization helpers for multi-exchange support.

Re-exports symbol normalization utilities from domain.market.symbols
for backwards compatibility.
"""

from trading_grid.domain.market.symbols import (
    KNOWN_QUOTE_CURRENCIES,
    to_concatenated_symbol,
    to_normalized_market_id,
)

__all__ = [
    "KNOWN_QUOTE_CURRENCIES",
    "to_concatenated_symbol",
    "to_normalized_market_id",
]
