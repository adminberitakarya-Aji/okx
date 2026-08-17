"""Tests for API schemas."""

from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trading_grid.api.schemas.common import (
    ErrorResponse,
    HealthResponse,
    OperationResponse,
    PaginatedResponse,
    PaginationParams,
    ReadinessResponse,
    ResponseEnvelope,
)
from trading_grid.api.schemas.grid import (
    BlueprintResponse,
    GridControlResponse,
    GridListResponse,
    GridRuntimeResponse,
    GridStartRequest,
    SectionResponse,
)
from trading_grid.api.schemas.research import (
    MarketRecommendationResponse,
    MarketResearchResponse,
    RecommendationListResponse,
    ResearchRunRequest,
    ResearchUniverseResponse,
)
from trading_grid.api.schemas.system import (
    AccountResponse,
    ApprovalDecisionRequest,
    ApprovalResponse,
    BalanceResponse,
    OrderResponse,
    PnlResponse,
    PositionResponse,
    RiskStateResponse,
    SystemStatusResponse,
)


class TestCommonSchemas:
    """Tests for common API schemas."""

    def test_error_response(self):
        """ErrorResponse should validate required fields."""
        error = ErrorResponse(
            code="NOT_FOUND",
            message="Resource not found",
            category="NOT_FOUND",
        )
        assert error.code == "NOT_FOUND"
        assert error.message == "Resource not found"
        assert error.category == "NOT_FOUND"
        assert error.retryable is False
        assert error.operation_id is None
        assert error.details is None

    def test_error_response_with_details(self):
        """ErrorResponse with optional fields."""
        error = ErrorResponse(
            code="VALIDATION_ERROR",
            message="Invalid input",
            category="VALIDATION",
            retryable=True,
            operation_id="op-123",
            details={"field": "price"},
        )
        assert error.retryable is True
        assert error.operation_id == "op-123"
        assert error.details == {"field": "price"}

    def test_error_response_invalid_category(self):
        """ErrorResponse should reject invalid category."""
        with pytest.raises(ValidationError):
            ErrorResponse(
                code="TEST",
                message="Test",
                category="INVALID_CATEGORY",  # type: ignore[arg-type]
            )

    def test_response_envelope(self):
        """ResponseEnvelope should wrap data."""
        envelope = ResponseEnvelope[dict](data={"key": "value"})
        assert envelope.success is True
        assert envelope.data == {"key": "value"}
        assert envelope.error is None
        assert envelope.timestamp is not None

    def test_response_envelope_with_error(self):
        """ResponseEnvelope with error."""
        error = ErrorResponse(code="ERR", message="Error", category="SYSTEM")
        envelope = ResponseEnvelope[dict](success=False, error=error)
        assert envelope.success is False
        assert envelope.error == error

    def test_operation_response(self):
        """OperationResponse should track operation status."""
        op = OperationResponse(
            operation_id="op-123",
            command_type="START_GRID",
            status="PENDING",
        )
        assert op.operation_id == "op-123"
        assert op.command_type == "START_GRID"
        assert op.status == "PENDING"
        assert op.created_at is not None
        assert op.started_at is None
        assert op.completed_at is None

    def test_operation_response_completed(self):
        """OperationResponse with completion."""
        now = datetime.utcnow()
        op = OperationResponse(
            operation_id="op-123",
            command_type="START_GRID",
            status="SUCCEEDED",
            started_at=now,
            completed_at=now,
            result_reference="grid-456",
        )
        assert op.status == "SUCCEEDED"
        assert op.result_reference == "grid-456"

    def test_pagination_params_defaults(self):
        """PaginationParams should have defaults."""
        params = PaginationParams()
        assert params.page == 1
        assert params.page_size == 50

    def test_pagination_params_validation(self):
        """PaginationParams should validate bounds."""
        with pytest.raises(ValidationError):
            PaginationParams(page=0)
        with pytest.raises(ValidationError):
            PaginationParams(page_size=0)
        with pytest.raises(ValidationError):
            PaginationParams(page_size=501)

    def test_paginated_response(self):
        """PaginatedResponse should contain items and metadata."""
        response = PaginatedResponse[str](
            items=["a", "b", "c"],
            total=100,
            page=1,
            page_size=50,
            total_pages=2,
        )
        assert len(response.items) == 3
        assert response.total == 100
        assert response.total_pages == 2

    def test_health_response(self):
        """HealthResponse should report status."""
        health = HealthResponse(
            status="healthy",
            version="1.0.0",
            environment="development",
        )
        assert health.status == "healthy"
        assert health.version == "1.0.0"
        assert health.components is None

    def test_readiness_response(self):
        """ReadinessResponse should report checks."""
        readiness = ReadinessResponse(
            status="READY",
            checks={"database": True, "redis": True},
        )
        assert readiness.status == "READY"
        assert readiness.checks["database"] is True


