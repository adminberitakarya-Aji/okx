# AI Trading Grid Workflow

Version: 1.0

Status: Foundation Draft

---

# 1. Purpose

`AI_TRADING_GRID_WORKFLOW.md` defines the end-to-end workflow for the AI Trading Grid system.

The system is a crypto spot trading strategy built around a hierarchical grid structure:

- Grid is divided into Sections.
- Grid spacing inside each Section is uniform.
- Section Gaps between Sections can be different and adaptive.
- BUY and SELL use immediate execution rather than passive limit-order queuing.
- AI determines strategic structure and recommendations.
- Deterministic engines calculate, simulate, validate, and execute the resulting strategy.
- Net profitability must account for both BUY-side and SELL-side execution economics.

This document defines the workflow before implementation of individual AI modules.

---

# 2. Core Strategy Definition

The system is not a conventional uniform grid.

The basic structure is:

```text
GRID STRATEGY
│
├── SECTION 1
│   ├── Grid 1
│   ├── Grid 2
│   ├── Grid 3
│   └── ...
│
├── SECTION 2
│   ├── Grid 1
│   ├── Grid 2
│   ├── Grid 3
│   └── ...
│
└── SECTION 3
    ├── Grid 1
    ├── Grid 2
    ├── Grid 3
    └── ...
```

Each Section has its own:

- Capital allocation
- Price range
- Number of grids
- Uniform grid spacing
- Section-level risk parameters

Between Sections there is a Section Gap.

---

# 3. Grid Spacing Rule

Grid spacing inside a Section MUST be uniform.

Example:

```text
SECTION 1

100
 ↓ 1%
99
 ↓ 1%
98
 ↓ 1%
97
 ↓ 1%
96
```

If Section 1 uses 1% grid spacing, all grids inside Section 1 use the same spacing.

The system MUST NOT treat every individual grid as an independently optimized spacing parameter.

This constraint provides:

- Predictable structure
- Simpler deterministic calculation
- Easier backtesting
- Clearer strategy explanation
- Lower strategy complexity

---

# 4. Section Gap Rule

Section Gap is the distance between the end of one Section and the beginning of the next Section.

Section Gaps do NOT need to be equal.

Example:

```text
SECTION 1
100
99
98
97
96

       ↓ 5% GAP

SECTION 2
91
90
89
88
87

       ↓ 10% GAP

SECTION 3
78
77
76
75
74
```

The Section Gap is intentionally designed to provide additional deployment zones when the market experiences a deeper decline.

Therefore:

```text
Grid Spacing
    = Uniform within a Section

Section Gap
    = Adaptive between Sections
```

This distinction is a fundamental characteristic of the strategy.

---

# 5. Capital Allocation

Capital is distributed across Sections rather than deployed uniformly across the entire price range.

Example:

```text
Capital = $1,000

Section 1 = 30%
Section 2 = 35%
Section 3 = 35%
```

The allocation may be determined by the AI strategy workflow and constrained by the Risk Engine.

The purpose is to preserve capital for deeper market movements.

The system should maintain awareness of:

- Capital deployed
- Capital remaining
- Capital reserved for future Sections
- Current exposure
- Maximum planned exposure

---

# 6. Immediate Execution Model

The system does not rely on a conventional passive limit-order grid.

Traditional grid behavior:

```text
Place Limit Order
       ↓
Wait for Market
       ↓
Price Reaches Order
       ↓
Order Fills
```

Our execution model:

```text
Market Condition
       ↓
Grid/Strategy Condition
       ↓
Execution Decision
       ↓
Immediate BUY / SELL
```

## 6.1 First Position Entry Rule (IMMEDIATE FIRST ENTRY)

When a grid is activated (started), the system executes an **immediate MARKET BUY** at the anchor level (Section 1, Level 0) to establish an initial position. This is NOT a queued limit order — it executes immediately at the current real-time market price.

