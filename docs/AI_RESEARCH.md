# AI Research

Version: 1.0

Status: Foundation

---

# 1. Purpose

`AI_RESEARCH.md` defines the conceptual role, scope, boundaries, and workflow of the AI Research system within the AI Trading Grid platform.

AI Research is responsible for researching the market universe, identifying markets suitable for the Grid Strategy, learning from historical market and trading data, and producing market recommendations.

AI Research is not the direct trading executor.

Its primary output is:

> **Market Recommendation**

The recommendation becomes an input to the Realtime AI / Grid Blueprint workflow.

---

# 2. Core Objective

# 3. Research Universe — Top 10 Eligible OKX Spot Markets

AI Research does not research every market available on OKX.

The initial Research Universe is:

```text
OKX SPOT MARKETS
      ↓
ELIGIBILITY FILTER
      ↓
UNIVERSE RANKING
      ↓
TOP 10 ELIGIBLE MARKETS
      ↓
AI RESEARCH
```

The Top 10 universe is dynamic and must be refreshed according to a deterministic research-universe policy.

At each historical observation time `T`, the system must reconstruct:

```text
Eligible Markets at T
      ↓
Ranking at T
      ↓
Top 10 at T
```

The system MUST NOT apply today's Top 10 retroactively to historical periods. This prevents survivorship bias.

The exact eligibility and ranking policy must be versioned.

The Top 10 rule limits the **AI Research universe**; it does not limit or redefine the reusable provider-independent feature specifications.

The objective of AI Research is to answer:

> **Which market is currently most suitable for our Grid Strategy, and why?**

The system should not simply rank assets based on price performance.

It must evaluate suitability according to the actual characteristics of our strategy:

```text
Liquidity
+
Volatility
+
Market Structure
+
Trend
+
Range Behavior
+
Timeframe Context
+
Price Position
+
Execution Economics
+
Capital Efficiency
+
Historical Grid Behavior
```

The goal is to find markets where the strategy has a reasonable structural and economic opportunity.

---

# 3. AI Research Is Not a Trading Signal Engine

AI Research should not primarily produce:

```text
BUY BTC
SELL ETH
```

Instead it produces:

```text
BTC
Grid Suitability: HIGH

ETH
Grid Suitability: MEDIUM

SOL
Grid Suitability: LOW
```

with supporting reasoning and measurable factors.

The recommendation answers:

> **Which market deserves attention from the Grid Strategy?**

The Realtime AI then answers:

> **Given the current market state, what Grid Blueprint should be used?**

---

# 4. Relationship With Realtime AI

```text
AI RESEARCH
    |
    | researches market
    | learns from history
    | evaluates suitability
    v
MARKET RECOMMENDATION
    |
    v
REALTIME AI
    |
    | reads current market state
    | compares realtime price
    | evaluates timeframe structure
    | evaluates trend
    v
GRID BLUEPRINT
```

AI Research provides market intelligence and recommendation.

Realtime AI performs the operational interpretation of the selected market.

---

# 5. Relationship With Deterministic Core

AI Research may recommend a market or identify a potentially favorable strategy condition.

It does not bypass deterministic validation.

```text
AI Research
    |
    v
Market Recommendation
    |
    v
Realtime AI
    |
    v
Strategy Blueprint
    |
    v
Deterministic Calculation
    |
    v
Simulation
    |
    v
Risk Validation
    |
    v
Execution
```

Deterministic systems remain responsible for mathematical correctness, execution economics, risk constraints, and execution safety.

---

# 6. Market Discovery

AI Research begins with the available market universe.

```text
MARKET UNIVERSE
      |
      v
INITIAL SCREENING
      |
      v
LIQUIDITY FILTER
      |
      v
VOLUME FILTER
      |
      v
EXECUTION COST FILTER
      |
      v
CANDIDATE MARKETS
```

Possible screening factors include:

- Liquidity
- Trading volume
- Spread
- Market depth
- Volatility
- Execution cost
- Availability
- Historical data quality
- Exchange support

Exact thresholds belong to the technical design.

