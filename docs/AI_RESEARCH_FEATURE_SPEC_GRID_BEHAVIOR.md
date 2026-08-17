# AI Research Feature Specification — Grid Behavior

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`
- `AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md`
- `AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md`

---

# 1. Purpose

This document defines the **Grid Behavior Feature Layer** for AI Research.

The layer describes how a market behaves when the actual Grid Strategy is applied to it.

It answers:

> **How does this market interact with our Section-based, uniform-grid, adaptive-gap, immediate-execution Grid Strategy?**

This layer is distinct from:

```text
Market State
→ What is happening in the market?

Execution Economics
→ What will immediate execution cost?

Grid Behavior
→ What happens when our Grid Strategy is applied?
```

---

# 2. Core Strategy Model

The Grid Strategy has the following structure:

```text
GRID STRATEGY
│
├── SECTION 1
│   ├── Uniform Grid Spacing
│   ├── Capital Allocation
│   └── Price Range
│
├── SECTION 2
│   ├── Uniform Grid Spacing
│   ├── Capital Allocation
│   └── Price Range
│
└── SECTION N
    ├── Uniform Grid Spacing
    ├── Capital Allocation
    └── Price Range

Section Gap:
Adaptive between Sections
```

Execution:

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

Grid Behavior features must reproduce this actual strategy model during historical simulation.

---

# 3. Scope

Grid Behavior contains:

```text
Grid Opportunity
Grid Hit Frequency
Grid Cycle Frequency
BUY Behavior
SELL Behavior
Section Activation
Section Depth
Capital Deployment
Capital Utilization
Exposure
Coin Accumulation
Average Acquisition
Drawdown
Recovery
Grid Completion
Net Strategy Outcomes
Historical Strategy Stability
```

This layer MUST NOT directly redefine:

- Monthly/Weekly/Daily market structure
- Trend methodology
- Execution fee schedule
- Raw spread
- Raw slippage
- Production trading rules

Those belong to other layers.

---

# 4. Critical Principle

Grid Behavior features must describe **observed or simulated strategy behavior**, not generic market assumptions.

The feature pipeline is:

```text
Market State
+
Execution Economics
+
Candidate Grid Blueprint
        ↓
Historical Grid Simulation
        ↓
Grid Behavior
```

Therefore every Grid Behavior observation must identify:

```text
Market
Observation Time
Blueprint Version
Grid Configuration
Simulation Window
```

This is mandatory for reproducibility.

---

# 5. Blueprint Context

A Grid Behavior feature is meaningless without knowing which Grid Blueprint produced it.

Minimum blueprint context:

```text
section_count
capital_allocation_by_section
grid_count_by_section
uniform_grid_spacing_by_section
section_gap_by_section
price_range_by_section
```

The actual blueprint parameters are not all necessarily ML features themselves; they are required context for interpreting outcomes.

---

# 6. Feature Contract Standard

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
Timeframe / Simulation Window
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
F-GRD-xxx
```

Field names:

```text
snake_case
```

---

# 7. Grid Opportunity

## F-GRD-001 — Grid Opportunity Frequency

Measures how often market movement creates a condition relevant to the candidate Grid Blueprint.

Concept:

```text
eligible_grid_events
/
observation_or_simulation_window
```

Purpose:

Determines whether the market frequently provides opportunities for the grid structure.

---

## F-GRD-002 — Grid Event Count

```text
grid_event_count
```

Number of eligible grid events during the simulation window.

---

## F-GRD-003 — Grid Opportunity Density

Concept:

```text
grid_event_count
/
time_window
```

Purpose:

Normalizes opportunity frequency across research windows.

---

# 8. Grid Trigger / Hit Behavior

The system must distinguish between:

```text
Grid level reached
```

and:

```text
Grid trade actually executed
```

because immediate execution still depends on strategy conditions and risk/economic validation.

## F-GRD-004 — Grid Level Touch Count

