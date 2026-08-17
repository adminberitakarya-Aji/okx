# AI Research Grid Simulator Specification

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`
- `AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md`
- `AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md`
- `AI_RESEARCH_FEATURE_SPEC_GRID_BEHAVIOR.md`
- `AI_RESEARCH_FEATURE_SPEC_DERIVED_ML.md`
- `AI_RESEARCH_LABEL_SPEC.md`
- `AI_RESEARCH_DATASET_SPEC.md`

---

# 1. Purpose

This document defines the deterministic Historical Grid Simulator used by AI Research.

The simulator exists to answer:

> **What would our actual Section-based, uniform-grid, adaptive-Section-Gap, immediate-execution Grid Strategy have done if it had been applied to historical market conditions?**

The simulator is a research component.

It is NOT:

- A production execution engine
- An AI decision maker
- A prediction model
- A generic limit-order grid simulator

Its primary responsibilities are:

```text
Candidate Blueprint
      +
Historical Market Data
      +
Execution Economics
      ↓
Deterministic Simulation
      ↓
Grid Events
      ↓
Strategy State
      ↓
Historical Outcomes
      ↓
Labels / Grid Behavior Features
```

---

# 2. Core Strategy Model

The simulated Grid Strategy is hierarchical:

```text
GRID
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
```

Between Sections:

```text
SECTION 1
     ↓
SECTION GAP 1
     ↓
SECTION 2
     ↓
SECTION GAP 2
     ↓
SECTION 3
```

Rules:

```text
Grid spacing inside a Section = uniform

Section Gap between Sections = may differ
```

---

# 3. Immediate Execution Model

The simulator MUST model:

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

It MUST NOT simulate passive waiting limit orders as the default strategy.

This distinction is fundamental.

Generic behavior:

```text
Place limit order
↓
Wait
↓
Fill if price reaches order
```

Our research simulation:

```text
Grid condition
↓
Execution decision
↓
Immediate BUY/SELL
↓
Actual/estimated execution economics
```

---

# 4. Simulator Objectives

The simulator must be able to produce:

1. Historical strategy outcomes.
2. Grid Behavior features.
3. Label outcomes for ML.
4. Stress outcomes.
5. Blueprint comparison results.
6. Section activation statistics.
7. Capital utilization statistics.
8. Coin accumulation statistics.
9. Net P&L.
10. Drawdown and recovery statistics.

---

# 5. Deterministic Principle

Given identical:

```text
Market Data
+
Blueprint
+
Initial State
+
Execution Model
+
Strategy Rules
+
Simulator Version
```

the simulator MUST produce the same result.

No LLM or stochastic AI component may influence the core simulation path.

---

# 6. Simulation Inputs

Minimum inputs:

```text
market_id
observation_timestamp
simulation_horizon
starting_capital
starting_asset_balance
candidate_blueprint
historical_market_data
execution_model
strategy_rules
```

Required version identifiers:

```text
simulator_version
execution_model_version
strategy_rule_version
blueprint_version
market_data_version
```

---

# 7. Initial Portfolio State

The simulator must explicitly define the initial state.

At minimum:

```text
quote_currency_balance
base_asset_balance
open_positions
reserved_capital
realized_pnl
unrealized_pnl
```

For a spot accumulation strategy, the initial condition must be configurable.

Initial asset balance should not be implicitly assumed to be zero in every research experiment.

The selected initial condition must be recorded with the simulation.

---

# 8. Candidate Blueprint

The simulator consumes a validated Candidate Blueprint.

Minimum blueprint:

```text
blueprint_id
capital
section_count
section_allocation
grid_count_per_section
uniform_grid_spacing_per_section
section_gap_per_transition
section_price_range
```

Optional:

```text
minimum_profit_requirement
execution_constraints
risk_constraints
section_activation_rules
```

---

# 9. Blueprint Validation

Before simulation:

```text
Candidate Blueprint
        ↓
