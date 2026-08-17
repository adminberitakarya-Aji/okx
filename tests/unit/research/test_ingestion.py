"""
Unit tests for research data ingestion.

Tests cover:
1. OKXHistoricalClient: row conversion, deduplication, validation, gap detection
2. BinanceHistoricalClient: row conversion, interval mapping, deduplication
3. BybitHistoricalClient: row conversion, interval mapping, deduplication
4. ParquetStorage: save/load round-trip, metadata, listing, exchange-aware paths
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from trading_grid.domain.market.models import Candle
from trading_grid.research.ingestion.binance_client import (
    BinanceDataError,
    BinanceHistoricalClient,
    BinanceIngestionStats,
    BinanceRateLimitError,
)
from trading_grid.research.ingestion.bybit_client import (
    BybitDataError,
    BybitHistoricalClient,
    BybitIngestionStats,
    BybitRateLimitError,
)
from trading_grid.research.ingestion.okx_client import (
    IngestionStats,
    OKXDataError,
    OKXHistoricalClient,
    RateLimitError,
)
from trading_grid.research.ingestion.storage import DatasetMetadata, ParquetStorage


def make_candle(
    timestamp: datetime,
    market_id: str = "BTC-USDT",
    open_price: Decimal = Decimal("50000"),
    close_price: Decimal = Decimal("50100"),
) -> Candle:
    """Create a test candle."""
    return Candle(
        market_id=market_id,
        timestamp=timestamp,
        open=open_price,
        high=max(open_price, close_price) + Decimal("50"),
        low=min(open_price, close_price) - Decimal("50"),
        close=close_price,
        volume=Decimal("100"),
        quote_volume=Decimal("5000000"),
    )


class TestIngestionStats:
    """Tests for IngestionStats."""

    def test_duration_none_when_not_completed(self) -> None:
        """Duration should be None when not completed."""
        stats = IngestionStats(market_id="BTC-USDT", interval="1H")
        assert stats.duration_seconds is None

    def test_duration_calculated_when_completed(self) -> None:
        """Duration should be calculated when completed."""
        stats = IngestionStats(market_id="BTC-USDT", interval="1H")
        stats.completed_at = stats.started_at + timedelta(seconds=10)
        assert stats.duration_seconds == pytest.approx(10.0)


class TestOKXDataErrors:
    """Tests for OKX data error classes."""

    def test_okx_data_error(self) -> None:
        """OKXDataError should store code and data."""
        err = OKXDataError("test error", code="50011", data={"foo": "bar"})
        assert err.code == "50011"
        assert err.data == {"foo": "bar"}
        assert "test error" in str(err)

    def test_rate_limit_error(self) -> None:
        """RateLimitError should have RATE_LIMIT code."""
        err = RateLimitError()
        assert err.code == "RATE_LIMIT"


class TestRowsToCandles:
    """Tests for OKXHistoricalClient._rows_to_candles."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = OKXHistoricalClient()

    def test_converts_valid_rows(self) -> None:
        """Should convert valid OKX rows to Candle objects."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        ts_ms = int(ts.timestamp() * 1000)

        rows = [
            [str(ts_ms), "50000.5", "50100.0", "49900.0", "50050.0", "123.45", "6172500.0"],
        ]

        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, ts_ms + 1000)

        assert len(candles) == 1
        candle = candles[0]
        assert candle.market_id == "BTC-USDT"
        assert candle.timestamp == ts
        assert candle.open == Decimal("50000.5")
        assert candle.high == Decimal("50100.0")
        assert candle.low == Decimal("49900.0")
        assert candle.close == Decimal("50050.0")
        assert candle.volume == Decimal("123.45")

    def test_skips_short_rows(self) -> None:
        """Should skip rows with fewer than 6 columns."""
        rows = [["1234567890000", "50000", "50100"]]
        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, 9999999999999)
        assert len(candles) == 0

    def test_skips_incomplete_candles(self) -> None:
        """Should skip candles with confirm=0."""
        ts_ms = 1704110400000
        rows = [
            [str(ts_ms), "50000", "50100", "49900", "50050", "100", "5000000", "0", "0"],
        ]
        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, ts_ms + 1000)
        assert len(candles) == 0

    def test_filters_by_time_range(self) -> None:
        """Should filter candles outside time range."""
        ts_ms = 1704110400000
        rows = [
            [str(ts_ms), "50000", "50100", "49900", "50050", "100", "5000000"],
        ]

        # Start after the candle
        candles = self.client._rows_to_candles(rows, "BTC-USDT", ts_ms + 1000, ts_ms + 2000)
        assert len(candles) == 0

        # End before the candle
        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, ts_ms - 1000)
        assert len(candles) == 0

    def test_skips_invalid_decimal_rows(self) -> None:
        """Should skip rows with invalid decimal values."""
        ts_ms = 1704110400000
        rows = [
            [str(ts_ms), "not-a-number", "50100", "49900", "50050", "100", "5000000"],
        ]
        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, ts_ms + 1000)
        assert len(candles) == 0


class TestRemoveDuplicates:
    """Tests for OKXHistoricalClient._remove_duplicates."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = OKXHistoricalClient()

    def test_removes_duplicate_timestamps(self) -> None:
        """Should remove candles with duplicate timestamps."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts), make_candle(ts), make_candle(ts + timedelta(hours=1))]

        unique, duplicates = self.client._remove_duplicates(candles)

        assert len(unique) == 2
        assert duplicates == 1

    def test_no_duplicates(self) -> None:
        """Should return all candles when no duplicates."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts), make_candle(ts + timedelta(hours=1))]

        unique, duplicates = self.client._remove_duplicates(candles)

        assert len(unique) == 2
        assert duplicates == 0


