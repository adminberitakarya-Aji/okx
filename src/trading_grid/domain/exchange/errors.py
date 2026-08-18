"""
Exchange domain errors.

This module defines the base exception hierarchy for all exchange adapters.
Exchange-specific errors (OKXAPIError, BinanceAPIError, BybitAPIError) must
inherit from ExchangeAPIError so the application layer can handle them
uniformly while still preserving exchange-specific error details.

Key rules:
1. ExchangeAPIError always carries `code` and `message` for debugging
2. Exchange-specific detail must NEVER be collapsed into a generic message
3. Secrets must NEVER appear in error messages
"""

from typing import Any

from trading_grid.domain.shared.errors import DomainError


class ExchangeError(DomainError):
    """Base exception for all exchange-related errors."""

    def __init__(self, message: str = "", code: str = "EXCHANGE_ERROR") -> None:
        # Do NOT call DomainError here directly to avoid overwriting code
        # in subclasses (e.g. ExchangeAPIError sets self.code before super())
        Exception.__init__(self, message)
        if not hasattr(self, "message"):
            self.message = message
        if not hasattr(self, "code"):
            self.code = code


class ExchangeAPIError(ExchangeError):
    """
    Base exception for exchange API errors.

    All exchange-specific API errors (OKX, Binance, Bybit) inherit from
    this class. The `code` and `message` attributes preserve exchange-specific
    error detail for debugging and audit logging.

    Attributes:
        code: Exchange-specific error code (e.g., OKX "51000", Binance "-1021")
        message: Human-readable error message
        data: Optional raw error payload from the exchange (never contains secrets)
    """

    def __init__(
        self,
        code: str,
        message: str,
        data: Any = None,
    ) -> None:
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class ExchangeConnectionError(ExchangeError):
    """Raised when connection to an exchange fails or is lost."""


class ExchangeNotConfiguredError(ExchangeError):
    """Raised when an exchange is selected but its credentials/config are missing."""

    def __init__(self, exchange_id: str) -> None:
        self.exchange_id = exchange_id
        super().__init__(
            f"Exchange '{exchange_id}' is selected but not configured. "
            "Provide the required API credentials in environment variables."
        )


class ExchangeAuthError(ExchangeError):
    """Raised when exchange authentication fails (invalid key, signature, etc.)."""