Deterministic Validation
```

Validation must ensure:

- Section allocations are valid.
- Total allocation does not exceed deployable capital.
- Grid count is valid.
- Grid spacing is positive.
- Grid spacing is uniform inside each Section.
- Section Gaps are valid.
- Section ranges are coherent.
- Price levels are ordered correctly.
- No impossible or duplicate grid levels exist unless explicitly allowed.
- Minimum order constraints are satisfiable.
- Strategy risk limits are valid.

Invalid blueprint result:

```text
INVALID_BLUEPRINT
```

It MUST NOT be converted into a negative strategy outcome.

---

# 10. Section Model

Each Section contains:

```text
Section ID
Section Allocation
Section Capital
Section Start Price
Section End Price
Grid Count
Uniform Grid Spacing
Section Gap to Next Section
Activation State
```

Example:

```text
SECTION 1

Range:
100 → 96

Grid Spacing:
1%

Grid:
100
99
98
97
96
```

The spacing remains uniform.

---

# 11. Section Gap Model

Section Gap is separate from Grid Spacing.

Example:

```text
SECTION 1
100 → 96

GAP
↓ 5%

SECTION 2
91 → 87

GAP
↓ 10%

SECTION 3
78 → 74
```

The simulator must preserve these explicit transitions.

Section Gaps may differ between Sections.

---

# 12. Grid Level Generation

The Grid Engine / simulator must derive exact grid levels deterministically from:

```text
Section Range
+
Grid Count
+
Uniform Grid Spacing
```

The simulator should support both:

```text
percentage spacing
```

and:

```text
absolute price spacing
```

if both are part of the blueprint specification.

The selected mode must be recorded.

---

# 13. Grid Level Integrity

Within a Section:

```text
GridSpacing(i) = GridSpacing(j)
```

for all valid grid pairs in that Section.

A candidate configuration violating this rule is invalid for this strategy definition.

---

# 14. Market Data Input

The simulator requires historical price data covering:

```text
T0
→
T1
```

where:

```text
T1 = T0 + simulation_horizon
```

Required minimum information depends on simulation granularity.

Possible source data:

```text
OHLCV
Trades
Bid/Ask History
Order Book / Depth
```

For execution realism, higher-resolution data may be required.

---

# 15. Simulation Granularity

The simulator should support configurable simulation resolution.

Examples:

```text
Tick
Trade
1s
1m
5m
15m
1h
```

The simulator MUST NOT assume that candle OHLC alone can always reproduce exact execution order.

The selected resolution must be recorded:

```text
simulation_data_granularity
```

---

# 16. OHLC Ambiguity

If only candle OHLC data is available, intrabar execution order may be ambiguous.

Example:

```text
Candle:
Open = 100
High = 105
Low = 95
Close = 102
```

A BUY level at 97 and SELL level at 104 were both reachable, but OHLC alone does not establish which occurred first.

Therefore the simulator must not invent a deterministic sequence without an explicit rule.

Possible approaches:

```text
Higher-resolution data
or
Conservative intrabar policy
or
Explicit scenario branching
```

The chosen method must be versioned.

---

# 17. Preferred Historical Execution Data

For the most accurate research:

```text
Trades
+
Bid/Ask
+
Depth where available
```

are preferred over coarse OHLC alone.

This is especially important because the strategy uses immediate execution.

---

# 18. Event Engine

The simulator should process the market chronologically.

Conceptually:

```text
Market Event
      ↓
Update Market State
      ↓
Evaluate Grid Conditions
      ↓
Evaluate Section Activation
      ↓
Evaluate Execution Economics
      ↓
Generate Immediate Execution
      ↓
Update Portfolio
      ↓
Update Strategy State
      ↓
Record Event
```

---

# 19. Event Ordering

When multiple events occur at the same timestamp, deterministic priority must be defined.

Recommended conceptual order:

```text
1. Market data update
2. Price/structure update
3. Section state evaluation
4. Grid condition evaluation
5. Risk/economic validation
6. BUY/SELL execution
7. Portfolio update
8. P&L update
9. Logging
```

Any alternative ordering must be explicitly versioned.

---

# 20. Market State During Simulation

The simulator may consume the same Market State definitions used by AI Research:

```text
Monthly
Weekly
Daily
Realtime Price
Proximity
Trend
Volatility
```

However, it must reconstruct them causally at each historical timestamp.

The simulator may not use future candle information.

---

# 21. Execution Model

Immediate execution must be modeled using the Execution Economics layer.

For BUY:

```text
Reference Buy Price
        ↓
Expected/Simulated Execution Price
        ↓
