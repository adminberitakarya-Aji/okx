"""Tests for Telegram message formatters."""

from datetime import UTC, datetime
from decimal import Decimal

from trading_grid.infrastructure.telegram.formatters import (
    format_account_created,
    format_account_status,
    format_approval_request,
    format_error,
    format_grid_status,
    format_header,
    format_live_confirmation,
    format_main_menu,
    format_market_detail,
    format_okx_not_connected,
    format_research_menu,
    format_settings,
    format_success,
    format_top10_list,
    format_unlink_warning,
    format_welcome_back,
    format_welcome_new_user,
)


class TestFormatHeader:
    def test_demo_environment(self):
        result = format_header("Test Menu", "DEMO")
        assert "Test Menu" in result
        assert "🟢 DEMO" in result

    def test_live_environment(self):
        result = format_header("Test Menu", "LIVE")
        assert "🔴 LIVE" in result

    def test_default_environment_is_demo(self):
        result = format_header("Test Menu")
        assert "🟢 DEMO" in result


class TestFormatWelcomeNewUser:
    def test_with_name(self):
        result = format_welcome_new_user("Alice")
        assert "Alice" in result
        assert "AI TRADING GRID" in result

    def test_without_name(self):
        result = format_welcome_new_user(None)
        assert "Trader" in result


class TestFormatWelcomeBack:
    def test_okx_connected_and_verified(self):
        result = format_welcome_back("Bob", "DEMO", okx_connected=True, okx_verified=True)
        assert "Bob" in result
        assert "Connected & Verified" in result
        assert "READY" in result

    def test_okx_connected_not_verified(self):
        result = format_welcome_back("Bob", "DEMO", okx_connected=True, okx_verified=False)
        assert "Connected" in result
        assert "NOT READY" in result

    def test_okx_not_connected(self):
        result = format_welcome_back("Bob", "LIVE", okx_connected=False, okx_verified=False)
        assert "Not connected" in result
        assert "🔴 LIVE" in result

    def test_without_name(self):
        result = format_welcome_back(None, "DEMO", okx_connected=False, okx_verified=False)
        assert "Trader" in result


class TestFormatAccountCreated:
    def test_with_display_name(self):
        result = format_account_created("user-123", "Alice")
        assert "user-123" in result
        assert "Alice" in result
        assert "Account Created" in result

    def test_without_display_name(self):
        result = format_account_created("user-123", None)
        assert "Trader" in result


class TestFormatMainMenu:
    def test_demo_connected(self):
        result = format_main_menu("DEMO", okx_connected=True, active_grids=3)
        assert "🟢 DEMO" in result
        assert "CONNECTED" in result
        assert "3" in result

    def test_live_not_connected(self):
        result = format_main_menu("LIVE", okx_connected=False, active_grids=0)
        assert "🔴 LIVE" in result
        assert "NOT CONNECTED" in result


class TestFormatResearchMenu:
    def test_with_last_update(self):
        dt = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)
        result = format_research_menu(last_update=dt)
        assert "2026-08-16 12:00 UTC" in result

    def test_without_last_update(self):
        result = format_research_menu(last_update=None)
        assert "Never" in result


class TestFormatTop10List:
    def test_empty_rankings(self):
        result = format_top10_list(None)
        assert "No research data" in result

    def test_empty_list(self):
        result = format_top10_list([])
        assert "No research data" in result

    def test_with_rankings(self):
        rankings = [
            {"market_id": "BTC-USDT", "rank": 1, "suitability": "HIGH", "score": 0.95},
            {"market_id": "ETH-USDT", "rank": 2, "suitability": "MEDIUM", "score": 0.85},
            {"market_id": "SOL-USDT", "rank": 3, "suitability": "LOW", "score": 0.75},
            {"market_id": "ADA-USDT", "rank": 4, "suitability": "HIGH", "score": 0.70},
        ]
        result = format_top10_list(rankings)
        assert "🥇" in result
        assert "🥈" in result
        assert "🥉" in result
        assert "#4" in result
        assert "BTC-USDT" in result
        assert "HIGH" in result

    def test_limits_to_10(self):
        rankings = [
            {"market_id": f"M{i}-USDT", "rank": i, "suitability": "HIGH"} for i in range(15)
        ]
        result = format_top10_list(rankings)
        assert "M9-USDT" in result
        assert "M10-USDT" not in result


