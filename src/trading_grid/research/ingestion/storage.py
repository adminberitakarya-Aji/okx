"""
Parquet-based research data storage.

This module provides versioned, exchange-aware storage for research data:
- Candle data stored as Parquet files
- Versioned directory structure: data/research/{version}/{exchange_id}/{market}/{interval}/
- Metadata tracking for data provenance

Directory structure:
    data/research/
    └── v1/
        ├── OKX/
        │   └── BTC-USDT/
        │       └── 1H/
        │           ├── candles.parquet
        │           └── metadata.json
        ├── BINANCE/
        │   └── BTC-USDT/
        │       └── 1H/
        │           ├── candles.parquet
        │           └── metadata.json
        └── BYBIT/
            └── BTC-USDT/
                └── 1H/
                    ├── candles.parquet
                    └── metadata.json

The exchange_id segment prevents data collision when the same market_id
(e.g., BTC-USDT) is ingested from multiple exchanges.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pandas as pd
import structlog

from trading_grid.domain.market.models import Candle

if TYPE_CHECKING:
    from trading_grid.domain.shared.types import ExchangeId, MarketId

logger = structlog.get_logger()

# Default data directory
DEFAULT_DATA_DIR = "data/research"
DEFAULT_VERSION = "v1"
DEFAULT_EXCHANGE_ID: ExchangeId = "OKX"


@dataclass
class DatasetMetadata:
    """Metadata for a stored dataset."""

    market_id: MarketId
    exchange_id: ExchangeId
    interval: str
    version: str
    candle_count: int
    start_time: datetime | None
    end_time: datetime | None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    gaps: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        d = asdict(self)
        # Convert datetimes to ISO strings
        for key in ("start_time", "end_time", "created_at", "updated_at"):
            if d.get(key) is not None:
                d[key] = d[key].isoformat() if isinstance(d[key], datetime) else d[key]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DatasetMetadata:
        """Create from dict."""
        for key in ("start_time", "end_time", "created_at", "updated_at"):
            if d.get(key) is not None and isinstance(d[key], str):
                d[key] = datetime.fromisoformat(d[key])
        return cls(**d)


class ParquetStorage:
    """
    Parquet-based storage for research data.

    Provides:
    - Versioned, exchange-aware directory structure
    - Candle data storage/retrieval
    - Metadata tracking
    - Data validation on load

    The exchange_id is set at construction time. Each ingestion client
    (OKX, Binance, Bybit) should create its own storage instance with
    the appropriate exchange_id to prevent data collision.

    Usage:
        storage = ParquetStorage("data/research", version="v1", exchange_id="OKX")
        storage.save_candles(candles, "BTC-USDT", "1H")
        candles = storage.load_candles("BTC-USDT", "1H")
    """

    def __init__(
        self,
        base_dir: str | Path = DEFAULT_DATA_DIR,
        version: str = DEFAULT_VERSION,
        exchange_id: ExchangeId = DEFAULT_EXCHANGE_ID,
    ) -> None:
        """
        Initialize storage.

        Args:
            base_dir: Base directory for research data
            version: Dataset version (e.g., "v1")
            exchange_id: Exchange identifier (e.g., "OKX", "BINANCE", "BYBIT")
        """
        self.base_dir = Path(base_dir)
        self.version = version
        self.exchange_id = exchange_id
        self.version_dir = self.base_dir / version

    def _exchange_dir(self) -> Path:
        """Get directory path for the current exchange."""
        return self.version_dir / self.exchange_id

    def _market_dir(self, market_id: MarketId, interval: str) -> Path:
        """Get directory path for a market/interval."""
        return self._exchange_dir() / market_id / interval

    def _parquet_path(self, market_id: MarketId, interval: str) -> Path:
        """Get parquet file path for a market/interval."""
        return self._market_dir(market_id, interval) / "candles.parquet"

    def _metadata_path(self, market_id: MarketId, interval: str) -> Path:
        """Get metadata file path for a market/interval."""
        return self._market_dir(market_id, interval) / "metadata.json"

    def save_candles(
        self,
        candles: list[Candle],
        market_id: MarketId,
        interval: str,
        gaps: list[str] | None = None,
    ) -> Path:
        """
        Save candles to Parquet file.

        Args:
            candles: List of Candle objects
            market_id: Market identifier
            interval: Candle interval
            gaps: List of detected gap descriptions

        Returns:
            Path to saved parquet file
        """
        if not candles:
            raise ValueError("Cannot save empty candle list")

        # Ensure directory exists
        market_dir = self._market_dir(market_id, interval)
        market_dir.mkdir(parents=True, exist_ok=True)

        # Convert to DataFrame
        df = self._candles_to_dataframe(candles)

        # Save parquet
        parquet_path = self._parquet_path(market_id, interval)
        df.to_parquet(parquet_path, index=False, compression="snappy")

        # Save metadata
        metadata = DatasetMetadata(
            market_id=market_id,
            exchange_id=self.exchange_id,
            interval=interval,
            version=self.version,
            candle_count=len(candles),
            start_time=candles[0].timestamp if candles else None,
            end_time=candles[-1].timestamp if candles else None,
            gaps=gaps or [],
            extra={"parquet_schema_version": self.PARQUET_SCHEMA_VERSION},
        )
        self._save_metadata(metadata, market_id, interval)

        logger.info(
            "candles_saved",
            market_id=market_id,
            exchange_id=self.exchange_id,
            interval=interval,
            count=len(candles),
            path=str(parquet_path),
        )

        return parquet_path

    def load_candles(
        self,
        market_id: MarketId,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[Candle]:
        """
        Load candles from Parquet file.

        Args:
            market_id: Market identifier
            interval: Candle interval
            start: Filter start time (inclusive)
            end: Filter end time (inclusive)

        Returns:
            List of Candle objects sorted by timestamp

        Raises:
            FileNotFoundError: If no data exists for market/interval
        """
        parquet_path = self._parquet_path(market_id, interval)

        if not parquet_path.exists():
            raise FileNotFoundError(
                f"No data found for {self.exchange_id}/{market_id}/{interval} at {parquet_path}"
            )

        df = pd.read_parquet(parquet_path)

        # Filter by time range
        if start is not None:
            df = df[df["timestamp"] >= start]
        if end is not None:
            df = df[df["timestamp"] <= end]

        candles = self._dataframe_to_candles(df, market_id)

        logger.info(
            "candles_loaded",
            market_id=market_id,
            exchange_id=self.exchange_id,
            interval=interval,
            count=len(candles),
        )

        return candles

    def load_metadata(self, market_id: MarketId, interval: str) -> DatasetMetadata | None:
        """Load metadata for a market/interval."""
        metadata_path = self._metadata_path(market_id, interval)

        if not metadata_path.exists():
            return None

        with metadata_path.open() as f:
            data = json.load(f)

        return DatasetMetadata.from_dict(data)

    def _save_metadata(self, metadata: DatasetMetadata, market_id: MarketId, interval: str) -> None:
        """Save metadata to JSON file."""
        metadata_path = self._metadata_path(market_id, interval)

        with metadata_path.open("w") as f:
            json.dump(metadata.to_dict(), f, indent=2, default=str)

    def list_exchanges(self) -> list[str]:
        """List all exchanges with stored data."""
        if not self.version_dir.exists():
            return []

        return sorted(
            d.name for d in self.version_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

    def list_markets(self) -> list[MarketId]:
        """List all markets with stored data for the current exchange."""
        exchange_dir = self._exchange_dir()
        if not exchange_dir.exists():
            return []

        return sorted(
            d.name for d in exchange_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

    def list_intervals(self, market_id: MarketId) -> list[str]:
        """List all intervals with stored data for a market."""
        market_dir = self._exchange_dir() / market_id

        if not market_dir.exists():
            return []

        return sorted(
            d.name for d in market_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
        )

    def get_data_summary(self) -> dict[str, Any]:
        """Get summary of all stored data for the current exchange."""
        summary: dict[str, Any] = {
            "version": self.version,
            "exchange_id": self.exchange_id,
            "base_dir": str(self.base_dir),
            "markets": {},
        }

        for market_id in self.list_markets():
            market_summary: dict[str, Any] = {}
            for interval in self.list_intervals(market_id):
                metadata = self.load_metadata(market_id, interval)
                if metadata:
                    market_summary[interval] = {
                        "candle_count": metadata.candle_count,
                        "start_time": metadata.start_time.isoformat()
                        if metadata.start_time
                        else None,
                        "end_time": metadata.end_time.isoformat() if metadata.end_time else None,
                        "gaps": len(metadata.gaps),
                    }
            summary["markets"][market_id] = market_summary

        return summary

    # Schema version for Parquet files.
    # v1: float64 columns (legacy, precision loss)
    # v2: string columns for Decimal fields (lossless round-trip)
    PARQUET_SCHEMA_VERSION = 2

    def _candles_to_dataframe(self, candles: list[Candle]) -> pd.DataFrame:
        """Convert Candle objects to DataFrame.

        [R-H3] Decimal fields are stored as strings to preserve precision.
        Float64 representation loses Decimal precision (e.g., 0.1 + 0.2 != 0.3).
        String round-trip is lossless: str(Decimal) -> Decimal(str).
        """
        records = [
            {
                "timestamp": c.timestamp,
                "open": str(c.open),
                "high": str(c.high),
                "low": str(c.low),
                "close": str(c.close),
                "volume": str(c.volume),
                "quote_volume": str(c.quote_volume),
                "trade_count": c.trade_count,
            }
            for c in candles
        ]

        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        return df.sort_values("timestamp").reset_index(drop=True)

    def _dataframe_to_candles(self, df: pd.DataFrame, market_id: MarketId) -> list[Candle]:
        """Convert DataFrame to Candle objects."""
        candles: list[Candle] = []

        for _, row in df.iterrows():
            candle = Candle(
                market_id=market_id,
                timestamp=row["timestamp"].to_pydatetime(),
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                quote_volume=Decimal(str(row["quote_volume"])),
                trade_count=int(row.get("trade_count", 0)),
            )
            candles.append(candle)

        return candles

    def delete_market_data(self, market_id: MarketId, interval: str | None = None) -> None:
        """
        Delete stored data for a market (optionally specific interval).

        Args:
            market_id: Market identifier
            interval: Specific interval to delete (None = all intervals)
        """
        import shutil

        target = (
            self._market_dir(market_id, interval) if interval else self._exchange_dir() / market_id
        )

        if target.exists():
            shutil.rmtree(target)
            logger.info(
                "market_data_deleted",
                market_id=market_id,
                exchange_id=self.exchange_id,
                interval=interval,
                path=str(target),
            )
