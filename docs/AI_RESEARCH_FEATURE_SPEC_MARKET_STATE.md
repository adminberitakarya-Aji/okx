# AI Research Feature Specification — Market State

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`

## 1. Purpose

Defines the Market State Feature Layer for AI Research.

It answers:

> What is happening in the market now, and where is realtime price relative to multi-timeframe market structure?

This layer is independent of execution economics and Grid Strategy outcomes.

## 2. Scope

```text
Market Identity
Realtime Price
Monthly Structure
Weekly Structure
Daily Structure
Price Position
Proximity
Monthly Breakdown Context
Trend
Volatility
Multi-Timeframe Relationships
Structural Pressure
```

This layer MUST NOT contain:
- trading fees
- slippage cost
- spread cost as an execution metric
- Grid performance
- Section activation statistics
- capital utilization caused by the Grid Strategy
- historical Net P&L

Those belong to other feature layers.

## 3. Core Market-Context Hierarchy

```text
MONTHLY
Macro Structure
    ↓
WEEKLY
Structural Refinement
    ↓
DAILY
Operational Refinement
    ↓
REALTIME PRICE
Current Market Position
```

When realtime price approaches an important Monthly level, the system increases analysis resolution:

```text
Realtime Price
    ↓
Monthly Proximity
    ↓
Weekly Refinement
    ↓
