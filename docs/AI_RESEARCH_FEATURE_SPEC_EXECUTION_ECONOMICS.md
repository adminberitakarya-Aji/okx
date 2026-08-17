# AI Research Feature Specification — Execution Economics

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`
- `AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md`

Purpose:

This document defines the **Execution Economics Feature Layer** for AI Research.

The layer answers:

> **Is this market economically suitable for our immediate-execution Grid Strategy after accounting for the real cost of BUY and SELL execution?**

The Grid Strategy uses immediate execution for both BUY and SELL. Therefore, execution economics is a first-class part of market research.

---

# 1. Scope

Execution Economics contains:

```text
Market Microstructure
Liquidity
Fee Model
Buy-Side Economics
Sell-Side Economics
Slippage
Spread Economics
Round-Trip Economics
Break-Even
Minimum Profitable Exit
Grid Economic Viability
Stress Execution Economics
Execution Burden
```

This layer MUST NOT contain:

- Monthly/Weekly/Daily market-state interpretation
- Trend classification
- Historical Grid P&L
- Section activation history
- Capital utilization caused by the strategy
- ML recommendation
- Direct trading commands

Those belong to other layers.

---

# 2. Core Principle

The strategy does not use passive limit-order queuing.

The execution model is:

```text
BUY
  ↓
Immediate Execution
  ↓
Position
  ↓
SELL
  ↓
Immediate Execution
```

Therefore:

```text
BUY COST
+
BUY FEE
+
BUY SLIPPAGE

AND

SELL COST
+
SELL FEE
+
SELL SLIPPAGE
```

must be evaluated together.

The economic question is not:

> Is Sell Price higher than Buy Price?

It is:

> Is the expected or realized Net P&L positive after the complete round-trip execution economics?

---

# 3. Critical Accounting Rule

The system must avoid double-counting spread and slippage.

Two representations may be used.

## Accounting View

```text
NET P&L
=
SELL PROCEEDS
− BUY COST
− BUY FEE
− SELL COST
− SELL FEE
− SPREAD COST
− SLIPPAGE COST
− OTHER EXECUTION COSTS
```

## Execution Model View

```text
Effective Buy Cost
=
Buy Execution Value
+
Buy Fee
+
Other Buy Costs

Effective Sell Proceeds
=
Sell Execution Value
− Sell Fee
− Other Sell Costs

NET P&L
=
Effective Sell Proceeds
− Effective Buy Cost
```

If spread/slippage are already incorporated into the actual execution prices or price-impact model, they MUST NOT be subtracted again.

This rule is mandatory.

---

# 4. Feature Contract Standard

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
Timeframe / Window
Update Frequency
Historical Availability
Training Availability
Inference Availability
Leakage Risk
Purpose
Notes
```

Naming convention:

```text
F-EXE-xxx
```

Field names:

```text
snake_case
```

---

# 5. Market Microstructure

## F-EXE-001 — Bid Price

```text
bid_price
```

Source:

Current best bid.

Type:

float.

Update:

Realtime.

Purpose:

Reference for immediate sell economics.

---

## F-EXE-002 — Ask Price

```text
ask_price
```

Source:

Current best ask.

Type:

float.

Update:

Realtime.

Purpose:

Reference for immediate buy economics.

---

## F-EXE-003 — Spread Absolute

```text
spread_absolute
```

Formula:

```text
ask_price - bid_price
```

Purpose:

Absolute bid/ask difference.

---

## F-EXE-004 — Spread Percentage

```text
spread_pct
```

Recommended formula:

```text
(ask_price - bid_price)
/
((ask_price + bid_price) / 2)
```

Purpose:

Makes spread comparable across markets.

---

## F-EXE-005 — Mid Price

```text
mid_price
```

Formula:

```text
(best_bid + best_ask) / 2
```

This duplicates a Market State reference intentionally because the value is essential to execution economics.

Canonical storage may reference the Market State value rather than duplicate physical data.

---

# 6. Liquidity

## F-EXE-006 — Top-of-Book Bid Depth

```text
bid_depth_top
```

Purpose:

Available quantity at best bid.

---

## F-EXE-007 — Top-of-Book Ask Depth

```text
ask_depth_top
```

