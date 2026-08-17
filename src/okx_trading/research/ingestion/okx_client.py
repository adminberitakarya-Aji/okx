"""
OKX historical data client for research ingestion.

This module downloads historical market data from OKX public API:
- Candles (OHLCV) with pagination
- Rate limit handling with exponential backoff
- Data validation (gaps, duplicates)

OKX API endpoints used (public, no auth required):
- GET /api/v5/market/candles — recent candles (max 300)
- GET /api/v5/market/history-candles — historical candles (max 100 per request)

Reference: https://www.okx.com/docs-v5/en/#order-book-trading-market-data-get-candlesticks
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from okx_trading.domain.market.models import Candle

if TYPE_CHECKING:
    from okx_trading.domain.shared.types import MarketId

logger = structlog.get_logger()

# OKX API constants
OKX_BASE_URL = "https://www.okx.com"
CANDLES_ENDPOINT = "/api/v5/market/candles"
HISTORY_CANDLES_ENDPOINT = "/api/v5/market/history-candles"
MAX_CANDLES_PER_REQUEST = 100  # history-candles limit
MAX_RECENT_CANDLES = 300  # candles endpoint limit

# Rate limiting: OKX public endpoints allow 20 requests per 2 seconds
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 2.0
REQUEST_INTERVAL = RATE_LIMIT_WINDOW_SECONDS / RATE_LIMIT_REQUESTS  # 0.1s between requests


@dataclass
class IngestionStats:
    """Statistics for a data ingestion run."""

    market_id: MarketId
    interval: str
    total_requests: int = 0
    total_candles: int = 0
    duplicates_removed: int = 0
    gaps_detected: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    @property
    def duration_seconds(self) -> float | None:
        """Get ingestion duration in seconds."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()


class OKXDataError(Exception):
    """Error from OKX data API."""

    def __init__(self, message: str, code: str = "UNKNOWN", data: Any = None) -> None:
        self.code = code
        self.data = data
        super().__init__(message)


class RateLimitError(OKXDataError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, code="RATE_LIMIT")