Number of times candidate grid levels were reached.

---

## F-GRD-005 — Grid Execution Trigger Count

Number of times grid conditions resulted in an execution event.

---

## F-GRD-006 — Grid Trigger Rate

Concept:

```text
grid_execution_trigger_count
/
grid_level_touch_count
```

Purpose:

Measures how often reached levels become actual strategy events.

---

# 9. BUY Behavior

## F-GRD-007 — Buy Event Count

Number of executed BUY events.

---

## F-GRD-008 — Buy Frequency

```text
buy_event_count
/
simulation_window
```

---

## F-GRD-009 — Average Buy Interval

Average time between executed BUY events.

---

## F-GRD-010 — Maximum Buy Burst

Maximum number of BUY events occurring inside a configured short interval.

Purpose:

Detects periods where capital may be deployed very quickly.

---

# 10. SELL Behavior

## F-GRD-011 — Sell Event Count

Number of executed SELL events.

---

## F-GRD-012 — Sell Frequency

```text
sell_event_count
/
simulation_window
```

---

## F-GRD-013 — Average Sell Interval

Average time between executed SELL events.

---

## F-GRD-014 — Buy-to-Sell Completion Rate

Concept:

```text
completed_sell_cycles
/
eligible_buy_cycles
```

Purpose:

Measures how often BUY activity eventually produces a completed SELL cycle within the defined analysis horizon.

---

# 11. Grid Cycle

A Grid Cycle represents a completed strategy loop:

```text
BUY
↓
POSITION
↓
SELL
```

## F-GRD-015 — Grid Cycle Count

Number of completed BUY → SELL cycles.

---

## F-GRD-016 — Grid Cycle Frequency

```text
completed_cycles
/
simulation_window
```

---

## F-GRD-017 — Average Cycle Duration

Average time from BUY execution to corresponding SELL completion.

---

## F-GRD-018 — Median Cycle Duration

Median BUY → SELL completion time.

Median is useful because cycle durations may be highly skewed.

---

## F-GRD-019 — Cycle Completion Rate

Percentage of initiated grid positions that complete within the defined simulation horizon.

---

# 12. Grid Cycle Quality

## F-GRD-020 — Average Cycle Net P&L

Average realized or simulated Net P&L per completed cycle.

The Net P&L definition must follow the Execution Economics layer.

---

## F-GRD-021 — Median Cycle Net P&L

Median Net P&L per completed cycle.

---

## F-GRD-022 — Positive Cycle Rate

```text
positive_net_pnl_cycles
/
completed_cycles
```

This is not the same as generic win rate because the cycle accounting includes actual execution economics.

---

## F-GRD-023 — Negative Cycle Rate

```text
negative_net_pnl_cycles
/
completed_cycles
```

---

## F-GRD-024 — Average Positive Cycle

Average Net P&L among positive cycles.

---

## F-GRD-025 — Average Negative Cycle

Average Net P&L among negative cycles.

---

# 13. Section Activation

Section behavior is a core characteristic of the Grid Strategy.

## F-GRD-026 — Section 1 Activation Rate

Percentage of simulation windows in which Section 1 becomes active.

---

## F-GRD-027 — Section 2 Activation Rate

---

## F-GRD-028 — Section 3 Activation Rate

---

For Section N:

```text
section_n_activation_rate
```

The exact number of Sections is configuration-dependent.

---

## F-GRD-029 — Section Activation Depth

Represents the deepest Section reached during a simulation.

Conceptual representation:

```text
1
2
3
...
N
```

---

## F-GRD-030 — Maximum Section Depth Frequency

Frequency with which the deepest Section is reached.

Purpose:

Identifies whether the market routinely consumes deep capital reserves.

---

# 14. Section Transition

## F-GRD-031 — Section 1 → Section 2 Transition Rate

Frequency with which market movement causes the strategy to progress from Section 1 into Section 2.

---

