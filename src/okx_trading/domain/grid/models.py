"""
Grid domain models.

This module defines the core grid strategy models:
- GridLevelModel: A single grid price level within a section
- Section: A group of grid levels with uniform spacing
- Blueprint: The complete grid strategy (multiple sections)

Key domain rules:
1. Grid spacing is UNIFORM within each Section
2. Section Gaps may DIFFER between Sections
3. Spot-only: no shorting, no leverage
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from okx_trading.domain.shared.types import (
    BlueprintId,
    GridLevel,
    GridStatus,
    MarketId,
    Price,
    Quantity,
    SectionId,
    SectionStatus,
    StrategyStatus,
)


@dataclass
class GridLevelModel:
    """
    A single grid price level within a section.

    This model is MUTABLE to support runtime fill-state tracking.
    After a BUY order fills at this level, mark_filled() is called.
    After a SELL order closes the position, mark_closed() is called,
    allowing the level to be re-bought in the next grid cycle.

    Attributes:
        level: Grid level index (0 = top of section, higher = lower price)
        price: The grid price level (design reference from blueprint)
        status: Current status of this grid level
        quantity: Quantity to trade at this level
        position_quantity: Current position quantity (if filled)
        entry_price: Actual entry price (if filled) — real fill price,
            which may differ from `price` due to market order slippage
    """

    level: GridLevel
    price: Price
    status: GridStatus = "PENDING"
    quantity: Quantity = Decimal("0")
    position_quantity: Quantity = Decimal("0")
    entry_price: Price | None = None

    def __post_init__(self) -> None:
        """Validate grid level constraints."""
        if self.level < 0:
            raise ValueError(f"Grid level must be non-negative, got {self.level}")
        if self.price <= 0:
            raise ValueError(f"Grid price must be positive, got {self.price}")

    @property
    def is_filled(self) -> bool:
        """Check if this grid level has an open position."""
        return self.position_quantity > 0

    def mark_filled(self, filled_quantity: Quantity, fill_price: Price) -> None:
        """
        Mark this level as filled with an open position.

        Called after a BUY order executes successfully at this level.
        The fill_price is the ACTUAL execution price (market order),
        not the blueprint design price.

        Args:
            filled_quantity: Quantity actually filled
            fill_price: Actual execution price
        """
        if filled_quantity <= 0:
            raise ValueError(f"Filled quantity must be positive, got {filled_quantity}")
        if fill_price <= 0:
            raise ValueError(f"Fill price must be positive, got {fill_price}")

        self.status = "FILLED"
        self.position_quantity = filled_quantity
        self.entry_price = fill_price

    def mark_closed(self) -> None:
        """
        Mark this level as closed (position sold).

        Called after a SELL order executes successfully, closing the
        position at this level. The level resets to PENDING so it can
        be re-bought in the next grid cycle (grid trading philosophy).
        """
        self.status = "PENDING"
        self.position_quantity = Decimal("0")
        self.entry_price = None


@dataclass
class Section:
    """
    A grid section with uniform spacing.

    A section is a group of grid levels with:
    - Uniform grid spacing (same percentage between all levels)
    - Its own capital allocation
    - Its own price range
    - A gap to the next section (may differ between sections)

    Attributes:
        section_id: Section identifier (1-based)
        upper_price: Top price boundary of the section
        lower_price: Bottom price boundary of the section
        grid_count: Number of grid levels in this section
        grid_spacing_pct: Uniform spacing percentage (e.g., 1.0 = 1%)
        capital_allocation_pct: Percentage of total capital allocated
        gap_to_next_pct: Gap percentage to the next section (None for last)
        status: Current section status
        levels: List of grid levels in this section
    """

    section_id: SectionId
    upper_price: Price
    lower_price: Price
    grid_count: int
    grid_spacing_pct: Decimal
    capital_allocation_pct: Decimal
    gap_to_next_pct: Decimal | None = None
    status: SectionStatus = "INACTIVE"
    levels: list[GridLevelModel] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate section constraints."""
        if self.section_id < 1:
            raise ValueError(f"Section ID must be >= 1, got {self.section_id}")
        if self.upper_price <= self.lower_price:
            raise ValueError(
                f"Upper price ({self.upper_price}) must be greater than "
                f"lower price ({self.lower_price})"
            )
        if self.grid_count < 1:
            raise ValueError(f"Grid count must be >= 1, got {self.grid_count}")
        if self.grid_spacing_pct <= 0:
            raise ValueError(f"Grid spacing must be positive, got {self.grid_spacing_pct}")
        if not (Decimal("0") <= self.capital_allocation_pct <= Decimal("100")):
            raise ValueError(
                f"Capital allocation must be 0-100%, got {self.capital_allocation_pct}"
            )

    @property
    def price_range(self) -> Price:
        """Calculate the price range of this section."""
        return self.upper_price - self.lower_price

    @property
    def filled_levels(self) -> list[GridLevelModel]:
        """Get all filled grid levels."""
        return [level for level in self.levels if level.is_filled]

    @property
    def fill_ratio(self) -> Decimal:
        """Calculate the ratio of filled levels (0-1)."""
        if not self.levels:
            return Decimal("0")
        return Decimal(len(self.filled_levels)) / Decimal(len(self.levels))


