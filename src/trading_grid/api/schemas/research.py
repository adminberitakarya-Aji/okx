"""
Research API schemas.

This module provides schemas for:
- Market recommendations
- Research universe
- Market research detail
- Research run operations
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

RecommendationLevel = Literal[
    "HIGH_PRIORITY",
    "MEDIUM_PRIORITY",
    "LOW_PRIORITY",
    "NOT_RECOMMENDED",
]


class MarketRecommendationResponse(BaseModel):
    """Market recommendation response."""

    market_id: str
    rank: int
    recommendation: RecommendationLevel
    suitability_score: Decimal = Field(..., ge=0, le=1)
    confidence: Decimal = Field(..., ge=0, le=1)
    market_regime: str | None = None
    execution_quality: str | None = None
    research_reasons: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class ResearchUniverseResponse(BaseModel):
    """Research universe response."""

    universe_type: str
    snapshot_id: str
    markets: list[str] = Field(default_factory=list)
    updated_at: datetime | None = None


class MarketResearchResponse(BaseModel):
    """Market research detail response."""

    market_id: str
    market_state: dict[str, object] = Field(default_factory=dict)
    execution_economics: dict[str, object] = Field(default_factory=dict)
    grid_suitability: dict[str, object] = Field(default_factory=dict)
    recommendation: MarketRecommendationResponse | None = None
    updated_at: datetime | None = None


class ResearchRunRequest(BaseModel):
    """Request to create a research run."""

    universe: str = Field(default="TOP_10", description="Research universe")
    environment: Literal["DEMO", "LIVE"] = Field(default="DEMO")


class RecommendationListResponse(BaseModel):
    """List of market recommendations."""

    recommendations: list[MarketRecommendationResponse] = Field(default_factory=list)
    total: int = 0
    model_version: str | None = None
    generated_at: datetime | None = None
