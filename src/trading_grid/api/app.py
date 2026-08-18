"""
FastAPI application factory.

This module provides:
- Application factory for creating FastAPI instances
- Middleware registration (auth, audit, CORS)
- Exception handlers
- Router registration

The API is the application boundary that:
1. Authenticates callers
2. Authorizes operations
3. Routes to use cases
4. Normalizes responses and errors
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from trading_grid.api.middleware.audit import AuditMiddleware
from trading_grid.api.middleware.auth import AuthMiddleware
from trading_grid.api.routes import (
    account,
    approvals,
    blueprints,
    demo,
    grid,
    health,
    markets,
    orders,
    pnl,
    positions,
    research,
    risk,
    simulations,
    system,
)
from trading_grid.api.routes.dependencies import set_multi_container
from trading_grid.api.schemas.common import ErrorResponse
from trading_grid.application.services.authorization import AuthorizationError
from trading_grid.application.services.service_container import MultiExchangeContainer
from trading_grid.config.settings import get_settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan handler."""
    settings = get_settings()
    logger.info(
        "application_starting",
        version=settings.app.version,
        environment=settings.app.env.value,
    )

    # Wire the service container for API routes
    multi_container = MultiExchangeContainer(settings)
    set_multi_container(multi_container)

    # Start background services
    await multi_container.start_all()

    yield

    # Stop background services
    await multi_container.stop_all()
    logger.info("application_stopping")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Configured FastAPI instance
    """
    settings = get_settings()

    app = FastAPI(
        title=settings.app.name,
        version=settings.app.version,
        description="AI Trading Grid System — Application Control API (OKX, Binance, Bybit)",
        lifespan=lifespan,
        docs_url="/docs" if settings.app.debug else None,
        redoc_url="/redoc" if settings.app.debug else None,
    )

    # Register middleware (order matters - last registered runs first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.app.debug else [],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(AuditMiddleware)
    app.add_middleware(AuthMiddleware)

    # Register exception handlers
    _register_exception_handlers(app)

    # Register routers
    _register_routers(app)

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers for normalized error responses."""

    @app.exception_handler(AuthorizationError)
    async def authorization_error_handler(
        request: Request, exc: AuthorizationError
    ) -> JSONResponse:
        """Handle authorization errors."""
        error = ErrorResponse(
            code="AUTHORIZATION_DENIED",
            message=exc.message,
            category="AUTHORIZATION",
            retryable=False,
        )
        return JSONResponse(status_code=403, content=error.model_dump())

    @app.exception_handler(ValueError)
    async def validation_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        """Handle validation errors."""
        error = ErrorResponse(
            code="VALIDATION_ERROR",
            message=str(exc),
            category="VALIDATION",
            retryable=False,
        )
        return JSONResponse(status_code=400, content=error.model_dump())

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        """Handle unexpected errors."""
        logger.error("unhandled_exception", error=str(exc), path=request.url.path)
        error = ErrorResponse(
            code="INTERNAL_ERROR",
            message="An internal error occurred",
            category="SYSTEM",
            retryable=True,
        )
        return JSONResponse(status_code=500, content=error.model_dump())


def _register_routers(app: FastAPI) -> None:
    """Register API routers."""
    app.include_router(health.router, tags=["Health"])
    app.include_router(system.router, prefix="/api/v1/system", tags=["System"])
    app.include_router(demo.router, prefix="/api/v1/demo", tags=["Demo Trading"])

    # New API namespaces (12 total per audit plan)
    app.include_router(research.router, prefix="/api/v1/research", tags=["Research"])
    app.include_router(markets.router, prefix="/api/v1/markets", tags=["Markets"])
    app.include_router(blueprints.router, prefix="/api/v1/blueprints", tags=["Blueprints"])
    app.include_router(simulations.router, prefix="/api/v1/simulations", tags=["Simulations"])
    app.include_router(grid.router, prefix="/api/v1/grid", tags=["Grid Control"])
    app.include_router(account.router, prefix="/api/v1/account", tags=["Account"])
    app.include_router(orders.router, prefix="/api/v1/orders", tags=["Orders"])
    app.include_router(positions.router, prefix="/api/v1/positions", tags=["Positions"])
    app.include_router(pnl.router, prefix="/api/v1/pnl", tags=["P&L"])
    app.include_router(risk.router, prefix="/api/v1/risk", tags=["Risk"])
    app.include_router(approvals.router, prefix="/api/v1/approvals", tags=["Approvals"])


# Application instance for uvicorn
app = create_app()
