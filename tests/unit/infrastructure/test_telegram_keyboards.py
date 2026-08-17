"""Tests for Telegram inline keyboard builders."""

from okx_trading.infrastructure.telegram.keyboards import (
    account_menu_keyboard,
    approval_keyboard,
    blueprint_detail_keyboard,
    blueprint_menu_keyboard,
    connect_okx_keyboard,
    grid_detail_keyboard,
    grid_menu_keyboard,
    grid_paused_keyboard,
    live_confirmation_keyboard,
    main_menu_keyboard,
    market_detail_keyboard,
    research_menu_keyboard,
    settings_menu_keyboard,
    simulate_menu_keyboard,
    top10_menu_keyboard,
    unlink_confirmation_keyboard,
    welcome_back_keyboard,
    welcome_new_user_keyboard,
)


def _get_all_callback_data(kb) -> list[str]:
    """Extract all callback_data from a keyboard."""
    result = []
    for row in kb.inline_keyboard:
        for button in row:
            if button.callback_data:
                result.append(button.callback_data)
    return result


class TestMainMenuKeyboard:
    def test_has_7_buttons(self):
        kb = main_menu_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert len(callbacks) == 7

    def test_button_layout(self):
        kb = main_menu_keyboard()
        assert len(kb.inline_keyboard) == 4
        assert len(kb.inline_keyboard[0]) == 2  # RESEARCH + TOP 10
        assert len(kb.inline_keyboard[1]) == 2  # BLUEPRINT + SIMULATE
        assert len(kb.inline_keyboard[2]) == 2  # GRID + ACCOUNT
        assert len(kb.inline_keyboard[3]) == 1  # SETTINGS

    def test_callback_data(self):
        kb = main_menu_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "menu:research" in callbacks
        assert "menu:top10" in callbacks
        assert "menu:blueprint" in callbacks
        assert "menu:simulate" in callbacks
        assert "menu:grid" in callbacks
        assert "menu:account" in callbacks
        assert "menu:settings" in callbacks


class TestResearchMenuKeyboard:
    def test_buttons(self):
        kb = research_menu_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "research:top10" in callbacks
        assert "research:markets" in callbacks
        assert "research:refresh" in callbacks
        assert "nav:main" in callbacks


class TestTop10MenuKeyboard:
    def test_with_markets(self):
        kb = top10_menu_keyboard(["BTC-USDT", "ETH-USDT", "SOL-USDT"])
        callbacks = _get_all_callback_data(kb)
        assert "market:BTC-USDT" in callbacks
        assert "market:ETH-USDT" in callbacks
        assert "market:SOL-USDT" in callbacks
        assert "nav:main" in callbacks

    def test_without_markets(self):
        kb = top10_menu_keyboard(None)
        callbacks = _get_all_callback_data(kb)
        assert callbacks == ["nav:main"]

    def test_display_shows_base_currency(self):
        kb = top10_menu_keyboard(["BTC-USDT"])
        assert kb.inline_keyboard[0][0].text == "BTC"

    def test_rows_of_two(self):
        kb = top10_menu_keyboard(["A-USDT", "B-USDT", "C-USDT"])
        # 2 markets in first row, 1 in second, then BACK
        assert len(kb.inline_keyboard[0]) == 2
        assert len(kb.inline_keyboard[1]) == 1


class TestMarketDetailKeyboard:
    def test_buttons(self):
        kb = market_detail_keyboard("BTC-USDT")
        callbacks = _get_all_callback_data(kb)
        assert "blueprint:view:BTC-USDT" in callbacks
        assert "simulate:run:BTC-USDT" in callbacks
        assert "menu:top10" in callbacks


class TestBlueprintMenuKeyboard:
    def test_with_blueprints(self):
        kb = blueprint_menu_keyboard(["BP-001", "BP-002"])
        callbacks = _get_all_callback_data(kb)
        assert "blueprint:detail:BP-001" in callbacks
        assert "blueprint:detail:BP-002" in callbacks
        assert "blueprint:refresh" in callbacks
        assert "nav:main" in callbacks

    def test_without_blueprints(self):
        kb = blueprint_menu_keyboard(None)
        callbacks = _get_all_callback_data(kb)
        assert "noop" in callbacks
        assert "blueprint:refresh" in callbacks


class TestBlueprintDetailKeyboard:
    def test_buttons_default_exchange(self):
        kb = blueprint_detail_keyboard("BP-001", "BTC-USDT")
        callbacks = _get_all_callback_data(kb)
        assert "simulate:run:BTC-USDT" in callbacks
        assert "grid:start:BP-001:OKX" in callbacks
        assert "menu:blueprint" in callbacks

    def test_single_exchange_shows_name(self):
        kb = blueprint_detail_keyboard("BP-001", "BTC-USDT", configured_exchanges=["BINANCE"])
        callbacks = _get_all_callback_data(kb)
        assert "grid:start:BP-001:BINANCE" in callbacks
        # Button text includes exchange name
        assert "BINANCE" in kb.inline_keyboard[1][0].text

    def test_multiple_exchanges_show_all(self):
        kb = blueprint_detail_keyboard(
            "BP-001", "BTC-USDT", configured_exchanges=["OKX", "BINANCE", "BYBIT"]
        )
        callbacks = _get_all_callback_data(kb)
        assert "grid:start:BP-001:OKX" in callbacks
        assert "grid:start:BP-001:BINANCE" in callbacks
        assert "grid:start:BP-001:BYBIT" in callbacks
        # All three in one row
        assert len(kb.inline_keyboard[1]) == 3


