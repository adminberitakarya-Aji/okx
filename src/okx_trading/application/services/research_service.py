"""
Research Service — Orchestrates market ranking and blueprint generation.

This service bridges the research/ML pipeline with the application layer:
- Provides market rankings via MarketRanker (when model predictions available)
- Falls back to heuristic ranking when no trained model exists
- Generates blueprints from recommendations via BlueprintGenerator
- Caches last ranking result for Telegram menu display

Dependency rules: application/ may import domain/ and research/.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog

from okx_trading.domain.exchange.interface import ExchangeAdapter
from okx_trading.domain.grid.models import Blueprint
from okx_trading.domain.shared.types import MarketId, Price
from okx_trading.research.models.blueprint_generator import BlueprintGenerator
from okx_trading.research.models.ranking import (
    MarketRanker,
    MarketRecommendation,
    ModelPredictions,
    SuitabilityEngine,
)
from okx_trading.research.simulator.grid_simulator import (
    GridSimulator,
    SimulationConfig,
    SimulationResult,
)

logger = structlog.get_logger()

# Default markets to rank when no model is available
DEFAULT_MARKETS: list[MarketId] = [
    "BTC-USDT",
    "ETH-USDT",
    "SOL-USDT",
    "XRP-USDT",
    "DOGE-USDT",
    "ADA-USDT",
    "AVAX-USDT",
    "DOT-USDT",
    "LINK-USDT",
    "MATIC-USDT",
]


@dataclass
class RankingResult:
    """Result of a market ranking run."""

    recommendations: list[MarketRecommendation]
    ranked_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    mode: str = "heuristic"  # "ml" or "heuristic"
    markets_evaluated: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendations": [r.to_dict() for r in self.recommendations],
            "ranked_at": self.ranked_at.isoformat(),
            "mode": self.mode,
            "markets_evaluated": self.markets_evaluated,
        }


class ResearchService:
    """
    Research Service — market ranking and blueprint generation.

    Provides two modes:
    1. ML mode: Uses trained model predictions via MarketRanker
    2. Heuristic mode: Uses market data (volatility, volume) for ranking
       when no trained model is available

    The heuristic mode ensures the TOP 10 menu is functional from day one,
    while ML mode activates automatically when a model is promoted.
    """

    def __init__(
        self,
        adapter: ExchangeAdapter | None = None,
        blueprint_generator: BlueprintGenerator | None = None,
    ) -> None:
        """
        Initialize research service.

        Args:
            adapter: Exchange adapter for market data (optional)
            blueprint_generator: Blueprint generator (optional, creates default)
        """
        self._adapter = adapter
        self._blueprint_generator = blueprint_generator or BlueprintGenerator()
        self._suitability_engine = SuitabilityEngine()
        self._market_ranker = MarketRanker(suitability_engine=self._suitability_engine)
        self._last_ranking: RankingResult | None = None
        self._blueprints: dict[str, Blueprint] = {}
        self._simulation_results: list[SimulationResult] = []

    @property
    def last_ranking(self) -> RankingResult | None:
        """Get the last ranking result."""
        return self._last_ranking

    @property
    def blueprints(self) -> dict[str, Blueprint]:
        """Get all generated blueprints."""
        return self._blueprints

    async def rank_markets(
        self,
        market_ids: list[MarketId] | None = None,
        top_n: int = 10,
    ) -> RankingResult:
        """
        Rank markets by grid suitability.

        Uses heuristic mode (market data based) when no ML model is available.

        Args:
            market_ids: Markets to rank (defaults to DEFAULT_MARKETS)
            top_n: Number of top markets to return

        Returns:
            RankingResult with recommendations
        """
        markets = market_ids or DEFAULT_MARKETS

        # Heuristic mode: create synthetic predictions from market data
        predictions_list = await self._generate_heuristic_predictions(markets)

        # MarketRanker expects dict[market_id -> list[ModelPredictions]]
        market_predictions: dict[str, list[ModelPredictions]] = {}
        for pred in predictions_list:
            market_predictions.setdefault(pred.market_id, []).append(pred)

        # Rank using MarketRanker (respects max_recommendations internally)
        recommendations = self._market_ranker.rank_markets(
            market_predictions=market_predictions,
        )

        # Limit to top_n
        recommendations = recommendations[:top_n]

        result = RankingResult(
            recommendations=recommendations,
            mode="heuristic",
            markets_evaluated=len(markets),
        )

        self._last_ranking = result

        logger.info(
            "markets_ranked",
            mode="heuristic",
            markets_evaluated=len(markets),
            recommendations=len(recommendations),
        )

        return result

    async def _generate_heuristic_predictions(
        self,
        market_ids: list[MarketId],
    ) -> list[ModelPredictions]:
        """
        Generate heuristic predictions from market data.

        Uses volatility and volume characteristics to estimate
        grid suitability when no ML model is available.

        This is NOT ML — it's a rule-based fallback that ensures
        the ranking UI is functional before model training completes.
        """
        predictions: list[ModelPredictions] = []
        now = datetime.now(UTC)

        for market_id in market_ids:
            # Try to get market data from adapter
            volatility = None
            volume_score = None

            if self._adapter is not None:
                try:
                    ticker = await self._adapter.get_ticker(market_id)
                    if ticker:
                        # Estimate volatility from bid-ask spread
                        bid = ticker.get("bid")
                        ask = ticker.get("ask")
                        if bid and ask:
                            bid_d = Decimal(str(bid))
                            ask_d = Decimal(str(ask))
                            if bid_d > 0:
                                spread_pct = float((ask_d - bid_d) / bid_d)
                                # Lower spread = more liquid = better for grid
                                volume_score = max(0.0, min(1.0, 1.0 - spread_pct * 100))

                        # Use 24h change as volatility proxy
                        change_24h = ticker.get("change_24h") or ticker.get("change24h")
                        if change_24h is not None:
                            volatility = abs(float(change_24h))
                except Exception:
                    logger.debug("heuristic_market_data_failed", market_id=market_id)

            # Default heuristic values for major markets
            if volatility is None:
                # Major pairs assumed moderate volatility
                volatility = 0.03 if market_id.startswith(("BTC", "ETH")) else 0.05

            if volume_score is None:
                # Major pairs assumed high liquidity
                volume_score = 0.8 if market_id.startswith(("BTC", "ETH")) else 0.6

            # Heuristic suitability estimation:
            # - Moderate volatility (2-5%) is ideal for grid
            # - High liquidity is better
            vol_score = max(0.0, min(1.0, 1.0 - abs(volatility - 0.035) / 0.035))

            # Positive PnL probability heuristic
            positive_pnl_prob = 0.4 + 0.3 * vol_score + 0.2 * volume_score

            pred = ModelPredictions(
                market_id=market_id,
                blueprint_id="heuristic",
                observation_timestamp=now,
                positive_pnl_probability=min(0.95, positive_pnl_prob),
                expected_net_pnl_return=0.02 * vol_score,
                expected_max_drawdown=0.15 + volatility,
                expected_capital_utilization=0.5 + 0.2 * volume_score,
                recovery_probability=0.6 + 0.2 * vol_score,
                capital_exhaustion_probability=max(0.05, 0.3 - 0.2 * volume_score),
            )
            predictions.append(pred)

        return predictions

    def generate_blueprint(
        self,
        recommendation: MarketRecommendation,
        current_price: Price,
        capital: Decimal | None = None,
    ) -> Blueprint:
        """
        Generate a blueprint from a recommendation.

        Args:
            recommendation: Market recommendation
            current_price: Current market price
            capital: Total capital

        Returns:
            Generated Blueprint
        """
        blueprint = self._blueprint_generator.generate(
            recommendation=recommendation,
            current_price=current_price,
            capital=capital,
        )

        # Fill the recommended_blueprint_id slot
        recommendation.recommended_blueprint_id = blueprint.blueprint_id

        # Store blueprint
        self._blueprints[blueprint.blueprint_id] = blueprint

        return blueprint

    def generate_default_blueprint(
        self,
        market_id: MarketId,
        current_price: Price,
        capital: Decimal | None = None,
    ) -> Blueprint:
        """
        Generate a default blueprint without ML recommendation.

        Args:
            market_id: Market to trade
            current_price: Current market price
            capital: Total capital

        Returns:
            Conservative Blueprint
        """
        blueprint = self._blueprint_generator.generate_default(
            market_id=market_id,
            current_price=current_price,
            capital=capital,
        )

        self._blueprints[blueprint.blueprint_id] = blueprint
        return blueprint

    def get_blueprint(self, blueprint_id: str) -> Blueprint | None:
        """Get a blueprint by ID."""
        return self._blueprints.get(blueprint_id)

    def get_service_status(self) -> dict[str, Any]:
        """Get research service status."""
        return {
            "last_ranking_at": (
                self._last_ranking.ranked_at.isoformat() if self._last_ranking else None
            ),
            "last_ranking_mode": self._last_ranking.mode if self._last_ranking else None,
            "blueprints_generated": len(self._blueprints),
            "simulations_run": len(self._simulation_results),
            "adapter_connected": self._adapter is not None,
        }

    # =========================================================================
    # SIMULATION
    # =========================================================================

    async def run_simulation(
        self,
        market_id: MarketId,
        interval: str = "1H",
        candle_limit: int = 168,
        capital: Decimal | None = None,
    ) -> SimulationResult:
        """
        Run a historical grid simulation for a market.

        Flow:
        1. Fetch historical candles from the exchange adapter
        2. Generate a default blueprint anchored to the latest close
        3. Run the deterministic GridSimulator over the candles

        Args:
            market_id: Market to simulate (e.g., "BTC-USDT")
            interval: Candle interval (default "1H")
            candle_limit: Number of candles to simulate (default 168 = 7 days)
            capital: Starting capital (defaults to generator default)

        Returns:
            SimulationResult with full performance metrics

        Raises:
            ValueError: If no candles available or adapter not connected
        """
        if self._adapter is None:
            raise ValueError("Exchange adapter not connected — cannot run simulation")

        # 1. Fetch historical candles
        candles = await self._adapter.get_candles(
            market_id=market_id,
            interval=interval,
            limit=candle_limit,
        )

        if not candles:
            raise ValueError(f"No candle data available for {market_id} ({interval})")

        # 2. Anchor blueprint to the latest close price
        latest_close = candles[-1].close
        blueprint = self.generate_default_blueprint(
            market_id=market_id,
            current_price=latest_close,
            capital=capital,
        )

        # 3. Configure and run simulator
        config = SimulationConfig(
            market_id=market_id,
            observation_timestamp=candles[0].timestamp,
            simulation_horizon_candles=len(candles),
            starting_capital=blueprint.total_capital,
        )

        simulator = GridSimulator(config)
        result = simulator.run(blueprint=blueprint, candles=candles)

        # Store simulation result for history display
        self._simulation_results.append(result)

        logger.info(
            "simulation_completed",
            market_id=market_id,
            blueprint_id=blueprint.blueprint_id,
            candles_processed=result.candles_processed,
            net_pnl_return_pct=result.net_pnl_return_pct,
            completed_cycles=result.completed_cycles,
        )

        return result

    def get_simulation_history(self, limit: int = 10) -> list[SimulationResult]:
        """Get recent simulation results."""
        return self._simulation_results[-limit:]
