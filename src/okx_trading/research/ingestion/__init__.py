"""
Research data ingestion module.

This module provides:
- OKXHistoricalClient: Download historical candles from OKX
- BinanceHistoricalClient: Download historical candles from Binance
- BybitHistoricalClient: Download historical candles from Bybit
- ParquetStorage: Versioned, exchange-aware Parquet-based data storage
"""

from okx_trading.research.ingestion.binance_client import (
    BinanceDataError,
    BinanceHistoricalClient,
    BinanceIngestionStats,
    BinanceRateLimitError,
)
from okx_trading.research.ingestion.bybit_client import (
    BybitDataError,
    BybitHistoricalClient,
    BybitIngestionStats,
    BybitRateLimitError,
)
from okx_trading.research.ingestion.okx_client import (
    IngestionStats,
    OKXDataError,
    OKXHistoricalClient,
    RateLimitError,
)
from okx_trading.research.ingestion.storage import DatasetMetadata, ParquetStorage

__all__ = [
    "BinanceDataError",
    "BinanceHistoricalClient",
    "BinanceIngestionStats",
    "BinanceRateLimitError",
    "BybitDataError",
    "BybitHistoricalClient",
    "BybitIngestionStats",
    "BybitRateLimitError",
    "DatasetMetadata",
    "IngestionStats",
    "OKXDataError",
    "OKXHistoricalClient",
    "ParquetStorage",
    "RateLimitError",
]
