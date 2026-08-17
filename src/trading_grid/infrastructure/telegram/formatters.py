"""
Telegram message formatters.

This module provides:
- State-aware welcome messages
- Menu header formatting
- Data display formatting
- Approval request formatting

Security rules:
1. Environment (DEMO/LIVE) is always visible
2. OKX credentials are NEVER displayed
3. Error messages do not leak internal details
"""

from datetime import datetime
from decimal import Decimal


def format_header(title: str, environment: str = "DEMO") -> str:
    """
    Format a menu header with environment badge.

    Args:
        title: Menu title
        environment: DEMO or LIVE

    Returns:
        Formatted header string
    """
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"
    return f"{title}\n━━━━━━━━━━━━━━━━━━\n{env_badge}"


def format_welcome_new_user(first_name: str | None) -> str:
    """
    Format welcome message for new users.

    Args:
        first_name: User's first name from Telegram

    Returns:
        Welcome message HTML
    """
    name = first_name or "Trader"
    return (
        f"🤖 <b>AI TRADING GRID</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome, <b>{name}</b>! 👋\n\n"
        f"This is an AI-assisted grid trading platform.\n\n"
        f"<b>Status:</b>\n"
        f"• Telegram: ✅ Connected\n"
        f"• Account: ❌ Not created\n"
        f"• OKX: ❌ Not connected\n\n"
        f"Create your account to get started."
    )


def format_welcome_back(
    first_name: str | None,
    environment: str,
    okx_connected: bool,
    okx_verified: bool,
) -> str:
    """
    Format welcome back message based on user state.

    Args:
        first_name: User's first name
        environment: DEMO or LIVE
        okx_connected: Whether OKX is connected
        okx_verified: Whether OKX is verified

    Returns:
        Welcome message HTML
    """
    name = first_name or "Trader"
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"

    okx_status = "✅ Connected" if okx_connected else "❌ Not connected"
    if okx_connected and okx_verified:
        okx_status = "✅ Connected & Verified"

    trading_status = "READY" if okx_connected and okx_verified else "NOT READY"

    return (
        f"🤖 <b>AI TRADING GRID</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"Welcome back, <b>{name}</b>!\n\n"
        f"<b>Status:</b>\n"
        f"• Telegram: ✅ Connected\n"
        f"• OKX: {okx_status}\n"
        f"• Environment: {env_badge}\n"
        f"• Trading: {trading_status}\n"
    )


def format_account_created(user_id: str, display_name: str | None) -> str:
    """
    Format account creation success message.

    Args:
        user_id: Application user ID
        display_name: User display name

    Returns:
        Success message HTML
    """
    name = display_name or "Trader"
    return (
        f"✅ <b>Account Created</b>\n\n"
        f"<b>Account:</b> {name}\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n\n"
        f"<b>Status:</b>\n"
        f"• Telegram: ✅ Connected\n"
        f"• OKX: ❌ Not connected\n\n"
        f"Next step: Connect your OKX account to start trading."
    )


def format_main_menu(
    environment: str,
    okx_connected: bool,
    active_grids: int = 0,
) -> str:
    """
    Format the main menu message.

    Args:
        environment: DEMO or LIVE
        okx_connected: Whether OKX is connected
        active_grids: Number of active grids

    Returns:
        Main menu message HTML
    """
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"
    okx_status = "✅ CONNECTED" if okx_connected else "❌ NOT CONNECTED"

    return (
        f"🤖 <b>AI TRADING GRID</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Environment:</b> {env_badge}\n"
        f"<b>OKX:</b> {okx_status}\n"
        f"<b>Active Grids:</b> {active_grids}\n"
    )


def format_research_menu(last_update: datetime | None = None) -> str:
    """
    Format the Research menu message.

    Args:
        last_update: Last research update time

    Returns:
        Research menu message HTML
    """
    update_str = last_update.strftime("%Y-%m-%d %H:%M UTC") if last_update else "Never"

    return (
        f"🔬 <b>AI RESEARCH</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Research Universe:</b>\n"
        f"TOP 10 OKX SPOT\n\n"
        f"<b>Last Update:</b>\n"
        f"{update_str}\n"
    )


def format_top10_list(
    rankings: list[dict[str, object]] | None = None,
) -> str:
    """
    Format the Top 10 market rankings.

    Args:
        rankings: List of market rankings with keys:
            - market_id: str
            - rank: int
            - suitability: str (HIGH/MEDIUM/LOW)
            - score: float

    Returns:
        Top 10 message HTML
    """
    if not rankings:
        return (
            "🏆 <b>TOP 10</b>\n"
            "━━━━━━━━━━━━━━━━━━\n\n"
            "No research data available yet.\n"
            "Run research to generate rankings."
        )

    medals = ["🥇", "🥈", "🥉"]
    lines = [
        "🏆 <b>TOP 10</b>",
        "━━━━━━━━━━━━━━━━━━\n",
    ]

    for i, r in enumerate(rankings[:10]):
        medal = medals[i] if i < 3 else f"#{i + 1}"
        market_id = str(r.get("market_id", "???"))
        suitability = str(r.get("suitability", "N/A"))
        lines.append(f"{medal} <b>{market_id}</b>")
        lines.append(f"   Suitability: {suitability}\n")

    return "\n".join(lines)