## F-GRD-032 — Section 2 → Section 3 Transition Rate

Equivalent for the next transition.

---

For N Sections:

```text
section_n_to_section_nplus1_transition_rate
```

---

## F-GRD-033 — Section Transition Speed

Measures time required for price/strategy state to progress from one Section to the next.

Purpose:

Detects whether capital can be consumed rapidly during sharp declines.

---

# 15. Section Gap Behavior

Section Gaps are strategically important because they allow deeper deployment.

## F-GRD-034 — Section Gap Reach Frequency

How often a Section Gap is traversed during the simulation window.

---

## F-GRD-035 — Average Drawdown to Section 2

Typical market drawdown required before Section 2 becomes active.

---

## F-GRD-036 — Average Drawdown to Section 3

Equivalent for Section 3.

---

For N Sections:

```text
average_drawdown_to_section_n
```

---

## F-GRD-037 — Section Gap Utilization

Measures how effectively the configured Section Gap separates capital deployment zones.

This feature should compare:

```text
configured_section_gap
vs
historical_market_movement
```

The final mathematical definition is subject to simulation research.

---

# 16. Capital Deployment

Capital deployment is central to the strategy.

## F-GRD-038 — Capital Deployed

Total capital used during the simulation.

---

## F-GRD-039 — Capital Deployment Ratio

```text
capital_deployed
/
starting_capital
```

---

## F-GRD-040 — Peak Capital Deployment

Maximum simultaneously deployed capital.

---

## F-GRD-041 — Capital Reserve Remaining

Capital still available after strategy deployment at a given point.

---

## F-GRD-042 — Minimum Capital Reserve

Lowest remaining reserve during the simulation.

This is particularly important during sharp market declines.

---

## F-GRD-043 — Capital Exhaustion Flag

Binary state:

```text
1 = configured deployable capital exhausted
0 = capital remains
```

This is a strategy risk signal, not a market-state feature.

---

# 17. Capital Deployment Speed

## F-GRD-044 — Capital Deployment Velocity

Concept:

```text
capital_deployed
/
time
```

Purpose:

Measures how quickly the strategy consumes capital.

This is useful because a market can have acceptable total drawdown but still consume capital too quickly.

---

## F-GRD-045 — Time to 50% Capital Deployment

Time required to deploy half of the deployable capital.

---

## F-GRD-046 — Time to 80% Capital Deployment

Time required to deploy 80% of deployable capital.

---

## F-GRD-047 — Time to Maximum Deployment

Time required to reach peak configured exposure.

---

# 18. Exposure

## F-GRD-048 — Average Exposure

Average open exposure during the simulation.

---

## F-GRD-049 — Peak Exposure

Maximum exposure reached.

---

## F-GRD-050 — Exposure Ratio

```text
exposure
/
starting_capital
```

---

## F-GRD-051 — Exposure Concentration

Measures how much total exposure is concentrated in a specific Section or price region.

Purpose:

Identifies hidden concentration risk.

---

# 19. Coin Accumulation

The system is spot-based.

Therefore coin accumulation is an important strategy outcome.

## F-GRD-052 — Total Coin Accumulated

Total asset quantity acquired over the simulation.

---

## F-GRD-053 — Average Acquisition Price

Weighted average acquisition price of accumulated coin.

---

## F-GRD-054 — Coin Accumulation Efficiency

Concept:

```text
coin_accumulated
/
capital_deployed
```

This can be normalized appropriately for cross-market comparison.

---

## F-GRD-055 — Additional Coin From Drawdown

Measures additional coin acquired as price moved into deeper Sections relative to the initial Section.

Purpose:

Quantifies the strategic benefit of deeper accumulation.

---

# 20. Cost-Basis Behavior

## F-GRD-056 — Average Cost Reduction

Change in average acquisition price as additional Sections are activated.

---

## F-GRD-057 — Cost-Basis Improvement Ratio

Concept:

