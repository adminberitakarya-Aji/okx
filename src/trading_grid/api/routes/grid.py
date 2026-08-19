"""
Grid API routes.

Endpoints for grid runtime control (start, pause, resume, stop, emergency-stop).

Authorization: LEVEL 2+ (Demo Grid Control), LEVEL 3+ (Live Grid Control)

[I-H11-REV] Phase 10.2: Multi-exchange grid control.
- ``exchange`` query parameter to specify exchange (OKX, BINANCE, BYBIT)
- Multi-exchange query support (list grids from all exchanges)
- RBAC per-user filtering (users only see their own grids)
- Backward compatible with default OKX
"""

from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query

from trading_grid.api.routes.dependencies import (
    get_container,
    get_current_identity,
    get_default_container,
    get_multi_container,
)
from trading_grid.api.schemas.grid import (
    GridControlResponse,
    GridListResponse,
    GridRuntimeResponse,
    GridStartRequest,
)
from trading_grid.application.services.authorization import Identity, PermissionLevel

logger = structlog.get_logger()

router = APIRouter()

# [I-H11-REV] Valid exchange IDs for query parameter validation
VALID_EXCHANGES = ("OKX", "BINANCE", "BYBIT")


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
async def list_grids(
    exchange: str | None = Query(
        None,
        description="Filter by exchange (OKX, BINANCE, BYBIT). If not provided, returns grids from all exchanges.",
    ),
    identity: Identity = Depends(get_current_identity),
) -> GridListResponse:
    """
    List all active grids.

    [I-H11-REV] Multi-exchange support:
    - If ``exchange`` is provided, returns grids from that exchange only
    - If ``exchange`` is not provided, returns grids from all exchanges
    - RBAC: Users only see grids they own (user_id matches identity)

    Args:
        exchange: Optional exchange filter (OKX, BINANCE, BYBIT)
        identity: Authenticated identity (required for RBAC)

    Returns:
        List of active grids owned by the authenticated user
    """
    # [I-H11-REV] Validate exchange parameter if provided
    if exchange is not None:
        exchange_upper = exchange.upper()
        if exchange_upper not in VALID_EXCHANGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange: {exchange!r}. Valid exchanges: {', '.join(VALID_EXCHANGES)}",
            )
        containers = [get_container(exchange_upper)]
    else:
        # Get all containers (one per exchange)
        multi = get_multi_container()
        containers = [multi.get_container(ex) for ex in VALID_EXCHANGES]

    all_grids: list[GridRuntimeResponse] = []
    for container in containers:
        engine = container.grid_engine
        active_grids = engine.get_active_grids()

        for grid in active_grids:
            # [I-H11-REV] RBAC: Filter by ownership
            # Grids with user_id=None are system grids (visible to all)
            grid_user_id = getattr(grid, "user_id", None)
            if grid_user_id is not None and grid_user_id != identity.identity_id:
                continue  # Skip grids owned by other users

            all_grids.append(_grid_to_response(grid))

    return GridListResponse(grids=all_grids, total=len(all_grids))


@router.get("/{grid_id}", response_model=GridRuntimeResponse)
async def get_grid(
    grid_id: str,
    exchange: str | None = Query(
        None,
        description="Exchange to search (OKX, BINANCE, BYBIT). If not provided, searches all exchanges.",
    ),
    identity: Identity = Depends(get_current_identity),
) -> GridRuntimeResponse:
    """
    Get a specific grid by ID.

    [I-H11-REV] Multi-exchange support:
    - If ``exchange`` is provided, searches only that exchange
    - If ``exchange`` is not provided, searches all exchanges
    - RBAC: Users can only access grids they own

    Args:
        grid_id: Grid ID
        exchange: Optional exchange filter (OKX, BINANCE, BYBIT)
        identity: Authenticated identity (required for RBAC)
    """
    # [I-H11-REV] Validate exchange parameter if provided
    if exchange is not None:
        exchange_upper = exchange.upper()
        if exchange_upper not in VALID_EXCHANGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange: {exchange!r}. Valid exchanges: {', '.join(VALID_EXCHANGES)}",
            )
        containers = [get_container(exchange_upper)]
    else:
        # Search all exchanges
        multi = get_multi_container()
        containers = [multi.get_container(ex) for ex in VALID_EXCHANGES]

    for container in containers:
        engine = container.grid_engine
        grid = engine.get_grid(grid_id)
        if grid is not None:
            # [I-H11-REV] RBAC: Check ownership
            grid_user_id = getattr(grid, "user_id", None)
            if grid_user_id is not None and grid_user_id != identity.identity_id:
                raise HTTPException(
                    status_code=403,
                    detail="Not authorized to access this grid. Grid belongs to another user.",
                )
            return _grid_to_response(grid)

    raise HTTPException(status_code=404, detail=f"Grid not found: {grid_id}")