class TestValidateCandles:
    """Tests for OKXHistoricalClient.validate_candles."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = OKXHistoricalClient()

    def test_empty_candles(self) -> None:
        """Should report issue for empty candle list."""
        issues = self.client.validate_candles([], "1H")
        assert len(issues) == 1
        assert "No candles" in issues[0]

    def test_valid_candles(self) -> None:
        """Should return no issues for valid candles."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts + timedelta(hours=i)) for i in range(5)]

        issues = self.client.validate_candles(candles, "1H")
        assert len(issues) == 0

    def test_detects_unsorted_candles(self) -> None:
        """Should detect unsorted candles."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [
            make_candle(ts + timedelta(hours=1)),
            make_candle(ts),
        ]

        issues = self.client.validate_candles(candles, "1H")
        assert any("not sorted" in issue for issue in issues)

    def test_detects_gaps(self) -> None:
        """Should detect gaps in candle data."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [
            make_candle(ts),
            make_candle(ts + timedelta(hours=5)),  # 4-hour gap
        ]

        issues = self.client.validate_candles(candles, "1H")
        assert any("gap" in issue.lower() for issue in issues)


class TestIntervalToSeconds:
    """Tests for OKXHistoricalClient._interval_to_seconds."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = OKXHistoricalClient()

    @pytest.mark.parametrize(
        ("interval", "expected"),
        [
            ("1m", 60),
            ("5m", 300),
            ("15m", 900),
            ("1H", 3600),
            ("4H", 14400),
            ("1D", 86400),
            ("1W", 604800),
        ],
    )
    def test_valid_intervals(self, interval: str, expected: int) -> None:
        """Should convert valid intervals to seconds."""
        assert self.client._interval_to_seconds(interval) == expected

    def test_invalid_interval(self) -> None:
        """Should raise ValueError for unknown interval."""
        with pytest.raises(ValueError, match="Unknown interval"):
            self.client._interval_to_seconds("invalid")


# ---------------------------------------------------------------------------
# Binance Client Tests
# ---------------------------------------------------------------------------


class TestBinanceIngestionStats:
    """Tests for BinanceIngestionStats."""

    def test_duration_none_when_not_completed(self) -> None:
        """Duration should be None when not completed."""
        stats = BinanceIngestionStats(market_id="BTC-USDT", interval="1H")
        assert stats.duration_seconds is None

    def test_duration_calculated_when_completed(self) -> None:
        """Duration should be calculated when completed."""
        stats = BinanceIngestionStats(market_id="BTC-USDT", interval="1H")
        stats.completed_at = stats.started_at + timedelta(seconds=10)
        assert stats.duration_seconds == pytest.approx(10.0)


class TestBinanceDataErrors:
    """Tests for Binance data error classes."""

    def test_binance_data_error(self) -> None:
        """BinanceDataError should store code and data."""
        err = BinanceDataError("test error", code=-1121, data={"foo": "bar"})
        assert err.code == -1121
        assert err.data == {"foo": "bar"}
        assert "test error" in str(err)

    def test_rate_limit_error(self) -> None:
        """BinanceRateLimitError should have 429 code."""
        err = BinanceRateLimitError()
        assert err.code == 429


class TestBinanceRowsToCandles:
    """Tests for BinanceHistoricalClient._rows_to_candles."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = BinanceHistoricalClient()

    def test_converts_valid_rows(self) -> None:
        """Should convert valid Binance rows to Candle objects."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        ts_ms = int(ts.timestamp() * 1000)
        close_ts_ms = ts_ms + 3599999

        rows = [
            [
                ts_ms,  # open_time
                "50000.50",  # open
                "50100.00",  # high
                "49900.00",  # low
                "50050.00",  # close
                "123.45",  # volume
                close_ts_ms,  # close_time
                "6172500.00",  # quote_volume
                1234,  # trade_count
                "60.00",  # taker_buy_base
                "3000000.00",  # taker_buy_quote
                "0",  # ignore
            ],
        ]

        candles = self.client._rows_to_candles(rows, "BTC-USDT", 0, ts_ms + 4000000)

        assert len(candles) == 1
        candle = candles[0]
        assert candle.market_id == "BTC-USDT"
        assert candle.timestamp == ts
        assert candle.open == Decimal("50000.50")
        assert candle.high == Decimal("50100.00")
        assert candle.low == Decimal("49900.00")
        assert candle.close == Decimal("50050.00")
        assert candle.volume == Decimal("123.45")
        assert candle.quote_volume == Decimal("6172500.00")
        assert candle.trade_count == 1234

    def test_skips_short_rows(self) -> None:
        """Should skip rows with fewer than 9 columns."""
        rows = [[1704110400000, "50000", "50100"]]
        candles = self.client._rows_to_candles(rows, "BTC-USDT", 0, 9999999999999)
        assert len(candles) == 0

    def test_filters_by_time_range(self) -> None:
        """Should filter candles outside time range."""
        ts_ms = 1704110400000
        rows = [
            [ts_ms, "50000", "50100", "49900", "50050", "100", ts_ms + 3599999, "5000000", 100],
        ]

        # Start after the candle
        candles = self.client._rows_to_candles(rows, "BTC-USDT", ts_ms + 1000, ts_ms + 2000)
        assert len(candles) == 0

        # End before the candle
        candles = self.client._rows_to_candles(rows, "BTC-USDT", 0, ts_ms - 1000)
        assert len(candles) == 0


class TestBinanceIntervalMapping:
    """Tests for BinanceHistoricalClient._to_binance_interval."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = BinanceHistoricalClient()

    @pytest.mark.parametrize(
        ("okx_interval", "binance_interval"),
        [
            ("1m", "1m"),
            ("5m", "5m"),
            ("15m", "15m"),
            ("30m", "30m"),
            ("1H", "1h"),
            ("2H", "2h"),
            ("4H", "4h"),
            ("6H", "6h"),
            ("12H", "12h"),
            ("1D", "1d"),
            ("1W", "1w"),
        ],
    )
    def test_interval_mapping(self, okx_interval: str, binance_interval: str) -> None:
        """Should map OKX-style intervals to Binance-style."""
        assert self.client._to_binance_interval(okx_interval) == binance_interval

    def test_invalid_interval(self) -> None:
        """Should raise ValueError for unsupported interval."""
        with pytest.raises(ValueError, match="Unsupported interval"):
            self.client._to_binance_interval("invalid")


