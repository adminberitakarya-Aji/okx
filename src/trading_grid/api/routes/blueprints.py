"""
Blueprints API routes.

Endpoints for grid blueprint management.

Authorization: LEVEL 1+ (Research / Simulation)
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException

from trading_grid.api.routes.dependencies import get_current_identity, get_default_container
from trading_grid.api.schemas.grid import (
    BlueprintGenerateRequest,
    BlueprintResponse,
    SectionResponse,
)
from trading_grid.application.services.authorization import Identity
from trading_grid.domain.grid.models import Blueprint

logger = structlog.get_logger()

router = APIRouter()


def _blueprint_to_response(blueprint: Blueprint) -> BlueprintResponse:
    """Convert a domain Blueprint to BlueprintResponse."""
    sections = [
        SectionResponse(
            section_id=s.section_id,
            upper_price=s.upper_price,
            lower_price=s.lower_price,
            grid_count=s.grid_count,
            grid_spacing_pct=s.grid_spacing_pct,
            capital_allocation_pct=s.capital_allocation_pct,
            gap_to_next_pct=s.gap_to_next_pct,
            status=s.status,
            fill_ratio=s.fill_ratio,
        )
        for s in blueprint.sections
    ]

    return BlueprintResponse(
        blueprint_id=blueprint.blueprint_id,
        market_id=blueprint.market_id,
        total_capital=blueprint.total_capital,
        section_count=blueprint.section_count,
        total_grid_count=blueprint.total_grid_count,
        sections=sections,
        status=blueprint.status,
        created_at=blueprint.created_at,
        updated_at=blueprint.updated_at,
        validation_status="VALID" if not blueprint.validate_allocations() else "INVALID",
    )


@router.get("", response_model=list[BlueprintResponse])
async def list_blueprints() -> list[BlueprintResponse]:
    """
    List all generated blueprints.

    Returns blueprints from the research service cache.
    """
    container = get_default_container()
    service = container.research_service

    blueprints = service.blueprints
    return [_blueprint_to_response(bp) for bp in blueprints.values()]


@router.get("/{blueprint_id}", response_model=BlueprintResponse)
async def get_blueprint(blueprint_id: str) -> BlueprintResponse:
    """
    Get a specific blueprint by ID.

    Args:
        blueprint_id: Blueprint ID (e.g., BP-xxx)
    """
    container = get_default_container()
    service = container.research_service

    blueprint = service.get_blueprint(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Blueprint not found: {blueprint_id}")

    return _blueprint_to_response(blueprint)


@router.post("/generate", response_model=BlueprintResponse, status_code=201)
async def generate_blueprint(
    request: BlueprintGenerateRequest,  # [I-L5] migrated to request body
    identity: Identity = Depends(get_current_identity),  # [I-C3] require identity
) -> BlueprintResponse:
    """
    Generate a new default blueprint for a market.

    Uses the BlueprintGenerator's default (conservative) configuration
    anchored to the current market price when available.

    [I-C3] The blueprint is owned by the authenticated identity.
    [I-L5] Parameters are now passed via request body (Pydantic model)
    instead of query params to support richer configuration options
    and align with REST best practices.
    """
    container = get_default_container()
    service = container.research_service

    market_id = request.market_id
    capital = request.capital
    market_id_upper = market_id.upper()

    # Try to get current price from the exchange adapter
    current_price = Decimal("100")  # fallback anchor
    adapter = service._adapter
    if adapter is not None:
        try:
            # [D-M8] get_ticker now returns a domain Ticker model
            ticker = await adapter.get_ticker(market_id_upper)
            if ticker.last_price > Decimal("0"):
                current_price = ticker.last_price
        except Exception:
            logger.debug("blueprint_price_fetch_failed", market_id=market_id_upper)

    try:
        blueprint = service.generate_default_blueprint(
            market_id=market_id_upper,
            current_price=current_price,
            capital=capital,
            user_id=identity.identity_id,  # [I-C3] set owner
        )
    except Exception as e:
        logger.error("blueprint_generation_failed", market_id=market_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Blueprint generation failed: {e}") from e

    return _blueprint_to_response(blueprint)


@router.post("/{blueprint_id}/validate")
async def validate_blueprint(blueprint_id: str) -> dict[str, Any]:
    """
    Validate a blueprint against deterministic rules.

    Checks:
    - Uniform spacing within sections
    - Valid section gaps
    - Capital allocation consistency
    """
    container = get_default_container()
    service = container.research_service

    blueprint = service.get_blueprint(blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Blueprint not found: {blueprint_id}")

    # Basic validation checks
    violations: list[str] = list(blueprint.validate_allocations())

    for section in blueprint.sections:
        if section.grid_count < 2:
            violations.append(f"Section {section.section_id}: grid_count < 2")
        if section.grid_spacing_pct <= 0:
            violations.append(f"Section {section.section_id}: invalid spacing")

    return {
        "blueprint_id": blueprint_id,
        "valid": len(violations) == 0,
        "violations": violations,
        "validated_at": datetime.now(UTC).isoformat(),
    }