class TestGridSchemas:
    """Tests for grid API schemas."""

    def test_section_response(self):
        """SectionResponse should contain section data."""
        section = SectionResponse(
            section_id=1,
            upper_price=Decimal("110"),
            lower_price=Decimal("90"),
            grid_count=10,
            grid_spacing_pct=Decimal("2"),
            capital_allocation_pct=Decimal("50"),
            status="ACTIVE",
        )
        assert section.section_id == 1
        assert section.grid_count == 10
        assert section.fill_ratio == Decimal("0")

    def test_blueprint_response(self):
        """BlueprintResponse should contain blueprint data."""
        now = datetime.utcnow()
        blueprint = BlueprintResponse(
            blueprint_id="bp-123",
            market_id="BTC-USDT",
            total_capital=Decimal("1000"),
            section_count=2,
            total_grid_count=20,
            status="VALIDATED",
            created_at=now,
            updated_at=now,
        )
        assert blueprint.blueprint_id == "bp-123"
        assert blueprint.sections == []

    def test_grid_runtime_response(self):
        """GridRuntimeResponse should contain runtime data."""
        grid = GridRuntimeResponse(
            grid_id="grid-123",
            market_id="BTC-USDT",
            environment="DEMO",
            status="RUNNING",
            blueprint_id="bp-123",
            capital=Decimal("1000"),
        )
        assert grid.grid_id == "grid-123"
        assert grid.environment == "DEMO"
        assert grid.deployed_capital == Decimal("0")

    def test_grid_start_request(self):
        """GridStartRequest should validate environment."""
        request = GridStartRequest(blueprint_id="bp-123")
        assert request.environment == "DEMO"
        assert request.idempotency_key is None

    def test_grid_start_request_live(self):
        """GridStartRequest with LIVE environment."""
        request = GridStartRequest(
            blueprint_id="bp-123",
            environment="LIVE",
            idempotency_key="key-123",
        )
        assert request.environment == "LIVE"

    def test_grid_control_response(self):
        """GridControlResponse should track status change."""
        response = GridControlResponse(
            grid_id="grid-123",
            operation_id="op-123",
            status="COMPLETED",
            previous_status="RUNNING",
            new_status="PAUSED",
        )
        assert response.previous_status == "RUNNING"
        assert response.new_status == "PAUSED"

    def test_grid_list_response(self):
        """GridListResponse should contain grids."""
        response = GridListResponse()
        assert response.grids == []
        assert response.total == 0