Daily Refinement
```

A Monthly Low is a strategic reference, not an automatic no-trade boundary. A break may create a cheaper accumulation opportunity, subject to capital and risk controls outside this layer.

## 4. Feature Contract

Every feature follows:

```text
Feature ID
Feature Name
Layer
Description
Inputs
Formula / Derivation
Data Type
Normalization
Valid Range
Timeframe
Update Frequency
Historical Availability
Training Availability
Inference Availability
Leakage Risk
Purpose
Notes
```

IDs use:

```text
F-MKT-xxx
```

Field names use `snake_case`.

## 5. Market Identity

### F-MKT-001 — Market ID

`market_id`

Type: string.

Purpose: identifies the market pair.

### F-MKT-002 — Exchange ID

`exchange_id`

Type: string/categorical.

Purpose: preserves provider context without making provider identity a direct market signal.

### F-MKT-003 — Observation Timestamp

`observation_timestamp`

Type: datetime.

Purpose: anchors every observation to a precise point in time.

Leakage risk: MEDIUM if time alignment is mishandled.

## 6. Realtime Price

### F-MKT-004 — Last Price

`last_price`

Type: float.

Update: realtime.

### F-MKT-005 — Best Bid

`best_bid`

Type: float.

Update: realtime.

### F-MKT-006 — Best Ask

`best_ask`

Type: float.

Update: realtime.

### F-MKT-007 — Mid Price

`mid_price`

Formula:

```text
(best_bid + best_ask) / 2
```

Purpose: neutral market-state reference.

## 7. Candle State Policy

Monthly, Weekly, and Daily data MUST distinguish:

```text
CLOSED
IN_PROGRESS
```

The current candle's High/Low/Close are provisional until the candle closes.

Historical research MUST reconstruct what was actually known at the observation timestamp.

No future candle value may enter an historical observation.

## 8. Monthly Structure

### F-MKT-008 — Monthly Open

`monthly_open`

### F-MKT-009 — Monthly High

`monthly_high`

Current candle is provisional.

### F-MKT-010 — Monthly Low

`monthly_low`

Core strategic downside reference.

A breach is not automatically negative.

### F-MKT-011 — Monthly Close

`monthly_close`

Current in-progress value is provisional.

### F-MKT-012 — Monthly Range

```text
monthly_high - monthly_low
```

### F-MKT-013 — Monthly Range %

```text
(monthly_high - monthly_low) / monthly_low
```

### F-MKT-014 — Monthly Body

```text
abs(monthly_close - monthly_open)
```

### F-MKT-015 — Monthly Body %

```text
abs(monthly_close - monthly_open) / monthly_open
```

### F-MKT-016 — Monthly Upper Wick

```text
monthly_high - max(monthly_open, monthly_close)
```

### F-MKT-017 — Monthly Lower Wick

```text
min(monthly_open, monthly_close) - monthly_low
```

### F-MKT-018 — Monthly Body-to-Range Ratio

```text
monthly_body / monthly_range
```

If range is zero, return an explicit null/invalid state.

## 9. Weekly Structure

### F-MKT-019 — Weekly Open
`weekly_open`

### F-MKT-020 — Weekly High
`weekly_high`

### F-MKT-021 — Weekly Low
`weekly_low`

### F-MKT-022 — Weekly Close
`weekly_close`

### F-MKT-023 — Weekly Range
```text
weekly_high - weekly_low
```

### F-MKT-024 — Weekly Range %
```text
(weekly_high - weekly_low) / weekly_low
```

### F-MKT-025 — Weekly Body
```text
abs(weekly_close - weekly_open)
```

### F-MKT-026 — Weekly Body %
```text
abs(weekly_close - weekly_open) / weekly_open
```

### F-MKT-027 — Weekly Upper Wick
```text
weekly_high - max(weekly_open, weekly_close)
```

### F-MKT-028 — Weekly Lower Wick
```text
min(weekly_open, weekly_close) - weekly_low
```

### F-MKT-029 — Weekly Body-to-Range Ratio
```text
weekly_body / weekly_range
```

## 10. Daily Structure

### F-MKT-030 — Daily Open
`daily_open`

### F-MKT-031 — Daily High
`daily_high`

### F-MKT-032 — Daily Low
`daily_low`

### F-MKT-033 — Daily Close
`daily_close`

### F-MKT-034 — Daily Range
```text
daily_high - daily_low
```

### F-MKT-035 — Daily Range %
```text
(daily_high - daily_low) / daily_low
```

### F-MKT-036 — Daily Body
```text
abs(daily_close - daily_open)
```

### F-MKT-037 — Daily Body %
```text
abs(daily_close - daily_open) / daily_open
```

### F-MKT-038 — Daily Upper Wick
```text
daily_high - max(daily_open, daily_close)
```

### F-MKT-039 — Daily Lower Wick
```text
min(daily_open, daily_close) - daily_low
```

### F-MKT-040 — Daily Body-to-Range Ratio
```text
daily_body / daily_range
```

## 11. Price Position

### F-MKT-041 — Monthly Price Position

```text
(last_price - monthly_low)
/
(monthly_high - monthly_low)
```

Conceptual range:

```text
0.00 = Monthly Low
0.50 = middle
1.00 = Monthly High
```

Keep raw value and, if required, a clipped representation.

### F-MKT-042 — Weekly Price Position

```text
(last_price - weekly_low)
/
(weekly_high - weekly_low)
```

### F-MKT-043 — Daily Price Position

```text
(last_price - daily_low)
/
(daily_high - daily_low)
```

## 12. Proximity

### F-MKT-044 — Distance to Monthly Low %

```text
(last_price - monthly_low) / monthly_low
```

Positive = above level.

Negative = below level.

### F-MKT-045 — Distance to Monthly High %

```text
(last_price - monthly_high) / monthly_high
```

### F-MKT-046 — Distance to Weekly Low %
```text
(last_price - weekly_low) / weekly_low
```

### F-MKT-047 — Distance to Weekly High %
```text
(last_price - weekly_high) / weekly_high
```

### F-MKT-048 — Distance to Daily Low %
```text
(last_price - daily_low) / daily_low
```

### F-MKT-049 — Distance to Daily High %
```text
(last_price - daily_high) / daily_high
```

## 13. Volatility-Adjusted Proximity

Concept:

```text
distance_to_level / reference_volatility
```

The exact volatility definition is finalized by the Volatility methodology.

### F-MKT-050
`monthly_low_distance_vol_adjusted`

### F-MKT-051
`monthly_high_distance_vol_adjusted`

### F-MKT-052
`weekly_low_distance_vol_adjusted`

### F-MKT-053
`weekly_high_distance_vol_adjusted`

### F-MKT-054
`daily_low_distance_vol_adjusted`

### F-MKT-055
`daily_high_distance_vol_adjusted`

The denominator MUST be causally available at observation time.

## 14. Monthly Low Context

### F-MKT-056 — Monthly Low Status

Conceptual states:

```text
ABOVE
NEAR
BREAKING
BELOW
RECOVERING
```

Thresholds must be measurable and validated statistically.

`BELOW` does not mean `BAD`.

### F-MKT-057 — Distance Below Monthly Low %

Recommended:

```text
min(
    (last_price - monthly_low) / monthly_low,
    0
)
```

0 = not below.

Negative = percentage below.

### F-MKT-058 — Monthly Low Break Flag

```text
1 = price below selected Monthly Low reference
0 = otherwise
```

The implementation MUST explicitly state whether the reference is:
- current in-progress Monthly Low, or
- previous closed Monthly Low.

These are distinct concepts and should not be conflated.

### F-MKT-059 — Monthly Low Recovery State

Conceptual:

```text
NO_BREAK
BREAKING
BELOW
RECOVERING_ABOVE
```

## 15. Previous Closed Monthly Reference

Stable historical references are useful because the current Monthly candle changes.

### F-MKT-060
`previous_monthly_high`

### F-MKT-061
`previous_monthly_low`

### F-MKT-062
`distance_to_previous_monthly_low_pct`

Formula:

```text
(last_price - previous_monthly_low) / previous_monthly_low
```

### F-MKT-063
`distance_to_previous_monthly_high_pct`

Formula:

```text
(last_price - previous_monthly_high) / previous_monthly_high
```

## 16. Monthly → Weekly Relationships

### F-MKT-064 — Monthly/Weekly Price Position Difference

```text
monthly_price_position - weekly_price_position
```

Purpose: captures relative structural positioning.

### F-MKT-065 — Monthly/Weekly Low Proximity Relationship

Inputs:

```text
distance_to_monthly_low_pct
distance_to_weekly_low_pct
```

Purpose: distinguishes:

```text
Near Monthly Low + Near Weekly Low
```

from:

```text
Near Monthly Low + Mid Weekly Range
```

The final normalization is subject to statistical testing.

## 17. Weekly → Daily Relationships

### F-MKT-066 — Weekly/Daily Price Position Difference

```text
weekly_price_position - daily_price_position
```

### F-MKT-067 — Weekly/Daily Low Proximity Relationship

Compares current proximity to Weekly Low and Daily Low.

## 18. Trend Features

Trend methodology is intentionally not fully locked here. This document defines feature contracts only.

### F-MKT-068
`monthly_trend_direction`

States:

```text
BULLISH
BEARISH
NEUTRAL
```

### F-MKT-069
`weekly_trend_direction`

### F-MKT-070
`daily_trend_direction`

### F-MKT-071
`monthly_trend_strength`

Conceptual range:

```text
0.0 - 1.0
```

### F-MKT-072
`weekly_trend_strength`

### F-MKT-073
`daily_trend_strength`

### F-MKT-074 — Trend Alignment

Combines Monthly, Weekly, and Daily trend context.

Conceptual states:

```text
ALIGNED_BULLISH
ALIGNED_BEARISH
MIXED
CORRECTIVE
COUNTER_TREND
NEUTRAL
```

Final taxonomy must be validated.

Trend is context, not an automatic trade blocker.

## 19. Volatility Features

Exact volatility methodology remains a separate decision.

### F-MKT-075
`current_volatility`

### F-MKT-076
`monthly_volatility`

### F-MKT-077
`weekly_volatility`

### F-MKT-078
`daily_volatility`

### F-MKT-079 — Volatility Regime

Conceptual:

```text
LOW
NORMAL
HIGH
EXTREME
```

Thresholds should preferably be derived from historical distributions.

### F-MKT-080 — Volatility Expansion

Captures whether current volatility is increasing relative to its baseline.

### F-MKT-081 — Volatility Compression

Captures whether current volatility is decreasing relative to its baseline.

## 20. Structural Pressure

### F-MKT-082 — Multi-Timeframe Low Pressure

Inputs:

```text
Monthly low proximity
Weekly low proximity
Daily low proximity
```

Concept:

```text
Monthly proximity
+
Weekly proximity
+
Daily proximity
```

Conceptual states:

```text
LOW
MEDIUM
HIGH
EXTREME
```

This is a derived market-state feature, not a trading signal.

### F-MKT-083 — Multi-Timeframe High Pressure

Equivalent for highs.

### F-MKT-084 — Structural Alignment State

Combines Monthly, Weekly, and Daily structural context.

Conceptual:

```text
ALIGNED
MIXED
TRANSITION
```

## 21. Refinement Priority

These features explicitly encode the hierarchical-resolution principle.

### F-MKT-085 — Monthly Context Priority

Conceptual:

```text
MONTHLY_DOMINANT
MONTHLY_REFINEMENT_REQUIRED
```

Driven by measurable proximity/structure rules.

### F-MKT-086 — Weekly Refinement Priority

Conceptual:

```text
LOW
MEDIUM
HIGH
```

Inputs may include:
- Monthly proximity
- Weekly structure
- Current price
- Volatility

### F-MKT-087 — Daily Refinement Priority

Conceptual:

```text
LOW
MEDIUM
HIGH
```

Purpose: represents required operational resolution of Daily context.

## 22. Feature Availability

Every feature must have a causal availability timestamp.

At any time `T`, only information available at or before `T` may be used.

Current Monthly/Weekly/Daily High/Low may be used as **in-progress** values only if the observation actually had access to them at that timestamp.

Future candle close, future high/low, future volatility, future trend, and future execution results are prohibited.

## 23. Normalization

Raw price must not be the only representation used for cross-market ML.

Preferred normalized representations:

```text
Percentage Distance
Range Position
Volatility-Adjusted Distance
Percentage Range
Body-to-Range Ratio
Relative Change
```

## 24. Missing Data

Missing values MUST NOT silently become zero.

Preferred representation:

```text
value
availability_flag
```

Example:

```text
best_bid = null
best_bid_available = false
```

## 25. Update Frequency

Realtime:

```text
last_price
best_bid
best_ask
mid_price
price_position
proximity
monthly_low_status
monthly_low_break_status
```

Candle updates:

```text
Monthly
Weekly
Daily
```

Derived context such as trend, volatility regime, structural pressure, and refinement priority may update on configurable intervals, but timestamps must remain aligned.

## 26. Historical Training Policy

A feature can be used for training only when the historical pipeline can reconstruct exactly what would have been known at that time.

This is more important than dataset size.

## 27. Leakage Rules

LOW risk examples:
- historical closed Monthly High
- current timestamped last price
- past candle range

MEDIUM risk examples:
- current in-progress Monthly High
- trend state
- volatility regime

HIGH risk and prohibited:
- future candle close
- future candle high/low
- future volatility
- future trend state
- future strategy outcome

## 28. Canonical Market State Object

Conceptual output:

```text
MarketState
│
├── identity
│   ├── market_id
│   ├── exchange_id
│   └── observation_timestamp
│
├── realtime
│   ├── last_price
│   ├── best_bid
│   ├── best_ask
│   └── mid_price
│
├── monthly
├── weekly
├── daily
│
├── position
│   ├── monthly_price_position
│   ├── weekly_price_position
│   └── daily_price_position
│
├── proximity
│   ├── monthly_high
│   ├── monthly_low
│   ├── weekly_high
│   ├── weekly_low
│   ├── daily_high
│   └── daily_low
│
├── monthly_low_context
│   ├── status
│   ├── break_flag
│   ├── distance_below
│   └── recovery_state
│
├── trend
│   ├── monthly
│   ├── weekly
│   ├── daily
│   └── alignment
│
├── volatility
│   ├── current
│   ├── monthly
│   ├── weekly
│   ├── daily
│   ├── regime
│   ├── expansion
│   └── compression
│
└── structural_context
    ├── monthly_weekly_relationship
    ├── weekly_daily_relationship
    ├── low_pressure
    ├── high_pressure
    ├── structural_alignment
    ├── monthly_context_priority
    ├── weekly_refinement_priority
    └── daily_refinement_priority