class TestFormatMarketDetail:
    def test_full_detail(self):
        result = format_market_detail(
            market_id="BTC-USDT",
            rank=1,
            suitability="HIGH",
            prob_positive_pnl=Decimal("0.85"),
            expected_pnl_pct=Decimal("12.5"),
            expected_drawdown_pct=Decimal("5.2"),
            monthly_regime="BULLISH",
            weekly_regime="RANGING",
            daily_regime="VOLATILE",
            execution_quality="GOOD",
        )
        assert "BTC-USDT" in result
        assert "#1" in result
        assert "HIGH" in result
        assert "85%" in result
        assert "+12.5%" in result
        assert "5.2%" in result
        assert "BULLISH" in result
        assert "GOOD" in result

    def test_minimal_detail(self):
        result = format_market_detail(market_id="ETH-USDT")
        assert "ETH-USDT" in result
        assert "N/A" in result


class TestFormatGridStatus:
    def test_running_grid(self):
        result = format_grid_status(
            grid_id="GRID-001",
            market_id="BTC-USDT",
            status="RUNNING",
            environment="DEMO",
            pnl=Decimal("15.50"),
            orders_filled=10,
        )
        assert "GRID-001" in result
        assert "🟢" in result
        assert "RUNNING" in result
        assert "+15.50 USDT" in result
        assert "10" in result

    def test_paused_grid(self):
        result = format_grid_status(
            grid_id="GRID-002",
            market_id="ETH-USDT",
            status="PAUSED",
            environment="LIVE",
        )
        assert "🟡" in result
        assert "🔴 LIVE" in result

    def test_stopped_grid(self):
        result = format_grid_status(
            grid_id="GRID-003",
            market_id="SOL-USDT",
            status="STOPPED",
            environment="DEMO",
        )
        assert "🔴" in result

    def test_unknown_status(self):
        result = format_grid_status(
            grid_id="GRID-004",
            market_id="BTC-USDT",
            status="UNKNOWN",
            environment="DEMO",
        )
        assert "⚪" in result


class TestFormatAccountStatus:
    def test_connected_verified_with_balance(self):
        result = format_account_status(
            environment="DEMO",
            okx_connected=True,
            okx_verified=True,
            balance_usdt=Decimal("1000.50"),
        )
        assert "Connected & Verified" in result
        assert "1,000.50 USDT" in result

    def test_not_connected_no_balance(self):
        result = format_account_status(
            environment="LIVE",
            okx_connected=False,
            okx_verified=False,
        )
        assert "Not connected" in result
        assert "N/A" in result


class TestFormatOkxNotConnected:
    def test_message(self):
        result = format_okx_not_connected()
        assert "OKX Not Connected" in result
        assert "web dashboard" in result


class TestFormatApprovalRequest:
    def test_live_approval(self):
        result = format_approval_request(
            approval_id="APR-001",
            operation="START_GRID",
            market_id="BTC-USDT",
            blueprint_id="BP-001",
            capital=Decimal("500.00"),
            expected_pnl_pct=Decimal("10.5"),
            expected_drawdown_pct=Decimal("3.2"),
            environment="LIVE",
        )
        assert "LIVE TRADING APPROVAL" in result
        assert "APR-001" in result
        assert "START_GRID" in result
        assert "BTC-USDT" in result
        assert "$500.00" in result

    def test_demo_approval(self):
        result = format_approval_request(
            approval_id="APR-002",
            operation="START_GRID",
            market_id="ETH-USDT",
            blueprint_id=None,
            capital=None,
            expected_pnl_pct=None,
            expected_drawdown_pct=None,
            environment="DEMO",
        )
        assert "APPROVAL REQUIRED" in result
        assert "N/A" in result


class TestFormatLiveConfirmation:
    def test_with_capital(self):
        result = format_live_confirmation("APR-001", "BTC-USDT", Decimal("1000.00"))
        assert "LIVE TRADING CONFIRMATION" in result
        assert "$1,000.00" in result
        assert "REAL funds" in result

    def test_without_capital(self):
        result = format_live_confirmation("APR-002", "ETH-USDT", None)
        assert "N/A" in result


class TestFormatSettings:
    def test_notifications_enabled(self):
        result = format_settings("DEMO", notifications_enabled=True)
        assert "✅ Enabled" in result

    def test_notifications_disabled(self):
        result = format_settings("LIVE", notifications_enabled=False)
        assert "❌ Disabled" in result
        assert "🔴 LIVE" in result


class TestFormatUnlinkWarning:
    def test_message(self):
        result = format_unlink_warning()
        assert "Unlink Telegram" in result
        assert "Warning" in result
        assert "Are you sure?" in result


class TestFormatError:
    def test_message(self):
        result = format_error("Something went wrong")
        assert "❌" in result
        assert "Something went wrong" in result


class TestFormatSuccess:
    def test_message(self):
        result = format_success("Operation completed")
        assert "✅" in result
        assert "Operation completed" in result
