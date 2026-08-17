"""
Tests for BlueprintGenerator — converts MarketRecommendation into executable Blueprint.

Tests cover:
- generate() from MarketRecommendation for each risk level (LOW, MEDIUM, HIGH)
- Section count, spacing, and capital allocation per risk level
- Grid count bounds (min/max per section)
- Price range calculation (±10% around current price)
- AVOID recommendation rejection
- Invalid price rejection
- generate_default() conservative fallback
- Blueprint metadata correctness
- Domain rule: uniform spacing within each section
- Domain rule: capital allocations sum to 100%
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from trading_grid.research.models.blueprint_generator import (
    BLUEPRINT_GENERATOR_VERSION,
    BlueprintConfig,
    BlueprintGenerator,
)
from trading_grid.research.models.ranking import (
    MarketRecommendation,
    RecommendationAction,
    RiskLevel,
    SuitabilityScore,
)


def _make_recommendation(
    market_id: str = "BTC-USDT",
    risk_level: RiskLevel = RiskLevel.LOW,
    action: RecommendationAction = RecommendationAction.BUY,
    total_score: float = 70.0,
    rank: int = 1,
) -> MarketRecommendation:
    """Create a MarketRecommendation for testing."""
    score = SuitabilityScore(
        market_id=market_id,
        blueprint_id="BP-TEST",
        observation_timestamp=datetime.now(UTC),
        total_score=total_score,
        risk_level=risk_level,
    )
    return MarketRecommendation(
        market_id=market_id,
        rank=rank,
        suitability_score=score,
        action=action,
        confidence=0.8,
    )


class TestBlueprintGeneratorInit:
    """Tests for BlueprintGenerator initialization."""

    def test_default_config(self):
        """Generator uses default config when none provided."""
        gen = BlueprintGenerator()
        assert gen.config.default_capital == Decimal("1000")

    def test_custom_config(self):
        """Generator accepts custom config."""
        config = BlueprintConfig(default_capital=Decimal("5000"))
        gen = BlueprintGenerator(config=config)
        assert gen.config.default_capital == Decimal("5000")


class TestGenerateFromRecommendation:
    """Tests for generate() from MarketRecommendation."""

    def test_low_risk_produces_three_sections(self):
        """LOW risk recommendation produces 3 sections."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.section_count == 3

    def test_medium_risk_produces_two_sections(self):
        """MEDIUM risk recommendation produces 2 sections."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.MEDIUM)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.section_count == 2

    def test_high_risk_produces_one_section(self):
        """HIGH risk recommendation produces 1 section."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.HIGH)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.section_count == 1

    def test_extreme_risk_produces_one_section(self):
        """EXTREME risk recommendation produces 1 section (fallback)."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.EXTREME)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.section_count == 1

    def test_spacing_by_risk_level(self):
        """Grid spacing matches risk level configuration."""
        gen = BlueprintGenerator()

        low_rec = _make_recommendation(risk_level=RiskLevel.LOW)
        low_bp = gen.generate(low_rec, current_price=Decimal("50000"))
        assert all(s.grid_spacing_pct == Decimal("0.5") for s in low_bp.sections)

        med_rec = _make_recommendation(risk_level=RiskLevel.MEDIUM)
        med_bp = gen.generate(med_rec, current_price=Decimal("50000"))
        assert all(s.grid_spacing_pct == Decimal("1.0") for s in med_bp.sections)

        high_rec = _make_recommendation(risk_level=RiskLevel.HIGH)
        high_bp = gen.generate(high_rec, current_price=Decimal("50000"))
        assert all(s.grid_spacing_pct == Decimal("2.0") for s in high_bp.sections)

    def test_avoid_recommendation_raises(self):
        """AVOID recommendation raises ValueError."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(action=RecommendationAction.AVOID)

        with pytest.raises(ValueError, match="AVOID"):
            gen.generate(rec, current_price=Decimal("50000"))

    def test_zero_price_raises(self):
        """Zero price raises ValueError."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()

        with pytest.raises(ValueError, match="positive"):
            gen.generate(rec, current_price=Decimal("0"))

    def test_negative_price_raises(self):
        """Negative price raises ValueError."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()

        with pytest.raises(ValueError, match="positive"):
            gen.generate(rec, current_price=Decimal("-100"))

    def test_default_capital_used(self):
        """Default capital is used when none specified."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.total_capital == Decimal("1000")

    def test_custom_capital(self):
        """Custom capital overrides default."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()
        blueprint = gen.generate(rec, current_price=Decimal("50000"), capital=Decimal("5000"))

        assert blueprint.total_capital == Decimal("5000")

    def test_blueprint_id_format(self):
        """Blueprint ID follows BP-<hex> format."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.blueprint_id.startswith("BP-")
        assert len(blueprint.blueprint_id) == 15  # "BP-" + 12 hex chars

    def test_blueprint_status_is_draft(self):
        """Generated blueprint starts in DRAFT status."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.status == "DRAFT"

    def test_metadata_contains_generator_info(self):
        """Blueprint metadata contains generator version and source info."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(total_score=75.0, risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        meta = blueprint.metadata
        assert meta["generator_version"] == BLUEPRINT_GENERATOR_VERSION
        assert meta["source_recommendation_rank"] == rec.rank
        assert meta["suitability_score"] == 75.0
        assert meta["risk_level"] == "LOW"
        assert meta["action"] == "BUY"
        assert "generated_at" in meta


class TestPriceRange:
    """Tests for price range calculation."""

    def test_price_range_is_plus_minus_10_percent(self):
        """Price range spans ±10% around current price."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()
        current_price = Decimal("50000")
        blueprint = gen.generate(rec, current_price=current_price)

        expected_upper = current_price * Decimal("1.10")
        expected_lower = current_price * Decimal("0.90")

        assert blueprint.highest_price == expected_upper
        assert blueprint.lowest_price == expected_lower

    def test_sections_cover_full_range(self):
        """Sections collectively cover the full price range."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        current_price = Decimal("100")
        blueprint = gen.generate(rec, current_price=current_price)

        # Highest section upper should be 110 (100 * 1.1)
        assert blueprint.sections[0].upper_price == current_price * Decimal("1.10")
        # Lowest section lower should be 90 (100 * 0.9)
        assert blueprint.sections[-1].lower_price == current_price * Decimal("0.90")

    def test_sections_are_contiguous(self):
        """Sections are ordered from top to bottom without overlap."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("1000"))

        for i in range(len(blueprint.sections) - 1):
            upper_section = blueprint.sections[i]
            lower_section = blueprint.sections[i + 1]
            # Upper section's lower price should equal lower section's upper price
            assert upper_section.lower_price == lower_section.upper_price