```

## 29. Current Feature Inventory

```text
F-MKT-001  market_id
F-MKT-002  exchange_id
F-MKT-003  observation_timestamp

F-MKT-004  last_price
F-MKT-005  best_bid
F-MKT-006  best_ask
F-MKT-007  mid_price

F-MKT-008  monthly_open
F-MKT-009  monthly_high
F-MKT-010  monthly_low
F-MKT-011  monthly_close
F-MKT-012  monthly_range
F-MKT-013  monthly_range_pct
F-MKT-014  monthly_body
F-MKT-015  monthly_body_pct
F-MKT-016  monthly_upper_wick
F-MKT-017  monthly_lower_wick
F-MKT-018  monthly_body_to_range

F-MKT-019  weekly_open
F-MKT-020  weekly_high
F-MKT-021  weekly_low
F-MKT-022  weekly_close
F-MKT-023  weekly_range
F-MKT-024  weekly_range_pct
F-MKT-025  weekly_body
F-MKT-026  weekly_body_pct
F-MKT-027  weekly_upper_wick
F-MKT-028  weekly_lower_wick
F-MKT-029  weekly_body_to_range

F-MKT-030  daily_open
F-MKT-031  daily_high
F-MKT-032  daily_low
F-MKT-033  daily_close
F-MKT-034  daily_range
F-MKT-035  daily_range_pct
F-MKT-036  daily_body
F-MKT-037  daily_body_pct
F-MKT-038  daily_upper_wick
F-MKT-039  daily_lower_wick
F-MKT-040  daily_body_to_range

