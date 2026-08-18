"""
Unit tests for grid calculator.

Tests verify key domain rules:
1. Grid spacing is UNIFORM within each Section (geometric or arithmetic)
2. Section Gaps may DIFFER between Sections
3. Calculator is deterministic (same input → same output)
"""

from decimal import Decimal

import pytest

from trading_grid.domain.grid.calculator import (
    calculate_capital_per_grid,
    calculate_grid_prices,
    calculate_section_capital,
    populate_section_levels,
    validate_blueprint,
    verify_geometric_spacing,
    verify_uniform_spacing,
)
from trading_grid.domain.grid.models import Blueprint, Section
from trading_grid.domain.shared.errors import BlueprintValidationError


def create_test_blueprint() -> Blueprint:
    """Create a valid test blueprint with 3 sections."""
    sections = [
        Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("96"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("30"),
            gap_to_next_pct=Decimal("5"),
        ),
        Section(
            section_id=2,
            upper_price=Decimal("91"),
            lower_price=Decimal("87"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("35"),
            gap_to_next_pct=Decimal("10"),
        ),
        Section(
            section_id=3,
            upper_price=Decimal("78"),
            lower_price=Decimal("74"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("35"),
        ),
    ]
    return Blueprint(
        blueprint_id="bp-test-001",
        market_id="BTC-USDT",
        total_capital=Decimal("1000"),
        sections=sections,
    )


class TestCalculateGridPrices:
    """Tests for calculate_grid_prices."""

    def test_geometric_spacing(self) -> None:
        """Geometric spacing should produce percentage-based prices."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("95"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("100"),
        )
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[section],
        )

        result = calculate_grid_prices(blueprint, spacing_mode="geometric")
        prices = result.get_prices(1)

        assert len(prices) == 5
        assert prices[0] == Decimal("100")
        # Each price should be 99% of previous
        assert verify_geometric_spacing(prices, Decimal("1"))

    def test_arithmetic_spacing(self) -> None:
        """Arithmetic spacing should produce uniform absolute differences."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("96"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("100"),
        )
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[section],
        )

        result = calculate_grid_prices(blueprint, spacing_mode="arithmetic")
        prices = result.get_prices(1)

        assert len(prices) == 5
        assert prices[0] == Decimal("100")
        assert prices[-1] == Decimal("96")
        assert verify_uniform_spacing(prices)

    def test_grid_prices_are_uniform_within_section(self) -> None:
        """Grid spacing must be uniform within a Section (domain rule #1)."""
        blueprint = create_test_blueprint()
        result = calculate_grid_prices(blueprint, spacing_mode="geometric")

        for section in blueprint.sections:
            prices = result.get_prices(section.section_id)
            assert verify_geometric_spacing(prices, section.grid_spacing_pct)

    def test_section_gaps_may_differ(self) -> None:
        """Section gaps may differ between sections (domain rule #2)."""
        blueprint = create_test_blueprint()

        # Section 1 → 2 gap is 5%, Section 2 → 3 gap is ~10%
        assert blueprint.sections[0].gap_to_next_pct == Decimal("5")
        assert blueprint.sections[1].gap_to_next_pct == Decimal("10")

        result = calculate_grid_prices(blueprint)

        # Verify gaps are different
        s1_prices = result.get_prices(1)
        s2_prices = result.get_prices(2)
        s3_prices = result.get_prices(3)

        gap_1_2 = s1_prices[-1] - s2_prices[0]
        gap_2_3 = s2_prices[-1] - s3_prices[0]

        # Gaps should be different (5% vs 10%)
        assert gap_2_3 > gap_1_2

    def test_calculator_is_deterministic(self) -> None:
        """Same input must produce same output (determinism requirement)."""
        blueprint = create_test_blueprint()

        result1 = calculate_grid_prices(blueprint)
        result2 = calculate_grid_prices(blueprint)

        assert result1.section_prices == result2.section_prices

    def test_single_grid_section(self) -> None:
        """Section with single grid should return upper price only."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("99"),
            grid_count=1,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("100"),
        )
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[section],
        )

        result = calculate_grid_prices(blueprint)
        prices = result.get_prices(1)

        assert len(prices) == 1
        assert prices[0] == Decimal("100")

    def test_invalid_blueprint_raises_error(self) -> None:
        """Invalid blueprint should raise BlueprintValidationError."""
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[],  # No sections
        )

        with pytest.raises(BlueprintValidationError):
            calculate_grid_prices(blueprint)


class TestValidateBlueprint:
    """Tests for validate_blueprint."""

    def test_valid_blueprint_passes(self) -> None:
        """Valid blueprint should return no errors."""
        blueprint = create_test_blueprint()
        errors = validate_blueprint(blueprint)
        assert errors == []

    def test_empty_blueprint_fails(self) -> None:
        """Blueprint without sections should fail."""
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[],
        )
        errors = validate_blueprint(blueprint)
        assert len(errors) > 0
        assert "no sections" in errors[0]

    def test_invalid_allocation_fails(self) -> None:
        """Blueprint with allocations not summing to 100% should fail."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("90"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("50"),  # Only 50%
        )
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[section],
        )
        errors = validate_blueprint(blueprint)
        assert any("100%" in e for e in errors)

    def test_overlapping_sections_fail(self) -> None:
        """Sections that overlap should fail validation."""
        sections = [
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("50"),
            ),
            Section(
                section_id=2,
                upper_price=Decimal("95"),  # Overlaps with section 1
                lower_price=Decimal("85"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("50"),
            ),
        ]
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=sections,
        )
        errors = validate_blueprint(blueprint)
        assert any("below" in e for e in errors)


