"""
Markets API routes.

Endpoints for market data queries.

Authorization: LEVEL 0+ (Read-only)
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Query

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.markets import MarketListResponse, MarketResponse

logger = structlog.get_logger()

router = APIRouter()


@router.get("", response_model=MarketListResponse)
async def get_markets(
    limit: int = Query(default=20, ge=1, le=100, description="Max markets to return"),
) -> MarketListResponse:
    """
    Get list of available markets.

    Returns markets from the research universe or default list.
    """
    container = get_default_container()
    service = container.research_service

    # Use last ranking markets if available
    last_ranking = service.last_ranking
    market_ids: list[str] = []
    if last_ranking and last_ranking.recommendations:
        market_ids = [r.market_id for r in last_ranking.recommendations][:limit]
    else:
        from trading_grid.application.services.research_service import DEFAULT_MARKETS

        market_ids = list(DEFAULT_MARKETS)[:limit]

    markets = [
        MarketResponse(
            market_id=mid,
            base_currency=mid.split("-")[0] if "-" in mid else mid,
            quote_currency=mid.split("-")[1] if "-" in mid else "USDT",
            status="ACTIVE",
        )
        for mid in market_ids
    ]

    return MarketListResponse(
        markets=markets,
        total=len(markets),
        updated_at=datetime.now(UTC),
    )


@router.get("/{market_id}", response_model=MarketResponse)
async def get_market(market_id: str) -> MarketResponse:
    """
    Get detail for a specific market.

    Args:
        market_id: Market ID (e.g., BTC-USDT)
    """
    market_id_upper = market_id.upper()

    # Validate market ID format
    if "-" not in market_id_upper:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid market ID format: {market_id}. Expected format: BASE-QUOTE",
        )

    parts = market_id_upper.split("-")
    return MarketResponse(
        market_id=market_id_upper,
        base_currency=parts[0],
        quote_currency=parts[1] if len(parts) > 1 else "USDT",
        status="ACTIVE",
        updated_at=datetime.now(UTC),
    )