F-MKT-041  monthly_price_position
F-MKT-042  weekly_price_position
F-MKT-043  daily_price_position

F-MKT-044  distance_to_monthly_low_pct
F-MKT-045  distance_to_monthly_high_pct
F-MKT-046  distance_to_weekly_low_pct
F-MKT-047  distance_to_weekly_high_pct
F-MKT-048  distance_to_daily_low_pct
F-MKT-049  distance_to_daily_high_pct

F-MKT-050  monthly_low_distance_vol_adjusted
F-MKT-051  monthly_high_distance_vol_adjusted
F-MKT-052  weekly_low_distance_vol_adjusted
F-MKT-053  weekly_high_distance_vol_adjusted
F-MKT-054  daily_low_distance_vol_adjusted
F-MKT-055  daily_high_distance_vol_adjusted

F-MKT-056  monthly_low_status
F-MKT-057  distance_below_monthly_low_pct
F-MKT-058  monthly_low_break_flag
F-MKT-059  monthly_low_recovery_state

F-MKT-060  previous_monthly_high
F-MKT-061  previous_monthly_low
F-MKT-062  distance_to_previous_monthly_low_pct
F-MKT-063  distance_to_previous_monthly_high_pct

F-MKT-064  monthly_weekly_price_position_difference
F-MKT-065  monthly_weekly_low_proximity_relationship
F-MKT-066  weekly_daily_price_position_difference
F-MKT-067  weekly_daily_low_proximity_relationship