Buy Cost
        ↓
Buy Fee
        ↓
Position
```

For SELL:

```text
Reference Sell Price
        ↓
Expected/Simulated Execution Price
        ↓
Sell Cost
        ↓
Sell Fee
        ↓
Net Proceeds
```

---

# 22. Spread Model

For simplified immediate execution:

```text
BUY reference → Ask
SELL reference → Bid
```

The exact execution model may incorporate depth and market impact.

Spread must not be separately charged if the bid/ask difference has already been reflected in execution prices.

---

# 23. Slippage Model

Slippage must be configurable.

Potential model inputs:

```text
Order Size
Bid/Ask
Depth
Liquidity
Volatility
Price Impact
Historical Slippage
Stress Condition
```

The same slippage model version must be used consistently when generating comparable labels.

---

# 24. Fee Model

The simulator must support:

```text
Buy Fee Rate
Sell Fee Rate
```

Potential fee schedules may vary by provider/account conditions.

The fee schedule must be captured in:

```text
execution_model_version
```

or an equivalent reference.

---

# 25. Exact Cost Accounting

The simulator must preserve:

```text
buy_notional
buy_execution_value
buy_fee
buy_slippage_cost
buy_other_cost

sell_notional
sell_execution_value
sell_fee
sell_slippage_cost
sell_other_cost
```

It must then derive:

```text
effective_buy_cost
effective_sell_proceeds
```

without double counting.

---

# 26. Canonical Net P&L

The accounting representation is:

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

The operational implementation should generally use:

```text
Effective Sell Proceeds
−
Effective Buy Cost
```

provided all applicable costs are embedded exactly once.

---

# 27. Buy Execution

When a BUY condition is triggered:

1. Verify sufficient available capital.
2. Determine intended order size.
3. Calculate/estimate execution price.
4. Calculate fees.
5. Calculate slippage/price impact.
6. Execute immediately in simulation.
7. Update base-asset quantity.
8. Reduce quote-currency balance.
9. Record the event.
10. Recalculate cost basis and exposure.

If insufficient capital:

```text
BUY_REJECTED_INSUFFICIENT_CAPITAL
```

The failure must be logged rather than silently ignored.

---

# 28. Sell Execution

When a SELL condition is triggered:

1. Verify sufficient asset quantity.
2. Determine intended sell quantity.
3. Calculate/estimate execution price.
4. Calculate fees.
5. Calculate slippage/price impact.
6. Execute immediately in simulation.
7. Update quote-currency balance.
8. Reduce base-asset quantity.
9. Record realized P&L.
10. Update position and cycle state.

If insufficient asset:

```text
SELL_REJECTED_INSUFFICIENT_ASSET
```

---

# 29. Position Model

The simulator must track at minimum:

```text
base_asset_quantity
quote_currency_balance
average_acquisition_price
open_cost_basis
realized_pnl
unrealized_pnl
total_pnl
```

Optional:

```text
position_lots
position_by_section
position_by_grid
```

Lot-level tracking may be valuable for detailed Grid Behavior research.

---

# 30. Section State Machine

Each Section should have explicit state.

Possible states:

```text
INACTIVE
ARMED
ACTIVE
PARTIALLY_DEPLOYED
FULLY_DEPLOYED
RECOVERING
COMPLETED
```

The exact production state taxonomy may evolve, but simulation state must be explicit and deterministic.

---

# 31. Section Activation

A Section becomes eligible according to its configured price relationship.

Example:

```text
Current Section
      ↓
Price moves through configured range/gap
      ↓
Next Section eligible
      ↓
Capital available?
      ↓
Execution permitted
```

The simulator must record:

```text
section_activation_timestamp
section_activation_price
section_activation_reason
```

---

# 32. Section Transition

When market moves from one Section toward the next:

```text
Section 1
    ↓
Section Gap
    ↓
