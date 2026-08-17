"""
Grid Calculator — Deterministic grid price calculation.

This module calculates exact grid prices from a Blueprint.
It is a pure, deterministic function with no side effects.

Key domain rules:
1. Grid spacing is UNIFORM within each Section
2. Section Gaps may DIFFER between Sections
3. Prices are calculated from top (upper_price) to bottom
4. The deterministic layer must NOT reinterpret the AI strategy

Example:
    Section 1: upper=100, spacing=1%, grids=5
    → Prices: 100, 99, 98.01, 97.03, 96.06 (geometric)

    Or with arithmetic spacing:
    → Prices: 100, 99, 98, 97, 96
"""

from decimal import ROUND_HALF_UP, Decimal

from okx_trading.domain.grid.models import (
    Blueprint,
    CalculatedGridPrices,
    GridLevelModel,
    Section,
)
from okx_trading.domain.shared.errors import (
    BlueprintValidationError,
)
from okx_trading.domain.shared.types import Price, SectionId


def calculate_grid_prices(
    blueprint: Blueprint,
    spacing_mode: str = "geometric",
    decimal_places: int = 8,
) -> CalculatedGridPrices:
    """
    Calculate exact grid prices for all sections in a blueprint.

    Args:
        blueprint: The strategy blueprint to calculate prices for
        spacing_mode: "geometric" (percentage-based) or "arithmetic" (fixed difference)
        decimal_places: Number of decimal places for price rounding

    Returns:
        CalculatedGridPrices with exact prices for each section

    Raises:
        BlueprintValidationError: If blueprint is invalid
        InvalidGridSpacingError: If grid spacing is out of bounds
    """
    # Validate blueprint first
    errors = validate_blueprint(blueprint)
    if errors:
        raise BlueprintValidationError(
            f"Blueprint validation failed: {errors[0]}",
            errors=errors,
        )

    section_prices: dict[SectionId, list[Price]] = {}

    for section in blueprint.sections:
        prices = _calculate_section_prices(
            section=section,
            spacing_mode=spacing_mode,
            decimal_places=decimal_places,
        )
        section_prices[section.section_id] = prices

    return CalculatedGridPrices(
        blueprint_id=blueprint.blueprint_id,
        section_prices=section_prices,
    )


def _calculate_section_prices(
    section: Section,
    spacing_mode: str,
    decimal_places: int,
) -> list[Price]:
    """
    Calculate grid prices for a single section.

    For geometric spacing (default):
        price[i] = upper_price * (1 - spacing_pct/100)^i

    For arithmetic spacing:
        price[i] = upper_price - (i * spacing_amount)
        where spacing_amount = (upper - lower) / (grid_count - 1)

    Args:
        section: The section to calculate prices for
        spacing_mode: "geometric" or "arithmetic"
        decimal_places: Decimal places for rounding

    Returns:
        List of prices from top to bottom
    """
    if section.grid_count == 1:
        return [section.upper_price]

    prices: list[Price] = []
    quantize_exp = Decimal(10) ** -decimal_places

    if spacing_mode == "geometric":
        # Geometric: each price is (1 - spacing%) of previous
        spacing_ratio = Decimal("1") - (section.grid_spacing_pct / Decimal("100"))
        current_price = section.upper_price

        for _ in range(section.grid_count):
            rounded_price = current_price.quantize(quantize_exp, rounding=ROUND_HALF_UP)
            prices.append(rounded_price)
            current_price = current_price * spacing_ratio

    elif spacing_mode == "arithmetic":
        # Arithmetic: equal absolute difference between prices
        price_range = section.upper_price - section.lower_price
        spacing_amount = price_range / Decimal(section.grid_count - 1)
        current_price = section.upper_price

        for _ in range(section.grid_count):
            rounded_price = current_price.quantize(quantize_exp, rounding=ROUND_HALF_UP)
            prices.append(rounded_price)
            current_price = current_price - spacing_amount

    else:
        raise ValueError(f"Unknown spacing mode: {spacing_mode}")

    return prices