---

# 7. Market Research

Candidate markets receive deeper analysis.

```text
Market
  |
  v
Monthly Structure
  |
  v
Weekly Structure
  |
  v
Daily Structure
  |
  v
Trend
  |
  v
Volatility
  |
  v
Price Position
  |
  v
Execution Economics
  |
  v
Historical Behavior
```

The objective is to understand market character rather than merely predict the next candle.

---

# 8. Multi-Timeframe Market Structure

Monthly, Weekly, and Daily candles are core market-context data.

```text
MONTHLY
    |
    v
WEEKLY
    |
    v
DAILY
```

## Monthly

Provides macro structural context:

- Monthly High
- Monthly Low
- Monthly Open
- Monthly Close
- Range
- Body
- Upper Wick
- Lower Wick
- Historical Monthly Levels
- Volatility
- Structural position

## Weekly

Provides medium-term structural resolution:

- Weekly High
- Weekly Low
- Weekly Open
- Weekly Close
- Range
- Recent swing structure
- Weekly volatility
- Weekly trend
- Weekly support/resistance areas

## Daily

Provides operational resolution:

- Daily High
- Daily Low
- Daily Open
- Daily Close
- Daily range
- Daily trend
- Daily volatility
- Recent price structure
- Local support/resistance

---

# 9. Realtime Price Context

Historical candles alone are not sufficient.

Realtime price must continuously be compared with important timeframe levels.

```text
REALTIME PRICE
      |
      +-- Distance to Monthly High
      +-- Distance to Monthly Low
      +-- Distance to Weekly High
      +-- Distance to Weekly Low
      +-- Distance to Daily High
      +-- Distance to Daily Low
```

The system must understand:

> **Where is the current price relative to the structure of the market?**

---

# 10. Monthly Proximity Principle

Monthly High and Monthly Low are strategic reference levels.

They are not automatically permanent support or resistance.

Example:

```text
Monthly Low = 90
Realtime Price = 92
```

The system recognizes that price is approaching the Monthly Low.

This should not automatically produce:

```text
WARNING
NO GRID
```

Instead it should trigger deeper structural analysis:

```text
PRICE APPROACHES MONTHLY LOW
             |
             v
      INCREASE ANALYSIS
          RESOLUTION
             |
             v
          WEEKLY
             |
             v
          DAILY
             |
             v
     BLUEPRINT REFINEMENT
```

---

# 11. Monthly Low as Strategic Opportunity

For a spot accumulation grid, approaching or breaking a Monthly Low can create an opportunity to acquire more coin at lower prices.

```text
Monthly Low
     |
     v
Price approaches
     |
     v
Weekly structure evaluated
     |
     v
Price breaks Monthly Low
     |
     v
Deeper Section becomes relevant
     |
     v
Lower acquisition price
     |
     v
Potentially more coin per unit of capital
```

However, the system must respect:

- Maximum capital deployment
- Maximum exposure
- Risk limits
- Reserve capital
- Maximum drawdown
- Strategy constraints

Lower price is an opportunity, not a guarantee of recovery.

---

# 12. Hierarchical Resolution Principle

Monthly, Weekly, and Daily are not three independent indicator stacks.

They form a hierarchy:

```text
MONTHLY
Macro Context
     |
     v
Realtime Price Proximity
     |
     v
WEEKLY
Structural Refinement
     |
     v
DAILY
Operational Refinement
     |
     v
GRID BLUEPRINT
```

The deeper the price moves into an important structural area, the more detailed the analysis becomes.

---

# 13. Trend Analysis

Trend analysis is an additional confirmation layer.

Trend does not automatically determine:

```text
GRID
or
NO GRID
```

Instead it modifies market interpretation.

Conceptual output:

```text
Trend Direction:
BULLISH / BEARISH / NEUTRAL

Trend Strength:
WEAK / MODERATE / STRONG

Trend Alignment:
ALIGNED / MIXED
```

Trend may influence:

- Market recommendation
- Grid suitability
- Capital allocation recommendation
- Section Gap recommendation
- Grid spacing recommendation
- Reserve capital recommendation