def format_market_detail(
    market_id: str,
    rank: int | None = None,
    suitability: str | None = None,
    prob_positive_pnl: Decimal | None = None,
    expected_pnl_pct: Decimal | None = None,
    expected_drawdown_pct: Decimal | None = None,
    monthly_regime: str | None = None,
    weekly_regime: str | None = None,
    daily_regime: str | None = None,
    execution_quality: str | None = None,
) -> str:
    """
    Format market detail view.

    Args:
        market_id: Market ID (e.g., "BTC-USDT")
        rank: Market rank
        suitability: Suitability level
        prob_positive_pnl: Probability of positive net P&L
        expected_pnl_pct: Expected net P&L percentage
        expected_drawdown_pct: Expected drawdown percentage
        monthly_regime: Monthly market regime
        weekly_regime: Weekly market regime
        daily_regime: Daily market regime
        execution_quality: Execution quality assessment

    Returns:
        Market detail message HTML
    """
    rank_str = f"#{rank}" if rank else "N/A"
    suit_str = suitability or "N/A"
    prob_str = f"{prob_positive_pnl:.0%}" if prob_positive_pnl else "N/A"
    pnl_str = f"+{expected_pnl_pct:.1f}%" if expected_pnl_pct else "N/A"
    dd_str = f"{expected_drawdown_pct:.1f}%" if expected_drawdown_pct else "N/A"

    return (
        f"📊 <b>{market_id}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Rank:</b> {rank_str}\n"
        f"<b>Suitability:</b> {suit_str}\n\n"
        f"<b>P(Positive Net P&L):</b> {prob_str}\n"
        f"<b>Expected Net P&L:</b> {pnl_str}\n"
        f"<b>Expected Drawdown:</b> {dd_str}\n\n"
        f"<b>Monthly:</b> {monthly_regime or 'N/A'}\n"
        f"<b>Weekly:</b> {weekly_regime or 'N/A'}\n"
        f"<b>Daily:</b> {daily_regime or 'N/A'}\n\n"
        f"<b>Execution:</b> {execution_quality or 'N/A'}\n"
    )


def format_grid_status(
    grid_id: str,
    market_id: str,
    status: str,
    environment: str,
    pnl: Decimal | None = None,
    orders_filled: int = 0,
) -> str:
    """
    Format grid status message.

    Args:
        grid_id: Grid ID
        market_id: Market ID
        status: Grid status (RUNNING/PAUSED/STOPPED)
        environment: DEMO or LIVE
        pnl: Current P&L
        orders_filled: Number of filled orders

    Returns:
        Grid status message HTML
    """
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"
    status_emoji = {"RUNNING": "🟢", "PAUSED": "🟡", "STOPPED": "🔴"}.get(status, "⚪")
    pnl_str = f"{pnl:+.2f} USDT" if pnl else "0.00 USDT"

    return (
        f"📈 <b>Grid Status</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Grid:</b> <code>{grid_id}</code>\n"
        f"<b>Market:</b> {market_id}\n"
        f"<b>Status:</b> {status_emoji} {status}\n"
        f"<b>Environment:</b> {env_badge}\n\n"
        f"<b>P&L:</b> {pnl_str}\n"
        f"<b>Orders Filled:</b> {orders_filled}\n"
    )


def format_account_status(
    environment: str,
    okx_connected: bool,
    okx_verified: bool,
    balance_usdt: Decimal | None = None,
) -> str:
    """
    Format account status message.

    Args:
        environment: DEMO or LIVE
        okx_connected: Whether OKX is connected
        okx_verified: Whether OKX is verified
        balance_usdt: USDT balance

    Returns:
        Account status message HTML
    """
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"
    okx_status = "✅ Connected" if okx_connected else "❌ Not connected"
    if okx_connected and okx_verified:
        okx_status = "✅ Connected & Verified"

    balance_str = f"{balance_usdt:,.2f} USDT" if balance_usdt else "N/A"

    return (
        f"💰 <b>ACCOUNT</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Environment:</b> {env_badge}\n"
        f"<b>OKX:</b> {okx_status}\n"
        f"<b>Balance:</b> {balance_str}\n"
    )


