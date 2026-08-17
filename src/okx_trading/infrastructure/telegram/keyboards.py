"""
Telegram inline keyboard builders.

This module provides:
- Main menu keyboard (7 buttons)
- Sub-menu keyboards for drill-down navigation
- Approval flow keyboards
- State-aware keyboard generation

Menu Structure (agreed):
    [ 🔬 RESEARCH ]  [ 🏆 TOP 10 ]
    [ 🧠 BLUEPRINT ] [ 🧪 SIMULATE ]
    [ 📈 GRID ]      [ 💰 ACCOUNT ]
    [ ⚙️ SETTINGS ]

Security rules:
1. OKX credentials are NEVER requested via Telegram
2. Environment (DEMO/LIVE) is always visible
3. Dangerous operations require explicit approval
"""

from collections.abc import Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Build the main menu inline keyboard.

    Layout:
        [ 🔬 RESEARCH ]  [ 🏆 TOP 10 ]
        [ 🧠 BLUEPRINT ] [ 🧪 SIMULATE ]
        [ 📈 GRID ]      [ 💰 ACCOUNT ]
        [ ⚙️ SETTINGS ]

    Returns:
        InlineKeyboardMarkup with 7 buttons
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔬 RESEARCH", callback_data="menu:research"),
                InlineKeyboardButton(text="🏆 TOP 10", callback_data="menu:top10"),
            ],
            [
                InlineKeyboardButton(text="🧠 BLUEPRINT", callback_data="menu:blueprint"),
                InlineKeyboardButton(text="🧪 SIMULATE", callback_data="menu:simulate"),
            ],
            [
                InlineKeyboardButton(text="📈 GRID", callback_data="menu:grid"),
                InlineKeyboardButton(text="💰 ACCOUNT", callback_data="menu:account"),
            ],
            [
                InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="menu:settings"),
            ],
        ]
    )


def research_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Build the Research sub-menu keyboard.

    Layout:
        [ 🏆 VIEW TOP 10 ]
        [ 📊 ALL MARKETS ]
        [ 🔄 REFRESH ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏆 VIEW TOP 10", callback_data="research:top10")],
            [InlineKeyboardButton(text="📊 ALL MARKETS", callback_data="research:markets")],
            [InlineKeyboardButton(text="🔄 REFRESH", callback_data="research:refresh")],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")],
        ]
    )


def top10_menu_keyboard(market_ids: list[str] | None = None) -> InlineKeyboardMarkup:
    """
    Build the Top 10 market selection keyboard.

    Args:
        market_ids: List of market IDs to show (e.g., ["BTC-USDT", "ETH-USDT"])

    Returns:
        InlineKeyboardMarkup with market buttons
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if market_ids:
        # Show markets in rows of 2
        for i in range(0, len(market_ids), 2):
            row = []
            for market_id in market_ids[i : i + 2]:
                # Display "BTC" instead of "BTC-USDT"
                display = market_id.split("-")[0]
                row.append(
                    InlineKeyboardButton(
                        text=display,
                        callback_data=f"market:{market_id}",
                    )
                )
            buttons.append(row)

    buttons.append([InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def market_detail_keyboard(market_id: str) -> InlineKeyboardMarkup:
    """
    Build the market detail action keyboard.

    Args:
        market_id: The market ID (e.g., "BTC-USDT")

    Layout:
        [ 🧠 BLUEPRINT ] [ 🧪 SIMULATE ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 BLUEPRINT",
                    callback_data=f"blueprint:view:{market_id}",
                ),
                InlineKeyboardButton(
                    text="🧪 SIMULATE",
                    callback_data=f"simulate:run:{market_id}",
                ),
            ],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="menu:top10")],
        ]
    )