Trend is contextual, not a standalone trading signal.

---

# 14. Grid Suitability

The central research question is:

> **Is this market suitable for our particular Grid Strategy?**

Grid Suitability should consider:

```text
Liquidity
+
Volatility
+
Range Behavior
+
Structure
+
Trend
+
Price Position
+
Execution Economics
+
Historical Strategy Performance
```

A market may be highly volatile but unsuitable if execution costs consume expected grid profit.

A market may trend strongly but still be suitable for a defensive accumulation structure.

---

# 15. Execution Economics in Research

Because the strategy uses immediate execution, AI Research must include execution economics.

Important factors include:

```text
Buy Cost
Buy Fee
Buy Slippage

Sell Cost
Sell Fee
Sell Slippage

Spread
Other Execution Costs
```

Conceptually:

```text
Expected Gross Movement
        |
        v
Execution Costs
        |
        v
Expected Net P&L
        |
        v
Grid Suitability
```

A market with excellent volatility but poor execution economics should not automatically receive a high recommendation.

---

# 16. Capital Efficiency

AI Research should evaluate:

- How much coin can be accumulated at lower prices
- How quickly price moves through grid levels
- Historical drawdowns
- Reserve capital requirements
- Effect on average acquisition price
- Exposure before recovery

This is important because the strategy intentionally uses multiple Sections.

---

# 17. Section-Aware Research

AI Research must understand the Grid Strategy:

```text
Section
 ├── Uniform Grid Spacing
 ├── Capital Allocation
 └── Price Range

Section Gap
 └── Adaptive distance to next Section
```

Research should evaluate compatibility with:

- Multiple deployment Sections
- Uniform grid spacing inside each Section
- Different Section Gaps
- Deep drawdowns
- Immediate execution
- Reserve capital

---

# 18. Market Recommendation

The primary output is a Market Recommendation.

Conceptually:

```text
Market
Grid Suitability
Confidence
Risk Profile
Market Regime
Trend
Volatility
Structure
Execution Economics
Reasoning
```

Example:

```text
BTC/USDT

Grid Suitability:
HIGH

Confidence:
0.88

Market Regime:
Corrective Bullish

Trend:
Weekly Bearish
Daily Bearish

Structure:
Near Monthly Low

Execution Economics:
Favorable

Recommendation:
HIGH PRIORITY
```

Exact scoring belongs to the technical design.

---

# 19. Market Ranking

When multiple markets are available:

```text
MARKET UNIVERSE
      |
      v
SCREENING
      |
      v
RESEARCH
      |
      v
GRID SUITABILITY
      |
      v
RANKING
      |
      v
TOP MARKETS
```

Ranking is based on suitability for the Grid Strategy, not simply expected price appreciation.

---

# 20. AI + ML Role

AI Research is the primary area where Machine Learning can be introduced.

ML can learn relationships between:

```text
Market Conditions
      |
      v
Grid Conditions
      |
      v
Execution
      |
      v
Actual Results
```

Potential learning targets include:

- Market suitability
- Volatility behavior
- Range behavior
- Trend behavior
- Breakdown behavior
- Recovery behavior
- Execution cost behavior
- Grid performance
- Capital efficiency
- Net P&L outcomes

---

# 21. Historical Dataset

The research dataset can combine:

## Market Data

- OHLCV
- Volume
- Volatility
- Spread
- Liquidity
- Market depth
- Monthly structure
- Weekly structure
- Daily structure
- Trend state

## Strategy Data

- Strategy Blueprint
- Section allocation
- Section Gap
- Grid spacing
- Grid count
- Capital deployment
- Exposure

## Execution Data

- Buy price
- Sell price
- Buy fee
- Sell fee
- Buy cost
- Sell cost
- Slippage
- Spread
- Other execution costs

## Outcome Data

- Net P&L
- Drawdown
- Recovery
- Number of executions
- Capital efficiency
- Coin accumulation
- Strategy outcome

---

# 22. Research Feedback Loop