```text
initial_average_cost
vs
current_average_cost
```

This should be represented as a normalized improvement ratio.

---

## F-GRD-058 — Cost-Basis Recovery Distance

Price movement required for the current position to reach break-even based on current cost basis and current execution economics.

Execution economics must be sourced from the Execution Economics layer rather than recalculated inconsistently here.

---

# 21. Drawdown

## F-GRD-059 — Maximum Market Drawdown During Strategy

Maximum decline relevant to the simulation window.

This is a contextual input to strategy behavior.

---

## F-GRD-060 — Maximum Strategy Drawdown

Maximum drawdown of the Grid portfolio/position state.

---

## F-GRD-061 — Average Drawdown at Section Activation

Average market or strategy drawdown when each Section activates.

---

## F-GRD-062 — Drawdown to Maximum Exposure

Drawdown level at which peak exposure was reached.

---

# 22. Recovery

Recovery is important because the strategy intentionally accumulates during declines.

## F-GRD-063 — Recovery Rate

Percentage of drawdown events that subsequently reach the defined recovery condition within the analysis horizon.

The recovery condition must be deterministic.

---

## F-GRD-064 — Average Recovery Time

Average time from a defined drawdown event to recovery.

---

## F-GRD-065 — Median Recovery Time

Median recovery duration.

---

## F-GRD-066 — Recovery After Section 2 Activation

Recovery behavior after Section 2 becomes active.

---

## F-GRD-067 — Recovery After Section 3 Activation

Equivalent for Section 3.

---

For N Sections:

```text
recovery_after_section_n_activation
```

---

# 23. Deep Drawdown Behavior

The strategy must distinguish:

```text
Normal Pullback
Deep Drawdown
Extreme Drawdown
```

Possible research states:

```text
Section 1 only
Section 2 required
Section 3 required
Maximum depth reached
Capital exhausted
```

These states are generated by the simulation.

---

# 24. Grid Capture

## F-GRD-068 — Gross Grid Capture

Gross value captured before execution costs.

---

## F-GRD-069 — Net Grid Capture

Grid capture after all execution economics.

This is more important than Gross Grid Capture.

---

## F-GRD-070 — Grid Capture Efficiency

Concept:

```text
Net Grid Capture
/
Gross Grid Opportunity
```

---

# 25. Strategy Efficiency

## F-GRD-071 — Capital Efficiency

Concept:

```text
Net Strategy Outcome
relative to
Average or Peak Capital Deployed
```

Final formula must be selected during outcome research.

---

## F-GRD-072 — Trade Efficiency

Concept:

```text
Net P&L
/
execution count
```

---

## F-GRD-073 — Cycle Efficiency

Concept:

```text
Net Cycle P&L
/
capital tied to cycle
```

---

## F-GRD-074 — Deployment Efficiency

Measures how effectively deployed capital contributes to completed profitable cycles.

---

# 26. Strategy Outcome

## F-GRD-075 — Historical Net P&L

Net strategy P&L for the simulation window.

It MUST use the canonical execution economics model.

---

## F-GRD-076 — Net P&L Return

```text
Net P&L
/
starting_capital
```

---

## F-GRD-077 — Realized P&L

Profit/loss from completed cycles.

---

## F-GRD-078 — Unrealized P&L

Open-position P&L at simulation cutoff.

---

## F-GRD-079 — Total Strategy P&L

```text
Realized P&L
+
Unrealized P&L
```

---

# 27. Recovery and Profitability Quality

## F-GRD-080 — Profit Factor

Concept:

```text
gross_positive_net_pnl
/
abs(gross_negative_net_pnl)
```

Undefined or invalid when denominator is zero; explicit handling is required.

---

## F-GRD-081 — Net P&L Volatility

Volatility of strategy returns or cycle outcomes over the research window.

---

## F-GRD-082 — Outcome Stability

Measures the consistency of Grid Strategy outcomes across historical windows.