Section 2
```

the simulator records:

```text
previous_section
next_section
transition_timestamp
transition_price
drawdown_at_transition
capital_state
```

---

# 33. Grid State

Each grid level should have a deterministic state.

Possible states:

```text
INACTIVE
ELIGIBLE
TRIGGERED
EXECUTED
COMPLETED
BLOCKED
```

The simulator must record the reason for blocked execution when applicable.

---

# 34. Grid Cycle Matching

A Grid Cycle is:

```text
BUY
↓
Position
↓
SELL
```

The simulator must maintain a deterministic mapping between BUY and corresponding SELL.

Possible approaches:

```text
FIFO
Lot-linked
Strategy-defined pairing
```

The selected method must be fixed in the strategy rule version.

For a strategy where each BUY has its own target, lot-linked tracking is recommended.

---

# 35. Per-Grid Target

Each Grid BUY may have its own target defined by the Strategy Blueprint.

The simulator must preserve:

```text
grid_id
entry_price
target_exit
quantity
section_id
status
```

A SELL event completes the corresponding grid cycle according to the strategy rule.

---

# 36. Immediate SELL vs Holding

The simulator must not force a SELL merely because price is above entry.

SELL should occur only when the configured strategy condition is satisfied, including minimum economics where applicable.

Example:

```text
Sell Price > Buy Price
```

is not sufficient if:

```text
Net P&L <= 0
```

after costs.

---

# 37. Minimum Profitable Exit

If the strategy uses Minimum Profitable Exit:

```text
Current Expected Sell
        ↓
Net P&L Calculation
        ↓
Net P&L > Minimum Profit Requirement?
```

If not:

```text
SELL NOT ECONOMICALLY VALID
```

This rule must be deterministic.

---

# 38. Capital Accounting

The simulator must distinguish:

```text
Starting Capital
Deployable Capital
Reserved Capital
Deployed Capital
Remaining Capital
```

For each Section:

```text
Section Capital Allocation
Section Capital Used
Section Capital Remaining
```

---

# 39. Capital Reservation

If the Blueprint reserves capital for deeper Sections:

```text
Section 1
↓
Section 2 reserve
↓
Section 3 reserve
```

the simulator must not spend reserved capital unless the strategy explicitly permits it.

This is essential to test the actual Section-Gap philosophy.

---

# 40. Capital Utilization

At each event:

```text
capital_utilization =
deployed_capital / deployable_capital
```

The simulator must record:

```text
current_utilization
peak_utilization
minimum_remaining_reserve
```

---

# 41. Coin Accumulation

Every BUY updates:

```text
base_asset_quantity
```

The simulator must record:

```text
coin_accumulated
average_acquisition_price
```

This is a key spot strategy outcome.

---

# 42. Cost Basis

The simulator must maintain a deterministic cost-basis method.

Possible:

```text
Weighted Average Cost
FIFO
Lot Based
```

The selected method must be fixed by strategy rule version.

For the initial Grid Strategy, weighted average cost or lot-linked tracking may be used depending on the intended production accounting.

---

# 43. Unrealized P&L

At each observation:

```text
unrealized_pnl
```

must be calculated using the defined valuation price.

The valuation method must be consistent.

Potential reference:

```text
bid
mid
last
```

For consistency with immediate liquidation economics, using an executable-side valuation may be appropriate.

The final valuation method must be versioned.

---

# 44. Drawdown Calculation

The simulator must calculate strategy drawdown from the equity curve.

Conceptually:

```text
Equity
↓
Peak Equity
↓
Current Equity
↓
Drawdown
```

At minimum:

```text
current_drawdown
maximum_drawdown
```

---

# 45. Recovery Calculation

Recovery must be deterministic.

Candidate definitions:

```text
Recovery to Initial Equity
Recovery to Break-Even
Recovery to Positive Net P&L
Recovery to Minimum Profit
```

The selected definition must be specified in the label version.

The simulator should be capable of recording multiple recovery states even if one is selected as the official label.

---

# 46. Capital Exhaustion

The simulator must identify:

```text
CAPITAL_EXHAUSTED
```

when configured deployable capital is fully committed or no further valid deployment is possible according to the strategy rules.

This is not automatically a failure label.

It is a strategy state that must be evaluated against subsequent recovery/outcome.

---

# 47. Section Depth

At every point:

```text
current_section_depth
maximum_section_depth
```

must be available.

Example:

```text
Section 1 active
→ depth = 1

Section 2 active
→ depth = 2

Section 3 active
→ depth = 3
```

---

# 48. Market Crash Scenario

The simulator must handle severe declines without special-casing them as errors.

Example:

```text
Monthly Low
     ↓
Break
     ↓