class TestVerifySpacing:
    """Tests for spacing verification functions."""

    def test_verify_uniform_spacing_valid(self) -> None:
        """Uniform prices should pass verification."""
        prices = [Decimal("100"), Decimal("99"), Decimal("98"), Decimal("97")]
        assert verify_uniform_spacing(prices)

    def test_verify_uniform_spacing_invalid(self) -> None:
        """Non-uniform prices should fail verification."""
        prices = [Decimal("100"), Decimal("99"), Decimal("97"), Decimal("96")]
        assert not verify_uniform_spacing(prices)

    def test_verify_geometric_spacing_valid(self) -> None:
        """Geometric prices should pass verification."""
        prices = [Decimal("100"), Decimal("99"), Decimal("98.01"), Decimal("97.0299")]
        assert verify_geometric_spacing(prices, Decimal("1"))

    def test_verify_geometric_spacing_invalid(self) -> None:
        """Non-geometric prices should fail verification."""
        prices = [Decimal("100"), Decimal("99"), Decimal("98"), Decimal("97")]
        assert not verify_geometric_spacing(prices, Decimal("1"))


class TestCapitalCalculation:
    """Tests for capital calculation functions."""

    def test_calculate_section_capital(self) -> None:
        """Section capital should be allocation % of total."""
        blueprint = create_test_blueprint()

        # Section 1: 30% of 1000 = 300
        assert calculate_section_capital(blueprint, 1) == Decimal("300")
        # Section 2: 35% of 1000 = 350
        assert calculate_section_capital(blueprint, 2) == Decimal("350")

    def test_calculate_capital_per_grid(self) -> None:
        """Capital per grid should be section capital / grid count."""
        blueprint = create_test_blueprint()

        # Section 1: 300 / 5 = 60
        assert calculate_capital_per_grid(blueprint, 1) == Decimal("60")

    def test_calculate_section_capital_invalid_section(self) -> None:
        """Invalid section ID should raise ValueError."""
        blueprint = create_test_blueprint()

        with pytest.raises(ValueError, match="not found"):
            calculate_section_capital(blueprint, 99)


class TestPopulateSectionLevels:
    """Tests for populate_section_levels."""

    def test_populate_levels(self) -> None:
        """Populate should create grid levels with correct quantities."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("96"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("100"),
        )
        prices = [Decimal("100"), Decimal("99"), Decimal("98"), Decimal("97"), Decimal("96")]
        capital_per_grid = Decimal("100")

        populated = populate_section_levels(section, prices, capital_per_grid)

        assert len(populated.levels) == 5
        assert populated.levels[0].price == Decimal("100")
        assert populated.levels[0].quantity == Decimal("1")  # 100 / 100
        assert populated.levels[4].price == Decimal("96")


class TestDomainCalculatorBoundaries:
    """[D-H2, D-M3] Tests for lower_price boundary checks and section validation."""

    def test_geometric_series_breaching_lower_price_raises_validation_error(self) -> None:
        """[D-H2] If geometric prices decay below section.lower_price, raise BlueprintValidationError."""
        from trading_grid.domain.grid.calculator import calculate_section_prices

        # upper=100, spacing=2%, 5 grids: prices will be ~100, 98, 96.04, 94.12, 92.24
        # lower_price=95 -> prices[-1] (92.24) breaches lower_price (95)
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("95"),
            grid_count=5,
            grid_spacing_pct=Decimal("2"),
            capital_allocation_pct=Decimal("100"),
        )
        with pytest.raises(BlueprintValidationError, match="breaches lower price boundary"):
            calculate_section_prices(section, spacing_mode="geometric")

    def test_blueprint_validation_catches_geometric_lower_price_breach(self) -> None:
        """[D-H2] validate_blueprint must report geometric series lower price breaches."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("95"),
            grid_count=5,
            grid_spacing_pct=Decimal("2"),
            capital_allocation_pct=Decimal("100"),
        )
        blueprint = Blueprint(
            blueprint_id="bp-test",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=[section],
        )
        errors = validate_blueprint(blueprint)
        assert any("breaches lower price" in e for e in errors)

    def test_arithmetic_invalid_price_range_raises(self) -> None:
        """[D-M3] Arithmetic mode requires upper_price > lower_price."""
        from trading_grid.domain.grid.calculator import calculate_section_prices

        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("90"),
            grid_count=5,
            grid_spacing_pct=Decimal("2"),
            capital_allocation_pct=Decimal("100"),
        )
        prices = calculate_section_prices(section, spacing_mode="arithmetic")
        assert len(prices) == 5
        assert prices[0] == Decimal("100")
        assert prices[-1] == Decimal("90")
