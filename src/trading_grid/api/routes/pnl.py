"""
P&L API routes.

Endpoints for P&L summary and breakdown queries.

P&L is sourced from GridRuntime state (realized/unrealized).
Operational counters (orders submitted/filled) come from DemoMetrics.

Authorization: LEVEL 0+ (Read-only)
"""

from datetime import UTC, datetime
from decimal import Decimal

import structlog
from fastapi import APIRouter

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.pnl import (
    PnlByGridResponse,
    PnlByMarketResponse,
    PnlDetailResponse,
    PnlSummaryResponse,
)

logger = structlog.get_logger()

router = APIRouter()


def _collect_grid_data() -> list[tuple[str, str, Decimal, Decimal, Decimal, int, str]]:
    """
    Collect P&L data from all demo sessions.

    Returns list of (grid_id, market_id, realized, unrealized, fees, fills, status).
    """
    container = get_default_container()
    demo_service = container.demo_service

    rows: list[tuple[str, str, Decimal, Decimal, Decimal, int, str]] = []

    for session in demo_service.get_all_sessions():
        runtime = session.grid_runtime
        metrics = session.metrics

        # Fees: approximate from filled orders count is not available directly;
        # use order fills as a proxy for activity. Real fees tracked per-order.
        fees = Decimal("0")

        rows.append(
            (
                runtime.grid_id,
                runtime.market_id,
                runtime.realized_pnl,
                runtime.unrealized_pnl,
                fees,
                metrics.orders_filled,
                session.status,
            )
        )

    return rows


@router.get("/summary", response_model=PnlSummaryResponse)
async def get_pnl_summary() -> PnlSummaryResponse:
    """
    Get P&L summary across all grids.

    Returns realized, unrealized, and net P&L.
    """
    rows = _collect_grid_data()

    total_realized = sum((r[2] for r in rows), Decimal("0"))
    total_unrealized = sum((r[3] for r in rows), Decimal("0"))
    total_fees = sum((r[4] for r in rows), Decimal("0"))
    total_fills = sum(r[5] for r in rows)

    return PnlSummaryResponse(
        environment="DEMO",
        realized_pnl=total_realized,
        unrealized_pnl=total_unrealized,
        total_pnl=total_realized + total_unrealized,
        total_fees=total_fees,
        net_pnl=total_realized + total_unrealized - total_fees,
        completed_cycles=0,
        total_buy_count=0,
        total_sell_count=total_fills,
        max_drawdown_pct=Decimal("0"),
        updated_at=datetime.now(UTC),
    )


@router.get("/by-grid", response_model=list[PnlByGridResponse])
async def get_pnl_by_grid() -> list[PnlByGridResponse]:
    """
    Get P&L breakdown by grid.

    Returns P&L for each grid session.
    """
    rows = _collect_grid_data()

    return [
        PnlByGridResponse(
            grid_id=grid_id,
            market_id=market_id,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            total_pnl=realized + unrealized,
            fees_paid=fees,
            completed_cycles=0,
            status=status,
        )
        for grid_id, market_id, realized, unrealized, fees, _fills, status in rows
    ]


@router.get("/by-market", response_model=list[PnlByMarketResponse])
async def get_pnl_by_market() -> list[PnlByMarketResponse]:
    """
    Get P&L breakdown by market.

    Aggregates P&L across all grids per market.
    """
    rows = _collect_grid_data()

    market_pnl: dict[str, PnlByMarketResponse] = {}

    for _grid_id, market_id, realized, unrealized, fees, _fills, _status in rows:
        if market_id not in market_pnl:
            market_pnl[market_id] = PnlByMarketResponse(market_id=market_id)

        entry = market_pnl[market_id]
        entry.realized_pnl += realized
        entry.unrealized_pnl += unrealized
        entry.total_pnl += realized + unrealized
        entry.fees_paid += fees

    return list(market_pnl.values())


@router.get("/detail", response_model=PnlDetailResponse)
async def get_pnl_detail() -> PnlDetailResponse:
    """
    Get detailed P&L with all breakdowns.

    Combines summary, by-grid, and by-market views.
    """
    summary = await get_pnl_summary()
    by_grid = await get_pnl_by_grid()
    by_market = await get_pnl_by_market()

    return PnlDetailResponse(
        summary=summary,
        by_grid=by_grid,
        by_market=by_market,
    )
