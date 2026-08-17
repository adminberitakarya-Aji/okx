"""
Binance historical data client for research ingestion.

This module downloads historical market data from Binance public API:
- Klines (OHLCV) with pagination
- Rate limit handling with exponential backoff
- Data validation (gaps, duplicates)

Binance API endpoints used (public, no auth required):
- GET /api/v3/klines — candlestick data (max 1000 per request)

Reference: https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints#klinecandlestick-data
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

from trading_grid.domain.market.models import Candle
from trading_grid.infrastructure.exchange.symbols import to_concatenated_symbol

if TYPE_CHECKING:
    from trading_grid.domain.shared.types import MarketId

logger = structlog.get_logger()

# Binance API constants
BINANCE_BASE_URL = "https://api.binance.com"
BINANCE_FALLBACK_URLS = [
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
]
KLINES_ENDPOINT = "/api/v3/klines"
MAX_KLINES_PER_REQUEST = 1000

# Rate limiting: Binance public endpoints allow 1200 weight per minute
# klines endpoint has weight 2, so ~600 requests/min = 10 req/s
# We use a conservative 5 req/s to stay safe
RATE_LIMIT_REQUESTS_PER_SECOND = 5.0
REQUEST_INTERVAL = 1.0 / RATE_LIMIT_REQUESTS_PER_SECOND

# Interval mapping: OKX-style → Binance-style
# OKX uses "1H", "4H", "1D"; Binance uses "1h", "4h", "1d"
INTERVAL_MAP = {
    "1m": "1m",
    "3m": "3m",
    "5m": "5m",
    "15m": "15m",
    "30m": "30m",
    "1H": "1h",
    "2H": "2h",
    "4H": "4h",
    "6H": "6h",
    "8H": "8h",
    "12H": "12h",
    "1D": "1d",
    "3D": "3d",
    "1W": "1w",
    "1M": "1M",
}


@dataclass
class BinanceIngestionStats:
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


class BinanceDataError(Exception):
    """Error from Binance data API."""

    def __init__(self, message: str, code: int = -1, data: Any = None) -> None:
        self.code = code
        self.data = data
        super().__init__(message)


class BinanceRateLimitError(BinanceDataError):
    """Rate limit exceeded."""

    def __init__(self, message: str = "Rate limit exceeded") -> None:
        super().__init__(message, code=429)


class BinanceHistoricalClient:
    """
    Client for downloading historical data from Binance.

    This client:
    - Uses only public endpoints (no authentication)
    - Supports automatic fallback to mirror endpoints (e.g. data-api.binance.vision)
    - Handles rate limiting with token bucket + exponential backoff
    - Paginates through historical data automatically
    - Validates data integrity (gaps, duplicates)

    Usage:
        async with BinanceHistoricalClient() as client:
            candles = await client.download_candles(
                market_id="BTC-USDT",
                interval="1H",
                start=datetime(2023, 1, 1, tzinfo=UTC),
                end=datetime(2024, 1, 1, tzinfo=UTC),
            )
    """

    def __init__(
        self,
        base_url: str = BINANCE_BASE_URL,
        fallback_urls: list[str] | None = None,
        timeout: float = 30.0,
        max_retries: int = 5,
    ) -> None:
        """
        Initialize the Binance historical data client.

        Args:
            base_url: Binance API base URL (default: https://api.binance.com)
            fallback_urls: Optional list of fallback URLs to try if primary fails
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts for failed requests
        """
        self.base_url = base_url.rstrip("/")
        if fallback_urls is not None:
            self.fallback_urls = [u.rstrip("/") for u in fallback_urls]
        else:
            self.fallback_urls = [
                u.rstrip("/") for u in BINANCE_FALLBACK_URLS if u.rstrip("/") != self.base_url
            ]
        self._endpoints = [self.base_url, *self.fallback_urls]
        self._current_endpoint_idx = 0
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    @property
    def active_base_url(self) -> str:
        """Get currently active base URL."""
        return self._endpoints[self._current_endpoint_idx]

    async def __aenter__(self) -> BinanceHistoricalClient:
        """Enter async context."""
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=5.0),
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
        retry=retry_if_exception_type((httpx.TransportError, BinanceRateLimitError)),
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=1, max=30),
        reraise=True,
    )
    async def _request(self, endpoint: str, params: dict[str, str]) -> list[list[Any]]:
        """
        Make a rate-limited request to Binance API with automatic fallback.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            List of kline data rows

        Raises:
            BinanceDataError: If API returns an error
            BinanceRateLimitError: If rate limited (triggers retry)
        """
        await self._rate_limit_wait()

        if self._client is None:
            raise RuntimeError("Client not initialized. Use 'async with' context manager.")

        # Try active endpoint and switch to fallback on TransportError
        while True:
            current_url = f"{self.active_base_url}{endpoint}"
            try:
                response = await self._client.get(current_url, params=params)
                break
            except httpx.TransportError as exc:
                if self._current_endpoint_idx + 1 < len(self._endpoints):
                    failed_url = self.active_base_url
                    self._current_endpoint_idx += 1
                    logger.warning(
                        "binance_endpoint_unreachable_switching_to_fallback",
                        failed_endpoint=failed_url,
                        fallback_endpoint=self.active_base_url,
                        error=str(exc),
                    )
                    continue
                # All endpoints exhausted, raise for tenacity retry
                raise

        if response.status_code == 429:
            raise BinanceRateLimitError("Binance rate limit exceeded (HTTP 429)")

        if response.status_code == 418:
            raise BinanceRateLimitError("Binance IP banned due to rate limit abuse (HTTP 418)")

        response.raise_for_status()
        data = response.json()

        # Binance returns error as {"code": -1121, "msg": "..."}
        if isinstance(data, dict) and "code" in data:
            raise BinanceDataError(
                f"Binance API error: {data.get('msg', 'Unknown error')}",
                code=data.get("code", -1),
                data=data,
            )

        result: list[list[Any]] = data
        return result

    def _to_binance_interval(self, interval: str) -> str:
        """Convert OKX-style interval to Binance-style."""
        if interval in INTERVAL_MAP:
            return INTERVAL_MAP[interval]
        # Try lowercase as fallback
        lower = interval.lower()
        if lower in INTERVAL_MAP.values():
            return lower
        raise ValueError(f"Unsupported interval: {interval}")

    async def download_candles(
        self,
        market_id: MarketId,
        interval: str = "1H",
        start: datetime | None = None,
        end: datetime | None = None,
        max_candles: int | None = None,
    ) -> tuple[list[Candle], BinanceIngestionStats]:
        """
        Download historical candles for a market.

        Paginates forward from `start` to `end` using startTime parameter.
        Binance returns candles in ascending order (oldest first).

        Args:
            market_id: Market identifier (e.g., "BTC-USDT")
            interval: Candle interval (1m, 5m, 15m, 30m, 1H, 4H, 1D, etc.)
            start: Start time (inclusive). If None, downloads as far back as possible.
            end: End time (inclusive). If None, uses current time.
            max_candles: Maximum number of candles to download (None = unlimited)

        Returns:
            Tuple of (list of Candle objects sorted ascending by time, BinanceIngestionStats)
        """
        stats = BinanceIngestionStats(market_id=market_id, interval=interval)

        if end is None:
            end = datetime.now(UTC)

        # Convert to millisecond timestamps (Binance uses ms)
        end_ms = int(end.timestamp() * 1000)
        start_ms = int(start.timestamp() * 1000) if start else 0

        # Convert market_id to Binance symbol format
        binance_symbol = to_concatenated_symbol(market_id)
        binance_interval = self._to_binance_interval(interval)

        all_rows: list[list[Any]] = []
        current_start_ms = start_ms

        logger.info(
            "candle_download_started",
            market_id=market_id,
            exchange="BINANCE",
            interval=interval,
            start=start.isoformat() if start else None,
            end=end.isoformat(),
        )

        while True:
            # Check max candles limit
            if max_candles and len(all_rows) >= max_candles:
                all_rows = all_rows[:max_candles]
                break

            params: dict[str, str] = {
                "symbol": binance_symbol,
                "interval": binance_interval,
                "limit": str(MAX_KLINES_PER_REQUEST),
                "startTime": str(current_start_ms),
                "endTime": str(end_ms),
            }

            rows = await self._request(KLINES_ENDPOINT, params)
            stats.total_requests += 1

            if not rows:
                logger.info("no_more_candles", market_id=market_id, total=len(all_rows))
                break

            all_rows.extend(rows)
            stats.total_candles = len(all_rows)

            # Binance returns ascending order; last row is newest
            # Use newest timestamp + 1ms as next pagination cursor
            newest_ts = int(rows[-1][0])
            current_start_ms = newest_ts + 1

            # Stop if we've reached the end time
            if newest_ts >= end_ms:
                break

            # Stop if we got less than max (no more data)
            if len(rows) < MAX_KLINES_PER_REQUEST:
                break

            # Log progress periodically
            if stats.total_requests % 10 == 0:
                newest_dt = datetime.fromtimestamp(newest_ts / 1000, tz=UTC)
                logger.info(
                    "download_progress",
                    market_id=market_id,
                    exchange="BINANCE",
                    candles=len(all_rows),
                    newest=newest_dt.isoformat(),
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
            exchange="BINANCE",
            interval=interval,
            candles=len(candles),
            requests=stats.total_requests,
            duplicates_removed=duplicates,
            duration_seconds=stats.duration_seconds,
        )

        return candles, stats

    def _rows_to_candles(
        self,
        rows: list[list[Any]],
        market_id: MarketId,
        start_ms: int,
        end_ms: int,
    ) -> list[Candle]:
        """
        Convert Binance API rows to Candle domain objects.

        Binance kline format:
        [0] open_time - timestamp (ms)
        [1] open - open price
        [2] high - high price
        [3] low - low price
        [4] close - close price
        [5] volume - volume (base currency)
        [6] close_time - timestamp (ms)
        [7] quote_volume - volume (quote currency)
        [8] trade_count - number of trades
        [9] taker_buy_base - taker buy base volume
        [10] taker_buy_quote - taker buy quote volume
        [11] ignore
        """
        candles: list[Candle] = []

        for row in rows:
            if len(row) < 9:
                continue

            ts_ms = int(row[0])

            # Filter by time range
            if start_ms and ts_ms < start_ms:
                continue
            if ts_ms > end_ms:
                continue

            try:
                candle = Candle(
                    market_id=market_id,
                    timestamp=datetime.fromtimestamp(ts_ms / 1000, tz=UTC),
                    open=Decimal(str(row[1])),
                    high=Decimal(str(row[2])),
                    low=Decimal(str(row[3])),
                    close=Decimal(str(row[4])),
                    volume=Decimal(str(row[5])),
                    quote_volume=Decimal(str(row[7])),
                    trade_count=int(row[8]),
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
        """Convert interval string to seconds."""
        units = {"m": 60, "H": 3600, "h": 3600, "D": 86400, "d": 86400, "W": 604800, "w": 604800}

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
        limit: int = MAX_KLINES_PER_REQUEST,
    ) -> list[Candle]:
        """
        Get recent candles (up to 1000) from the klines endpoint.

        Args:
            market_id: Market identifier
            interval: Candle interval
            limit: Number of candles (max 1000)

        Returns:
            List of Candle objects sorted ascending by time
        """
        limit = min(limit, MAX_KLINES_PER_REQUEST)

        binance_symbol = to_concatenated_symbol(market_id)
        binance_interval = self._to_binance_interval(interval)

        params: dict[str, str] = {
            "symbol": binance_symbol,
            "interval": binance_interval,
            "limit": str(limit),
        }

        rows = await self._request(KLINES_ENDPOINT, params)
        candles = self._rows_to_candles(
            rows, market_id, 0, int(datetime.now(UTC).timestamp() * 1000)
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
            except (BinanceDataError, httpx.HTTPError):
                continue

        return available