def validate_blueprint(blueprint: Blueprint) -> list[str]:
    """
    Validate a blueprint for calculation readiness.

    Checks:
    1. At least one section exists
    2. Capital allocations sum to 100%
    3. Grid spacing is within bounds
    4. Sections are ordered correctly (top to bottom)
    5. Section gaps are consistent

    Returns:
        List of validation error messages (empty if valid)
    """
    errors: list[str] = []

    # Check sections exist
    if not blueprint.sections:
        errors.append("Blueprint has no sections")
        return errors

    # Check capital allocations
    allocation_errors = blueprint.validate_allocations()
    errors.extend(allocation_errors)

    # Check each section
    for section in blueprint.sections:
        # Check spacing bounds
        if section.grid_spacing_pct <= Decimal("0"):
            errors.append(f"Section {section.section_id}: spacing must be positive")
        if section.grid_spacing_pct > Decimal("50"):
            errors.append(
                f"Section {section.section_id}: spacing {section.grid_spacing_pct}% "
                f"exceeds maximum 50%"
            )

        # Check grid count
        if section.grid_count < 1:
            errors.append(f"Section {section.section_id}: grid count must be >= 1")

    # Check section ordering (each section should be below previous)
    for i in range(1, len(blueprint.sections)):
        prev_section = blueprint.sections[i - 1]
        curr_section = blueprint.sections[i]

        if curr_section.upper_price >= prev_section.lower_price:
            errors.append(
                f"Section {curr_section.section_id} upper price "
                f"({curr_section.upper_price}) must be below section "
                f"{prev_section.section_id} lower price ({prev_section.lower_price})"
            )

    # Check gap consistency (gap_to_next should match actual gap)
    for i in range(len(blueprint.sections) - 1):
        section = blueprint.sections[i]
        next_section = blueprint.sections[i + 1]

        if section.gap_to_next_pct is not None:
            actual_gap_pct = (
                (section.lower_price - next_section.upper_price) / section.lower_price
            ) * 100

            # Allow small tolerance for rounding
            tolerance = Decimal("0.5")
            if abs(actual_gap_pct - section.gap_to_next_pct) > tolerance:
                errors.append(
                    f"Section {section.section_id}: declared gap "
                    f"{section.gap_to_next_pct}% does not match actual gap "
                    f"{actual_gap_pct:.2f}%"
                )

    return errors


def verify_uniform_spacing(prices: list[Price], tolerance: Decimal = Decimal("0.01")) -> bool:
    """
    Verify that spacing between prices is uniform (for arithmetic mode).

    Args:
        prices: List of prices to check
        tolerance: Allowed deviation from uniform spacing

    Returns:
        True if spacing is uniform within tolerance
    """
    if len(prices) < 3:
        return True

    spacings = [prices[i] - prices[i + 1] for i in range(len(prices) - 1)]
    first_spacing = spacings[0]

    return all(abs(spacing - first_spacing) <= tolerance for spacing in spacings[1:])


def verify_geometric_spacing(
    prices: list[Price],
    expected_spacing_pct: Decimal,
    tolerance: Decimal = Decimal("0.01"),
) -> bool:
    """
    Verify that spacing follows geometric (percentage) pattern.

    Args:
        prices: List of prices to check
        expected_spacing_pct: Expected spacing percentage
        tolerance: Allowed deviation in percentage points

    Returns:
        True if spacing matches expected geometric pattern
    """
    if len(prices) < 2:
        return True

    expected_ratio = Decimal("1") - (expected_spacing_pct / Decimal("100"))

    for i in range(len(prices) - 1):
        if prices[i] == 0:
            return False
        actual_ratio = prices[i + 1] / prices[i]
        if abs(actual_ratio - expected_ratio) > (tolerance / Decimal("100")):
            return False

    return True


def calculate_section_capital(
    blueprint: Blueprint,
    section_id: SectionId,
) -> Decimal:
    """
    Calculate capital allocated to a section.

    Args:
        blueprint: The strategy blueprint
        section_id: Section ID to calculate capital for

    Returns:
        Capital amount in quote currency (e.g., USDT)
    """
    section = blueprint.get_section(section_id)
    if section is None:
        raise ValueError(f"Section {section_id} not found")

    return blueprint.total_capital * (section.capital_allocation_pct / Decimal("100"))


def calculate_capital_per_grid(
    blueprint: Blueprint,
    section_id: SectionId,
) -> Decimal:
    """
    Calculate capital per grid level in a section.

    Args:
        blueprint: The strategy blueprint
        section_id: Section ID

    Returns:
        Capital per grid in quote currency
    """
    section = blueprint.get_section(section_id)
    if section is None:
        raise ValueError(f"Section {section_id} not found")

    section_capital = calculate_section_capital(blueprint, section_id)
    return section_capital / Decimal(section.grid_count)


def populate_section_levels(
    section: Section,
    prices: list[Price],
    capital_per_grid: Decimal,
) -> Section:
    """
    Populate a section with grid levels from calculated prices.

    Args:
        section: The section to populate
        prices: Calculated prices for this section
        capital_per_grid: Capital allocated per grid level

    Returns:
        Section with populated levels
    """
    levels: list[GridLevelModel] = []

    for i, price in enumerate(prices):
        # Calculate quantity: capital / price
        quantity = (capital_per_grid / price) if price > 0 else Decimal("0")

        level = GridLevelModel(
            level=i,
            price=price,
            quantity=quantity,
        )
        levels.append(level)

    section.levels = levels
    return section
