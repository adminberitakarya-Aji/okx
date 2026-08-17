"""
Simulations API routes.

Endpoints for running and querying grid simulations.

Authorization: LEVEL 1+ (Research / Simulation)
"""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter, HTTPException

from okx_trading.api.routes.dependencies import get_default_container
from okx_trading.api.schemas.simulations import (
    SimulationListResponse,
    SimulationResultResponse,
    SimulationRunRequest,
)

logger = structlog.get_logger()

router = APIRouter()


def _result_to_response(result: object, simulation_id: str) -> SimulationResultResponse:
    """Convert a SimulationResult to response schema."""
    from okx_trading.research.simulator.grid_simulator import SimulationResult  # noqa: TC001

    r: SimulationResult = result  # type: ignore[assignment]

    return SimulationResultResponse(
        simulation_id=simulation_id,
        market_id=r.market_id,
        status="COMPLETED",
        candles_processed=r.candles_processed,
        initial_capital=r.initial_capital,
        total_pnl=r.total_pnl,
        net_pnl_return_pct=Decimal(str(r.net_pnl_return_pct)),
        realized_pnl=r.realized_pnl,
        unrealized_pnl=r.unrealized_pnl,
        completed_cycles=r.completed_cycles,
        total_buy_count=r.total_buy_count,
        total_sell_count=r.total_sell_count,
        open_lots=r.open_lots,
        total_fees_paid=r.total_fees_paid,
        max_drawdown_pct=Decimal(str(r.max_drawdown_pct)),
        simulation_status=r.simulation_status,
        completed_at=datetime.now(UTC),
    )


@router.post("/runs", response_model=SimulationResultResponse, status_code=201)
async def run_simulation(request: SimulationRunRequest) -> SimulationResultResponse:
    """
    Run a grid simulation for a market.

    Executes the deterministic grid simulator over historical candles.
    """
    container = get_default_container()
    service = container.research_service

    simulation_id = f"SIM-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

    try:
        result = await service.run_simulation(
            market_id=request.market_id.upper(),
            interval=request.interval,
            candle_limit=request.candle_limit,
        )
    except Exception as e:
        logger.error("simulation_failed", market_id=request.market_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Simulation failed: {e}") from e

    return _result_to_response(result, simulation_id)


@router.get("/history", response_model=SimulationListResponse)
async def get_simulation_history(limit: int = 10) -> SimulationListResponse:
    """
    Get recent simulation results.

    Args:
        limit: Maximum number of results to return
    """
    container = get_default_container()
    service = container.research_service

    history = service.get_simulation_history(limit=limit)

    simulations = [_result_to_response(r, f"SIM-{i}") for i, r in enumerate(reversed(history))]

    return SimulationListResponse(
        simulations=simulations,
        total=len(simulations),
    )