class TestBinanceRemoveDuplicates:
    """Tests for BinanceHistoricalClient._remove_duplicates."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = BinanceHistoricalClient()

    def test_removes_duplicate_timestamps(self) -> None:
        """Should remove candles with duplicate timestamps."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts), make_candle(ts), make_candle(ts + timedelta(hours=1))]

        unique, duplicates = self.client._remove_duplicates(candles)

        assert len(unique) == 2
        assert duplicates == 1


# ---------------------------------------------------------------------------
# Bybit Client Tests
# ---------------------------------------------------------------------------


class TestBybitIngestionStats:
    """Tests for BybitIngestionStats."""

    def test_duration_none_when_not_completed(self) -> None:
        """Duration should be None when not completed."""
        stats = BybitIngestionStats(market_id="BTC-USDT", interval="1H")
        assert stats.duration_seconds is None

    def test_duration_calculated_when_completed(self) -> None:
        """Duration should be calculated when completed."""
        stats = BybitIngestionStats(market_id="BTC-USDT", interval="1H")
        stats.completed_at = stats.started_at + timedelta(seconds=10)
        assert stats.duration_seconds == pytest.approx(10.0)


class TestBybitDataErrors:
    """Tests for Bybit data error classes."""

    def test_bybit_data_error(self) -> None:
        """BybitDataError should store code and data."""
        err = BybitDataError("test error", code=10001, data={"foo": "bar"})
        assert err.code == 10001
        assert err.data == {"foo": "bar"}
        assert "test error" in str(err)

    def test_rate_limit_error(self) -> None:
        """BybitRateLimitError should have 10006 code."""
        err = BybitRateLimitError()
        assert err.code == 10006