class TestSimulateMenuKeyboard:
    def test_buttons(self):
        kb = simulate_menu_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "simulate:history" in callbacks
        assert "nav:main" in callbacks

    def test_with_markets(self):
        kb = simulate_menu_keyboard(market_ids=["BTC-USDT", "ETH-USDT"])
        callbacks = _get_all_callback_data(kb)
        assert "simulate:run:BTC-USDT" in callbacks
        assert "simulate:run:ETH-USDT" in callbacks
        assert "simulate:history" in callbacks
        assert "nav:main" in callbacks


class TestGridMenuKeyboard:
    def test_with_grids(self):
        kb = grid_menu_keyboard(["GRID-001", "GRID-002"])
        callbacks = _get_all_callback_data(kb)
        assert "grid:detail:GRID-001" in callbacks
        assert "grid:detail:GRID-002" in callbacks
        assert "grid:orders" in callbacks
        assert "grid:pnl" in callbacks
        assert "grid:risk" in callbacks
        assert "nav:main" in callbacks

    def test_without_grids(self):
        kb = grid_menu_keyboard(None)
        callbacks = _get_all_callback_data(kb)
        assert "noop" in callbacks


class TestGridDetailKeyboard:
    def test_buttons(self):
        kb = grid_detail_keyboard("GRID-001")
        callbacks = _get_all_callback_data(kb)
        assert "grid:pause:GRID-001" in callbacks
        assert "grid:stop:GRID-001" in callbacks
        assert "grid:orders:GRID-001" in callbacks
        assert "grid:pnl:GRID-001" in callbacks
        assert "menu:grid" in callbacks


class TestGridPausedKeyboard:
    def test_buttons(self):
        kb = grid_paused_keyboard("GRID-001")
        callbacks = _get_all_callback_data(kb)
        assert "grid:resume:GRID-001" in callbacks
        assert "grid:stop:GRID-001" in callbacks
        assert "menu:grid" in callbacks


class TestAccountMenuKeyboard:
    def test_buttons(self):
        kb = account_menu_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "account:balance" in callbacks
        assert "account:pnl" in callbacks
        assert "account:risk" in callbacks
        assert "account:okx" in callbacks
        assert "nav:main" in callbacks


class TestSettingsMenuKeyboard:
    def test_buttons(self):
        kb = settings_menu_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "settings:notifications" in callbacks
        assert "settings:environment" in callbacks
        assert "settings:unlink" in callbacks
        assert "nav:main" in callbacks


class TestApprovalKeyboard:
    def test_buttons(self):
        kb = approval_keyboard("APR-001")
        callbacks = _get_all_callback_data(kb)
        assert "approve:APR-001" in callbacks
        assert "reject:APR-001" in callbacks


class TestLiveConfirmationKeyboard:
    def test_buttons(self):
        kb = live_confirmation_keyboard("APR-001")
        callbacks = _get_all_callback_data(kb)
        assert "confirm_live:APR-001" in callbacks
        assert "reject:APR-001" in callbacks


class TestConnectOkxKeyboard:
    def test_has_url_button(self):
        kb = connect_okx_keyboard()
        url_buttons = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
        assert len(url_buttons) == 1
        assert "connect/okx" in url_buttons[0]

    def test_back_button(self):
        kb = connect_okx_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "nav:main" in callbacks


class TestUnlinkConfirmationKeyboard:
    def test_buttons(self):
        kb = unlink_confirmation_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert "unlink:confirm" in callbacks
        assert "menu:settings" in callbacks


class TestWelcomeNewUserKeyboard:
    def test_buttons(self):
        kb = welcome_new_user_keyboard()
        callbacks = _get_all_callback_data(kb)
        assert callbacks == ["auth:create"]


class TestWelcomeBackKeyboard:
    def test_okx_not_connected(self):
        kb = welcome_back_keyboard(okx_connected=False)
        callbacks = _get_all_callback_data(kb)
        assert "menu:settings" in callbacks
        # Has URL button for connect
        url_buttons = [btn.url for row in kb.inline_keyboard for btn in row if btn.url]
        assert len(url_buttons) == 1

    def test_okx_connected(self):
        kb = welcome_back_keyboard(okx_connected=True)
        callbacks = _get_all_callback_data(kb)
        assert "menu:top10" in callbacks
        assert "menu:research" in callbacks
        assert "menu:grid" in callbacks