Section 2
     ↓
Section 3
     ↓
Deep Drawdown
```

The simulator continues until:

```text
horizon end
or
strategy terminal condition
```

unless a mandatory risk stop exists in the Blueprint.

---

# 49. No Forced Recovery

The simulator must never assume:

```text
market will recover
```

Recovery must come from actual future market data.

This is essential.

A cheap entry price is not itself a successful outcome.

---

# 50. Simulation Terminal Conditions

Possible terminal conditions:

```text
HORIZON_END
CAPITAL_EXHAUSTED
RISK_LIMIT_REACHED
STRATEGY_STOP
DATA_END
INVALID_STATE
```

Terminal condition must be recorded.

---

# 51. Scenario Modes

The simulator should support at least:

```text
BASELINE
STRESS
EXTREME
```

Stress mode may apply:

```text
higher slippage
wider spread
lower liquidity
higher volatility
```

depending on the Execution Economics specification.

Stress modes must be deterministic and versioned.

---

# 52. Reproducibility

Simulation reproducibility requires:

```text
simulator_version
strategy_rule_version
blueprint_version
execution_model_version
market_data_version
initial_portfolio_state
```

If any of these changes, the simulation result may change.

---

# 53. Simulation Event Log

Every execution-relevant event should be recorded.

Minimum:

```text
event_id
timestamp
event_type
market_price
section_id
grid_id
action
requested_quantity
executed_quantity
execution_price
fee
slippage
capital_before
capital_after
asset_before
asset_after
realized_pnl
unrealized_pnl
```

---

# 54. Event Types

Possible events:

```text
MARKET_UPDATE
SECTION_ACTIVATED
SECTION_TRANSITION
GRID_TRIGGERED
BUY_EXECUTED
SELL_EXECUTED
BUY_REJECTED
SELL_REJECTED
CAPITAL_RESERVED
CAPITAL_RELEASED
RISK_BLOCK
RECOVERY_STARTED
RECOVERY_COMPLETED
CAPITAL_EXHAUSTED
SIMULATION_TERMINATED
```

---

# 55. Simulation Output

Conceptual output:

```text
SimulationResult
│
├── identity
│   ├── simulation_run_id
│   ├── market_id
│   ├── observation_timestamp
│   ├── horizon
│   ├── blueprint_id
│   └── version_set
│
├── initial_state
│
├── final_state
│
├── events
│
├── performance
│   ├── net_pnl
│   ├── return
│   ├── realized_pnl
│   ├── unrealized_pnl
│   ├── max_drawdown
│   └── recovery
│
├── grid_behavior
│   ├── grid_events
│   ├── cycles
│   ├── section_activation
│   ├── capital_utilization
│   ├── coin_accumulation
│   └── section_depth
│
└── terminal
    ├── terminal_condition
    └── simulation_status
```

---

# 56. Simulation Metrics for Labels

The simulator must be able to produce at minimum:

```text
Net P&L
Net P&L Return
Maximum Drawdown
Peak Capital Utilization
Recovery Event
Recovery Time
Maximum Section Depth
Capital Exhaustion
Coin Accumulation
Cost-Basis Improvement
```

These become inputs to the Label Generator.

---

# 57. Simulation Metrics for Grid Behavior

The simulator must provide:

```text
Grid Event Count
Grid Opportunity Frequency
BUY Count
SELL Count
Cycle Count
Cycle Completion
Section Activation Rate
Section Transition Rate
Section Depth
Capital Deployment
Capital Reserve
Exposure
Coin Accumulation
Recovery
Grid Capture
```

These populate the Grid Behavior feature layer.

---

# 58. Simulation + Label Generation

The relationship is:

```text
Candidate Observation
        ↓
Candidate Blueprint
        ↓
Historical Simulation
        ↓
SimulationResult
        ↓
Label Generator
        ↓
Labels
```

The simulator itself should not decide the final ML label taxonomy.

That belongs to `AI_RESEARCH_LABEL_SPEC.md`.

---

# 59. Simulation + Grid Behavior Generation

The relationship is:

```text
SimulationResult
      ↓
Grid Behavior Feature Extractor
      ↓