class TestBybitRowsToCandles:
    """Tests for BybitHistoricalClient._rows_to_candles."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = BybitHistoricalClient()

    def test_converts_valid_rows(self) -> None:
        """Should convert valid Bybit rows to Candle objects."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        ts_ms = int(ts.timestamp() * 1000)

        rows = [
            [
                str(ts_ms),  # startTime
                "50000.50",  # open
                "50100.00",  # high
                "49900.00",  # low
                "50050.00",  # close
                "123.45",  # volume
                "6172500.00",  # turnover
            ],
        ]

        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, ts_ms + 1000)

        assert len(candles) == 1
        candle = candles[0]
        assert candle.market_id == "BTC-USDT"
        assert candle.timestamp == ts
        assert candle.open == Decimal("50000.50")
        assert candle.high == Decimal("50100.00")
        assert candle.low == Decimal("49900.00")
        assert candle.close == Decimal("50050.00")
        assert candle.volume == Decimal("123.45")
        assert candle.quote_volume == Decimal("6172500.00")

    def test_skips_short_rows(self) -> None:
        """Should skip rows with fewer than 6 columns."""
        rows = [["1704110400000", "50000", "50100"]]
        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, 9999999999999)
        assert len(candles) == 0

    def test_filters_by_time_range(self) -> None:
        """Should filter candles outside time range."""
        ts_ms = 1704110400000
        rows = [
            [str(ts_ms), "50000", "50100", "49900", "50050", "100", "5000000"],
        ]

        # Start after the candle
        candles = self.client._rows_to_candles(rows, "BTC-USDT", ts_ms + 1000, ts_ms + 2000)
        assert len(candles) == 0

        # End before the candle
        candles = self.client._rows_to_candles(rows, "BTC-USDT", None, ts_ms - 1000)
        assert len(candles) == 0