```text
GRID ACTIVATION
       ↓
Fetch Current Market Price
       ↓
Execute MARKET BUY at Anchor Level
       ↓
Mark Anchor Level as FILLED
       ↓
Grid Starts with Initial Position
```

Key behaviors:

- **Anchor Level**: `blueprint.sections[0].levels[0]` (highest price level in Section 1)
- **Order Type**: MARKET order (immediate execution, not limit order)
- **Idempotency Key**: `{grid_id}:INITIAL_ENTRY` (prevents duplicate execution on retry)
- **On Success**: Anchor level marked `FILLED` with actual fill price as `entry_price`
- **On Failure**: Grid still starts without initial position (graceful degradation)

This immediate first entry provides the grid with an initial position to trade against. Subsequent level triggers use crossing detection (see Section 6.2).

## 6.2 Crossing Detection for Subsequent Levels

After the initial entry, subsequent BUY/SELL triggers use **crossing detection**:

```text
Price Crossing DOWN through unfilled level → BUY trigger
Price Crossing UP through filled level → SELL trigger
```

**Fill-State Guard** (prevents double-execution):

- BUY only triggers if the level is NOT filled (no open position at that level)
- SELL only triggers if the level IS filled (has a position to sell)

This ensures:

1. No double-buy on already-filled levels when price oscillates
2. No selling levels that have no open position (spot-only, no shorting)
3. Each level maintains at most one open position at a time

The internal architecture should use provider-independent terminology such as:

- Immediate Execution
- Market Execution
- Taker Execution

The term "swap" may be used when describing DEX behavior, but it should not become the core architecture terminology.

Provider adapters translate the generic execution instruction into provider-specific execution mechanisms.

Example:

```text
Strategy Engine
      │
      ▼
Immediate Execution
      │
 ┌────┼─────┐
 ▼    ▼     ▼
OKX  CEX   DEX
 │          │
Market      Swap
Buy/Sell
```

---

# 7. Why Immediate Execution Changes the AI Problem

The system does not only need to determine:

> Where should an order exist?

It must determine:

> When is an immediate execution economically justified?

Therefore the AI workflow must evaluate:

- Current market condition
- Expected movement
- Grid level
- Position state
- Execution cost
- Expected exit price
- Expected net P&L
- Risk
- Available capital

A BUY or SELL decision must not be based only on gross price movement.

---

# 8. Execution Economics

Immediate execution creates execution costs that must be included in strategy decisions.

The system must model BUY and SELL sides separately.

## 8.1 BUY Side

```text
BUY EXECUTION

Buy Cost
+ Buy Fee
+ Buy Slippage
+ Other Buy-side Costs

= Effective Buy Cost
```

## 8.2 SELL Side

```text
SELL EXECUTION

Sell Proceeds
- Sell Cost
- Sell Fee
- Sell Slippage
- Other Sell-side Costs

= Effective Sell Proceeds
```

The implementation must avoid double-counting spread and slippage.

If spread is already represented by the execution price model, it must not be added again as a separate cost.

---

# 9. Net P&L Model

The conceptual Net P&L model is:

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

The actual deterministic implementation should derive the final calculation from the execution model so that:

- Buy-side costs are accounted for once.
- Sell-side costs are accounted for once.
- Spread is not double-counted.
- Slippage is not double-counted.
- Provider-specific fees are represented correctly.

The fundamental rule is:

> A trade is profitable only when the expected or realized Net P&L is positive after execution costs.

---

# 10. Minimum Profitable Exit

Each position should have a calculated Minimum Profitable Exit Price.

Conceptually:

```text
Entry
  ↓
Buy-side execution economics
  ↓
Position cost basis
  ↓
Expected sell-side execution economics
  ↓
Minimum profitable exit
```

Example:

```text
Entry Price = $100

Estimated total execution costs
= 0.55%

Minimum Profitable Exit
> $100.55
```

Therefore:

```text
Current Price = $100.30
→ Not yet economically profitable

Current Price = $101.00
→ Potentially profitable
→ Continue through strategy/risk evaluation
```

The system must never classify a position as profitable solely because:

```text
Sell Price > Buy Price
```

---

# 11. AI Workflow Overview

The complete workflow is:

```text
MARKET DATA
     │
     ▼
MARKET INTELLIGENCE
     │
     ▼
REGIME DETECTION
     │
     ▼
OPPORTUNITY SCORING
     │
     ▼
CAPITAL PLANNING
     │
     ▼
SECTION OPTIMIZATION
     │
     ▼
GRID OPTIMIZATION
     │
     ▼
EXECUTION ECONOMICS
     │
     ▼
STRATEGY BLUEPRINT
     │
     ▼
DETERMINISTIC CALCULATION
     │
     ▼
WHAT-IF SIMULATION
     │
     ▼
RISK VALIDATION
     │
 ┌───┴────┐
 │        │
FAIL     PASS
 │        │
 ▼        ▼
REPLAN   APPROVAL/POLICY
          │
          ▼
     GRID ENGINE
          │
          ▼
   EXECUTION ENGINE
          │
          ▼
      EXCHANGE
          │
          ▼
   LIVE MONITORING
          │
          ▼
    AI FEEDBACK LOOP
```

---

# 12. AI Job 1 — Market Intelligence

Market Intelligence collects and interprets market information.

Inputs may include:

- Price
- OHLCV
- Volume
- Volatility
- ATR
- Spread
- Liquidity
- Market depth
- Momentum
- Trend indicators
- Historical behavior
- Relevant market context

Outputs:

```text
Market Intelligence State
```

The output should be structured data rather than free-form text whenever possible.

---

# 13. AI Job 2 — Regime Detection

Regime Detection classifies the current market environment.

Possible regimes include:

- Bullish
- Bearish
- Sideways
- High Volatility
- Low Volatility
- Volatility Expansion
- Volatility Contraction
- Transition
- Extreme/Abnormal Conditions

The exact regime taxonomy is implementation-dependent and must be validated through research/backtesting.

Output:

```text
Market Regime
Confidence
Supporting Factors
Risk Flags
```

---

# 14. AI Job 3 — Opportunity Scoring

The Opportunity layer determines whether the current market condition is suitable for the strategy.

Possible factors:

- Expected price range
- Volatility
- Liquidity
- Historical behavior
- Execution economics
- Recovery potential
- Risk/reward
- Expected net profitability

Output:

```text
Opportunity Score
Strategy Suitability
Risk Flags
```

A high-volatility market is NOT automatically considered a good grid opportunity.

The system must determine whether the expected movement is large enough to overcome execution costs.

---

# 15. AI Job 4 — Capital Planning

Capital Planning determines how available capital should be distributed across Sections.

Example:

```text
Capital = $1,000

Section 1 = 30%
Section 2 = 35%
Section 3 = 35%
```

The AI may recommend a different allocation depending on market regime and risk.

The deterministic Risk Engine must enforce:

- Maximum capital usage
- Maximum exposure
- Reserve requirements
- User-defined limits
- Strategy constraints

---

# 16. AI Job 5 — Section Optimization

Section Optimization determines:

- Number of Sections
- Allocation per Section
- Section price ranges
- Section Gaps
- Section activation conditions

The key principle is:

> Section Gaps are allowed to differ.

The AI may produce:

```text
Section 1 → Section 2 Gap = 5%
Section 2 → Section 3 Gap = 10%
Section 3 → Section 4 Gap = 15%
```

These values are examples only.

Actual values must be calculated and validated from market data, volatility, expected drawdown, liquidity, capital availability, and execution economics.

---

# 17. AI Job 6 — Grid Optimization

Grid Optimization determines parameters inside each Section.

For each Section:

```text
Section
├── Grid Count
├── Uniform Grid Spacing
├── Price Range
├── Capital Allocation
└── Execution Parameters
```

