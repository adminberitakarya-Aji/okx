# AI Research Feature Specification — Derived ML

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`
- `AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md`
- `AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md`
- `AI_RESEARCH_FEATURE_SPEC_GRID_BEHAVIOR.md`

---

# 1. Purpose

This document defines the **Derived ML Feature Layer** for AI Research.

Derived ML features are calculated from upstream feature layers:

```text
MARKET STATE
      +
EXECUTION ECONOMICS
      +
GRID BEHAVIOR
      ↓
DERIVED ML FEATURES
      ↓
ML MODEL
      ↓
PREDICTION
      ↓
SUITABILITY / RECOMMENDATION
```

Derived ML does not introduce new exchange data.

Its purpose is to transform existing measurable features into higher-level representations that capture meaningful structural, economic, and strategy relationships.

---

# 2. Core Principle

A Derived ML feature must answer:

> **What meaningful relationship exists between upstream features that may help the ML model understand Grid suitability?**

A feature should not be created merely because two fields can be mathematically combined.

Every derived feature must have:

- A clear rationale
- A deterministic derivation where possible
- A documented source feature set
- A causal timestamp
- A defined normalization
- A clear relationship to the Grid Strategy

---

# 3. Layer Boundary

Derived ML is not the final decision layer.

It does NOT directly produce:

```text
BUY
SELL
EXECUTE
```

It does NOT directly replace:

```text
Market Recommendation
```

The architecture is:

```text
Derived Features
      ↓
ML Model
      ↓
Prediction
      ↓
Suitability Engine
      ↓