Purpose:

Available quantity at best ask.

---

## F-EXE-008 — Depth Near Price

```text
depth_near_price
```

Purpose:

Measures executable liquidity within a defined price band.

The price band must be deterministic and documented.

---

## F-EXE-009 — Recent Volume

```text
recent_volume
```

Purpose:

Recent trading activity.

Volume must not be treated as identical to liquidity.

---

## F-EXE-010 — Liquidity Score

```text
liquidity_score
```

Concept:

Normalized representation of executable liquidity.

The exact scoring methodology remains open for technical implementation.

Purpose:

Provides a standardized liquidity factor for cross-market comparison.

---

# 7. Fee Model

The fee model must distinguish BUY and SELL.

## F-EXE-011 — Buy Fee Rate

```text
buy_fee_rate
```

Type:

float.

Representation:

Decimal percentage.

Example:

```text
0.002 = 0.20%
```

---

## F-EXE-012 — Sell Fee Rate

```text
sell_fee_rate
```

---

## F-EXE-013 — Estimated Buy Fee

```text
estimated_buy_fee
```

Concept:

```text
Buy Notional × Buy Fee Rate
```

---

## F-EXE-014 — Estimated Sell Fee

```text
estimated_sell_fee
```

Concept:

```text
Sell Notional × Sell Fee Rate
```

Actual formula depends on provider fee mechanics.

---

# 8. Buy-Side Economics

Immediate BUY means the system must estimate the actual cost of acquiring the asset.

## F-EXE-015 — Buy Notional

```text
buy_notional
```

Represents the amount of capital committed to the BUY.

---

## F-EXE-016 — Estimated Buy Execution Price

```text
estimated_buy_execution_price
```

Concept:

```text
Expected average fill price for the BUY
```

It may differ from best ask because of:

- Order size
- Order-book depth
- Price impact
- Slippage
- Market conditions

---

## F-EXE-017 — Buy Slippage Percentage

```text
estimated_buy_slippage_pct
```

Concept:

```text
(estimated_buy_execution_price - reference_buy_price)
/
reference_buy_price
```

For immediate market BUY, the reference is normally the best ask or another explicitly defined benchmark.

---

## F-EXE-018 — Buy Slippage Cost

```text
estimated_buy_slippage_cost
```

Concept:

```text
estimated_buy_execution_price
− reference_buy_price
```

or the equivalent notional impact.

The implementation must define whether this is:

```text
per unit
or
total notional
```

Both can be represented if needed.

---

## F-EXE-019 — Effective Buy Cost

```text
effective_buy_cost
```

Concept:

```text
Buy Execution Value
+
Buy Fee
+
Other Buy Costs
```

If slippage is already reflected in the Buy Execution Value, it MUST NOT be added again.

---

## F-EXE-020 — Effective Buy Cost Percentage

```text
effective_buy_cost_pct
```

Measures total buy-side execution burden relative to a reference capital amount.

---

# 9. Sell-Side Economics

Immediate SELL must be modeled independently.

## F-EXE-021 — Sell Notional

```text
sell_notional
```

Represents the intended value of the SELL.

---

## F-EXE-022 — Estimated Sell Execution Price

```text
estimated_sell_execution_price
```

Expected average fill price for immediate SELL.

---

## F-EXE-023 — Sell Slippage Percentage

```text
estimated_sell_slippage_pct
```

Concept:

```text
(reference_sell_price - estimated_sell_execution_price)
/
reference_sell_price
```

For immediate market SELL, the reference is normally the best bid or another explicitly defined benchmark.

---

## F-EXE-024 — Sell Slippage Cost

```text
estimated_sell_slippage_cost
```

Represents the economic impact of sell-side price impact/slippage.

---

## F-EXE-025 — Effective Sell Proceeds

```text
effective_sell_proceeds
```

Concept:

```text
Sell Execution Value
− Sell Fee
− Other Sell Costs
```

If the execution price already includes slippage/price impact, slippage MUST NOT be subtracted again.

---

## F-EXE-026 — Effective Sell Proceeds Percentage

```text
effective_sell_proceeds_pct
```

Represents the economic value retained after sell-side execution costs.

---

# 10. Sell Cost Definition

