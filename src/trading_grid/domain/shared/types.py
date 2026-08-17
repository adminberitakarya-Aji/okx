"""
Core type definitions for the OKX Trading system.

This module defines the fundamental types used across the domain layer.
All monetary values use Decimal to avoid floating-point precision issues.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

# ============================================================================
# IDENTIFIERS
# ============================================================================

MarketId = str
"""Market identifier, e.g., 'BTC-USDT', 'ETH-USDT'."""

ExchangeId = Literal["OKX", "BINANCE", "BYBIT"]
"""Supported exchange identifier."""

OrderId = str
"""Unique order identifier from the exchange."""

TradeId = str
"""Unique trade/fill identifier."""

PositionId = str
"""Unique position identifier."""

BlueprintId = str
"""Unique strategy blueprint identifier."""

# ============================================================================
# TIME
# ============================================================================

Timestamp = datetime
"""UTC timestamp. All timestamps must be timezone-aware (UTC)."""

# ============================================================================
# NUMERIC TYPES
# ============================================================================

Price = Decimal
"""Price value. Never use float for prices."""

Quantity = Decimal
"""Quantity/amount value. Never use float for quantities."""

Percentage = Decimal
"""Percentage value (0-100 scale, e.g., 1.5 = 1.5%)."""

Ratio = Decimal
"""Ratio value (0-1 scale, e.g., 0.015 = 1.5%)."""

# ============================================================================
# GRID TYPES
# ============================================================================

GridSide = Literal["BUY", "SELL"]
"""Grid order side."""

GridLevel = int
"""Grid level index within a section (0-based)."""

SectionId = int
"""Section identifier (1-based)."""

GridStatus = Literal[
    "PENDING",  # Grid level exists but no position
    "ACTIVE",  # Grid has an open position
    "FILLED",  # Grid level BUY order filled, position open
    "EXECUTING",  # Grid is currently executing
    "COMPLETED",  # Grid cycle completed (buy + sell)
    "DISABLED",  # Grid is disabled
]
"""Status of a grid level."""

SectionStatus = Literal[
    "INACTIVE",  # Section not yet activated
    "ACTIVE",  # Section is active
    "PARTIAL",  # Section partially filled
    "FULL",  # Section fully deployed
    "CLOSED",  # Section closed
]
"""Status of a grid section."""

# ============================================================================
# ORDER TYPES
# ============================================================================

OrderType = Literal["MARKET", "LIMIT"]
"""Order type. Note: This system primarily uses MARKET (immediate execution)."""

OrderStatus = Literal[
    "PENDING",  # Order created but not submitted
    "SUBMITTED",  # Order sent to exchange
    "ACKNOWLEDGED",  # Exchange acknowledged the order
    "PARTIALLY_FILLED",  # Order partially filled
    "FILLED",  # Order completely filled
    "CANCELLED",  # Order cancelled
    "REJECTED",  # Order rejected by exchange
    "FAILED",  # Order failed (error)
]
"""Order lifecycle status."""

OrderSide = Literal["BUY", "SELL"]
"""Order side."""

# ============================================================================
# MARKET REGIME TYPES
# ============================================================================

MarketRegime = Literal[
    "BULLISH",  # Upward trending market
    "BEARISH",  # Downward trending market
    "SIDEWAYS",  # Range-bound market
    "HIGH_VOLATILITY",  # High volatility conditions
    "LOW_VOLATILITY",  # Low volatility conditions
    "VOLATILITY_EXPANSION",  # Volatility increasing
    "VOLATILITY_CONTRACTION",  # Volatility decreasing
    "TRANSITION",  # Market in transition
    "EXTREME",  # Extreme/abnormal conditions
]
"""Market regime classification."""

# ============================================================================
# EXECUTION TYPES
# ============================================================================

ExecutionMode = Literal["DEMO", "LIVE"]
"""Trading execution mode."""

ExecutionType = Literal["IMMEDIATE", "PASSIVE"]
"""Execution type. This system uses IMMEDIATE (taker) execution."""

# ============================================================================
# RISK TYPES
# ============================================================================

RiskLevel = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
"""Risk level classification."""

ValidationStatus = Literal["PASS", "FAIL", "WARNING"]
"""Risk validation result status."""

# ============================================================================
# STRATEGY TYPES
# ============================================================================

StrategyStatus = Literal[
    "DRAFT",  # Blueprint created, not validated
    "VALIDATED",  # Passed risk validation
    "APPROVED",  # Human approved
    "ACTIVE",  # Strategy is running
    "PAUSED",  # Strategy paused
    "COMPLETED",  # Strategy completed
    "TERMINATED",  # Strategy terminated
]
"""Strategy lifecycle status."""

# ============================================================================
# CONSTANTS
# ============================================================================

MAX_SECTIONS = 10
"""Maximum number of sections in a grid strategy."""

MAX_GRIDS_PER_SECTION = 100
"""Maximum number of grid levels per section."""

MIN_GRID_SPACING_PCT = Decimal("0.1")
"""Minimum grid spacing percentage."""

MAX_GRID_SPACING_PCT = Decimal("10.0")
"""Maximum grid spacing percentage."""

DEFAULT_QUOTE_CURRENCY = "USDT"
"""Default quote currency for spot trading."""