Recommendation Engine
```

This prevents feature engineering from becoming an undeclared decision engine.

---

# 4. Feature Contract Standard

Every feature follows:

```text
Feature ID
Feature Name
Layer
Description
Source Features
Formula / Derivation
Data Type
Normalization
Valid Range
Timeframe / Window
Update Frequency
Historical Availability
Training Availability
Inference Availability
Causal Cutoff
Leakage Risk
Purpose
Notes
```

Naming convention:

```text
F-ML-xxx
```

Field names:

```text
snake_case
```

---

# 5. Domain Architecture

Derived ML is divided into seven domains:

```text
DERIVED ML
│
├── 01. Structural Alignment
├── 02. Proximity Intelligence
├── 03. Trend + Structure Interaction
├── 04. Volatility + Opportunity
├── 05. Execution-Adjusted Opportunity
├── 06. Grid Compatibility
└── 07. Capital / Risk / Recovery
```

---

# 6. Structural Alignment

Structural Alignment combines Monthly, Weekly, Daily, and realtime price context.

## F-ML-001 — Multi-Timeframe Price Alignment

Source:

```text
monthly_price_position
weekly_price_position
daily_price_position
```

Purpose:

Measures whether realtime price occupies a similar relative position across the three timeframe ranges.

A market where:

```text
Monthly = 0.10
Weekly  = 0.15
Daily   = 0.18
```

has a different structural state from:

```text
Monthly = 0.10
Weekly  = 0.60
Daily   = 0.80
```

The exact formula should preserve directional information and remain normalized.

---

## F-ML-002 — Multi-Timeframe Low Alignment

Source:

```text
monthly_price_position
weekly_price_position
daily_price_position
```

and low-proximity features.

Purpose:

Measures whether realtime price is simultaneously near the lower ranges of Monthly, Weekly, and Daily structures.

This is especially relevant to the Grid Strategy's deeper accumulation logic.

---

## F-ML-003 — Multi-Timeframe High Alignment

Equivalent representation for upper structural ranges.

Purpose:

Provides symmetric structural information.

---

## F-ML-004 — Structural Range Alignment

Source:

```text
monthly_price_position
weekly_price_position
daily_price_position
monthly_weekly_price_position_difference
weekly_daily_price_position_difference
```

Purpose:

Measures how similar the current price location is across timeframe ranges.

---

## F-ML-005 — Structural Alignment Consistency

Purpose:

Measures whether Monthly, Weekly, and Daily context remain consistently aligned over a historical rolling window.

This should use only observations available before the prediction timestamp.

---

# 7. Proximity Intelligence

Proximity features transform raw distance into context-aware relationships.

## F-ML-006 — Monthly Low Volatility-Adjusted Proximity

Source:

```text
distance_to_monthly_low_pct
monthly_low_distance_vol_adjusted
```

Purpose:

Represents how close price is to Monthly Low relative to current market volatility.

A 2% distance means different things in a market with:

```text
1% volatility
```

versus:

```text
8% volatility
```

---

## F-ML-007 — Monthly High Volatility-Adjusted Proximity

Equivalent for Monthly High.

---

## F-ML-008 — Weekly Low Volatility-Adjusted Proximity

Equivalent for Weekly Low.

---

## F-ML-009 — Weekly High Volatility-Adjusted Proximity

Equivalent for Weekly High.

---

## F-ML-010 — Daily Low Volatility-Adjusted Proximity

Equivalent for Daily Low.

---

## F-ML-011 — Daily High Volatility-Adjusted Proximity

Equivalent for Daily High.

These features should reference the canonical adjusted-distance features rather than recalculate inconsistent formulas.

---

## F-ML-012 — Multi-Timeframe Low Pressure

Sources:

```text
distance_to_monthly_low_pct
distance_to_weekly_low_pct
distance_to_daily_low_pct
monthly_low_distance_vol_adjusted
weekly_low_distance_vol_adjusted
daily_low_distance_vol_adjusted
```

Purpose:

Measures the combined structural pressure toward lower timeframe boundaries.

The preferred representation is continuous.

Optional categorical interpretation:

```text
LOW
MEDIUM
HIGH
EXTREME
```

should be generated by a separate deterministic interpretation layer if required.

---

## F-ML-013 — Multi-Timeframe High Pressure

Equivalent upper-range representation.

---

## F-ML-014 — Monthly Breakdown Depth Relative to Volatility

Sources:

```text
distance_below_monthly_low_pct
current_volatility
```

Concept:

```text
break_depth
/
reference_volatility
```

Purpose:

Measures the severity of Monthly Low breakdown in volatility units.

---

## F-ML-015 — Monthly Breakdown Persistence

Source:

Historical sequence of:

```text
monthly_low_status
monthly_low_break_flag
monthly_low_recovery_state
```

Purpose:

Distinguishes:

```text
brief Monthly Low break
```

from:

```text
persistent breakdown
```

Only historical observations before the current prediction point may be used.

---

# 8. Trend + Structure Interaction

Trend must not be treated as an isolated indicator.

## F-ML-016 — Trend Alignment Score

Source:

```text
monthly_trend_direction
weekly_trend_direction
daily_trend_direction
```

Purpose:

Converts multi-timeframe trend direction into a consistent numerical representation.

Example conceptual encoding:

```text
Bullish  = +1
Neutral  =  0
Bearish  = -1
```

The exact weighting is implementation-dependent.

---

## F-ML-017 — Trend Strength Composite

Sources:

```text
monthly_trend_strength
weekly_trend_strength
daily_trend_strength
```

Purpose:

Summarizes directional strength across timeframes while preserving information about timeframe hierarchy.

---

## F-ML-018 — Trend-Structure Alignment

Sources:

```text
trend_direction
trend_strength
price_position
structural_alignment
```

Purpose:

Distinguishes market states such as:

```text
Strong trend aligned with price structure
```

from:

```text
Macro trend opposing lower-timeframe movement
```

---

## F-ML-019 — Corrective Structure Context

Derived concept:

```text
Monthly trend
+
Weekly trend
+
Daily trend
+
Price proximity
```

Purpose:

Helps represent conditions such as:

```text
Monthly Bullish
Weekly Bearish
Daily Bearish
Price Near Monthly Low
```

This is intended as a market-state representation, not a hard-coded trading label.

---

## F-ML-020 — Counter-Trend Pressure

Measures the degree to which lower timeframe trends oppose the dominant higher timeframe trend.

Purpose:

Useful for distinguishing:

```text
normal correction
```

from:

```text
strong counter-trend movement
```

---

# 9. Volatility + Opportunity

Volatility must be interpreted in relation to the strategy's required movement.

## F-ML-021 — Volatility Opportunity Ratio

Source:

```text
expected_market_movement
reference_volatility
```

Concept:

```text
Expected Movement
/
Reference Volatility
```

Purpose:

Measures whether available volatility provides meaningful movement relative to the market's normal behavior.

---

## F-ML-022 — Volatility Regime Stability

Sources:

```text
current_volatility
historical_volatility
volatility_regime
volatility_expansion
volatility_compression
```

Purpose:

Distinguishes:

```text
High but stable volatility
```

from:

```text
High and rapidly expanding volatility
```

This can be represented as a continuous stability measure.

---

## F-ML-023 — Volatility Expansion Opportunity

Combines:

```text
volatility_expansion
expected_market_movement
grid_opportunity_frequency
```

Purpose:

Measures whether rising volatility is historically associated with increased usable Grid opportunity.

Historical Grid outcomes must only come from the causal historical window.

---

## F-ML-024 — Volatility-to-Grid Relationship

Sources:

```text
volatility
grid_opportunity_frequency
grid_cycle_frequency
```

Purpose:

Measures the relationship between market volatility and actual Grid activity.

---

# 10. Execution-Adjusted Opportunity

This is one of the core differentiated areas of the system.

## F-ML-025 — Execution-Cost-Adjusted Opportunity

Sources:

```text
expected_gross_move
expected_round_trip_cost
```

Concept:

```text
Expected Gross Opportunity
− Expected Execution Cost
```

Purpose:

Measures the remaining economic opportunity after immediate execution costs.

---

## F-ML-026 — Execution Opportunity Retention Ratio

Sources:

```text
expected_net_opportunity
expected_gross_move
```

Concept:

```text
Expected Net Opportunity
/
Expected Gross Opportunity
```

Example:

```text
Gross Opportunity = 1.50%
Execution Cost = 0.30%