The term "Sell Cost" must not remain ambiguous.

For technical accounting, separate:

```text
sell_notional
sell_fee
sell_slippage_cost
other_sell_cost
```

Therefore:

```text
Sell Proceeds
```

represents transaction value received before applicable deductions.

```text
Sell Costs
```

represent the deductions required to turn gross transaction value into effective sell proceeds.

This prevents the same value from being subtracted multiple times.

---

# 11. Round-Trip Economics

A Grid cycle is economically meaningful only after both sides are considered.

```text
BUY
  ↓
POSITION
  ↓
SELL
```

## F-EXE-027 — Round-Trip Fee

Concept:

```text
Estimated Buy Fee
+
Estimated Sell Fee
```

---

## F-EXE-028 — Round-Trip Execution Cost

Concept:

```text
Buy-side execution burden
+
Sell-side execution burden
+
Other round-trip costs
```

The implementation must avoid double-counting.

---

## F-EXE-029 — Expected Gross Move

```text
expected_gross_move
```

Represents expected price movement between entry and exit before execution costs.

This is an input from market/strategy context and may later be supplied by other research engines.

---

## F-EXE-030 — Expected Net Move

Concept:

```text
Expected Gross Move
− Expected Round-Trip Cost
```

Purpose:

Estimates remaining economic movement after immediate-execution costs.

---

## F-EXE-031 — Expected Net P&L

Concept:

```text
Expected Effective Sell Proceeds
− Expected Effective Buy Cost
```

This is the primary round-trip economics metric.

---

# 12. Break-Even

## F-EXE-032 — Break-Even Price

The minimum expected sell price at which:

```text
Net P&L = 0
```

after applicable costs.

Break-even must use the execution model rather than a simplistic percentage addition.

---

## F-EXE-033 — Minimum Profitable Exit

The minimum exit price required for:

```text
Net P&L > 0
```

The threshold may include a configurable minimum-profit requirement.

Example:

```text
Break-even = $100.60

Minimum Profit Requirement = $0.20

Minimum Profitable Exit = $100.80
```

---

## F-EXE-034 — Required Gross Movement

Minimum gross price movement required for positive economics.

Concept:

```text
Required Gross Move
=
Round-Trip Costs
+
Minimum Desired Net Profit
```

This becomes important for grid spacing analysis.

---

# 13. Execution Cost Ratio

## F-EXE-035 — Execution Cost Ratio

Concept:

```text
Expected Round-Trip Execution Cost
/
Expected Gross Movement
```

Example:

```text
Expected Move = 1.50%
Execution Cost = 0.30%

Ratio = 20%
```

Interpretation:

20% of expected gross movement is consumed by execution cost.

The ratio should preferably be represented as a continuous value.

---

# 14. Execution Burden

Execution Burden decomposes total cost impact.

## F-EXE-036 — Fee Burden Ratio

```text
Total Fees
/
Expected Gross Opportunity
```

---

## F-EXE-037 — Spread Burden Ratio

```text
Spread-related cost
/
Expected Gross Opportunity
```

---

## F-EXE-038 — Slippage Burden Ratio

```text
Expected Slippage Cost
/
Expected Gross Opportunity
```

---

## F-EXE-039 — Total Execution Burden Ratio

Concept:

```text
Total Execution Costs
/
Expected Gross Opportunity
```

This is one of the most valuable cross-market comparison features.

---

# 15. Grid Economic Viability

The system must determine whether the expected price movement can economically support an immediate-execution grid cycle.

## F-EXE-040 — Expected Grid Movement

Represents expected gross price movement relevant to the candidate grid configuration.

---

## F-EXE-041 — Expected Grid Round-Trip Cost

Represents expected total execution burden for one complete:

```text
BUY → SELL
```

cycle.

---

## F-EXE-042 — Expected Grid Net Opportunity

Concept:

```text
Expected Grid Movement
− Expected Grid Round-Trip Cost
```

---

## F-EXE-043 — Grid Economic Viability

Conceptual states:

```text
NOT_VIABLE
MARGINAL
VIABLE
STRONG
```

This is a derived economic state, not an ML prediction.

The final thresholds require historical validation.

---

# 16. Grid Spacing Economic Threshold