Historical Grid Behavior
```

Rolling historical behavior must be calculated only from completed simulations before the prediction timestamp.

---

# 60. Simulation Quality Checks

Every run should validate:

```text
No negative balances unless explicitly permitted
No impossible order quantities
No invalid price levels
No duplicate impossible executions
No future data usage
No cost double counting
No invalid Section transitions
No invalid Grid spacing
```

---

# 61. Accounting Invariants

At all times:

```text
Assets + Cash + P&L accounting
```

must reconcile according to the chosen valuation and accounting method.

Examples:

```text
base_asset_quantity >= 0
quote_currency_balance >= 0
```

unless shorting/margin is explicitly introduced in a future strategy version.

This specification is for spot.

---

# 62. Spot-Only Constraint

The simulator MUST NOT assume:

```text
Short position
Borrowed asset
Leverage
Liquidation
Funding fee
```

unless a future strategy version explicitly changes the system.

Current scope:

```text
Crypto Spot Grid
```

---

# 63. No Shorting

A SELL requires asset inventory.

Therefore:

```text
SELL quantity
<=
available base asset
```

This is fundamental to the spot model.

---

# 64. Multiple Sections and Portfolio State

The simulator must maintain:

```text
Section-level capital
Section-level positions
Global portfolio state
```

This permits research into:

```text
Which Section produced which outcome?
```

and:

```text
How much capital was consumed by deeper Sections?
```

---

# 65. Blueprint Sensitivity Simulation

The simulator should support batch evaluation:

```text
Blueprint A
Blueprint B
Blueprint C
...
```

for the same:

```text
Market
Observation Time
Future Market Window
```

This allows ML research to compare:

```text
Same Market
Different Blueprint
→ Different Outcome
```

This is essential to the Blueprint-conditional target architecture.

---

# 66. Batch Simulation

Conceptually:

```text
Market
  ↓
Observation T
  ↓
Candidate Blueprints
  ├── BP-001
  ├── BP-002
  ├── BP-003
  └── ...
       ↓
Parallel / Batch Simulation
       ↓
Simulation Results
```

Each result must retain its own:

```text
blueprint_id
simulation_run_id
```

---

# 67. Deterministic Candidate Blueprint Generation

If candidate Blueprints are generated automatically, the generator must be deterministic.

Example parameter dimensions:

```text
Section Count
Grid Spacing
Section Gap
Allocation
Grid Count
```

The generator must enforce strategy constraints.

---

# 68. Simulation Computational Efficiency

Because the initial Research Universe is:

```text
Top 10 OKX Spot Markets
```

the simulator can focus on research depth.

However, total workload may still be large:

```text
10 Markets
×
Observation Timestamps
×
Blueprints
×
Horizon
×
Historical Data
```

Therefore simulation should support:

```text
Batching
Caching
Reusable Market Windows
Feature Snapshot Caching
Execution Model Caching
Parallel Research Jobs
```

---

# 69. Cached Historical Windows

If multiple Blueprints use the same:

```text
Market
+
Observation Time
+
Horizon
```

the underlying market data window should be loaded once and reused.

This reduces unnecessary I/O.

---

# 70. Simulation Versioning

A change to any of the following requires a new simulator or model version:

```text
Execution logic
Section activation logic
Grid trigger rules
Cycle pairing
Fee handling
Slippage handling
Price valuation
Capital allocation handling
Risk handling
```

A simulation result must always reference its version.

---

# 71. Simulator Testing

The simulator requires deterministic unit tests for:

```text
Grid Level Generation
Section Gap Handling
Capital Allocation
BUY Execution
SELL Execution
Fee Calculation
Slippage
P&L
Cycle Matching
Section Activation
Capital Exhaustion
Drawdown
Recovery
```

Tests must include edge cases.

---

# 72. Edge Cases

The simulator must explicitly handle:

```text
No market movement
One-sided movement
Immediate reversal
Fast crash through multiple Sections
Price gaps
Missing data
Zero range candle
Insufficient capital
Insufficient asset
Tiny order below exchange minimum
Extreme spread
Extreme slippage
Simulation ending with open positions
```

---

# 73. Price Gaps

If market data jumps across multiple grid levels between observations, the simulator must apply a deterministic rule.

It must not assume all skipped levels executed unless the chosen execution model logically supports that.

This is especially important when using coarse historical data.

---

# 74. Multiple Grid Levels Crossed

Example:

```text
Price:
100
  ↓
