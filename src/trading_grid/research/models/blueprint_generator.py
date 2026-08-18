"""
Blueprint Generator — Converts MarketRecommendation into executable Blueprint.

This module bridges the gap between the ML ranking output
(MarketRecommendation) and the grid execution input (Blueprint).

Per AI_TRADING_GRID_WORKFLOW.md:
- AI provides intelligence (ranking, suitability)
- Blueprint Generator translates recommendations into grid parameters
- Deterministic calculator produces exact prices
- Risk validation gates execution

The generator uses the suitability score and risk level to determine:
- Number of sections (1-3 based on risk)
- Grid spacing (tighter for high-confidence, wider for uncertain)
- Capital allocation per section
- Grid count per section
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from json import dumps as json_dumps

import structlog

from trading_grid.domain.grid.models import Blueprint, Section
from trading_grid.domain.shared.types import Price
from trading_grid.research.models.ranking import (
    MarketRecommendation,
    RecommendationAction,
    RiskLevel,
)

logger = structlog.get_logger()

BLUEPRINT_GENERATOR_VERSION = "blueprint-gen-v001"


@dataclass
class BlueprintConfig:
    """Configuration for blueprint generation."""

    # Default capital for demo grids (USDT)
    default_capital: Decimal = Decimal("1000")

    # Grid spacing ranges by risk level (percentage)
    spacing_low_risk: Decimal = Decimal("0.5")
    spacing_medium_risk: Decimal = Decimal("1.0")
    spacing_high_risk: Decimal = Decimal("2.0")

    # Grid count ranges
    min_grids_per_section: int = 3
    max_grids_per_section: int = 10

    # Section count by risk level
    sections_low_risk: int = 3
    sections_medium_risk: int = 2
    sections_high_risk: int = 1

    # Price range as percentage of current price
    price_range_pct: Decimal = Decimal("10")  # ±10% around current price


class BlueprintGenerator:
    """
    Generates executable Blueprints from MarketRecommendations.

    Usage:
        generator = BlueprintGenerator()
        blueprint = generator.generate(recommendation, current_price)
    """

    def __init__(self, config: BlueprintConfig | None = None) -> None:
        self.config = config or BlueprintConfig()

    def generate(
        self,
        recommendation: MarketRecommendation,
        current_price: Price,
        capital: Decimal | None = None,
    ) -> Blueprint:
        """
        Generate a Blueprint from a MarketRecommendation.

        Args:
            recommendation: The market recommendation with suitability score
            current_price: Current market price (anchor for grid)
            capital: Total capital (defaults to config.default_capital)

        Returns:
            Blueprint ready for deterministic calculation and risk validation

        Raises:
            ValueError: If recommendation action is AVOID or price invalid
        """
        if recommendation.action == RecommendationAction.AVOID:
            raise ValueError(
                f"Cannot generate blueprint for AVOID recommendation: {recommendation.market_id}"
            )

        if current_price <= 0:
            raise ValueError(f"Current price must be positive, got {current_price}")

        total_capital = capital or self.config.default_capital
        risk_level = recommendation.suitability_score.risk_level

        # Determine section count based on risk
        section_count = self._get_section_count(risk_level)

        # Determine grid spacing based on risk
        spacing = self._get_spacing(risk_level)

        # Calculate price range
        range_pct = self.config.price_range_pct
        upper_price = current_price * (1 + range_pct / 100)
        lower_price = current_price * (1 - range_pct / 100)

        # Generate sections
        sections = self._generate_sections(
            section_count=section_count,
            upper_price=upper_price,
            lower_price=lower_price,
            spacing=spacing,
            total_capital=total_capital,
        )

        # [R-M8] Deterministic Blueprint ID: hash of stable input parameters so that
        # identical recommendations and capital inputs always produce the same Blueprint ID.
        # This enables idempotent re-runs and reliable audit trail correlation.
        _id_payload = json_dumps(
            {
                "market_id": recommendation.market_id,
                "total_capital": str(total_capital),
                "section_count": section_count,
                "spacing": str(spacing),
                "risk_level": risk_level.value,
                "range_pct": str(range_pct),
                "generator_version": BLUEPRINT_GENERATOR_VERSION,
            },
            sort_keys=True,
        )
        blueprint_id = f"BP-{sha256(_id_payload.encode()).hexdigest()[:12].upper()}"

        blueprint = Blueprint(
            blueprint_id=blueprint_id,
            market_id=recommendation.market_id,
            total_capital=total_capital,
            sections=sections,
            status="DRAFT",
            metadata={
                "generator_version": BLUEPRINT_GENERATOR_VERSION,
                "source_recommendation_rank": recommendation.rank,
                "suitability_score": recommendation.suitability_score.total_score,
                "risk_level": risk_level.value,
                "action": recommendation.action.value,
                "confidence": recommendation.confidence,
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )

        logger.info(
            "blueprint_generated",
            blueprint_id=blueprint_id,
            market_id=recommendation.market_id,
            sections=section_count,
            total_grids=blueprint.total_grid_count,
            risk_level=risk_level.value,
        )

        return blueprint

    def _get_section_count(self, risk_level: RiskLevel) -> int:
        """Determine section count based on risk level."""
        if risk_level == RiskLevel.LOW:
            return self.config.sections_low_risk
        if risk_level == RiskLevel.MEDIUM:
            return self.config.sections_medium_risk
        return self.config.sections_high_risk

    def _get_spacing(self, risk_level: RiskLevel) -> Decimal:
        """Determine grid spacing based on risk level."""
        if risk_level == RiskLevel.LOW:
            return self.config.spacing_low_risk
        if risk_level == RiskLevel.MEDIUM:
            return self.config.spacing_medium_risk
        return self.config.spacing_high_risk

    def _generate_sections(
        self,
        section_count: int,
        upper_price: Price,
        lower_price: Price,
        spacing: Decimal,
        total_capital: Decimal,
    ) -> list[Section]:
        """Generate sections with uniform spacing within each."""
        sections: list[Section] = []

        # Divide price range equally among sections
        total_range = upper_price - lower_price
        section_range = total_range / section_count

        # Capital allocation: equal split
        capital_per_section = Decimal("100") / section_count

        for i in range(section_count):
            section_upper = upper_price - (section_range * i)
            section_lower = upper_price - (section_range * (i + 1))

            # Calculate grid count based on range and spacing
            # For geometric spacing: count = range / (price * spacing%)
            avg_price = (section_upper + section_lower) / 2
            grid_count = int(section_range / (avg_price * spacing / 100))
            grid_count = max(
                self.config.min_grids_per_section,
                min(grid_count, self.config.max_grids_per_section),
            )

            # Gap to next section (None for last)
            gap_to_next = spacing / 2 if i < section_count - 1 else None

            section = Section(
                section_id=i + 1,
                upper_price=section_upper,
                lower_price=section_lower,
                grid_count=grid_count,
                grid_spacing_pct=spacing,
                capital_allocation_pct=capital_per_section,
                gap_to_next_pct=gap_to_next,
                status="INACTIVE",
            )
            sections.append(section)

        return sections

    def generate_default(
        self,
        market_id: str,
        current_price: Price,
        capital: Decimal | None = None,
    ) -> Blueprint:
        """
        Generate a default blueprint without ML recommendation.

        Used when no trained model is available (fallback mode).
        Creates a conservative single-section grid.

        Args:
            market_id: Market to trade
            current_price: Current market price
            capital: Total capital

        Returns:
            Conservative Blueprint with single section
        """
        total_capital = capital or self.config.default_capital

        # Conservative: single section, medium spacing
        range_pct = Decimal("5")  # Tighter range for default
        upper_price = current_price * (1 + range_pct / 100)
        lower_price = current_price * (1 - range_pct / 100)

        spacing = self.config.spacing_medium_risk
        avg_price = (upper_price + lower_price) / 2
        grid_count = int((upper_price - lower_price) / (avg_price * spacing / 100))
        grid_count = max(3, min(grid_count, 8))

        section = Section(
            section_id=1,
            upper_price=upper_price,
            lower_price=lower_price,
            grid_count=grid_count,
            grid_spacing_pct=spacing,
            capital_allocation_pct=Decimal("100"),
            gap_to_next_pct=None,
            status="INACTIVE",
        )

        # [R-M8] Deterministic ID for generate_default as well
        _id_payload = json_dumps(
            {
                "market_id": market_id,
                "total_capital": str(total_capital),
                "mode": "default_fallback",
                "generator_version": BLUEPRINT_GENERATOR_VERSION,
            },
            sort_keys=True,
        )
        blueprint_id = f"BP-{sha256(_id_payload.encode()).hexdigest()[:12].upper()}"

        blueprint = Blueprint(
            blueprint_id=blueprint_id,
            market_id=market_id,
            total_capital=total_capital,
            sections=[section],
            status="DRAFT",
            metadata={
                "generator_version": BLUEPRINT_GENERATOR_VERSION,
                "mode": "default_fallback",
                "generated_at": datetime.now(UTC).isoformat(),
            },
        )

        logger.info(
            "default_blueprint_generated",
            blueprint_id=blueprint_id,
            market_id=market_id,
            grids=grid_count,
        )

        return blueprint