Because grid spacing inside each Section is uniform, its economic viability is important.

A candidate Section spacing must satisfy:

```text
Expected Gross Grid Movement
>
Expected Round-Trip Execution Cost
```

Preferably:

```text
Expected Net Opportunity
>
Minimum Required Net Opportunity
```

This feature layer does not choose the final Section grid spacing.

It provides the economics needed by the Blueprint and Grid Optimization layers.

---

# 17. Stress Execution Economics

Execution costs are not constant.

The system should evaluate scenarios.

Conceptual conditions:

```text
NORMAL
HIGH_VOLATILITY
LOW_LIQUIDITY
STRESS
EXTREME
```

---

## F-EXE-044 — Normal Execution Cost

Expected execution cost under normal conditions.

---

## F-EXE-045 — Stress Execution Cost

Expected execution cost under elevated volatility/liquidity stress.

---

## F-EXE-046 — Extreme Execution Cost

Expected execution cost under severe execution conditions.

The exact stress model is implementation-dependent.

---

## F-EXE-047 — Execution Cost Stress Multiplier

Concept:

```text
Stress Execution Cost
/
Normal Execution Cost
```

Purpose:

Measures sensitivity of economics to execution deterioration.

---

# 18. Slippage Model Inputs

Slippage should not be treated as a fixed constant.

Conceptually:

```text
Order Size
+
Liquidity
+
Depth
+
Volatility
+
Execution Side
+
Market Condition
        ↓
Expected Slippage
```

---

## F-EXE-048 — Buy Order Size

```text
buy_order_size
```

---

## F-EXE-049 — Sell Order Size

```text
sell_order_size
```

---

## F-EXE-050 — Buy Order Size / Liquidity Ratio

Concept:

```text
Buy Order Size
/
Relevant Available Liquidity
```

---

## F-EXE-051 — Sell Order Size / Liquidity Ratio

Equivalent for SELL.

These features help explain why the same market can produce different slippage for different capital sizes.

---

# 19. Execution Price Impact

## F-EXE-052 — Expected Buy Price Impact

Expected movement from reference buy price to average immediate execution price.

---

## F-EXE-053 — Expected Sell Price Impact

Expected movement from reference sell price to average immediate execution price.

---

## F-EXE-054 — Execution Impact Asymmetry

Concept:

```text
Buy Price Impact
vs
Sell Price Impact
```

Purpose:

Captures whether execution conditions differ materially by side.

---

# 20. Liquidity Stress

## F-EXE-055 — Liquidity Stress Score

Measures deterioration of executable liquidity relative to normal conditions.

Conceptual states:

```text
LOW
NORMAL
HIGH
EXTREME
```

Exact calculation remains open.

---

## F-EXE-056 — Spread Stress

Measures spread expansion relative to normal spread.

Concept:

```text
Current Spread
/
Historical/Normal Spread
```

---

# 21. Economic Opportunity Margin

This is a highly important derived feature.

## F-EXE-057 — Economic Opportunity Margin

Concept:

```text
Expected Gross Opportunity
− Total Expected Execution Cost
```

It can be represented in:

```text
absolute value
percentage
```

Purpose:

Measures how much economic room remains after execution.

---

## F-EXE-058 — Economic Opportunity Margin %

Concept:

```text
Expected Net Opportunity
/
Expected Gross Opportunity
```

Example:

```text
Gross = 1.50%
Cost = 0.30%

Net Opportunity = 1.20%
Margin = 80%
```

---

# 22. Execution Quality

## F-EXE-059 — Execution Quality Score

A normalized research feature combining:

```text
Spread
Liquidity
Slippage
Depth
Execution Cost
```

This is not the final Market Recommendation score.

It is an execution-specific quality measure.

---

## F-EXE-060 — Execution Cost Stability

Measures how stable execution costs are over a research window.

A market with:

```text
Average cost = low
Variance = very high
```

may be less attractive than a market with:

```text
Average cost = slightly higher
Variance = low
```

This feature allows ML to learn that distinction.

---

# 23. Historical Execution Economics

The research system can maintain historical statistics for execution conditions.

## F-EXE-061 — Historical Average Buy Slippage

---

## F-EXE-062 — Historical Average Sell Slippage

---

