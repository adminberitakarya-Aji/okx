"""
Tests for ResearchService — orchestration layer for market ranking and blueprint generation.

Tests cover:
- rank_markets() heuristic mode (no ML model)
- rank_markets() → generate_blueprint() → get_blueprint() round-trip
- generate_blueprint() from MarketRecommendation
- generate_default_blueprint() without recommendation
- get_blueprint() lookup (found / not found)
- get_service_status() reporting
- _generate_heuristic_predictions() with and without adapter
- run_simulation() error paths (no adapter, no candles)
- get_simulation_history()
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from okx_trading.application.services.research_service import (
    DEFAULT_MARKETS,
    RankingResult,
    ResearchService,
)
from okx_trading.domain.grid.models import Blueprint
from okx_trading.research.models.ranking import (
    MarketRecommendation,
    RecommendationAction,
    RiskLevel,
    SuitabilityScore,
)


def _make_recommendation(
    market_id: str = "BTC-USDT",
    rank: int = 1,
    total_score: float = 70.0,
    risk_level: RiskLevel = RiskLevel.LOW,
    action: RecommendationAction = RecommendationAction.BUY,
) -> MarketRecommendation:
    """Create a MarketRecommendation for testing."""
    score = SuitabilityScore(
        market_id=market_id,
        blueprint_id="BP-TEST",
        observation_timestamp=datetime.now(UTC),
        total_score=total_score,
        risk_level=risk_level,
    )
    return MarketRecommendation(
        market_id=market_id,
        rank=rank,
        suitability_score=score,
        action=action,
        confidence=0.8,
    )


class TestResearchServiceInit:
    """Tests for ResearchService initialization."""

    def test_default_init(self):
        """Service initializes with default blueprint generator."""
        service = ResearchService()
        assert service.last_ranking is None
        assert service.blueprints == {}

    def test_init_with_adapter(self):
        """Service accepts an optional adapter."""
        adapter = MagicMock()
        service = ResearchService(adapter=adapter)
        assert service._adapter is adapter

    def test_init_with_custom_generator(self):
        """Service accepts a custom blueprint generator."""
        from okx_trading.research.models.blueprint_generator import BlueprintGenerator

        gen = BlueprintGenerator()
        service = ResearchService(blueprint_generator=gen)
        assert service._blueprint_generator is gen


class TestRankMarkets:
    """Tests for rank_markets() heuristic mode."""

    async def test_returns_ranking_result(self):
        """rank_markets returns a RankingResult with recommendations."""
        service = ResearchService()
        result = await service.rank_markets(market_ids=["BTC-USDT", "ETH-USDT"], top_n=5)

        assert isinstance(result, RankingResult)
        assert result.mode == "heuristic"
        assert result.markets_evaluated == 2
        assert len(result.recommendations) > 0

    async def test_uses_default_markets_when_none(self):
        """rank_markets uses DEFAULT_MARKETS when no market_ids given."""
        service = ResearchService()
        result = await service.rank_markets()

        assert result.markets_evaluated == len(DEFAULT_MARKETS)

    async def test_respects_top_n(self):
        """rank_markets limits results to top_n."""
        service = ResearchService()
        result = await service.rank_markets(top_n=3)

        assert len(result.recommendations) <= 3

    async def test_stores_last_ranking(self):
        """rank_markets caches the result in last_ranking."""
        service = ResearchService()
        assert service.last_ranking is None

        result = await service.rank_markets(market_ids=["BTC-USDT"])
        assert service.last_ranking is result

    async def test_recommendations_have_valid_scores(self):
        """Each recommendation has a positive suitability score."""
        service = ResearchService()
        result = await service.rank_markets(market_ids=["BTC-USDT", "ETH-USDT", "SOL-USDT"])

        for rec in result.recommendations:
            assert rec.suitability_score.total_score > 0
            assert rec.market_id in ["BTC-USDT", "ETH-USDT", "SOL-USDT"]

    async def test_ranking_result_to_dict(self):
        """RankingResult.to_dict() serializes correctly."""
        service = ResearchService()
        result = await service.rank_markets(market_ids=["BTC-USDT"])
        d = result.to_dict()

        assert "recommendations" in d
        assert "ranked_at" in d
        assert d["mode"] == "heuristic"
        assert d["markets_evaluated"] == 1


class TestGenerateHeuristicPredictions:
    """Tests for _generate_heuristic_predictions()."""

    async def test_without_adapter_uses_defaults(self):
        """Without adapter, uses default heuristic values."""
        service = ResearchService(adapter=None)
        preds = await service._generate_heuristic_predictions(["BTC-USDT", "SOL-USDT"])

        assert len(preds) == 2
        for pred in preds:
            assert pred.positive_pnl_probability is not None
            assert 0 <= pred.positive_pnl_probability <= 1

    async def test_btc_eth_get_higher_defaults(self):
        """BTC/ETH get higher default liquidity scores than altcoins."""
        service = ResearchService(adapter=None)
        preds = await service._generate_heuristic_predictions(["BTC-USDT", "DOGE-USDT"])

        btc_pred = next(p for p in preds if p.market_id == "BTC-USDT")
        doge_pred = next(p for p in preds if p.market_id == "DOGE-USDT")

        # BTC should have higher capital utilization (proxy for liquidity)
        assert btc_pred.expected_capital_utilization > doge_pred.expected_capital_utilization

    async def test_with_adapter_uses_ticker_data(self):
        """With adapter, uses ticker data for volatility/volume estimates."""
        adapter = MagicMock()
        adapter.get_ticker = AsyncMock(
            return_value={
                "bid": "50000",
                "ask": "50010",
                "change_24h": "0.03",
            }
        )
        service = ResearchService(adapter=adapter)
        preds = await service._generate_heuristic_predictions(["BTC-USDT"])

        assert len(preds) == 1
        adapter.get_ticker.assert_called_once_with("BTC-USDT")

    async def test_adapter_failure_falls_back_to_defaults(self):
        """If adapter raises, falls back to default heuristic values."""
        adapter = MagicMock()
        adapter.get_ticker = AsyncMock(side_effect=Exception("connection error"))
        service = ResearchService(adapter=adapter)
        preds = await service._generate_heuristic_predictions(["BTC-USDT"])

        assert len(preds) == 1
        assert preds[0].positive_pnl_probability is not None

    async def test_adapter_returns_none_ticker(self):
        """If adapter returns None ticker, falls back to defaults."""
        adapter = MagicMock()
        adapter.get_ticker = AsyncMock(return_value=None)
        service = ResearchService(adapter=adapter)
        preds = await service._generate_heuristic_predictions(["BTC-USDT"])

        assert len(preds) == 1
        assert preds[0].positive_pnl_probability is not None


class TestGenerateBlueprint:
    """Tests for generate_blueprint() from recommendation."""

    def test_generates_and_stores_blueprint(self):
        """generate_blueprint creates a blueprint and stores it."""
        service = ResearchService()
        rec = _make_recommendation(market_id="BTC-USDT", risk_level=RiskLevel.LOW)
        price = Decimal("50000")

        blueprint = service.generate_blueprint(rec, current_price=price)

        assert isinstance(blueprint, Blueprint)
        assert blueprint.market_id == "BTC-USDT"
        assert blueprint.blueprint_id in service.blueprints
        assert service.get_blueprint(blueprint.blueprint_id) is blueprint

    def test_fills_recommended_blueprint_id(self):
        """generate_blueprint sets recommendation.recommended_blueprint_id."""
        service = ResearchService()
        rec = _make_recommendation(market_id="ETH-USDT")
        price = Decimal("3000")

        blueprint = service.generate_blueprint(rec, current_price=price)

        assert rec.recommended_blueprint_id == blueprint.blueprint_id

    def test_custom_capital(self):
        """generate_blueprint respects custom capital."""
        service = ResearchService()
        rec = _make_recommendation()
        price = Decimal("50000")

        blueprint = service.generate_blueprint(rec, current_price=price, capital=Decimal("5000"))

        assert blueprint.total_capital == Decimal("5000")

    def test_avoid_recommendation_raises(self):
        """generate_blueprint raises ValueError for AVOID recommendation."""
        service = ResearchService()
        rec = _make_recommendation(action=RecommendationAction.AVOID)
        price = Decimal("50000")

        with pytest.raises(ValueError, match="AVOID"):
            service.generate_blueprint(rec, current_price=price)


class TestGenerateDefaultBlueprint:
    """Tests for generate_default_blueprint()."""

    def test_generates_single_section_blueprint(self):
        """generate_default_blueprint creates a conservative single-section blueprint."""
        service = ResearchService()
        blueprint = service.generate_default_blueprint(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        assert isinstance(blueprint, Blueprint)
        assert blueprint.market_id == "BTC-USDT"
        assert blueprint.section_count == 1
        assert blueprint.blueprint_id in service.blueprints

    def test_custom_capital(self):
        """generate_default_blueprint respects custom capital."""
        service = ResearchService()
        blueprint = service.generate_default_blueprint(
            market_id="SOL-USDT",
            current_price=Decimal("150"),
            capital=Decimal("2000"),
        )

        assert blueprint.total_capital == Decimal("2000")

    def test_stored_and_retrievable(self):
        """Default blueprint is stored and retrievable via get_blueprint."""
        service = ResearchService()
        blueprint = service.generate_default_blueprint(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )

        retrieved = service.get_blueprint(blueprint.blueprint_id)
        assert retrieved is blueprint


class TestGetBlueprint:
    """Tests for get_blueprint()."""

    def test_returns_none_for_unknown_id(self):
        """get_blueprint returns None for non-existent blueprint ID."""
        service = ResearchService()
        assert service.get_blueprint("BP-NONEXISTENT") is None

    def test_returns_stored_blueprint(self):
        """get_blueprint returns a previously stored blueprint."""
        service = ResearchService()
        blueprint = service.generate_default_blueprint(
            market_id="BTC-USDT",
            current_price=Decimal("50000"),
        )
        assert service.get_blueprint(blueprint.blueprint_id) is blueprint


class TestRankToBlueprintRoundTrip:
    """Integration test: rank_markets → generate_blueprint → get_blueprint."""

    async def test_full_round_trip(self):
        """Full flow: rank markets, pick top recommendation, generate blueprint, retrieve it."""
        service = ResearchService()

        # Step 1: Rank markets
        result = await service.rank_markets(market_ids=["BTC-USDT", "ETH-USDT"], top_n=5)
        assert len(result.recommendations) > 0

        # Step 2: Pick top recommendation
        top_rec = result.recommendations[0]

        # Step 3: Generate blueprint from recommendation
        blueprint = service.generate_blueprint(
            recommendation=top_rec,
            current_price=Decimal("50000"),
        )

        # Step 4: Retrieve blueprint
        retrieved = service.get_blueprint(blueprint.blueprint_id)
        assert retrieved is blueprint
        assert retrieved.market_id == top_rec.market_id
        assert top_rec.recommended_blueprint_id == blueprint.blueprint_id

    async def test_multiple_blueprints_stored(self):
        """Multiple blueprints can be generated and stored independently."""
        service = ResearchService()
        result = await service.rank_markets(market_ids=["BTC-USDT", "ETH-USDT", "SOL-USDT"])

        blueprint_ids = []
        for rec in result.recommendations:
            bp = service.generate_blueprint(rec, current_price=Decimal("100"))
            blueprint_ids.append(bp.blueprint_id)

        assert len(service.blueprints) == len(blueprint_ids)
        for bp_id in blueprint_ids:
            assert service.get_blueprint(bp_id) is not None


class TestGetServiceStatus:
    """Tests for get_service_status()."""

    def test_initial_status(self):
        """Initial status shows no ranking, no blueprints."""
        service = ResearchService()
        status = service.get_service_status()

        assert status["last_ranking_at"] is None
        assert status["last_ranking_mode"] is None
        assert status["blueprints_generated"] == 0
        assert status["adapter_connected"] is False

    async def test_status_after_ranking(self):
        """Status reflects ranking after rank_markets."""
        service = ResearchService()
        await service.rank_markets(market_ids=["BTC-USDT"])

        status = service.get_service_status()
        assert status["last_ranking_at"] is not None
        assert status["last_ranking_mode"] == "heuristic"

    def test_status_with_adapter(self):
        """Status shows adapter_connected=True when adapter is set."""
        adapter = MagicMock()
        service = ResearchService(adapter=adapter)
        status = service.get_service_status()
        assert status["adapter_connected"] is True

    def test_status_after_blueprint_generation(self):
        """Status counts generated blueprints."""
        service = ResearchService()
        service.generate_default_blueprint("BTC-USDT", Decimal("50000"))
        service.generate_default_blueprint("ETH-USDT", Decimal("3000"))

        status = service.get_service_status()
        assert status["blueprints_generated"] == 2


class TestRunSimulation:
    """Tests for run_simulation() error paths."""

    async def test_no_adapter_raises_value_error(self):
        """run_simulation raises ValueError when adapter is not connected."""
        service = ResearchService(adapter=None)

        with pytest.raises(ValueError, match="adapter not connected"):
            await service.run_simulation(market_id="BTC-USDT")

    async def test_no_candles_raises_value_error(self):
        """run_simulation raises ValueError when no candle data available."""
        adapter = MagicMock()
        adapter.get_candles = AsyncMock(return_value=[])
        service = ResearchService(adapter=adapter)

        with pytest.raises(ValueError, match="No candle data"):
            await service.run_simulation(market_id="BTC-USDT")


class TestGetSimulationHistory:
    """Tests for get_simulation_history()."""

    def test_empty_history(self):
        """get_simulation_history returns empty list initially."""
        service = ResearchService()
        assert service.get_simulation_history() == []

    def test_respects_limit(self):
        """get_simulation_history respects the limit parameter."""
        service = ResearchService()
        # Inject mock simulation results
        for _i in range(5):
            mock_result = MagicMock()
            service._simulation_results.append(mock_result)

        history = service.get_simulation_history(limit=3)
        assert len(history) == 3
        # Should return the last 3
        assert history == service._simulation_results[-3:]