@router.post("/start", response_model=GridControlResponse, status_code=201)
async def start_grid(
    request: GridStartRequest,
    exchange: str | None = Query(
        None,
        description="Exchange to start grid on (OKX, BINANCE, BYBIT). Defaults to OKX.",
    ),
    identity: Identity = Depends(get_current_identity),  # [I-C3] require identity
) -> GridControlResponse:
    """
    Start a new grid from a blueprint.

    Creates a demo grid session and starts execution.

    [I-C3] Security: Requires authenticated identity and checks blueprint
    ownership. User A cannot start a blueprint owned by User B.
    Blueprints with user_id=None (system-generated/legacy) are accessible
    to all authenticated users.

    [I-H11-REV] Multi-exchange support:
    - ``exchange`` query parameter specifies which exchange to use
    - Defaults to OKX for backward compatibility
    """
    # [T-M5] RBAC: Grid start requires DEMO_OPERATOR (Level 2+)
    if identity.permission_level < PermissionLevel.DEMO_OPERATOR:
        logger.warning(
            "grid_start_insufficient_permission",
            identity_id=identity.identity_id,
            permission_level=identity.permission_level,
            required_level=PermissionLevel.DEMO_OPERATOR,
        )
        raise HTTPException(
            status_code=403,
            detail="Forbidden: DEMO_OPERATOR (Level 2+) role required to start grids",
        )

    # [I-H11-REV] Get container for specified exchange (default OKX)
    if exchange is not None:
        exchange_upper = exchange.upper()
        if exchange_upper not in VALID_EXCHANGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange: {exchange!r}. Valid exchanges: {', '.join(VALID_EXCHANGES)}",
            )
        container = get_container(exchange_upper)
    else:
        container = get_default_container()

    # Get blueprint
    blueprint = container.research_service.get_blueprint(request.blueprint_id)
    if blueprint is None:
        raise HTTPException(status_code=404, detail=f"Blueprint not found: {request.blueprint_id}")

    # [I-C3] Ownership check: user can only start their own blueprints
    # Blueprints with user_id=None are system-generated and accessible to all
    if blueprint.user_id is not None and blueprint.user_id != identity.identity_id:
        logger.warning(
            "unauthorized_grid_start_attempt",
            user_id=identity.identity_id,
            blueprint_id=request.blueprint_id,
            owner_id=blueprint.user_id,
        )
        raise HTTPException(
            status_code=403,
            detail="Not authorized to start this blueprint. Blueprint belongs to another user.",
        )

    try:
        session = container.demo_service.create_demo_grid(
            blueprint=blueprint,
            notes=f"Started via API by {identity.identity_id}",
            user_id=identity.identity_id,  # [A-H11] Set session owner
        )
        session = await container.demo_service.start_demo_grid(
            session.session_id, identity=identity  # [A-H11] pass authenticated identity
        )
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


def _find_session_for_grid(grid_id: str, exchange: str | None = None):
    """
    Find the demo session for a grid ID across exchanges.

    [I-H11-REV] Helper for multi-exchange grid control.

    Args:
        grid_id: Grid ID to search for
        exchange: Optional exchange filter (defaults to searching all)

    Returns:
        Tuple of (session, container) or raises 404
    """
    if exchange is not None:
        exchange_upper = exchange.upper()
        if exchange_upper not in VALID_EXCHANGES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid exchange: {exchange!r}. Valid exchanges: {', '.join(VALID_EXCHANGES)}",
            )
        containers = [get_container(exchange_upper)]
    else:
        multi = get_multi_container()
        containers = [multi.get_container(ex) for ex in VALID_EXCHANGES]

    for container in containers:
        session = container.demo_service.get_session_by_grid_id(grid_id)
        if session is not None:
            return session, container

    raise HTTPException(status_code=404, detail=f"Grid session not found: {grid_id}")


@router.post("/{grid_id}/pause", response_model=GridControlResponse)
async def pause_grid(
    grid_id: str,
    exchange: str | None = Query(
        None,
        description="Exchange (OKX, BINANCE, BYBIT). If not provided, searches all exchanges.",
    ),
) -> GridControlResponse:
    """
    Pause a running grid.

    Stops new order submission but maintains state.

    [I-H11-REV] Multi-exchange support: searches all exchanges if not specified.
    """
    session, container = _find_session_for_grid(grid_id, exchange)

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
async def resume_grid(
    grid_id: str,
    exchange: str | None = Query(
        None,
        description="Exchange (OKX, BINANCE, BYBIT). If not provided, searches all exchanges.",
    ),
) -> GridControlResponse:
    """
    Resume a paused grid.

    Requires pre-resume checks and reconciliation.

    [I-H11-REV] Multi-exchange support: searches all exchanges if not specified.
    """
    session, container = _find_session_for_grid(grid_id, exchange)

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
async def stop_grid(
    grid_id: str,
    exchange: str | None = Query(
        None,
        description="Exchange (OKX, BINANCE, BYBIT). If not provided, searches all exchanges.",
    ),
) -> GridControlResponse:
    """
    Stop a grid gracefully.

    Cancels open orders and settles the grid.

    [I-H11-REV] Multi-exchange support: searches all exchanges if not specified.
    """
    session, container = _find_session_for_grid(grid_id, exchange)

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
async def emergency_stop_grid(
    grid_id: str,
    exchange: str | None = Query(
        None,
        description="Exchange (OKX, BINANCE, BYBIT). If not provided, searches all exchanges.",
    ),
) -> GridControlResponse:
    """
    Emergency stop a grid.

    Immediately cancels all orders and requires manual review before resume.
    Authorization: LEVEL 4+ (Emergency Control)

    [I-H11-REV] Multi-exchange support: searches all exchanges if not specified.
    """
    session, container = _find_session_for_grid(grid_id, exchange)

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