## F-EXE-063 — Historical Average Spread

---

## F-EXE-064 — Historical Average Round-Trip Cost

---

## F-EXE-065 — Historical Execution Cost Volatility

These are research features only when calculated strictly from data available before the observation being predicted.

---

# 24. Market-Specific Execution Context

Execution economics must remain market-specific.

For example:

```text
BTC/USDT
```

and:

```text
LOW-LIQUIDITY-ALT/USDT
```

may have the same nominal fee but dramatically different:

```text
Spread
Liquidity
Slippage
Price Impact
```

Therefore fee alone must never be used as a complete execution-cost proxy.

---

# 25. Immediate Execution Economics Workflow

```text
MARKET DATA
     |
     v
BID / ASK
     |
     v
SPREAD
     |
     v
LIQUIDITY / DEPTH
     |
     v
ORDER SIZE
     |
     v
EXPECTED PRICE IMPACT
     |
     v
BUY ECONOMICS
     |
     v
SELL ECONOMICS
     |
     v
ROUND-TRIP COST
     |
     v
BREAK-EVEN
     |
     v
EXPECTED NET OPPORTUNITY
     |
     v
GRID ECONOMIC VIABILITY
```

---

# 26. Provider Independence

This feature layer must be provider-independent.

Provider adapters may supply:

```text
Fee Schedule
Order Book
Market Rules
Execution Reports
```

The internal normalized layer should expose:

```text
buy_fee_rate
sell_fee_rate
bid_price
ask_price
depth
estimated_slippage
```

The strategy and ML systems should not depend directly on provider-specific API semantics.

---

# 27. Historical Integrity

Execution Economics features must obey the same causal reconstruction rules as Market State.

At historical observation time `T`, only execution information available at or before `T` may be used.

Prohibited:

```text
Future spread
Future slippage
Future liquidity
Future execution result
Future fee change
```

unless the research experiment explicitly models a known scheduled future parameter.

---

# 28. Missing Data

Missing liquidity/depth/slippage information MUST NOT silently become zero.

Recommended:

```text
feature_value
availability_flag
```

Example:

```text
estimated_buy_slippage_pct = null
buy_slippage_available = false
```

The model should know the difference between:

```text
zero slippage
```

and:

```text
slippage unknown
```

---

# 29. Execution Economics Output Object

Conceptually:

```text
ExecutionEconomics
│
├── microstructure
│   ├── bid
│   ├── ask
│   ├── mid
│   └── spread
│
├── liquidity
│   ├── top_of_book_depth
│   ├── depth_near_price
│   └── liquidity_score
│
├── fees
│   ├── buy_fee_rate
│   ├── sell_fee_rate
│   ├── estimated_buy_fee
│   └── estimated_sell_fee
│
├── buy
│   ├── notional
│   ├── estimated_execution_price
│   ├── slippage_pct
│   ├── slippage_cost
│   └── effective_cost
│
├── sell
│   ├── notional
│   ├── estimated_execution_price
│   ├── slippage_pct
│   ├── slippage_cost
│   └── effective_proceeds
│
├── round_trip
│   ├── total_fee
│   ├── total_execution_cost
│   ├── expected_gross_move
│   ├── expected_net_move
│   └── expected_net_pnl
│
├── break_even
│   ├── break_even_price
│   ├── minimum_profitable_exit
│   └── required_gross_move
│
├── viability
│   ├── execution_cost_ratio
│   ├── economic_opportunity_margin
│   └── grid_economic_viability
│
└── stress
    ├── normal
    ├── stress
    ├── extreme
    └── stress_multiplier
```

---

# 30. Boundary With Other Feature Layers

Execution Economics is separate from Market State.

```text
MARKET STATE
What is happening?
```

Execution Economics:

```text
What will it cost to execute immediately?
```

Grid Behavior:

```text
How did our Grid Strategy behave?
```

Derived ML:

```text
What useful relationships can be derived from all upstream layers?
```

---

# 31. Final Feature Inventory