Net Opportunity = 1.20%

Retention = 80%
```

---

## F-ML-027 — Execution Burden Composite

Sources:

```text
fee_burden_ratio
spread_burden_ratio
slippage_burden_ratio
total_execution_burden_ratio
```

Purpose:

Creates a consolidated representation of how heavily execution costs consume the expected trading opportunity.

---

## F-ML-028 — Execution Stress Resilience

Sources:

```text
normal_execution_cost
stress_execution_cost
extreme_execution_cost
execution_cost_stress_multiplier
```

Purpose:

Measures how much economic viability degrades under stressed execution.

---

## F-ML-029 — Liquidity-Adjusted Opportunity

Sources:

```text
expected_net_opportunity
liquidity_score
buy_order_size_liquidity_ratio
sell_order_size_liquidity_ratio
```

Purpose:

Measures whether the apparent opportunity remains attractive at the required execution size.

---

# 11. Grid Compatibility

Grid Compatibility is the most strategy-specific Derived ML domain.

## F-ML-030 — Market-to-Grid Compatibility

Sources:

```text
Market State
Execution Economics
Grid Behavior
```

Purpose:

Represents how well the market's characteristics match the actual Grid Strategy.

This is a research-derived feature and must be built from causally available information only.

---

## F-ML-031 — Grid Opportunity Quality

Sources:

```text
grid_opportunity_frequency
grid_cycle_frequency
positive_cycle_rate
expected_grid_net_opportunity
```

Purpose:

Distinguishes:

```text
many grid events
```

from:

```text
many economically useful grid events
```

---

## F-ML-032 — Grid Capture Quality

Sources:

```text
gross_grid_capture
net_grid_capture
grid_capture_efficiency
```

Purpose:

Measures how much of the theoretical movement is converted into actual net strategy capture.

---

## F-ML-033 — Grid Depth Compatibility

Sources:

```text
historical drawdown
section_activation
section_gap
capital_reserve
```

Purpose:

Measures whether the configured Section depth is compatible with typical historical price movement.

Example:

```text
Typical Drawdown = 8%
Section 2 Activation = around 5%
Section 3 Activation = around 12%
```

This creates a meaningful relationship between market drawdown behavior and Section architecture.

---

## F-ML-034 — Section Deployment Efficiency

Sources:

```text
section_activation
capital_deployed
net_pnl
recovery
```

Purpose:

Measures whether capital allocated to deeper Sections contributes meaningfully to strategy outcomes.

---

## F-ML-035 — Section Gap Effectiveness

Sources:

```text
section_gap_utilization
section_transition_rate
section_transition_speed
recovery
net_pnl
```

Purpose:

Measures whether Section Gaps are producing useful separation between capital deployment zones.

---

## F-ML-036 — Grid Spacing Economic Fit

Sources:

```text
uniform_grid_spacing
expected_grid_movement
expected_grid_round_trip_cost
grid_economic_viability
```

Purpose:

Measures how well a candidate uniform Section grid spacing fits the market's economics.

Important:

This compares different valid candidate Blueprints.

It does NOT permit non-uniform grid spacing within a Section.

---

# 12. Capital / Risk / Recovery

## F-ML-037 — Capital Consumption Risk

Sources:

```text
capital_deployment_velocity
peak_exposure
section_activation_depth
capital_exhaustion_frequency
```

Purpose:

Measures how quickly and deeply the strategy may consume available capital.

---

## F-ML-038 — Capital Reserve Resilience

Sources:

```text
minimum_capital_reserve
capital_exhaustion_frequency
maximum_section_depth_frequency
recovery
```

Purpose:

Measures how well the strategy maintains reserve capacity through historical drawdowns.

---

## F-ML-039 — Recovery Efficiency

Sources:

```text
recovery_rate
average_recovery_time
cost_basis_improvement_ratio
net_pnl
```

Purpose:

Measures how effectively deeper accumulation is followed by recovery.

---

## F-ML-040 — Drawdown-to-Recovery Quality

Sources:

```text
drawdown
section_activation
cost_basis_improvement
recovery
net_pnl
```

Concept:

```text
Drawdown
→ Section Deployment
→ Cost Basis Improvement
→ Recovery
→ Net Outcome
```

Purpose:

Represents whether the intended defensive accumulation mechanism is historically effective.

---

## F-ML-041 — Capital Efficiency Under Drawdown

Sources:

```text
capital_deployed
coin_accumulated
drawdown
recovery
net_pnl
```

Purpose:

Measures how efficiently capital converts deeper market declines into additional coin accumulation and eventual strategy outcomes.

---

## F-ML-042 — Recovery Failure Pressure

Sources:

```text
recovery_failure_rate
capital_exhaustion_frequency
maximum_strategy_drawdown
```

Purpose:

Represents risk that deeper accumulation does not recover within the tested horizon.

---

# 13. Historical Strategy Context Features

Some Derived ML features should represent rolling historical behavior.

## F-ML-043 — Rolling Grid Suitability Context

Sources:

Historical rolling:

```text
grid_opportunity_frequency
positive_cycle_rate
net_pnl
drawdown
recovery
```

Purpose:

Provides recent strategy behavior context at observation time T.

Critical:

Only historical data before T may be included.

---

## F-ML-044 — Rolling Execution-Adjusted Grid Quality

Sources:

Historical rolling:

```text
expected_net_opportunity
execution_cost_ratio
grid_capture_efficiency
```

Purpose:

Measures recent economic quality of the Grid opportunity.

---

## F-ML-045 — Rolling Section Depth Profile

Sources:

Historical rolling:

```text
section_2_activation_rate
section_3_activation_rate
maximum_section_depth_frequency
```

Purpose:

Represents recent depth requirements of the market relative to the Grid architecture.

---

# 14. Derived Feature Classes

Derived ML features should be classified into two technical classes.

## Class A — Deterministic Derived Features

These have explicit formulas and can be reproduced exactly.

Examples:

```text
Volatility-Adjusted Proximity
Trend Alignment Score
Execution Opportunity Retention
Execution Cost Ratio
```

Characteristics:

- Deterministic
- Reproducible
- Versionable
- Easy to audit

---

## Class B — Research-Derived Features

These depend on historical statistical analysis.

Examples:

```text
Market-to-Grid Compatibility
Grid Opportunity Quality
Recovery Efficiency
Section Deployment Efficiency
```

Characteristics:

- Derived from historical observations
- Must have causal cutoff
- Must be versioned
- Must be monitored for bias
- Must not silently use future outcomes

---

# 15. Feature Selection Principle

Derived features MUST NOT be created indiscriminately.

Every feature must have a reason.

Required question:

> **What relationship does this derived feature represent that the upstream features do not represent clearly enough on their own?**

If the answer is unclear, the feature should not be added.

This reduces:

- Redundancy
- Multicollinearity
- Overfitting
- Feature explosion
- Unnecessary complexity

---

# 16. Feature Leakage Policy

Derived ML is especially sensitive to leakage.

Invalid:

```text
Future Net P&L
→
Derived Feature
→
Prediction at T
```

Valid:

```text
Market State at T
+
Execution Economics at T
+
Past Grid Behavior before T
→
Derived ML at T
→
Prediction
→
Future Outcome
```

Every derived feature must specify:

```text
causal_cutoff
source_time_window
```

---

# 17. Historical Window Rules

A derived feature using historical behavior must specify a window.

Examples:

```text
7D
30D
90D
180D
365D
```

These are examples only.

The window must be selected through research and validation.

The system should preserve the original window in feature metadata.

---

# 18. Normalization

Derived ML features should generally use normalized representations.

Preferred forms:

```text
Ratio
Percentage
Z-score
Percentile
Bounded Score
Volatility Units
Relative Difference
```

Raw price-derived values should not be preferred when they prevent cross-market comparison.

---

# 19. Data Availability

Each feature must preserve:

```text
feature_value
availability
causal_cutoff
source_window
```

A feature with insufficient source data should return an explicit unavailable state.

It must not silently become:

```text
0
```

---

# 20. Derived ML Output Object

Conceptual:

```text
DerivedMLFeatures
│
├── structural
│   ├── multi_timeframe_price_alignment
│   ├── multi_timeframe_low_alignment
│   ├── multi_timeframe_high_alignment
│   └── structural_alignment_consistency
│
├── proximity
│   ├── volatility_adjusted_proximity
│   ├── low_pressure
│   ├── high_pressure
│   ├── breakdown_depth_volatility
│   └── breakdown_persistence
│
├── trend
│   ├── trend_alignment_score
│   ├── trend_strength_composite
│   ├── trend_structure_alignment
│   ├── corrective_context
│   └── counter_trend_pressure
│
├── volatility
│   ├── volatility_opportunity_ratio
│   ├── volatility_regime_stability
│   ├── volatility_expansion_opportunity
│   └── volatility_grid_relationship
│
├── execution
│   ├── cost_adjusted_opportunity
│   ├── opportunity_retention
│   ├── execution_burden
│   ├── execution_stress_resilience
│   └── liquidity_adjusted_opportunity
│
├── grid
│   ├── market_to_grid_compatibility
│   ├── grid_opportunity_quality
│   ├── grid_capture_quality
│   ├── grid_depth_compatibility
│   ├── section_deployment_efficiency
│   ├── section_gap_effectiveness
│   └── grid_spacing_economic_fit
│
└── capital_recovery
    ├── capital_consumption_risk
    ├── capital_reserve_resilience
    ├── recovery_efficiency
    ├── drawdown_to_recovery_quality
    ├── capital_efficiency_under_drawdown
    └── recovery_failure_pressure