```text
MARKET CONDITION
      |
      v
RESEARCH
      |
      v
RECOMMENDATION
      |
      v
BLUEPRINT
      |
      v
EXECUTION
      |
      v
RESULT
      |
      v
HISTORICAL DATASET
      |
      v
AI RESEARCH + ML
      |
      v
NEW INSIGHT
```

The system can learn which market characteristics have historically produced better outcomes for the specific Grid Strategy.

---

# 23. Research Must Not Directly Modify Production Strategy

AI Research may discover:

> Market X performs better when Section Gap increases under high weekly volatility.

It may produce a recommendation such as:

```text
Section Gap adjustment candidate
```

But it must not silently modify the production Grid Engine.

Any strategy change must pass through:

```text
Research Finding
      |
      v
Recommendation
      |
      v
Deterministic Validation
      |
      v
Backtest / Simulation
      |
      v
Human or Policy Approval
      |
      v
Production Strategy
```

---

# 24. Research vs Realtime AI

## AI Research

Question:

> **Which market is suitable and what have we learned from historical behavior?**

Focus:

- Market universe
- Historical analysis
- ML
- Pattern discovery
- Market ranking
- Market recommendation
- Strategy research

## Realtime AI

Question:

> **Given the current market state, how should the selected market's Grid Blueprint be structured?**

Focus:

- Realtime price
- Monthly proximity
- Weekly refinement
- Daily refinement
- Trend confirmation
- Section allocation
- Uniform grid spacing
- Adaptive Section Gap
- Current execution economics

---

# 25. Complete AI Architecture

```text
                         MARKET UNIVERSE
                               |
                               v
                     +-------------------+
                     |   AI RESEARCH     |
                     |      + ML         |
                     +---------+---------+
                               |
                    Market Recommendation
                               |
                               v
                     +-------------------+
                     |    REALTIME AI    |
                     | Market Context    |
                     | Proximity         |
                     | Trend             |
                     | Blueprint         |
                     +---------+---------+
                               |
                         Grid Blueprint
                               |
                               v
                     +-------------------+
                     | DETERMINISTIC     |
                     | CORE              |
                     | Calculation       |
                     | Simulation        |
                     | Risk              |
                     | Economics         |
                     +---------+---------+
                               |
                               v
                      IMMEDIATE EXECUTION
                               |
                               v
                           EXCHANGE
                               |
                               v
                         ACTUAL RESULTS
                               |
                               +-------------> AI RESEARCH + ML
```

---

# 26. Non-Negotiable Principles

1. AI Research is a market research and recommendation system.
2. AI Research does not directly execute trades.
3. AI Research does not silently modify production strategy.
4. Monthly, Weekly, and Daily structures are core market-context data.
5. Realtime price must be evaluated relative to timeframe structural levels.
6. Approaching a Monthly Low triggers deeper Weekly/Daily analysis.
7. A Monthly Low is a strategic reference, not automatically a no-trade boundary.
8. A break below a Monthly Low may create an opportunity for deeper accumulation.
9. Capital and exposure limits remain mandatory.
10. Trend is a confirmation/context layer, not an automatic trade blocker.
11. Grid suitability must include immediate-execution economics.
12. Net P&L is more important than gross price movement.
13. ML recommendations remain subject to deterministic validation.
14. Research findings remain separated from production execution logic.

---

# 27. Final Definition

AI Research is:

> **The market intelligence and machine-learning layer that continuously researches the available market universe, evaluates each market against the characteristics and economics of our hierarchical immediate-execution Grid Strategy, learns from historical market and trading outcomes, and produces ranked Market Recommendations for the Realtime AI Blueprint Engine.**

Its purpose is not to replace the Grid Engine.

Its purpose is to help the system answer:

> **Where should our Grid Strategy look, and what have we learned about the conditions in which it works best?**

The Realtime AI then answers:

> **Given the selected market and its current state, how should the Grid Blueprint be structured?**

The Deterministic Core then answers:

> **Is that blueprint mathematically and economically valid?**

The Execution Engine answers:

> **How do we execute it safely?**