A market producing:

```text
+10%
-9%
+8%
-8%
```

is behaviorally different from one producing:

```text
+3%
+3%
+4%
+3%
```

even if average return is similar.

---

# 28. Strategy Stress Behavior

## F-GRD-083 — Maximum Capital Stress

Maximum capital utilization during stress scenarios.

---

## F-GRD-084 — Maximum Section Stress

Deepest Section reached under stress.

---

## F-GRD-085 — Recovery Failure Rate

Percentage of simulated drawdown events that fail to recover within the defined horizon.

This is important and must be evaluated with a clearly defined horizon.

---

## F-GRD-086 — Capital Exhaustion Frequency

Frequency with which simulated strategy exhausts configured deployable capital.

---

# 29. Blueprint Sensitivity

The same market may behave differently under different Blueprints.

Therefore research should record sensitivity.

## F-GRD-087 — Grid Spacing Sensitivity

Measures how outcomes change when uniform grid spacing is varied within valid configurations.

This does NOT mean spacing varies inside one Section.

It means separate candidate Blueprints are compared.

---

## F-GRD-088 — Section Gap Sensitivity

Measures outcome sensitivity to different Section Gap configurations.

---

## F-GRD-089 — Allocation Sensitivity

Measures outcome sensitivity to different Section capital allocations.

---

## F-GRD-090 — Section Count Sensitivity

Measures outcome sensitivity to different numbers of Sections.

---

# 30. Blueprint Interaction

Grid Behavior must preserve the fact that:

```text
Grid spacing:
Uniform within each Section

Section Gap:
May differ between Sections
```

Historical simulation must never transform a Section into a collection of individually optimized grid spacings.

For example:

```text
VALID

Section 1:
1%
1%
1%
1%

Section 2:
1.5%
1.5%
1.5%
1.5%
```

Invalid:

```text
Section 1:
1%
1.2%
1.4%
1.8%
```

unless that behavior is explicitly a different future strategy definition.

---

# 31. Historical Grid Simulation Dependency

Grid Behavior features are generated primarily by:

```text
Historical Market Data
+
Market State Features
+
Execution Economics
+
Candidate Grid Blueprint
+
Immediate Execution Rules
```

Conceptually:

```text
Historical Data
      ↓
Market State
      +
Execution Economics
      +
Blueprint
      ↓
Grid Simulator
      ↓
Grid Behavior Features
```

---

# 32. Simulation Window

Every Grid Behavior observation MUST define its simulation horizon.

Possible windows:

```text
7D
14D
30D
60D
90D
180D
365D
```

These are examples only.

The research system should support multiple horizons.

---

# 33. Forward Outcome Principle

For ML training, Grid Behavior features are generally future-outcome labels or post-observation behavioral measurements.

Example:

```text
Observation Time T
       ↓
Build features available at T
       ↓
Run future simulation T → T+H
       ↓
Generate Grid Behavior outcomes
```

The future simulation outcome MUST NOT be accidentally included among input features for the same observation.

This distinction is mandatory.

---

# 34. Leakage Risk

Grid Behavior is especially vulnerable to future leakage because many features are outcomes.

Examples:

```text
Historical Net P&L
Recovery Time
Section Activation Rate
Coin Accumulation
Maximum Drawdown
Capital Exhaustion
```

These must be used carefully.

For example:

```text
Past rolling historical Grid Behavior
```

may be a valid feature if calculated only from data strictly before T.

But:

```text
Future Grid P&L from T to T+30
```

is an outcome label, not an input feature.

---

# 35. Rolling Historical Grid Behavior

For ML input features, historical Grid Behavior should often be transformed into rolling windows.

Examples:

```text
past_30d_grid_cycle_frequency
past_90d_section_2_activation_rate
past_180d_average_cycle_net_pnl
past_90d_capital_exhaustion_rate
```

This allows the model to learn from recent historical strategy behavior while preserving causal ordering.