```

---

# 21. What Derived ML Must Not Become

Derived ML MUST NOT directly become:

```text
BUY_SCORE
SELL_SCORE
EXECUTE_NOW
```

unless a later, separately defined model explicitly produces such an output.

The intended flow is:

```text
Derived Features
      ↓
ML Research Model
      ↓
Predictions
      ↓
Suitability Engine
      ↓
Recommendation Engine
```

This separation is architectural.

---

# 22. Market Recommendation Boundary

Derived ML provides model-ready representations.

The Recommendation Engine decides how predictions should be translated into:

```text
HIGH PRIORITY
RECOMMENDED
NEUTRAL
LOW PRIORITY
AVOID
```

Recommendation must remain explainable through underlying:

```text
Market State
Execution Economics
Grid Behavior
Derived ML
Model Prediction
```

---

# 23. Initial Feature Inventory

```text
F-ML-001  multi_timeframe_price_alignment
F-ML-002  multi_timeframe_low_alignment
F-ML-003  multi_timeframe_high_alignment
F-ML-004  structural_range_alignment
F-ML-005  structural_alignment_consistency

F-ML-006  monthly_low_vol_adjusted_proximity
F-ML-007  monthly_high_vol_adjusted_proximity
F-ML-008  weekly_low_vol_adjusted_proximity
F-ML-009  weekly_high_vol_adjusted_proximity
F-ML-010  daily_low_vol_adjusted_proximity
F-ML-011  daily_high_vol_adjusted_proximity
F-ML-012  multi_timeframe_low_pressure
F-ML-013  multi_timeframe_high_pressure
F-ML-014  monthly_breakdown_depth_relative_to_volatility
F-ML-015  monthly_breakdown_persistence

