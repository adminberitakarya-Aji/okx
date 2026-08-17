"""
Unit tests for grid domain models.

Tests verify key domain rules:
1. Grid spacing is uniform within each Section
2. Section Gaps may differ between Sections
3. Blueprint validation
"""

from decimal import Decimal

import pytest

from okx_trading.domain.grid.models import (
    Blueprint,
    CalculatedGridPrices,
    GridLevelModel,
    Section,
)


class TestGridLevelModel:
    """Tests for GridLevelModel."""

    def test_valid_grid_level(self) -> None:
        """Grid level with valid values should be created."""
        level = GridLevelModel(
            level=0,
            price=Decimal("100"),
            quantity=Decimal("0.1"),
        )
        assert level.level == 0
        assert level.price == Decimal("100")
        assert level.status == "PENDING"
        assert not level.is_filled

    def test_negative_level_raises_error(self) -> None:
        """Negative grid level should raise ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            GridLevelModel(level=-1, price=Decimal("100"))

    def test_zero_price_raises_error(self) -> None:
        """Zero price should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            GridLevelModel(level=0, price=Decimal("0"))

    def test_negative_price_raises_error(self) -> None:
        """Negative price should raise ValueError."""
        with pytest.raises(ValueError, match="positive"):
            GridLevelModel(level=0, price=Decimal("-100"))

    def test_is_filled_with_position(self) -> None:
        """Grid level with position quantity should be filled."""
        level = GridLevelModel(
            level=0,
            price=Decimal("100"),
            position_quantity=Decimal("0.1"),
            entry_price=Decimal("100"),
        )
        assert level.is_filled


class TestSection:
    """Tests for Section."""

    def test_valid_section(self) -> None:
        """Section with valid values should be created."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("90"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("30"),
        )
        assert section.section_id == 1
        assert section.price_range == Decimal("10")
        assert section.status == "INACTIVE"

    def test_invalid_section_id(self) -> None:
        """Section ID < 1 should raise ValueError."""
        with pytest.raises(ValueError, match="Section ID"):
            Section(
                section_id=0,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("30"),
            )

    def test_upper_price_must_be_greater_than_lower(self) -> None:
        """Upper price must be greater than lower price."""
        with pytest.raises(ValueError, match="greater than"):
            Section(
                section_id=1,
                upper_price=Decimal("90"),
                lower_price=Decimal("100"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("30"),
            )

    def test_invalid_grid_count(self) -> None:
        """Grid count < 1 should raise ValueError."""
        with pytest.raises(ValueError, match="Grid count"):
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=0,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("30"),
            )

    def test_invalid_spacing(self) -> None:
        """Non-positive spacing should raise ValueError."""
        with pytest.raises(ValueError, match="spacing"):
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("0"),
                capital_allocation_pct=Decimal("30"),
            )

    def test_invalid_capital_allocation(self) -> None:
        """Capital allocation outside 0-100 should raise ValueError."""
        with pytest.raises(ValueError, match="Capital allocation"):
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("150"),
            )

    def test_fill_ratio_empty(self) -> None:
        """Fill ratio with no levels should be 0."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("90"),
            grid_count=5,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("30"),
        )
        assert section.fill_ratio == Decimal("0")

    def test_fill_ratio_with_levels(self) -> None:
        """Fill ratio should calculate correctly."""
        section = Section(
            section_id=1,
            upper_price=Decimal("100"),
            lower_price=Decimal("90"),
            grid_count=4,
            grid_spacing_pct=Decimal("1"),
            capital_allocation_pct=Decimal("30"),
            levels=[
                GridLevelModel(level=0, price=Decimal("100"), position_quantity=Decimal("1")),
                GridLevelModel(level=1, price=Decimal("99"), position_quantity=Decimal("0")),
                GridLevelModel(level=2, price=Decimal("98"), position_quantity=Decimal("1")),
                GridLevelModel(level=3, price=Decimal("97"), position_quantity=Decimal("0")),
            ],
        )
        assert section.fill_ratio == Decimal("0.5")
        assert len(section.filled_levels) == 2


class TestBlueprint:
    """Tests for Blueprint."""

    def test_valid_blueprint(self) -> None:
        """Blueprint with valid values should be created."""
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
        )
        assert blueprint.blueprint_id == "bp-001"
        assert blueprint.status == "DRAFT"
        assert blueprint.section_count == 0

    def test_invalid_capital(self) -> None:
        """Non-positive capital should raise ValueError."""
        with pytest.raises(ValueError, match="capital"):
            Blueprint(
                blueprint_id="bp-001",
                market_id="BTC-USDT",
                total_capital=Decimal("0"),
            )

    def test_blueprint_with_sections(self) -> None:
        """Blueprint should track sections correctly."""
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
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=sections,
        )

        assert blueprint.section_count == 3
        assert blueprint.total_grid_count == 15
        assert blueprint.highest_price == Decimal("100")
        assert blueprint.lowest_price == Decimal("74")
        assert blueprint.capital_allocation_sum == Decimal("100")

    def test_validate_allocations_valid(self) -> None:
        """Valid allocations should return no errors."""
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
                upper_price=Decimal("85"),
                lower_price=Decimal("75"),
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
        assert blueprint.validate_allocations() == []

    def test_validate_allocations_invalid(self) -> None:
        """Invalid allocations should return errors."""
        sections = [
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("30"),
            ),
        ]
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=sections,
        )
        errors = blueprint.validate_allocations()
        assert len(errors) == 1
        assert "100%" in errors[0]

    def test_get_section(self) -> None:
        """get_section should return correct section."""
        sections = [
            Section(
                section_id=1,
                upper_price=Decimal("100"),
                lower_price=Decimal("90"),
                grid_count=5,
                grid_spacing_pct=Decimal("1"),
                capital_allocation_pct=Decimal("100"),
            ),
        ]
        blueprint = Blueprint(
            blueprint_id="bp-001",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            sections=sections,
        )
        assert blueprint.get_section(1) is not None
        assert blueprint.get_section(2) is None


class TestCalculatedGridPrices:
    """Tests for CalculatedGridPrices."""

    def test_get_prices(self) -> None:
        """get_prices should return prices for section."""
        prices = CalculatedGridPrices(
            blueprint_id="bp-001",
            section_prices={
                1: [Decimal("100"), Decimal("99"), Decimal("98")],
                2: [Decimal("91"), Decimal("90"), Decimal("89")],
            },
        )
        assert prices.get_prices(1) == [Decimal("100"), Decimal("99"), Decimal("98")]
        assert prices.get_prices(3) == []

    def test_all_prices_sorted_descending(self) -> None:
        """all_prices should return sorted prices."""
        prices = CalculatedGridPrices(
            blueprint_id="bp-001",
            section_prices={
                1: [Decimal("100"), Decimal("98")],
                2: [Decimal("91"), Decimal("89")],
            },
        )
        assert prices.all_prices == [
            Decimal("100"),
            Decimal("98"),
            Decimal("91"),
            Decimal("89"),
        ]