---

# 36. Grid Behavior Output Object

Conceptually:

```text
GridBehavior
│
├── opportunity
│   ├── event_count
│   ├── opportunity_frequency
│   └── opportunity_density
│
├── execution_behavior
│   ├── buy_count
│   ├── sell_count
│   ├── trigger_rate
│   └── cycle_count
│
├── cycles
│   ├── average_duration
│   ├── completion_rate
│   ├── average_net_pnl
│   ├── positive_rate
│   └── negative_rate
│
├── sections
│   ├── activation_rates
│   ├── maximum_depth
│   ├── transition_rates
│   └── gap_behavior
│
├── capital
│   ├── deployed
│   ├── reserve
│   ├── deployment_velocity
│   └── utilization
│
├── exposure
│   ├── average
│   ├── peak
│   └── concentration
│
├── accumulation
│   ├── coin_accumulated
│   ├── average_cost
│   └── cost_basis_improvement
│
├── drawdown
│   ├── maximum
│   ├── section_activation
│   └── maximum_exposure_drawdown
│
├── recovery
│   ├── recovery_rate
│   ├── recovery_time
│   └── recovery_failure_rate
│
├── outcome
│   ├── net_pnl
│   ├── return
│   ├── realized
│   ├── unrealized
│   └── total
│
└── sensitivity
    ├── grid_spacing
    ├── section_gap
    ├── allocation
    └── section_count
```

---

# 37. Final Feature Inventory

```text
F-GRD-001  grid_opportunity_frequency
F-GRD-002  grid_event_count
F-GRD-003  grid_opportunity_density
F-GRD-004  grid_level_touch_count
F-GRD-005  grid_execution_trigger_count
F-GRD-006  grid_trigger_rate

F-GRD-007  buy_event_count
F-GRD-008  buy_frequency
F-GRD-009  average_buy_interval
F-GRD-010  maximum_buy_burst

F-GRD-011  sell_event_count
F-GRD-012  sell_frequency
F-GRD-013  average_sell_interval
F-GRD-014  buy_to_sell_completion_rate

F-GRD-015  grid_cycle_count
F-GRD-016  grid_cycle_frequency
F-GRD-017  average_cycle_duration
F-GRD-018  median_cycle_duration
F-GRD-019  cycle_completion_rate

F-GRD-020  average_cycle_net_pnl
F-GRD-021  median_cycle_net_pnl
F-GRD-022  positive_cycle_rate
F-GRD-023  negative_cycle_rate
F-GRD-024  average_positive_cycle
F-GRD-025  average_negative_cycle

F-GRD-026  section_1_activation_rate
F-GRD-027  section_2_activation_rate
F-GRD-028  section_3_activation_rate
F-GRD-029  section_activation_depth
F-GRD-030  maximum_section_depth_frequency

F-GRD-031  section_1_to_section_2_transition_rate
F-GRD-032  section_2_to_section_3_transition_rate
F-GRD-033  section_transition_speed

F-GRD-034  section_gap_reach_frequency
F-GRD-035  average_drawdown_to_section_2
F-GRD-036  average_drawdown_to_section_3
F-GRD-037  section_gap_utilization

F-GRD-038  capital_deployed
F-GRD-039  capital_deployment_ratio
F-GRD-040  peak_capital_deployment
F-GRD-041  capital_reserve_remaining
F-GRD-042  minimum_capital_reserve
F-GRD-043  capital_exhaustion_flag

F-GRD-044  capital_deployment_velocity
F-GRD-045  time_to_50pct_capital_deployment
F-GRD-046  time_to_80pct_capital_deployment
F-GRD-047  time_to_maximum_deployment

F-GRD-048  average_exposure
F-GRD-049  peak_exposure
F-GRD-050  exposure_ratio
F-GRD-051  exposure_concentration

F-GRD-052  total_coin_accumulated
F-GRD-053  average_acquisition_price
F-GRD-054  coin_accumulation_efficiency
F-GRD-055  additional_coin_from_drawdown

F-GRD-056  average_cost_reduction
F-GRD-057  cost_basis_improvement_ratio
F-GRD-058  cost_basis_recovery_distance

F-GRD-059  maximum_market_drawdown_during_strategy
F-GRD-060  maximum_strategy_drawdown
F-GRD-061  average_drawdown_at_section_activation
F-GRD-062  drawdown_to_maximum_exposure

F-GRD-063  recovery_rate
F-GRD-064  average_recovery_time
F-GRD-065  median_recovery_time
F-GRD-066  recovery_after_section_2_activation
F-GRD-067  recovery_after_section_3_activation

F-GRD-068  gross_grid_capture
F-GRD-069  net_grid_capture
F-GRD-070  grid_capture_efficiency

F-GRD-071  capital_efficiency
F-GRD-072  trade_efficiency
F-GRD-073  cycle_efficiency
F-GRD-074  deployment_efficiency

F-GRD-075  historical_net_pnl
F-GRD-076  net_pnl_return
F-GRD-077  realized_pnl
F-GRD-078  unrealized_pnl
F-GRD-079  total_strategy_pnl

F-GRD-080  profit_factor
F-GRD-081  net_pnl_volatility
F-GRD-082  outcome_stability

F-GRD-083  maximum_capital_stress
F-GRD-084  maximum_section_stress
F-GRD-085  recovery_failure_rate
F-GRD-086  capital_exhaustion_frequency

F-GRD-087  grid_spacing_sensitivity
F-GRD-088  section_gap_sensitivity
F-GRD-089  allocation_sensitivity
F-GRD-090  section_count_sensitivity
```