```text
F-EXE-001  bid_price
F-EXE-002  ask_price
F-EXE-003  spread_absolute
F-EXE-004  spread_pct
F-EXE-005  mid_price

F-EXE-006  bid_depth_top
F-EXE-007  ask_depth_top
F-EXE-008  depth_near_price
F-EXE-009  recent_volume
F-EXE-010  liquidity_score

F-EXE-011  buy_fee_rate
F-EXE-012  sell_fee_rate
F-EXE-013  estimated_buy_fee
F-EXE-014  estimated_sell_fee

F-EXE-015  buy_notional
F-EXE-016  estimated_buy_execution_price
F-EXE-017  estimated_buy_slippage_pct
F-EXE-018  estimated_buy_slippage_cost
F-EXE-019  effective_buy_cost
F-EXE-020  effective_buy_cost_pct

F-EXE-021  sell_notional
F-EXE-022  estimated_sell_execution_price
F-EXE-023  estimated_sell_slippage_pct
F-EXE-024  estimated_sell_slippage_cost
F-EXE-025  effective_sell_proceeds
F-EXE-026  effective_sell_proceeds_pct

F-EXE-027  round_trip_fee
F-EXE-028  round_trip_execution_cost
F-EXE-029  expected_gross_move
F-EXE-030  expected_net_move
F-EXE-031  expected_net_pnl

F-EXE-032  break_even_price
F-EXE-033  minimum_profitable_exit
F-EXE-034  required_gross_move

F-EXE-035  execution_cost_ratio
F-EXE-036  fee_burden_ratio
F-EXE-037  spread_burden_ratio
F-EXE-038  slippage_burden_ratio
F-EXE-039  total_execution_burden_ratio

F-EXE-040  expected_grid_movement
F-EXE-041  expected_grid_round_trip_cost
F-EXE-042  expected_grid_net_opportunity
F-EXE-043  grid_economic_viability

F-EXE-044  normal_execution_cost
F-EXE-045  stress_execution_cost
F-EXE-046  extreme_execution_cost
F-EXE-047  execution_cost_stress_multiplier

F-EXE-048  buy_order_size
F-EXE-049  sell_order_size
F-EXE-050  buy_order_size_liquidity_ratio
F-EXE-051  sell_order_size_liquidity_ratio

F-EXE-052  expected_buy_price_impact
F-EXE-053  expected_sell_price_impact
F-EXE-054  execution_impact_asymmetry

F-EXE-055  liquidity_stress_score
F-EXE-056  spread_stress

F-EXE-057  economic_opportunity_margin
F-EXE-058  economic_opportunity_margin_pct

F-EXE-059  execution_quality_score
F-EXE-060  execution_cost_stability

F-EXE-061  historical_average_buy_slippage
F-EXE-062  historical_average_sell_slippage
F-EXE-063  historical_average_spread
F-EXE-064  historical_average_round_trip_cost
F-EXE-065  historical_execution_cost_volatility
```

---

# 32. Non-Negotiable Rules

1. BUY and SELL execution economics are modeled independently.
2. Buy Cost and Sell Cost remain explicitly distinguishable.
3. Buy Fee and Sell Fee are separate features.
4. Immediate execution must be assumed when evaluating the Grid Strategy.
5. Spread and slippage must never be double-counted.
6. Net P&L is the economic truth.
7. Sell Price > Buy Price does not automatically mean profit.
8. Execution cost must be compared with expected gross movement.
9. High volatility does not automatically mean high Grid suitability.
10. High volume does not automatically mean good execution liquidity.
11. Missing execution data must not be silently interpreted as zero cost.
12. Historical execution features must obey causal time alignment.
13. Execution Economics provides economics; it does not make the final Market Recommendation.
14. The final strategy still passes through deterministic calculation and risk validation.

---

# 33. Final Definition

Execution Economics is:

> **The feature layer that measures the real economic cost and viability of immediate BUY/SELL execution, including liquidity, spread, fees, slippage, price impact, round-trip cost, break-even, and expected Net P&L, so AI Research can distinguish markets that merely move from markets that move economically for the Grid Strategy.**

Its central logic is:

```text
Market Movement
      +
Immediate Execution
      ↓
Actual Economic Cost
      ↓
Break-Even
      ↓
Net Opportunity
      ↓
Grid Economic Viability
```

This layer feeds AI Research and later Derived ML Features, but does not itself execute trades or directly change the production Grid Strategy.