def format_okx_not_connected() -> str:
    """
    Format the "OKX not connected" warning message.

    Returns:
        Warning message HTML
    """
    return (
        "⚠️ <b>OKX Not Connected</b>\n\n"
        "<b>Status:</b>\n"
        "• Telegram: ✅ Connected\n"
        "• OKX: ❌ Not connected\n\n"
        "To start trading, connect your OKX account.\n\n"
        "🔒 <i>For security, OKX API credentials are entered\n"
        "via the secure web dashboard, not Telegram chat.</i>"
    )


def format_approval_request(
    approval_id: str,
    operation: str,
    market_id: str,
    blueprint_id: str | None,
    capital: Decimal | None,
    expected_pnl_pct: Decimal | None,
    expected_drawdown_pct: Decimal | None,
    environment: str,
) -> str:
    """
    Format approval request message.

    Args:
        approval_id: Approval request ID
        operation: Operation description
        market_id: Market ID
        blueprint_id: Blueprint ID
        capital: Capital amount
        expected_pnl_pct: Expected P&L percentage
        expected_drawdown_pct: Expected drawdown percentage
        environment: DEMO or LIVE

    Returns:
        Approval request message HTML
    """
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"
    capital_str = f"${capital:,.2f}" if capital else "N/A"
    pnl_str = f"+{expected_pnl_pct:.1f}%" if expected_pnl_pct else "N/A"
    dd_str = f"{expected_drawdown_pct:.1f}%" if expected_drawdown_pct else "N/A"

    header = (
        "🚨 <b>LIVE TRADING APPROVAL</b>" if environment == "LIVE" else "⚠️ <b>APPROVAL REQUIRED</b>"
    )

    return (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Operation:</b> {operation}\n"
        f"<b>Market:</b> {market_id}\n"
        f"<b>Blueprint:</b> <code>{blueprint_id or 'N/A'}</code>\n\n"
        f"<b>Capital:</b> {capital_str}\n"
        f"<b>Expected P&L:</b> {pnl_str}\n"
        f"<b>Expected DD:</b> {dd_str}\n\n"
        f"<b>Environment:</b> {env_badge}\n\n"
        f"Approval ID: <code>{approval_id}</code>"
    )


def format_live_confirmation(
    approval_id: str,
    market_id: str,
    capital: Decimal | None,
) -> str:
    """
    Format LIVE trading final confirmation message.

    Args:
        approval_id: Approval request ID
        market_id: Market ID
        capital: Capital amount

    Returns:
        Live confirmation message HTML
    """
    capital_str = f"${capital:,.2f}" if capital else "N/A"

    return (
        f"🚨 <b>LIVE TRADING CONFIRMATION</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"You are about to start <b>LIVE</b> trading:\n\n"
        f"<b>Market:</b> {market_id}\n"
        f"<b>Capital:</b> {capital_str}\n\n"
        f"<b>Environment:</b> 🔴 LIVE\n\n"
        f"⚠️ <i>This will use REAL funds.\n"
        f"This action cannot be undone.</i>\n\n"
        f"Approval ID: <code>{approval_id}</code>"
    )


def format_settings(
    environment: str,
    notifications_enabled: bool = True,
) -> str:
    """
    Format settings menu message.

    Args:
        environment: DEMO or LIVE
        notifications_enabled: Whether notifications are enabled

    Returns:
        Settings message HTML
    """
    env_badge = "🔴 LIVE" if environment == "LIVE" else "🟢 DEMO"
    notif_str = "✅ Enabled" if notifications_enabled else "❌ Disabled"

    return (
        f"⚙️ <b>SETTINGS</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Environment:</b> {env_badge}\n"
        f"<b>Notifications:</b> {notif_str}\n"
    )


def format_unlink_warning() -> str:
    """
    Format unlink Telegram warning message.

    Returns:
        Warning message HTML
    """
    return (
        "🔓 <b>Unlink Telegram</b>\n"
        "━━━━━━━━━━━━━━━━━━\n\n"
        "⚠️ <b>Warning:</b>\n\n"
        "This will disconnect your Telegram from the system.\n\n"
        "<b>What will be kept:</b>\n"
        "• Your account\n"
        "• OKX connection\n"
        "• Grid state\n"
        "• Research data\n\n"
        "<b>What will be removed:</b>\n"
        "• Telegram notifications\n"
        "• Telegram control access\n\n"
        "Are you sure?"
    )


def format_error(message: str) -> str:
    """
    Format error message (no internal details leaked).

    Args:
        message: User-friendly error message

    Returns:
        Error message HTML
    """
    return f"❌ <b>Error</b>\n\n{message}"


def format_success(message: str) -> str:
    """
    Format success message.

    Args:
        message: Success message

    Returns:
        Success message HTML
    """
    return f"✅ {message}"