95
```

and levels:

```text
99
98
97
96
```

If the selected historical resolution shows a jump from 100 to 95, the simulator must not automatically execute four independent market buys unless the event sequence is knowable.

The handling method must be explicitly defined:

```text
high-resolution reconstruction
or
conservative policy
or
scenario branching
```

---

# 75. Historical Data Quality

The simulator must record:

```text
data_quality_status
data_granularity
missing_intervals
reconstruction_method
```

A simulation based on coarse or incomplete data should be distinguishable from a high-fidelity run.

---

# 76. Research Fidelity Levels

The simulator should support research fidelity levels.

Conceptually:

```text
LEVEL 1
OHLC-based

LEVEL 2
High-resolution trades

LEVEL 3
Trades + Bid/Ask

LEVEL 4
Trades + Bid/Ask + Depth
```

The highest practical level should be preferred for final validation.

Results from different fidelity levels should not be treated as identical.

---

# 77. Label Integrity Rule

The label generator may only use:

```text
VALID simulation result
```

for ground-truth outcome creation.

Required:

```text
simulation_status = COMPLETED
```

or an explicitly valid terminal status that still produces a well-defined outcome.

---

# 78. Terminal Outcome With Open Position

At horizon end, the simulator may have:

```text
open asset
```

The portfolio must be marked to market using the defined valuation methodology.

The resulting:

```text
realized_pnl
unrealized_pnl
total_pnl
```

must remain distinguishable.

---

# 79. No Artificial Liquidation

The simulator must not automatically sell all assets at horizon end unless:

```text
label definition explicitly requires terminal liquidation
```

Instead the label specification determines whether:

```text
end-of-horizon valuation
```

or:

```text
terminal liquidation
```

is used.

---

# 80. Simulation Audit Trail

Every research simulation should be auditable from:

```text
Simulation ID
↓
Market Data
↓
Blueprint
↓
Execution Model
↓
Events
↓
Portfolio State
↓
Outcome
↓
Labels
```

This is essential for debugging ML labels.

---

# 81. Non-Negotiable Rules

1. The simulator is deterministic.
2. The simulator models our actual Grid Strategy, not a generic grid.
3. Grid spacing is uniform within each Section.
4. Section Gaps may differ.
5. BUY is immediate execution.
6. SELL is immediate execution.
7. Spot-only inventory rules apply.
8. No shorting or leverage.
9. Buy and Sell execution costs are modeled separately.
10. Fees, spread, and slippage are never double-counted.
11. Monthly/Weekly/Daily market context must be reconstructed causally.
12. Future data must never influence decisions before it occurs.
13. OHLC ambiguity must not be silently fabricated.
14. Invalid simulations are not negative labels.
15. Every simulation is versioned.
16. Every event is auditable.
17. Blueprint identity is preserved.
18. Capital reserves and Section allocations are explicit.
19. Recovery is observed, never assumed.
20. Cheap prices do not automatically equal successful outcomes.
21. Candidate Blueprints may be compared, but each simulation uses a fixed valid Blueprint unless dynamic reconfiguration is explicitly being tested.
22. Production execution is outside the simulator's responsibility.

---

# 82. Final Simulator Definition

The AI Research Grid Simulator is:

> **A deterministic historical execution environment that reproduces the behavior of the actual Section-based, uniform-grid, adaptive-Section-Gap, immediate-execution spot Grid Strategy across historical market data and execution economics, producing auditable strategy states and outcomes for Grid Behavior analysis and ML label generation.**

Its core workflow is:

```text
Historical Market Data
        +
Valid Candidate Blueprint
        +
Execution Economics
        +
Strategy Rules
        ↓
DETERMINISTIC GRID SIMULATOR
        ↓
BUY / SELL EVENTS
        ↓
SECTION + GRID STATE
        ↓
CAPITAL / POSITION STATE
        ↓
NET P&L / DRAWDOWN / RECOVERY
        ↓
SIMULATION RESULT
        ↓
GRID BEHAVIOR
+
ML LABELS
```

The simulator is the bridge between:

```text
Research Features
```

and:

```text
Historical Ground Truth
```

It must therefore be treated as a core research infrastructure component, not as a convenience backtest script.