class OKXHistoricalClient:
    """
    Client for downloading historical data from OKX.

    This client:
    - Uses only public endpoints (no authentication)
    - Handles rate limiting with token bucket + exponential backoff
    - Paginates through historical data automatically
    - Validates data integrity (gaps, duplicates)

    Usage:
        async with OKXHistoricalClient() as client:
            candles = await client.download_candles(
                market_id="BTC-USDT",
                interval="1H",
                start=datetime(2023, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 1, tzinfo=UTC),
            )
    """

    def __init__(
        self,
        base_url: str = OKX_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 5,
    ) -> None:
        """
        Initialize the OKX historical data client.

        Args:
            base_url: OKX API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> OKXHistoricalClient:
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"User-Agent": "okx-trading-research/0.1.0"},
        )
        return self

    async def __aexit__(self, *args: object) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _rate_limit_wait(self) -> None:
        """Wait to respect rate limits."""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request_time
            if elapsed < REQUEST_INTERVAL:
                await asyncio.sleep(REQUEST_INTERVAL - elapsed)
            self._last_request_time = asyncio.get_event_loop().time()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, RateLimitError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _request(self, endpoint: str, params: dict[str, str]) -> list[list[str]]:
        """
        Make a rate-limited request to OKX API.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            List of candle data rows

        Raises:
            OKXDataError: If API returns an error
            RateLimitError: If rate limited (triggers retry)
        """
        await self._rate_limit_wait()

        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        response = await self._client.get(endpoint, params=params)

        if response.status_code == 429:
            raise RateLimitError("OKX rate limit exceeded (HTTP 429)")

        response.raise_for_status()
        data = response.json()

        if data.get("code") != "0":
            raise OKXDataError(
                f"OKX API error: {data.get('msg', 'Unknown error')}",
                code=data.get("code", "UNKNOWN"),
                data=data,
            )

        result: list[list[str]] = data.get("data", [])
        return result

    async def download_candles(
        self,
        market_id: MarketId,
        interval: str = "1H",
        start: datetime | None = None,
        end: datetime | None = None,
        max_candles: int | None = None,
    ) -> tuple[list[Candle], IngestionStats]:
        """
        Download historical candles for a market.

        Paginates backwards from `end` to `start` using the `after` parameter.
        OKX returns candles in descending order (newest first).

        Args:
            market_id: Market identifier (e.g., "BTC-USDT")
            interval: Candle interval (1m, 5m, 15m, 30m, 1H, 4H, 1D, etc.)
            start: Start time (inclusive). If None, downloads as far back as possible.
            end: End time (inclusive). If None, uses current time.
            max_candles: Maximum number of candles to download (None = unlimited)

        Returns:
            Tuple of (list of Candle objects sorted ascending by time, IngestionStats)
        """
        stats = IngestionStats(market_id=market_id, interval=interval)

        if end is None:
            end = datetime.now(UTC)

        # Convert to millisecond timestamps (OKX uses ms)
        end_ms = int(end.timestamp() * 1000)
        start_ms = int(start.timestamp() * 1000) if start else None

        all_rows: list[list[str]] = []
        after_ms = end_ms  # Pagination cursor: get candles before this time

        logger.info(
            "candle_download_started",
            market_id=market_id,
            interval=interval,
            start=start.isoformat() if start else None,
            end=end.isoformat(),
        )

        while True:
            # Check max candles limit
            if max_candles and len(all_rows) >= max_candles:
                all_rows = all_rows[:max_candles]
                break

            params = {
                "instId": market_id,
                "bar": interval,
                "limit": str(MAX_CANDLES_PER_REQUEST),
                "after": str(after_ms),
            }

            rows = await self._request(HISTORY_CANDLES_ENDPOINT, params)
            stats.total_requests += 1

            if not rows:
                logger.info("no_more_candles", market_id=market_id, total=len(all_rows))
                break

            all_rows.extend(rows)
            stats.total_candles = len(all_rows)

            # OKX returns descending order; last row is oldest
            # Use oldest timestamp as next pagination cursor
            oldest_ts = int(rows[-1][0])
            after_ms = oldest_ts

            # Stop if we've reached the start time
            if start_ms and oldest_ts <= start_ms:
                break

            # Log progress periodically
            if stats.total_requests % 10 == 0:
                oldest_dt = datetime.fromtimestamp(oldest_ts / 1000, tz=UTC)
                logger.info(
                    "download_progress",
                    market_id=market_id,
                    candles=len(all_rows),
                    oldest=oldest_dt.isoformat(),
                )

        # Convert to Candle objects and sort ascending
        candles = self._rows_to_candles(all_rows, market_id, start_ms, end_ms)
        candles.sort(key=lambda c: c.timestamp)

        # Remove duplicates
        candles, duplicates = self._remove_duplicates(candles)
        stats.duplicates_removed = duplicates

        stats.completed_at = datetime.now(UTC)

        logger.info(
            "candle_download_completed",
            market_id=market_id,
            interval=interval,
            candles=len(candles),
            requests=stats.total_requests,
            duplicates_removed=duplicates,
            duration_seconds=stats.duration_seconds,
        )

        return candles, stats

    def _rows_to_candles(
        self,
        rows: list[list[str]],
        market_id: MarketId,
        start_ms: int | None,
        end_ms: int,
    ) -> list[Candle]:
        """
        Convert OKX API rows to Candle domain objects.

        OKX candle format:
        [0] ts - timestamp (ms)
        [1] o - open price
        [2] h - high price
        [3] l - low price
        [4] c - close price
        [5] vol - volume (base currency)
        [6] volCcy - volume (quote currency)
        [7] volCcyQuote - quote volume
        [8] confirm - 0 = incomplete, 1 = complete
        """
        candles: list[Candle] = []

        for row in rows:
            if len(row) < 6:
                continue

            ts_ms = int(row[0])

            # Filter by time range
            if start_ms and ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                continue

            # Skip incomplete candles (last candle may be incomplete)
            if len(row) > 8 and row[8] == "0":
                continue

            try:
                candle = Candle(
                    market_id=market_id,
                    timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                    open=Decimal(row[1]),
                    high=Decimal(row[2]),
                    low=Decimal(row[3]),
                    close=Decimal(row[4]),
                    volume=Decimal(row[5]),
                    quote_volume=Decimal(row[6]) if len(row) > 6 else Decimal("0"),
                )
                candles.append(candle)
            except (ValueError, ArithmeticError) as e:
                logger.warning("invalid_candle_row", row=row, error=str(e))
                continue

        return candles

    def _remove_duplicates(self, candles: list[Candle]) -> tuple[list[Candle], int]:
        """Remove duplicate candles (same timestamp), keeping first occurrence."""
        seen: set[datetime] = set()
        unique: list[Candle] = []
        duplicates = 0

        for candle in candles:
            if candle.timestamp in seen:
                duplicates += 1
            else:
                seen.add(candle.timestamp)
                unique.append(candle)

        return unique, duplicates

    def validate_candles(
        self,
        candles: list[Candle],
        interval: str,
    ) -> list[str]:
        """
        Validate candle data integrity.

        Checks:
        1. Candles are sorted by timestamp
        2. No duplicate timestamps
        3. Detects gaps in data

        Args:
            candles: List of candles to validate
            interval: Expected interval (for gap detection)

        Returns:
            List of validation warnings/errors (empty if valid)
        """
        issues: list[str] = []

        if not candles:
            issues.append("No candles to validate")
            return issues

        # Check sorted
        for i in range(1, len(candles)):
            if candles[i].timestamp < candles[i - 1].timestamp:
                issues.append(f"Candles not sorted at index {i}")
                break

        # Check duplicates
        timestamps = [c.timestamp for c in candles]
        if len(timestamps) != len(set(timestamps)):
            issues.append("Duplicate timestamps detected")

        # Check gaps
        expected_interval = self._interval_to_seconds(interval)
        gaps = self._detect_gaps(candles, expected_interval)
        if gaps:
            issues.append(f"{len(gaps)} gaps detected in candle data")

        return issues

    def _detect_gaps(
        self,
        candles: list[Candle],
        expected_interval_seconds: int,
    ) -> list[tuple[datetime, datetime]]:
        """Detect gaps in candle data."""
        gaps: list[tuple[datetime, datetime]] = []

        for i in range(1, len(candles)):
            prev_ts = candles[i - 1].timestamp
            curr_ts = candles[i].timestamp
            diff = (curr_ts - prev_ts).total_seconds()

            # Allow small tolerance for timestamp precision
            if diff > expected_interval_seconds * 1.5:
                gaps.append((prev_ts, curr_ts))

        return gaps

    def _interval_to_seconds(self, interval: str) -> int:
        """Convert OKX interval string to seconds."""
        units = {"m": 60, "H": 3600, "D": 86400, "W": 604800, "M": 2592000}

        for suffix, multiplier in units.items():
            if interval.endswith(suffix):
                try:
                    return int(interval[:-1]) * multiplier
                except ValueError:
                    break

        raise ValueError(f"Unknown interval format: {interval}")

    async def get_recent_candles(
        self,
        market_id: MarketId,
        interval: str = "1H",
        limit: int = MAX_RECENT_CANDLES,
    ) -> list[Candle]:
        """
        Get recent candles (up to 300) from the candles endpoint.

        This is faster than history-candles for recent data.

        Args:
            market_id: Market identifier
            interval: Candle interval
            limit: Number of candles (max 300)

        Returns:
            List of Candle objects sorted ascending by time
        """
        limit = min(limit, MAX_RECENT_CANDLES)

        params = {
            "instId": market_id,
            "bar": interval,
            "limit": str(limit),
        }

        rows = await self._request(CANDLES_ENDPOINT, params)
        candles = self._rows_to_candles(
            rows, market_id, None, int(datetime.now(UTC).timestamp() * 1000)
        )
        candles.sort(key=lambda c: c.timestamp)
        return candles

    async def get_available_intervals(self, market_id: MarketId) -> list[str]:
        """
        Check which intervals have data for a market.

        Tests each standard interval with a small request.

        Args:
            market_id: Market identifier

        Returns:
            List of intervals that have data
        """
        standard_intervals = ["1m", "5m", "15m", "30m", "1H", "2H", "4H", "6H", "12H", "1D", "1W"]
        available: list[str] = []

        for interval in standard_intervals:
            try:
                candles = await self.get_recent_candles(market_id, interval, limit=1)
                if candles:
                    available.append(interval)
            except (OKXDataError, httpx.HTTPError):
                continue

        return available