class TestResearchSchemas:
    """Tests for research API schemas."""

    def test_market_recommendation_response(self):
        """MarketRecommendationResponse should contain recommendation."""
        rec = MarketRecommendationResponse(
            market_id="BTC-USDT",
            rank=1,
            recommendation="HIGH_PRIORITY",
            suitability_score=Decimal("0.85"),
            confidence=Decimal("0.9"),
        )
        assert rec.market_id == "BTC-USDT"
        assert rec.rank == 1
        assert rec.research_reasons == []

    def test_market_recommendation_score_bounds(self):
        """Suitability score must be 0-1."""
        with pytest.raises(ValidationError):
            MarketRecommendationResponse(
                market_id="BTC-USDT",
                rank=1,
                recommendation="HIGH_PRIORITY",
                suitability_score=Decimal("1.5"),
                confidence=Decimal("0.9"),
            )

    def test_research_universe_response(self):
        """ResearchUniverseResponse should contain markets."""
        universe = ResearchUniverseResponse(
            universe_type="TOP_10",
            snapshot_id="snap-123",
            markets=["BTC-USDT", "ETH-USDT"],
        )
        assert len(universe.markets) == 2

    def test_market_research_response(self):
        """MarketResearchResponse should contain research data."""
        research = MarketResearchResponse(
            market_id="BTC-USDT",
            market_state={"volatility": 0.02},
            execution_economics={"spread_pct": 0.01},
            grid_suitability={"score": 0.8},
        )
        assert research.market_id == "BTC-USDT"
        assert research.recommendation is None

    def test_research_run_request(self):
        """ResearchRunRequest should have defaults."""
        request = ResearchRunRequest()
        assert request.universe == "TOP_10"
        assert request.environment == "DEMO"

    def test_recommendation_list_response(self):
        """RecommendationListResponse should contain recommendations."""
        response = RecommendationListResponse()
        assert response.recommendations == []
        assert response.total == 0


class TestSystemSchemas:
    """Tests for system API schemas."""

    def test_system_status_response(self):
        """SystemStatusResponse should contain status."""
        status = SystemStatusResponse(environment="DEMO")
        assert status.environment == "DEMO"
        assert status.api_status == "UNKNOWN"

    def test_risk_state_response(self):
        """RiskStateResponse should contain risk metrics."""
        risk = RiskStateResponse(
            risk_level="LOW",
            total_capital=Decimal("1000"),
            deployed_capital=Decimal("500"),
        )
        assert risk.risk_level == "LOW"
        assert risk.active_grids == 0

    def test_approval_response(self):
        """ApprovalResponse should contain approval data."""
        approval = ApprovalResponse(
            approval_id="appr-123",
            operation_id="op-123",
            operation_type="START_LIVE_GRID",
            environment="LIVE",
            requested_by="user",
            description="Start live grid",
            status="PENDING",
            requested_at=datetime.utcnow(),
        )
        assert approval.status == "PENDING"
        assert approval.decided_by is None

    def test_approval_decision_request(self):
        """ApprovalDecisionRequest should validate decision."""
        decision = ApprovalDecisionRequest(decision="APPROVE")
        assert decision.decision == "APPROVE"
        assert decision.reason is None

    def test_approval_decision_request_invalid(self):
        """Invalid decision should be rejected."""
        with pytest.raises(ValidationError):
            ApprovalDecisionRequest(decision="INVALID")  # type: ignore[arg-type]

    def test_account_response(self):
        """AccountResponse should contain balances."""
        account = AccountResponse(environment="DEMO")
        assert account.balances == []
        assert account.total_equity == Decimal("0")

    def test_balance_response(self):
        """BalanceResponse should contain balance data."""
        balance = BalanceResponse(
            asset="USDT",
            available=Decimal("1000"),
            frozen=Decimal("100"),
            total=Decimal("1100"),
        )
        assert balance.asset == "USDT"
        assert balance.total == Decimal("1100")

    def test_order_response(self):
        """OrderResponse should contain order data."""
        order = OrderResponse(
            order_id="ord-123",
            market_id="BTC-USDT",
            side="BUY",
            order_type="MARKET",
            quantity=Decimal("0.01"),
            status="FILLED",
        )
        assert order.side == "BUY"
        assert order.filled_quantity == Decimal("0")

    def test_position_response(self):
        """PositionResponse should contain position data."""
        position = PositionResponse(
            position_id="pos-123",
            market_id="BTC-USDT",
            quantity=Decimal("0.01"),
            average_entry_price=Decimal("50000"),
        )
        assert position.unrealized_pnl == Decimal("0")

    def test_pnl_response(self):
        """PnlResponse should contain P&L data."""
        pnl = PnlResponse(
            period="24h",
            realized_pnl=Decimal("50"),
            unrealized_pnl=Decimal("10"),
            total_pnl=Decimal("60"),
        )
        assert pnl.period == "24h"
        assert pnl.net_pnl == Decimal("0")