Important constraint:

> Grid spacing inside a Section is uniform.

Example:

```text
Section 1
Grid Spacing = 1%

100
99
98
97
96
```

The AI may choose a different uniform spacing for another Section:

```text
Section 2
Grid Spacing = 1.5%

91
89.65
88.30
86.97
```

The difference between Sections is allowed.

The spacing of individual grids within the same Section is not independently optimized.

---

# 18. Execution Economics Evaluation

Before finalizing a strategy, the system evaluates whether its grid structure is economically viable.

The evaluation must consider:

- Buy cost
- Sell cost
- Buy fee
- Sell fee
- Spread
- Slippage
- Other execution costs
- Expected movement
- Expected net P&L

Example comparison:

```text
Grid Spacing = 0.5%
Grid Spacing = 1.0%
Grid Spacing = 2.0%
Grid Spacing = 3.0%
```

The system evaluates whether each spacing provides sufficient expected net return after execution costs.

Therefore:

> Grid spacing is not selected solely from volatility.

It must also satisfy economic viability.

---

# 19. Strategy Blueprint

After AI analysis, the system produces a Strategy Blueprint.

Conceptual structure:

```text
Strategy Blueprint
│
├── Asset
├── Capital
├── Market Regime
├── Opportunity Score
│
├── Section 1
│   ├── Allocation
│   ├── Price Range
│   ├── Grid Count
│   ├── Uniform Grid Spacing
│   └── Section Gap to Section 2
│
├── Section 2
│   ├── Allocation
│   ├── Price Range
│   ├── Grid Count
│   ├── Uniform Grid Spacing
│   └── Section Gap to Section 3
│
└── Section 3
    ├── Allocation
    ├── Price Range
    ├── Grid Count
    └── Uniform Grid Spacing
```

The Blueprint is a strategic proposal.

It is not yet an executable order set.

---

# 20. Deterministic Calculation

The Blueprint is passed to deterministic calculation engines.

They calculate:

- Exact grid prices
- Exact Section boundaries
- Order size
- Capital per grid
- Exposure
- Fees
- Slippage estimates
- Spread estimates
- Break-even prices
- Minimum profitable exits
- Expected P&L
- Maximum exposure
- Other strategy metrics

The deterministic layer must not reinterpret the AI strategy.

Its role is to calculate and enforce constraints.

---

# 21. What-If Simulation

Every candidate Strategy Blueprint should be tested against multiple market scenarios.

Example:

```text
Scenario A
Market declines 5%

Scenario B
Market declines 10%

Scenario C
Market declines 15%

Scenario D
Market declines 30%
```

The simulation evaluates:

- Which Sections activate
- Capital deployed
- Capital remaining
- Position exposure
- Average entry
- Expected recovery
- Drawdown
- Net P&L
- Remaining defensive capacity
- Execution cost
- Risk limits

The goal is to determine whether the Section architecture actually protects capital during deeper market declines.

---

# 22. Risk Validation

The candidate strategy passes through deterministic Risk Validation.

Validation checks may include:

- Maximum capital allocation
- Maximum exposure
- Maximum drawdown
- Minimum reserve capital
- Minimum profitable exit
- Minimum expected net P&L
- Maximum acceptable execution cost
- Maximum slippage assumption
- Section constraints
- Grid constraints
- User-defined limits

Result:

```text
PASS
```

or:

```text
FAIL
```

If FAIL:

```text
FAIL
 ↓
Identify Constraint
 ↓
Replan / Recalculate
 ↓
Simulation
 ↓
Risk Validation
```

The system must not execute a strategy that fails mandatory risk constraints.

---

# 23. Approval and Execution Policy

Depending on the configured operating mode, a validated strategy may require user approval before execution.

Conceptually:

```text
AI Recommendation
       ↓
Blueprint
       ↓
Calculation
       ↓
Simulation
       ↓
Risk Validation
       ↓
Approval / Policy
       ↓
Execution
```