---

# 38. Non-Negotiable Rules

1. Grid Behavior describes the behavior of the actual Grid Strategy, not a generic grid.
2. The strategy uses uniform grid spacing within each Section.
3. Section Gaps may differ between Sections.
4. BUY and SELL are modeled as immediate execution.
5. Grid Behavior must use the canonical Net P&L economics.
6. Gross Grid Capture and Net Grid Capture must remain separate.
7. Market drawdown is not automatically a strategy failure.
8. Deeper Section activation is a measurable behavior, not automatically a negative outcome.
9. Capital reserve and capital exhaustion must be measurable.
10. Coin accumulation is a first-class spot strategy outcome.
11. Historical Grid Behavior features used for ML inputs must be causally available before the prediction timestamp.
12. Future simulation outcomes must not leak into input features.
13. Different candidate Blueprints may be compared, but grid spacing must remain uniform within each Section.
14. Grid Behavior does not directly execute trades.
15. Grid Behavior does not directly modify production strategy.

---

# 39. Boundary With Other Feature Layers

```text
MARKET STATE
    ↓
What is happening?

EXECUTION ECONOMICS
    ↓
What does immediate execution cost?

GRID BEHAVIOR
    ↓
What happens when our Grid Strategy is applied?

DERIVED ML
    ↓
What relationships can be learned across these layers?
```

Grid Behavior may consume Market State and Execution Economics outputs through the simulation pipeline, but its outputs represent strategy behavior.

---

# 40. Final Definition

Grid Behavior is:

> **The feature layer that measures how our specific Section-based, uniform-grid, adaptive-Section-Gap, immediate-execution Grid Strategy behaves across historical market conditions, including opportunity frequency, grid cycles, Section activation, capital deployment, coin accumulation, drawdown, recovery, execution outcomes, and strategy stability.**

Its central workflow is:

```text
Market State
      +
Execution Economics
      +
Candidate Grid Blueprint
      ↓
Historical Grid Simulation
      ↓
Grid Behavior
      ↓
AI / ML Research
```

The purpose is not merely to determine whether the market moved.

The purpose is to determine:

> **How the market behaved when exposed to our actual Grid Strategy.**
