"""
Grid API routes.

Endpoints for grid runtime control (start, pause, resume, stop, emergency-stop).

Authorization: LEVEL 2+ (Demo Grid Control), LEVEL 3+ (Live Grid Control)

.. note::
    TODO [I-L3]: Grid control routes currently hardcode ``get_default_container()``
    (OKX only). Multi-exchange support requires an ``exchange`` query parameter
    and per-exchange container dispatch.
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import structlog
from fastapi import APIRouter, HTTPException

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.grid import (
    GridControlResponse,
    GridListResponse,
    GridRuntimeResponse,
    GridStartRequest,
)

logger = structlog.get_logger()

router = APIRouter()


def _grid_to_response(
    grid: object, environment: Literal["DEMO", "LIVE"] = "DEMO"
) -> GridRuntimeResponse:
    """Convert a GridRuntime to response schema."""
    from trading_grid.application.services.grid_engine import GridRuntime  # noqa: TC001

    g: GridRuntime = grid  # type: ignore[assignment]

    return GridRuntimeResponse(
        grid_id=g.grid_id,
        market_id=g.market_id,
        environment=environment,
        status=g.status,
        blueprint_id=g.blueprint.blueprint_id,
        capital=g.blueprint.total_capital,
        deployed_capital=g.deployed_capital,
        capital_utilization=g.capital_utilization,
        exposure=Decimal("0"),
        unrealized_pnl=g.unrealized_pnl,
        realized_pnl=g.realized_pnl,
        section_depth=len(g.blueprint.sections),
        active_sections=len(g.blueprint.sections),
        started_at=g.started_at,
        updated_at=datetime.now(UTC),
    )


@router.get("", response_model=GridListResponse)
async def list_grids() -> GridListResponse:
    """
    List all active grids.

    Returns grids managed by the grid engine.
    """
    container = get_default_container()
    engine = container.grid_engine

    active_grids = engine.get_active_grids()
    grids = [_grid_to_response(g) for g in active_grids]

    return GridListResponse(grids=grids, total=len(grids))


@router.get("/{grid_id}", response_model=GridRuntimeResponse)
async def get_grid(grid_id: str) -> GridRuntimeResponse:
    """
    Get a specific grid by ID.

    Args:
        grid_id: Grid ID
    """
    container = get_default_container()
    engine = container.grid_engine

    grid = engine.get_grid(grid_id)
    if grid is None:
        raise HTTPException(status_code=404, detail=f"Grid not found: {grid_id}")

    return _grid_to_response(grid)


@router.post("/start", response_model=GridControlResponse, status_code=201)
async def start_grid(request: GridStartRequest) -> GridControlResponse:
    """
    Start a new grid from a blueprint.

    Creates a demo grid session and starts execution.
    """
    container = get_default_container()

    # Get blueprint
    blueprint = container.research_service.get_blueprint(request.blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Blueprint not found: {request.blueprint_id}")

    try:
        session = container.demo_service.create_demo_grid(
            blueprint=blueprint,
            notes="Started via API",
        )
        session = await container.demo_service.start_demo_grid(session.session_id)
    except Exception as e:
        logger.error("grid_start_failed", blueprint_id=request.blueprint_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Grid start failed: {e}") from e

    return GridControlResponse(
        grid_id=session.grid_runtime.grid_id,
        operation_id=f"OP-GRID-START-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        status="SUCCEEDED",
        previous_status="CREATED",
        new_status="RUNNING",
    )


@router.post("/{grid_id}/pause", response_model=GridControlResponse)
async def pause_grid(grid_id: str) -> GridControlResponse:
    """
    Pause a running grid.

    Stops new order submission but maintains state.
    """
    container = get_default_container()

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Grid session not found: {grid_id}")

    try:
        container.demo_service.pause_demo_grid(session.session_id)
    except Exception as e:
        logger.error("grid_pause_failed", grid_id=grid_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Grid pause failed: {e}") from e

    return GridControlResponse(
        grid_id=grid_id,
        operation_id=f"OP-GRID-PAUSE-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        status="SUCCEEDED",
        previous_status="RUNNING",
        new_status="PAUSED",
    )


@router.post("/{grid_id}/resume", response_model=GridControlResponse)
async def resume_grid(grid_id: str) -> GridControlResponse:
    """
    Resume a paused grid.

    Requires pre-resume checks and reconciliation.
    """
    container = get_default_container()

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Grid session not found: {grid_id}")

    try:
        container.demo_service.resume_demo_grid(session.session_id)
    except Exception as e:
        logger.error("grid_resume_failed", grid_id=grid_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Grid resume failed: {e}") from e

    return GridControlResponse(
        grid_id=grid_id,
        operation_id=f"OP-GRID-RESUME-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        status="SUCCEEDED",
        previous_status="PAUSED",
        new_status="RUNNING",
    )


@router.post("/{grid_id}/stop", response_model=GridControlResponse)
async def stop_grid(grid_id: str) -> GridControlResponse:
    """
    Stop a grid gracefully.

    Cancels open orders and settles the grid.
    """
    container = get_default_container()

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Grid session not found: {grid_id}")

    try:
        container.demo_service.stop_demo_grid(
            session.session_id,
            reason="Stopped via API",
        )
    except Exception as e:
        logger.error("grid_stop_failed", grid_id=grid_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Grid stop failed: {e}") from e

    return GridControlResponse(
        grid_id=grid_id,
        operation_id=f"OP-GRID-STOP-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        status="SUCCEEDED",
        previous_status="RUNNING",
        new_status="STOPPED",
    )


@router.post("/{grid_id}/emergency-stop", response_model=GridControlResponse)
async def emergency_stop_grid(grid_id: str) -> GridControlResponse:
    """
    Emergency stop a grid.

    Immediately cancels all orders and requires manual review before resume.
    Authorization: LEVEL 4+ (Emergency Control)
    """
    container = get_default_container()

    session = container.demo_service.get_session_by_grid_id(grid_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Grid session not found: {grid_id}")

    try:
        container.demo_service.emergency_stop_demo_grid(
            session.session_id,
            reason="Emergency stop via API",
        )
    except Exception as e:
        logger.error("grid_emergency_stop_failed", grid_id=grid_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Emergency stop failed: {e}") from e

    return GridControlResponse(
        grid_id=grid_id,
        operation_id=f"OP-GRID-EMERGENCY-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
        status="SUCCEEDED",
        previous_status="RUNNING",
        new_status="EMERGENCY_STOPPED",
    )
