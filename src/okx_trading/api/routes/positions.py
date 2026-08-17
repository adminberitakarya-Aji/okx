"""
Positions API routes.

Endpoints for position queries.

Authorization: LEVEL 0+ (Read-only)
"""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException

from okx_trading.api.routes.dependencies import get_default_container
from okx_trading.api.schemas.positions import PositionListResponse, PositionResponse
from okx_trading.domain.execution.models import Position

logger = structlog.get_logger()

router = APIRouter()


async def _current_price_for(market_id: str) -> Decimal | None:
    """Best-effort fetch of the current market price for P&L marking."""
    container = get_default_container()
    adapter = container.research_service._adapter
    if adapter is None:
        return None
    try:
        ticker = await adapter.get_ticker(market_id)
        if ticker:
            last = ticker.get("last") or ticker.get("close")
            if last is not None:
                return Decimal(str(last))
    except Exception:
        logger.debug("position_price_fetch_failed", market_id=market_id)
    return None


async def _position_to_response(position: Position, environment: str = "DEMO") -> PositionResponse:
    """Convert a domain Position to PositionResponse."""
    current_price = await _current_price_for(position.market_id)
    mark_price = current_price if current_price is not None else position.average_entry_price

    return PositionResponse(
        market_id=position.market_id,
        quantity=position.quantity,
        average_entry_price=position.average_entry_price,
        current_price=current_price,
        unrealized_pnl=position.unrealized_pnl(mark_price),
        realized_pnl=position.realized_pnl,
        grid_id=None,
        environment=environment,
        updated_at=position.updated_at,
    )


@router.get("", response_model=PositionListResponse)
async def list_positions() -> PositionListResponse:
    """
    List all open positions.

    Returns positions tracked by the execution engine.
    """
    container = get_default_container()
    engine = container.execution_engine

    positions = engine.get_positions()
    open_positions = [p for p in positions if p.is_open]

    responses = [await _position_to_response(p) for p in open_positions]

    return PositionListResponse(
        positions=responses,
        total=len(responses),
        environment="DEMO",
        updated_at=datetime.now(UTC),
    )


@router.get("/{market_id}", response_model=PositionResponse)
async def get_position(market_id: str) -> PositionResponse:
    """
    Get position for a specific market.

    Args:
        market_id: Market ID (e.g., BTC-USDT)
    """
    container = get_default_container()
    engine = container.execution_engine

    position = engine.get_position(market_id.upper())
    if position is None or not position.is_open:
        raise HTTPException(status_code=404, detail=f"No open position for market: {market_id}")

    return await _position_to_response(position)
