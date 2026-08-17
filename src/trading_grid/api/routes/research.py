"""
Research API routes.

Endpoints for AI research results, market recommendations, and research runs.

Authorization: LEVEL 1+ (Research / Simulation)
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

import structlog
from fastapi import APIRouter, HTTPException, Query

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.common import OperationResponse, OperationStatus
from trading_grid.api.schemas.research import (
    MarketRecommendationResponse,
    RecommendationLevel,
    RecommendationListResponse,
    ResearchRunRequest,
    ResearchUniverseResponse,
)

logger = structlog.get_logger()

router = APIRouter()

# Map risk level to recommendation level
_RISK_TO_RECOMMENDATION = {
    "LOW": "HIGH_PRIORITY",
    "MEDIUM": "MEDIUM_PRIORITY",
    "HIGH": "LOW_PRIORITY",
    "EXTREME": "NOT_RECOMMENDED",
}


@router.get("/universe", response_model=ResearchUniverseResponse)
async def get_research_universe() -> ResearchUniverseResponse:
    """
    Get the current research universe (Top 10 market selection).

    Returns the list of markets in the research universe.
    """
    container = get_default_container()
    service = container.research_service

    status = service.get_service_status()
    last_ranking = service.last_ranking

    markets: list[str] = []
    if last_ranking and last_ranking.recommendations:
        markets = [r.market_id for r in last_ranking.recommendations]

    return ResearchUniverseResponse(
        universe_type="TOP_10",
        snapshot_id=status.get("last_ranking_id", "N/A"),
        markets=markets,
        updated_at=status.get("last_ranking_at"),
    )


@router.get("/recommendations", response_model=RecommendationListResponse)
async def get_recommendations(
    top_n: int = Query(default=10, ge=1, le=50, description="Number of recommendations"),
) -> RecommendationListResponse:
    """
    Get market recommendations from the AI research pipeline.

    Returns ranked markets with suitability scores and recommendations.
    """
    container = get_default_container()
    service = container.research_service

    try:
        result = await service.rank_markets(top_n=top_n)
    except Exception as e:
        logger.error("research_ranking_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Research ranking failed: {e}") from e

    recommendations: list[MarketRecommendationResponse] = []
    if result.recommendations:
        for r in result.recommendations:
            recommendations.append(
                MarketRecommendationResponse(
                    market_id=r.market_id,
                    rank=r.rank,
                    recommendation=cast(
                        "RecommendationLevel",
                        _RISK_TO_RECOMMENDATION.get(
                            r.suitability_score.risk_level.value, "NOT_RECOMMENDED"
                        ),
                    ),
                    suitability_score=Decimal(str(r.suitability_score.total_score)),
                    confidence=Decimal(str(r.suitability_score.total_score)),
                    market_regime=None,
                    execution_quality=None,
                    research_reasons=[],
                    updated_at=datetime.now(UTC),
                )
            )

    return RecommendationListResponse(
        recommendations=recommendations,
        total=len(recommendations),
        model_version="heuristic-v1",
        generated_at=datetime.now(UTC),
    )


@router.get("/market/{market_id}")
async def get_market_research(market_id: str) -> dict[str, Any]:
    """
    Get research detail for a specific market.

    Returns market state, execution economics, and grid suitability.
    """
    container = get_default_container()
    service = container.research_service

    # Check if market is in last ranking
    last_ranking = service.last_ranking
    recommendation = None
    if last_ranking and last_ranking.recommendations:
        for r in last_ranking.recommendations:
            if r.market_id == market_id.upper():
                recommendation = {
                    "market_id": r.market_id,
                    "rank": r.rank,
                    "suitability_score": float(r.suitability_score.total_score),
                    "risk_level": r.suitability_score.risk_level.value,
                    "action": r.action.value,
                }
                break

    if recommendation is None:
        raise HTTPException(status_code=404, detail=f"No research data for market: {market_id}")

    return {
        "market_id": market_id.upper(),
        "recommendation": recommendation,
        "market_state": {},
        "execution_economics": {},
        "grid_suitability": {},
        "updated_at": datetime.now(UTC).isoformat(),
    }


@router.post("/runs", response_model=OperationResponse, status_code=202)
async def create_research_run(request: ResearchRunRequest) -> OperationResponse:
    """
    Create a new research run (async operation).

    Triggers the AI research pipeline to rank markets.
    Returns an operation ID for status polling.
    """
    container = get_default_container()
    service = container.research_service

    operation_id = f"OP-RESEARCH-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    try:
        await service.rank_markets(top_n=10)
        status: OperationStatus = "SUCCEEDED"
    except Exception as e:
        logger.error("research_run_failed", operation_id=operation_id, error=str(e))
        status = "FAILED"

    return OperationResponse(
        operation_id=operation_id,
        command_type="RESEARCH_RUN",
        status=status,
        created_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        environment=request.environment,
        resource_type="research",
        resource_id=request.universe,
    )