@dataclass
class Blueprint:
    """
    Grid strategy blueprint.

    A blueprint defines the complete grid strategy:
    - Market to trade
    - Total capital
    - Multiple sections with their configurations
    - Strategy metadata

    The blueprint is a strategic proposal from the AI layer.
    It must pass deterministic calculation and risk validation
    before execution.

    Attributes:
        blueprint_id: Unique blueprint identifier
        market_id: Market to trade (e.g., 'BTC-USDT')
        total_capital: Total capital allocated to this strategy
        sections: List of sections (ordered from top to bottom)
        status: Current strategy status
        created_at: Creation timestamp (UTC)
        updated_at: Last update timestamp (UTC)
        metadata: Additional metadata (regime, scores, etc.)
    """

    blueprint_id: BlueprintId
    market_id: MarketId
    total_capital: Decimal
    sections: list[Section] = field(default_factory=list)
    status: StrategyStatus = "DRAFT"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate blueprint constraints."""
        if self.total_capital <= 0:
            raise ValueError(f"Total capital must be positive, got {self.total_capital}")

    @property
    def section_count(self) -> int:
        """Get the number of sections."""
        return len(self.sections)

    @property
    def total_grid_count(self) -> int:
        """Get the total number of grid levels across all sections."""
        return sum(section.grid_count for section in self.sections)

    @property
    def highest_price(self) -> Price | None:
        """Get the highest price in the blueprint."""
        if not self.sections:
            return None
        return max(section.upper_price for section in self.sections)

    @property
    def lowest_price(self) -> Price | None:
        """Get the lowest price in the blueprint."""
        if not self.sections:
            return None
        return min(section.lower_price for section in self.sections)

    @property
    def capital_allocation_sum(self) -> Decimal:
        """Get the sum of all section capital allocations."""
        return sum((section.capital_allocation_pct for section in self.sections), Decimal("0"))

    def get_section(self, section_id: SectionId) -> Section | None:
        """Get a section by ID."""
        for section in self.sections:
            if section.section_id == section_id:
                return section
        return None

    def validate_allocations(self) -> list[str]:
        """
        Validate that capital allocations sum to 100%.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors: list[str] = []
        allocation_sum = self.capital_allocation_sum
        if allocation_sum != Decimal("100"):
            errors.append(f"Capital allocations must sum to 100%, got {allocation_sum}%")
        return errors


@dataclass(frozen=True)
class CalculatedGridPrices:
    """
    Calculated grid prices for a blueprint.

    This is the output of deterministic grid calculation.
    Contains exact prices for all grid levels.

    Attributes:
        blueprint_id: The blueprint these prices were calculated from
        section_prices: Map of section_id to list of grid prices
        calculated_at: Calculation timestamp
    """

    blueprint_id: BlueprintId
    section_prices: dict[SectionId, list[Price]]
    calculated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def get_prices(self, section_id: SectionId) -> list[Price]:
        """Get grid prices for a section."""
        return self.section_prices.get(section_id, [])

    @property
    def all_prices(self) -> list[Price]:
        """Get all grid prices across all sections."""
        prices: list[Price] = []
        for section_prices in self.section_prices.values():
            prices.extend(section_prices)
        return sorted(prices, reverse=True)