def blueprint_menu_keyboard(blueprint_ids: list[str] | None = None) -> InlineKeyboardMarkup:
    """
    Build the Blueprint list keyboard.

    Args:
        blueprint_ids: List of blueprint IDs to show

    Layout:
        [ BP-001 ] [ BP-002 ]
        [ 🔄 REFRESH ]
        [ ⬅️ BACK ]
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if blueprint_ids:
        for i in range(0, len(blueprint_ids), 2):
            row = []
            for bp_id in blueprint_ids[i : i + 2]:
                row.append(
                    InlineKeyboardButton(
                        text=bp_id,
                        callback_data=f"blueprint:detail:{bp_id}",
                    )
                )
            buttons.append(row)
    else:
        buttons.append([InlineKeyboardButton(text="No blueprints yet", callback_data="noop")])

    buttons.append([InlineKeyboardButton(text="🔄 REFRESH", callback_data="blueprint:refresh")])
    buttons.append([InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def blueprint_detail_keyboard(
    blueprint_id: str,
    market_id: str,
    configured_exchanges: Sequence[str] | None = None,
) -> InlineKeyboardMarkup:
    """
    Build the blueprint detail action keyboard with exchange selection.

    Args:
        blueprint_id: The blueprint ID
        market_id: The market ID
        configured_exchanges: List of configured exchange IDs (e.g., ["OKX", "BINANCE"])

    Layout (single exchange):
        [ 🧪 SIMULATE ]
        [ 🚀 START GRID — OKX ]
        [ ⬅️ BACK ]

    Layout (multiple exchanges):
        [ 🧪 SIMULATE ]
        [ 🚀 OKX ] [ 🚀 BINANCE ] [ 🚀 BYBIT ]
        [ ⬅️ BACK ]
    """
    exchanges = configured_exchanges or ["OKX"]

    buttons: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="🧪 SIMULATE",
                callback_data=f"simulate:run:{market_id}",
            )
        ],
    ]

    if len(exchanges) == 1:
        # Single exchange: one button with exchange name
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"🚀 START GRID — {exchanges[0]}",
                    callback_data=f"grid:start:{blueprint_id}:{exchanges[0]}",
                )
            ]
        )
    else:
        # Multiple exchanges: row of exchange buttons
        row = []
        for ex in exchanges:
            row.append(
                InlineKeyboardButton(
                    text=f"🚀 {ex}",
                    callback_data=f"grid:start:{blueprint_id}:{ex}",
                )
            )
        buttons.append(row)

    buttons.append([InlineKeyboardButton(text="⬅️ BACK", callback_data="menu:blueprint")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def simulate_menu_keyboard(market_ids: list[str] | None = None) -> InlineKeyboardMarkup:
    """
    Build the Simulation menu keyboard.

    Args:
        market_ids: List of market IDs to offer for simulation

    Layout:
        [ BTC-USDT ] [ ETH-USDT ]
        [ SOL-USDT ] [ XRP-USDT ]
        ...
        [ 📋 SIMULATION HISTORY ]
        [ ⬅️ BACK ]
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if market_ids:
        for i in range(0, len(market_ids), 2):
            row = []
            for mid in market_ids[i : i + 2]:
                row.append(
                    InlineKeyboardButton(
                        text=f"🧪 {mid}",
                        callback_data=f"simulate:run:{mid}",
                    )
                )
            buttons.append(row)
    else:
        buttons.append([InlineKeyboardButton(text="No markets available", callback_data="noop")])

    buttons.append(
        [InlineKeyboardButton(text="📋 SIMULATION HISTORY", callback_data="simulate:history")]
    )
    buttons.append([InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def grid_menu_keyboard(grid_ids: list[str] | None = None) -> InlineKeyboardMarkup:
    """
    Build the Grid control menu keyboard.

    Args:
        grid_ids: List of active grid IDs

    Layout:
        [ GRID-001 ] [ GRID-002 ]
        [ 📋 ORDERS ] [ 📊 P&L ]
        [ 🛡 RISK STATUS ]
        [ ⬅️ BACK ]
    """
    buttons: list[list[InlineKeyboardButton]] = []

    if grid_ids:
        for i in range(0, len(grid_ids), 2):
            row = []
            for grid_id in grid_ids[i : i + 2]:
                row.append(
                    InlineKeyboardButton(
                        text=grid_id,
                        callback_data=f"grid:detail:{grid_id}",
                    )
                )
            buttons.append(row)
    else:
        buttons.append([InlineKeyboardButton(text="No active grids", callback_data="noop")])

    buttons.append(
        [
            InlineKeyboardButton(text="📋 ORDERS", callback_data="grid:orders"),
            InlineKeyboardButton(text="📊 P&L", callback_data="grid:pnl"),
        ]
    )
    buttons.append([InlineKeyboardButton(text="🛡 RISK STATUS", callback_data="grid:risk")])
    buttons.append([InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def grid_detail_keyboard(grid_id: str) -> InlineKeyboardMarkup:
    """
    Build the grid detail control keyboard.

    Args:
        grid_id: The grid ID

    Layout:
        [ ⏸ PAUSE ] [ ⏹ STOP ]
        [ 📋 ORDERS ] [ 📊 P&L ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="⏸ PAUSE", callback_data=f"grid:pause:{grid_id}"),
                InlineKeyboardButton(text="⏹ STOP", callback_data=f"grid:stop:{grid_id}"),
            ],
            [
                InlineKeyboardButton(text="📋 ORDERS", callback_data=f"grid:orders:{grid_id}"),
                InlineKeyboardButton(text="📊 P&L", callback_data=f"grid:pnl:{grid_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="menu:grid")],
        ]
    )


def grid_paused_keyboard(grid_id: str) -> InlineKeyboardMarkup:
    """
    Build the keyboard for a paused grid.

    Args:
        grid_id: The grid ID

    Layout:
        [ ▶️ RESUME ] [ ⏹ STOP ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="▶️ RESUME", callback_data=f"grid:resume:{grid_id}"),
                InlineKeyboardButton(text="⏹ STOP", callback_data=f"grid:stop:{grid_id}"),
            ],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="menu:grid")],
        ]
    )