class TestSectionProperties:
    """Tests for section-level properties."""

    def test_grid_count_within_bounds(self):
        """Grid count per section is within configured min/max bounds."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        for section in blueprint.sections:
            assert section.grid_count >= gen.config.min_grids_per_section
            assert section.grid_count <= gen.config.max_grids_per_section

    def test_capital_allocation_sums_to_100(self):
        """Capital allocations across sections sum to approximately 100%.

        Note: Decimal division (e.g., 100/3) causes tiny rounding residuals,
        so we check within a small tolerance rather than exact equality.
        """
        gen = BlueprintGenerator()

        for risk in (RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH):
            rec = _make_recommendation(risk_level=risk)
            blueprint = gen.generate(rec, current_price=Decimal("50000"))
            total_alloc = sum(s.capital_allocation_pct for s in blueprint.sections)
            # Allow tiny Decimal rounding tolerance (< 0.01%)
            assert abs(total_alloc - Decimal("100")) < Decimal("0.01"), (
                f"Capital allocation for {risk}: {total_alloc}"
            )

    def test_gap_to_next_set_for_non_last_sections(self):
        """gap_to_next_pct is set for all sections except the last."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        for i, section in enumerate(blueprint.sections):
            if i < len(blueprint.sections) - 1:
                assert section.gap_to_next_pct is not None
            else:
                assert section.gap_to_next_pct is None

    def test_section_ids_are_sequential(self):
        """Section IDs are 1-based and sequential."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        for i, section in enumerate(blueprint.sections):
            assert section.section_id == i + 1

    def test_section_status_is_inactive(self):
        """All sections start in INACTIVE status."""
        gen = BlueprintGenerator()
        rec = _make_recommendation()
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        for section in blueprint.sections:
            assert section.status == "INACTIVE"

    def test_upper_price_greater_than_lower(self):
        """Each section's upper price is greater than its lower price."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        for section in blueprint.sections:
            assert section.upper_price > section.lower_price