F-ML-016  trend_alignment_score
F-ML-017  trend_strength_composite
F-ML-018  trend_structure_alignment
F-ML-019  corrective_structure_context
F-ML-020  counter_trend_pressure

F-ML-021  volatility_opportunity_ratio
F-ML-022  volatility_regime_stability
F-ML-023  volatility_expansion_opportunity
F-ML-024  volatility_to_grid_relationship

F-ML-025  execution_cost_adjusted_opportunity
F-ML-026  execution_opportunity_retention_ratio
F-ML-027  execution_burden_composite
F-ML-028  execution_stress_resilience
F-ML-029  liquidity_adjusted_opportunity

F-ML-030  market_to_grid_compatibility
F-ML-031  grid_opportunity_quality
F-ML-032  grid_capture_quality
F-ML-033  grid_depth_compatibility
F-ML-034  section_deployment_efficiency
F-ML-035  section_gap_effectiveness
F-ML-036  grid_spacing_economic_fit

F-ML-037  capital_consumption_risk
F-ML-038  capital_reserve_resilience
F-ML-039  recovery_efficiency
F-ML-040  drawdown_to_recovery_quality
F-ML-041  capital_efficiency_under_drawdown
F-ML-042  recovery_failure_pressure

F-ML-043  rolling_grid_suitability_context
F-ML-044  rolling_execution_adjusted_grid_quality
F-ML-045  rolling_section_depth_profile
```

---

# 24. Non-Negotiable Rules

1. Derived ML consumes upstream features; it does not introduce raw exchange data.
2. Every Derived ML feature must have a documented rationale.
3. Every historical feature must be causally available at the prediction timestamp.
4. Future strategy outcomes must never leak into input features.
5. Grid spacing remains uniform inside a Section.
6. Section Gaps may differ between Sections.
7. Immediate BUY and SELL economics remain part of the upstream execution model.
8. Derived ML does not directly execute trades.
9. Derived ML does not silently modify production strategy.
10. Derived ML is not the final Market Recommendation.
11. Feature versions must be reproducible.
12. Redundant or weakly justified features should be removed rather than accumulated indefinitely.
13. Research-derived features must be explicitly distinguished from deterministic derived features.
14. Every research-derived rolling feature must declare its historical window.

---

# 25. Final Definition

Derived ML is:

> **The feature layer that transforms Market State, Execution Economics, and Grid Behavior into normalized, strategy-aware relationships that help ML learn which market conditions are most compatible with the Grid Strategy.**

Its central workflow is:

```text
MARKET STATE
        +
EXECUTION ECONOMICS
        +
GRID BEHAVIOR
        ↓
DERIVED ML
        ↓
ML MODEL
        ↓
PREDICTION
        ↓
SUITABILITY ENGINE
        ↓
MARKET RECOMMENDATION
```

Derived ML does not decide the trade.

Its role is to make the relationship between:

```text
Market
+
Execution
+
Grid
+
Capital
+
Recovery
```

more learnable, measurable, and explainable for the ML layer.
