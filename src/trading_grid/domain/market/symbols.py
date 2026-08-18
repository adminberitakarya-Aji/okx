"""
Market symbol normalization helpers for multi-exchange support.

The domain layer uses the normalized market ID format "BTC-USDT" (OKX style).
Binance and Bybit use the concatenated format "BTCUSDT". These helpers convert
between the two formats so the domain and application layers stay exchange-agnostic.

Rules:
1. Domain format is ALWAYS "BASE-QUOTE" (e.g., "BTC-USDT")
2. Conversion must round-trip: normalize(to_native(x)) == x
3. Invalid symbols raise ValueError — never silently guess
"""

from trading_grid.domain.shared.types import MarketId

# Order matters: check longer/more specific quotes first
KNOWN_QUOTE_CURRENCIES: tuple[str, ...] = (
    # Stablecoins (longest first to avoid ambiguous prefix matches)
    "FDUSD",
    "PYUSD",
    "USDD",
    "TUSD",
    "BUSD",
    "USDC",
    "USDT",
    "USDP",
    "DAI",
    # Crypto quote assets
    "WBTC",
    "BNB",
    "BTC",
    "ETH",
    "SOL",
    "XRP",
    "TRX",
    # Fiat currencies
    "USD",
    "EUR",
    "GBP",
    "AUD",
    "BRL",
    "TRY",
    "JPY",
    "KRW",
    "CAD",
    "CHF",
    "SGD",
    "HKD",
    "UAH",
    "RUB",
    "NGN",
    "VND",
    "IDR",
    "PLN",
    "CZK",
    "RON",
    "ARS",
    "ZAR",
)


def to_concatenated_symbol(market_id: MarketId) -> str:
    """
    Convert normalized market ID to concatenated exchange symbol.

    "BTC-USDT" → "BTCUSDT" (Binance/Bybit format)

    Args:
        market_id: Normalized market ID (e.g., "BTC-USDT")

    Returns:
        Concatenated symbol (e.g., "BTCUSDT")

    Raises:
        ValueError: If market_id is not in "BASE-QUOTE" format
    """
    parts = market_id.split("-")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"Invalid market ID '{market_id}': expected 'BASE-QUOTE' format (e.g., 'BTC-USDT')"
        )
    return f"{parts[0].upper()}{parts[1].upper()}"


def to_normalized_market_id(
    symbol: str, quotes: tuple[str, ...] = KNOWN_QUOTE_CURRENCIES
) -> MarketId:
    """
    Convert concatenated exchange symbol to normalized market ID.

    "BTCUSDT" → "BTC-USDT"

    This uses a list of known quote currencies to split the symbol correctly
    (e.g., "BTCUSDT" → base=BTC, quote=USDT; "ETHBTC" → base=ETH, quote=BTC).

    Args:
        symbol: Concatenated symbol (e.g., "BTCUSDT")
        quotes: Optional custom quote currencies tuple

    Returns:
        Normalized market ID (e.g., "BTC-USDT")

    Raises:
        ValueError: If the symbol cannot be split into base/quote
    """
    symbol_upper = symbol.upper()

    for quote in quotes:
        if symbol_upper.endswith(quote) and len(symbol_upper) > len(quote):
            base = symbol_upper[: -len(quote)]
            return f"{base}-{quote}"

    raise ValueError(f"Cannot split symbol '{symbol}' into base/quote currencies")
