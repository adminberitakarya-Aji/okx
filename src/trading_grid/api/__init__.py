"""
API layer for the OKX AI Trading Grid System.

This package contains:
- app: FastAPI application factory
- middleware: Authentication and audit middleware
- routes: API endpoint definitions
- schemas: Request/response schemas

The API is the application boundary that:
1. Authenticates callers
2. Authorizes operations
3. Routes to use cases
4. Normalizes responses and errors
"""

from trading_grid.api.app import app, create_app

__all__ = ["app", "create_app"]