class TestBybitIntervalMapping:
    """Tests for BybitHistoricalClient._to_bybit_interval."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = BybitHistoricalClient()

    @pytest.mark.parametrize(
        ("okx_interval", "bybit_interval"),
        [
            ("1m", "1"),
            ("5m", "5"),
            ("15m", "15"),
            ("30m", "30"),
            ("1H", "60"),
            ("2H", "120"),
            ("4H", "240"),
            ("6H", "360"),
            ("12H", "720"),
            ("1D", "D"),
            ("1W", "W"),
        ],
    )
    def test_interval_mapping(self, okx_interval: str, bybit_interval: str) -> None:
        """Should map OKX-style intervals to Bybit-style."""
        assert self.client._to_bybit_interval(okx_interval) == bybit_interval

    def test_invalid_interval(self) -> None:
        """Should raise ValueError for unsupported interval."""
        with pytest.raises(ValueError, match="Unsupported interval"):
            self.client._to_bybit_interval("invalid")


class TestBybitRemoveDuplicates:
    """Tests for BybitHistoricalClient._remove_duplicates."""

    def setup_method(self) -> None:
        """Set up test client."""
        self.client = BybitHistoricalClient()

    def test_removes_duplicate_timestamps(self) -> None:
        """Should remove candles with duplicate timestamps."""
        ts = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts), make_candle(ts), make_candle(ts + timedelta(hours=1))]

        unique, duplicates = self.client._remove_duplicates(candles)

        assert len(unique) == 2
        assert duplicates == 1


# ---------------------------------------------------------------------------
# ParquetStorage Tests (Exchange-Aware)
# ---------------------------------------------------------------------------


class TestParquetStorage:
    """Tests for ParquetStorage with exchange-aware paths."""

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        """Should save and load candles correctly."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts + timedelta(hours=i)) for i in range(5)]

        storage.save_candles(candles, "BTC-USDT", "1H")
        loaded = storage.load_candles("BTC-USDT", "1H")

        assert len(loaded) == 5
        assert loaded[0].market_id == "BTC-USDT"
        assert loaded[0].open == candles[0].open
        assert loaded[0].close == candles[0].close

    def test_save_empty_raises_error(self, tmp_path: Path) -> None:
        """Should raise ValueError when saving empty list."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        with pytest.raises(ValueError, match="empty"):
            storage.save_candles([], "BTC-USDT", "1H")

    def test_load_nonexistent_raises_error(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError for non-existent data."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        with pytest.raises(FileNotFoundError):
            storage.load_candles("BTC-USDT", "1H")

    def test_load_with_time_filter(self, tmp_path: Path) -> None:
        """Should filter candles by time range."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts + timedelta(hours=i)) for i in range(10)]

        storage.save_candles(candles, "BTC-USDT", "1H")

        # Load only first 5 hours
        loaded = storage.load_candles("BTC-USDT", "1H", start=ts, end=ts + timedelta(hours=4))
        assert len(loaded) == 5

    def test_metadata_saved_and_loaded(self, tmp_path: Path) -> None:
        """Should save and load metadata correctly."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts + timedelta(hours=i)) for i in range(5)]

        storage.save_candles(candles, "BTC-USDT", "1H", gaps=["gap1"])
        metadata = storage.load_metadata("BTC-USDT", "1H")

        assert metadata is not None
        assert metadata.market_id == "BTC-USDT"
        assert metadata.exchange_id == "OKX"
        assert metadata.interval == "1H"
        assert metadata.candle_count == 5
        assert metadata.start_time == ts
        assert metadata.gaps == ["gap1"]

    def test_list_markets(self, tmp_path: Path) -> None:
        """Should list all markets with data."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts)]

        storage.save_candles(candles, "BTC-USDT", "1H")
        storage.save_candles(candles, "ETH-USDT", "1H")

        markets = storage.list_markets()
        assert markets == ["BTC-USDT", "ETH-USDT"]

    def test_list_intervals(self, tmp_path: Path) -> None:
        """Should list all intervals for a market."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts)]

        storage.save_candles(candles, "BTC-USDT", "1H")
        storage.save_candles(candles, "BTC-USDT", "4H")

        intervals = storage.list_intervals("BTC-USDT")
        assert intervals == ["1H", "4H"]

    def test_list_markets_empty(self, tmp_path: Path) -> None:
        """Should return empty list when no data."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")
        assert storage.list_markets() == []

    def test_delete_market_data(self, tmp_path: Path) -> None:
        """Should delete market data."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts)]

        storage.save_candles(candles, "BTC-USDT", "1H")
        storage.delete_market_data("BTC-USDT", "1H")

        assert storage.list_intervals("BTC-USDT") == []

    def test_get_data_summary(self, tmp_path: Path) -> None:
        """Should return data summary."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts + timedelta(hours=i)) for i in range(5)]

        storage.save_candles(candles, "BTC-USDT", "1H")

        summary = storage.get_data_summary()
        assert summary["version"] == "v1"
        assert summary["exchange_id"] == "OKX"
        assert "BTC-USDT" in summary["markets"]
        assert summary["markets"]["BTC-USDT"]["1H"]["candle_count"] == 5

    def test_exchange_aware_path_structure(self, tmp_path: Path) -> None:
        """Should store data under exchange-specific directory."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="BINANCE")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts)]

        path = storage.save_candles(candles, "BTC-USDT", "1H")

        # Verify path includes exchange_id
        assert "BINANCE" in str(path)
        assert path == tmp_path / "v1" / "BINANCE" / "BTC-USDT" / "1H" / "candles.parquet"

    def test_no_collision_between_exchanges(self, tmp_path: Path) -> None:
        """Same market on different exchanges should NOT collide."""
        okx_storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")
        binance_storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="BINANCE")
        bybit_storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="BYBIT")

        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Different candle data per exchange to verify isolation
        okx_candles = [make_candle(ts, open_price=Decimal("50000"))]
        binance_candles = [make_candle(ts, open_price=Decimal("50001"))]
        bybit_candles = [make_candle(ts, open_price=Decimal("50002"))]

        okx_storage.save_candles(okx_candles, "BTC-USDT", "1H")
        binance_storage.save_candles(binance_candles, "BTC-USDT", "1H")
        bybit_storage.save_candles(bybit_candles, "BTC-USDT", "1H")

        # Load back and verify each exchange has its own data
        okx_loaded = okx_storage.load_candles("BTC-USDT", "1H")
        binance_loaded = binance_storage.load_candles("BTC-USDT", "1H")
        bybit_loaded = bybit_storage.load_candles("BTC-USDT", "1H")

        assert okx_loaded[0].open == Decimal("50000")
        assert binance_loaded[0].open == Decimal("50001")
        assert bybit_loaded[0].open == Decimal("50002")

    def test_list_exchanges(self, tmp_path: Path) -> None:
        """Should list all exchanges with stored data."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        candles = [make_candle(ts)]

        okx_storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="OKX")
        binance_storage = ParquetStorage(base_dir=tmp_path, version="v1", exchange_id="BINANCE")

        okx_storage.save_candles(candles, "BTC-USDT", "1H")
        binance_storage.save_candles(candles, "BTC-USDT", "1H")

        exchanges = okx_storage.list_exchanges()
        assert exchanges == ["BINANCE", "OKX"]

    def test_default_exchange_id_is_okx(self, tmp_path: Path) -> None:
        """Default exchange_id should be OKX for backward compatibility."""
        storage = ParquetStorage(base_dir=tmp_path, version="v1")
        assert storage.exchange_id == "OKX"


class TestDatasetMetadata:
    """Tests for DatasetMetadata."""

    def test_to_dict_and_from_dict_round_trip(self) -> None:
        """Should serialize and deserialize correctly."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        metadata = DatasetMetadata(
            market_id="BTC-USDT",
            exchange_id="OKX",
            interval="1H",
            version="v1",
            candle_count=100,
            start_time=ts,
            end_time=ts + timedelta(hours=99),
        )

        d = metadata.to_dict()
        restored = DatasetMetadata.from_dict(d)

        assert restored.market_id == metadata.market_id
        assert restored.exchange_id == metadata.exchange_id
        assert restored.interval == metadata.interval
        assert restored.candle_count == metadata.candle_count
        assert restored.start_time == metadata.start_time

    def test_exchange_id_required(self) -> None:
        """DatasetMetadata should require exchange_id."""
        ts = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        metadata = DatasetMetadata(
            market_id="BTC-USDT",
            exchange_id="BINANCE",
            interval="1H",
            version="v1",
            candle_count=100,
            start_time=ts,
            end_time=ts,
        )
        assert metadata.exchange_id == "BINANCE"