def account_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Build the Account menu keyboard.

    Layout:
        [ 💰 BALANCE ]
        [ 📊 P&L SUMMARY ]
        [ 🛡 RISK LIMITS ]
        [ 🔗 OKX CONNECTION ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💰 BALANCE", callback_data="account:balance")],
            [InlineKeyboardButton(text="📊 P&L SUMMARY", callback_data="account:pnl")],
            [InlineKeyboardButton(text="🛡 RISK LIMITS", callback_data="account:risk")],
            [InlineKeyboardButton(text="🔗 OKX CONNECTION", callback_data="account:okx")],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")],
        ]
    )


def settings_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Build the Settings menu keyboard.

    Layout:
        [ 🔔 NOTIFICATIONS ]
        [ 🌐 ENVIRONMENT ]
        [ 🔓 UNLINK TELEGRAM ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔔 NOTIFICATIONS", callback_data="settings:notifications")],
            [InlineKeyboardButton(text="🌐 ENVIRONMENT", callback_data="settings:environment")],
            [InlineKeyboardButton(text="🔓 UNLINK TELEGRAM", callback_data="settings:unlink")],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")],
        ]
    )


def approval_keyboard(approval_id: str) -> InlineKeyboardMarkup:
    """
    Build the approval flow keyboard.

    Args:
        approval_id: The approval request ID

    Layout:
        [ ✅ APPROVE ] [ ❌ REJECT ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ APPROVE",
                    callback_data=f"approve:{approval_id}",
                ),
                InlineKeyboardButton(
                    text="❌ REJECT",
                    callback_data=f"reject:{approval_id}",
                ),
            ],
        ]
    )


def live_confirmation_keyboard(approval_id: str) -> InlineKeyboardMarkup:
    """
    Build the LIVE trading confirmation keyboard.

    LIVE requires 2-step confirmation:
    1. First confirmation
    2. Final "CONFIRM LIVE" button

    Args:
        approval_id: The approval request ID

    Layout:
        [ 🔴 CONFIRM LIVE ] [ CANCEL ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔴 CONFIRM LIVE",
                    callback_data=f"confirm_live:{approval_id}",
                ),
                InlineKeyboardButton(
                    text="CANCEL",
                    callback_data=f"reject:{approval_id}",
                ),
            ],
        ]
    )


def connect_okx_keyboard() -> InlineKeyboardMarkup:
    """
    Build the "Connect OKX" prompt keyboard.

    This button opens the secure web dashboard,
    NOT a chat-based credential input.

    Layout:
        [ 🔗 CONNECT OKX (Web) ]
        [ ⬅️ BACK ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔗 CONNECT OKX (Web)",
                    url="https://app.okx-trading.local/connect/okx",
                )
            ],
            [InlineKeyboardButton(text="⬅️ BACK", callback_data="nav:main")],
        ]
    )


def unlink_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Build the unlink Telegram confirmation keyboard.

    Layout:
        [ 🔓 CONFIRM UNLINK ] [ CANCEL ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔓 CONFIRM UNLINK", callback_data="unlink:confirm"),
                InlineKeyboardButton(text="CANCEL", callback_data="menu:settings"),
            ],
        ]
    )


def welcome_new_user_keyboard() -> InlineKeyboardMarkup:
    """
    Build the welcome keyboard for new users.

    Layout:
        [ 🚀 CREATE ACCOUNT ]
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🚀 CREATE ACCOUNT", callback_data="auth:create")],
        ]
    )


def welcome_back_keyboard(okx_connected: bool) -> InlineKeyboardMarkup:
    """
    Build the welcome back keyboard based on user state.

    Args:
        okx_connected: Whether OKX is connected

    Layout (OKX not connected):
        [ 🔗 CONNECT OKX ]
        [ ⚙️ SETTINGS ]

    Layout (OKX connected):
        [ 🏆 TOP 10 ] [ 🔬 RESEARCH ]
        [ 📈 GRID ]
    """
    if not okx_connected:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🔗 CONNECT OKX",
                        url="https://app.okx-trading.local/connect/okx",
                    )
                ],
                [InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="menu:settings")],
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🏆 TOP 10", callback_data="menu:top10"),
                InlineKeyboardButton(text="🔬 RESEARCH", callback_data="menu:research"),
            ],
            [InlineKeyboardButton(text="📈 GRID", callback_data="menu:grid")],
        ]
    )
