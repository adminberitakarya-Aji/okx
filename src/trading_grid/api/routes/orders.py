"""
Orders API routes.

Endpoints for order queries and cancellation.

Authorization: LEVEL 0+ (Read), LEVEL 2+ (Cancel)
"""

from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, HTTPException, Query

from trading_grid.api.routes.dependencies import get_default_container
from trading_grid.api.schemas.orders import (
    OrderCancelResponse,
    OrderListResponse,
    OrderResponse,
)
from trading_grid.domain.execution.models import Order

logger = structlog.get_logger()

router = APIRouter()


def _order_to_response(order: Order, environment: str = "DEMO") -> OrderResponse:
    """Convert a domain Order to OrderResponse."""
    metadata = order.metadata or {}
    grid_id = metadata.get("grid_id")
    grid_level = metadata.get("grid_level")

    return OrderResponse(
        order_id=order.order_id,
        client_order_id=order.exchange_order_id,
        market_id=order.market_id,
        side=order.side,
        order_type=order.order_type,
        status=order.status,
        price=order.price,
        quantity=order.quantity,
        filled_quantity=order.filled_quantity,
        average_fill_price=order.average_fill_price,
        grid_id=str(grid_id) if grid_id is not None else None,
        grid_level=int(str(grid_level)) if grid_level is not None else None,
        environment=environment,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


@router.get("", response_model=OrderListResponse)
async def list_orders(
    market_id: str | None = Query(default=None, description="Filter by market ID"),
    active_only: bool = Query(default=False, description="Only return active orders"),
    limit: int = Query(default=50, ge=1, le=200),
) -> OrderListResponse:
    """
    List orders with optional filters.

    Args:
        market_id: Filter by market ID (e.g., BTC-USDT)
        active_only: Only return active (unfilled/uncancelled) orders
        limit: Max results
    """
    container = get_default_container()
    engine = container.execution_engine

    if market_id:
        orders = engine.get_orders_for_market(market_id.upper())
    elif active_only:
        orders = engine.get_active_orders()
    else:
        # No direct "all orders" accessor; combine active + positions is not
        # appropriate. Use active orders as the safe default view.
        orders = engine.get_active_orders()

    if active_only and market_id:
        orders = [o for o in orders if o.is_active]

    orders = orders[:limit]

    order_responses = [_order_to_response(o) for o in orders]

    return OrderListResponse(
        orders=order_responses,
        total=len(order_responses),
        page_size=limit,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str) -> OrderResponse:
    """
    Get a specific order by ID.

    Args:
        order_id: Order ID
    """
    container = get_default_container()
    engine = container.execution_engine

    order = engine.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

    return _order_to_response(order)


@router.delete("/{order_id}", response_model=OrderCancelResponse)
async def cancel_order(order_id: str) -> OrderCancelResponse:
    """
    Cancel an open order.

    Authorization: LEVEL 2+ (Demo Grid Control)
    """
    container = get_default_container()
    engine = container.execution_engine

    order = engine.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Order not found: {order_id}")

    try:
        result = await engine.cancel_order(order_id)
    except Exception as e:
        logger.error("order_cancel_failed", order_id=order_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Order cancel failed: {e}") from e

    return OrderCancelResponse(
        order_id=order_id,
        status="SUCCEEDED" if result else "FAILED",
        cancelled=result,
        reason=None if result else "Order not active or cancel rejected",
        timestamp=datetime.now(UTC),
    )