F-MKT-068  monthly_trend_direction
F-MKT-069  weekly_trend_direction
F-MKT-070  daily_trend_direction
F-MKT-071  monthly_trend_strength
F-MKT-072  weekly_trend_strength
F-MKT-073  daily_trend_strength
F-MKT-074  trend_alignment

F-MKT-075  current_volatility
F-MKT-076  monthly_volatility
F-MKT-077  weekly_volatility
F-MKT-078  daily_volatility
F-MKT-079  volatility_regime
F-MKT-080  volatility_expansion
F-MKT-081  volatility_compression

F-MKT-082  multi_timeframe_low_pressure
F-MKT-083  multi_timeframe_high_pressure
F-MKT-084  structural_alignment_state

F-MKT-085  monthly_context_priority
F-MKT-086  weekly_refinement_priority
F-MKT-087  daily_refinement_priority
```

## 30. Boundary With Other Feature Layers

Market State MUST remain separate from:

```text
AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md
AI_RESEARCH_FEATURE_SPEC_GRID_BEHAVIOR.md
AI_RESEARCH_FEATURE_SPEC_DERIVED_ML.md
```

Market State describes the market.

Execution Economics describes the cost of immediate execution.

Grid Behavior describes how the market behaved under our strategy.

Derived ML Features combine upstream information for modeling.

## 31. Final Definition

Market State is the canonical, causally reconstructable representation of:

```text
Monthly Structure
+
Weekly Structure
+
Daily Structure
+
Realtime Price
+
Price Position
+
Proximity
+
Monthly Breakdown Context
+
Trend
+
Volatility
+
Multi-Timeframe Relationships
+
Structural Pressure
```

The strategy-specific principle remains:

```text
Monthly Context
     ↓
Realtime Price Proximity
     ↓
Weekly Refinement
     ↓
Daily Refinement
     ↓
Market State
```

A Monthly Low breach is a market state, not an automatic failure state.

The purpose of this layer is to provide clean, measurable, versionable market information to the next research stages.