The AI should not bypass deterministic validation.

---

# 24. Grid Engine

The Grid Engine receives the validated Strategy Blueprint.

Its responsibilities include:

- Tracking Sections
- Tracking Grid states
- Tracking capital allocation
- Tracking activated grids
- Tracking positions
- Determining eligible execution events
- Maintaining strategy state

The Grid Engine is deterministic.

It does not independently invent strategy parameters.

---

# 25. Immediate Execution Engine

When an eligible grid condition is reached, the Execution Engine determines the immediate execution action.

Conceptually:

```text
Grid Condition
      ↓
Execution Decision
      ↓
Execution Economics Check
      ↓
Risk Check
      ↓
Immediate BUY / SELL
```

The execution layer records:

- Requested price
- Executed price
- Quantity
- Fee
- Slippage
- Spread/price impact where available
- Timestamp
- Provider response
- Realized P&L

---

# 26. Exchange Adapter

The strategy layer remains provider-independent.

Example:

```text
Strategy
   ↓
Immediate Execution Request
   ↓
Exchange Adapter
   ├── OKX
   ├── Binance
   └── Future Providers
```

OKX is currently a priority integration candidate.

The adapter translates the generic execution model into provider-specific API operations.

---

# 27. Live Monitoring

Once the strategy is active, the system continuously monitors:

- Market price
- Volatility
- Liquidity
- Spread
- Execution quality
- Positions
- Capital
- Active Sections
- Activated Grids
- Realized P&L
- Unrealized P&L
- Net P&L
- Drawdown
- Remaining reserve

---

# 28. AI Live Strategy Intelligence

The AI monitors the difference between:

```text
EXPECTED
vs.
ACTUAL
```

Examples:

```text
Expected Slippage
vs.
Actual Slippage

Expected Volatility
vs.
Actual Volatility

Expected Execution Cost
vs.
Actual Execution Cost

Expected Net P&L
vs.
Actual Net P&L
```

The AI may identify:

- Normal conditions
- Warning
- Strategy degradation
- Recalculation candidate
- Emergency condition

---

# 29. Feedback Loop

The system creates a continuous feedback loop:

```text
STRATEGY
   ↓
EXECUTION
   ↓
RESULT
   ↓
OBSERVATION
   ↓
AI ANALYSIS
   ↓
RECOMMENDATION
   ↓
VALIDATION
   ↓
UPDATED STRATEGY
```

The AI must learn from actual execution behavior, especially:

- Real fees
- Real slippage
- Real spread
- Actual fills
- Actual market behavior
- Actual strategy performance

The feedback loop must not directly modify production strategy logic without validation.

---

# 30. AI vs Deterministic Responsibility

## AI Responsibilities

AI may:

- Interpret market conditions
- Detect regime
- Score opportunities
- Recommend capital allocation
- Recommend Section structure
- Recommend Section Gaps
- Recommend uniform grid spacing per Section
- Evaluate strategy alternatives
- Identify risk conditions
- Analyze historical performance
- Recommend strategy changes

## Deterministic Responsibilities

Deterministic engines must:

- Calculate prices
- Calculate order sizes
- Calculate fees
- Calculate execution economics
- Calculate P&L
- Calculate exposure
- Run simulations
- Enforce risk constraints
- Validate strategy
- Manage state
- Execute orders

Core principle:

> AI determines strategic intent. Deterministic systems determine mathematical correctness and execution safety.

---

# 31. Core AI Workflow

The complete logical flow is:

```text
                    MARKET DATA
                         │
                         ▼
                MARKET INTELLIGENCE
                         │
                         ▼
                 REGIME DETECTION
                         │
                         ▼
                OPPORTUNITY SCORING
                         │
                         ▼
                 CAPITAL PLANNING
                         │
                         ▼
                SECTION OPTIMIZATION
                         │
                         ▼
                  GRID OPTIMIZATION
                         │
                         ▼
              EXECUTION ECONOMICS
                         │
                         ▼
                 STRATEGY BLUEPRINT
                         │
                         ▼
              DETERMINISTIC ENGINE
                         │
                         ▼
                 WHAT-IF SIMULATION
                         │
                         ▼
                  RISK VALIDATION
                         │
                    ┌────┴────┐
                    │         │
                  FAIL       PASS
                    │         │
                    ▼         ▼
                  REPLAN    APPROVAL
                              │
                              ▼
                         GRID ENGINE
                              │
                              ▼
                     EXECUTION ENGINE
                              │
                              ▼
                           EXCHANGE
                              │
                              ▼
                       LIVE MONITORING
                              │
                              ▼
                         AI FEEDBACK
                              │
                              └──────────►
                                  Strategy Intelligence
```

---

# 32. Non-Negotiable Strategy Rules

The following rules are foundational.

## Rule 1

Grid spacing inside a Section is uniform.

## Rule 2

Section Gaps may differ between Sections.

## Rule 3

Section Gaps exist partly to preserve capital deployment capacity during deeper market declines.

## Rule 4

BUY and SELL use immediate execution.

## Rule 5

The system does not depend on passive limit-order queuing.

## Rule 6

BUY-side execution costs must be modeled.

## Rule 7

SELL-side execution costs must be modeled.

## Rule 8

Sell Cost must be explicitly accounted for.

## Rule 9

Net P&L, not gross price movement, determines economic profitability.

## Rule 10

Spread and slippage must not be double-counted.

## Rule 11

AI does not bypass deterministic validation.

## Rule 12

AI recommendations are not automatically equivalent to executable orders.

## Rule 13

Provider-specific execution logic belongs inside Exchange Adapters.

## Rule 14

The strategy core remains provider-independent.

---

# 33. Target System Philosophy

The system is not designed as:

```text
AI → Trade
```

It is designed as:

```text
AI
 ↓
Understand Market
 ↓
Design Strategy
 ↓
Calculate
 ↓
Simulate
 ↓
Validate
 ↓
Execute
 ↓
Observe
 ↓
Learn
```

The central objective is:

> Build an AI-assisted trading system that can adapt the structure of hierarchical spot grids while preserving deterministic calculation, economic viability, risk control, and immediate execution discipline.

---

# 34. Future Module Breakdown

This workflow should later be decomposed into dedicated specifications.

Potential future documents/modules:

```text
AI Market Intelligence
AI Regime Detection
AI Opportunity Scoring
AI Capital Planner
AI Section Optimizer
AI Grid Optimizer
Execution Economics Engine
Strategy Blueprint Engine
Simulation Engine
Risk Validation Engine
Grid Engine
Immediate Execution Engine
Live Strategy Intelligence
Feedback / Research Engine
Exchange Adapter
```

These modules must be derived from this workflow rather than independently redefining the strategy.

---

# 35. Final Architectural Principle

The defining architecture is:

```text
                    AI STRATEGY INTELLIGENCE
                              │
                              ▼
                     STRATEGY BLUEPRINT
                              │
                    ┌─────────┴─────────┐
                    │                   │
             DETERMINISTIC          SIMULATION
             CALCULATION                │
                    │                   │
                    └─────────┬─────────┘
                              ▼
                       RISK VALIDATION
                              │
                              ▼
                         GRID ENGINE
                              │
                              ▼
                   IMMEDIATE EXECUTION
                              │
                              ▼
                    EXCHANGE / DEX
                              │
                              ▼
                       LIVE RESULTS
                              │
                              ▼
                     AI FEEDBACK LOOP
```

The system's unique strategic identity is therefore:

**Hierarchical Sections + Uniform Grid Spacing Within Each Section + Adaptive Section Gaps + Immediate Execution + Execution-Cost-Aware Net P&L + AI Strategy Intelligence.**