class TestGenerateDefault:
    """Tests for generate_default() fallback mode."""

    def test_single_section(self):
        """Default blueprint has a single section."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert blueprint.section_count == 1

    def test_tighter_price_range(self):
        """Default blueprint uses ±5% range (tighter than ±10%)."""
        gen = BlueprintGenerator()
        current_price = Decimal("100")
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=current_price,
        )

        expected_upper = current_price * Decimal("1.05")
        expected_lower = current_price * Decimal("0.95")

        assert blueprint.highest_price == expected_upper
        assert blueprint.lowest_price == expected_lower

    def test_medium_spacing(self):
        """Default blueprint uses medium-risk spacing."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert blueprint.sections[0].grid_spacing_pct == gen.config.spacing_medium_risk

    def test_grid_count_bounded_3_to_8(self):
        """Default blueprint grid count is between 3 and 8."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert 3 <= blueprint.sections[0].grid_count <= 8

    def test_full_capital_allocation(self):
        """Default blueprint allocates 100% to the single section."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert blueprint.sections[0].capital_allocation_pct == Decimal("100")
        assert blueprint.validate_allocations() == []

    def test_default_capital(self):
        """Default blueprint uses default capital."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert blueprint.total_capital == Decimal("1000")

    def test_custom_capital(self):
        """Default blueprint accepts custom capital."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
            capital=Decimal("2500"),
        )

        assert blueprint.total_capital == Decimal("2500")

    def test_metadata_indicates_fallback_mode(self):
        """Default blueprint metadata indicates fallback mode."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert blueprint.metadata["mode"] == "default_fallback"
        assert blueprint.metadata["generator_version"] == BLUEPRINT_GENERATOR_VERSION

    def test_no_gap_to_next(self):
        """Default blueprint single section has no gap_to_next."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert blueprint.sections[0].gap_to_next_pct is None


class TestVariousPriceLevels:
    """Tests for blueprint generation at various price levels."""

    @pytest.mark.parametrize(
        "price",
        [
            Decimal("0.0001"),  # Very low price (micro-cap)
            Decimal("1"),
            Decimal("100"),
            Decimal("50000"),  # BTC-like
            Decimal("100000"),
        ],
    )
    def test_valid_blueprint_at_various_prices(self, price: Decimal):
        """Blueprint is valid at various price levels."""
        gen = BlueprintGenerator()
        rec = _make_recommendation(risk_level=RiskLevel.MEDIUM)
        blueprint = gen.generate(rec, current_price=price)

        assert blueprint.total_capital > 0
        assert blueprint.section_count == 2
        assert blueprint.highest_price > blueprint.lowest_price
        total_alloc = sum(s.capital_allocation_pct for s in blueprint.sections)
        assert abs(total_alloc - Decimal("100")) < Decimal("0.01")

        for section in blueprint.sections:
            assert section.upper_price > section.lower_price
            assert section.grid_count >= 3

    @pytest.mark.parametrize(
        "price",
        [
            Decimal("0.0001"),
            Decimal("1"),
            Decimal("50000"),
        ],
    )
    def test_default_blueprint_at_various_prices(self, price: Decimal):
        """Default blueprint is valid at various price levels."""
        gen = BlueprintGenerator()
        blueprint = gen.generate_default(market_id="TEST-USDT", current_price=price)

        assert blueprint.section_count == 1
        assert blueprint.highest_price > blueprint.lowest_price
        assert blueprint.sections[0].grid_count >= 3


class TestCustomConfig:
    """Tests for custom BlueprintConfig."""

    def test_custom_section_counts(self):
        """Custom section counts are respected."""
        config = BlueprintConfig(
            sections_low_risk=2,
            sections_medium_risk=1,
            sections_high_risk=1,
        )
        gen = BlueprintGenerator(config=config)
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert blueprint.section_count == 2

    def test_custom_spacing(self):
        """Custom spacing is respected."""
        config = BlueprintConfig(
            spacing_low_risk=Decimal("0.25"),
        )
        gen = BlueprintGenerator(config=config)
        rec = _make_recommendation(risk_level=RiskLevel.LOW)
        blueprint = gen.generate(rec, current_price=Decimal("50000"))

        assert all(s.grid_spacing_pct == Decimal("0.25") for s in blueprint.sections)

    def test_custom_price_range(self):
        """Custom price range percentage is respected."""
        config = BlueprintConfig(price_range_pct=Decimal("20"))
        gen = BlueprintGenerator(config=config)
        rec = _make_recommendation()
        current_price = Decimal("100")
        blueprint = gen.generate(rec, current_price=current_price)

        assert blueprint.highest_price == current_price * Decimal("1.20")
        # Allow tiny Decimal rounding tolerance from section division
        assert abs(blueprint.lowest_price - current_price * Decimal("0.80")) < Decimal("0.001")
