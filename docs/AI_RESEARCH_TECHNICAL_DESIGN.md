# AI Research Technical Design

Version: 1.0

Status: Technical Foundation

Related:
- `AI_RESEARCH.md`
- `AI_TRADING_GRID_WORKFLOW.md`

---

# 1. Purpose

`AI_RESEARCH_TECHNICAL_DESIGN.md` defines how AI Research is technically structured to research markets, evaluate Grid suitability, learn from historical outcomes, and produce Market Recommendations.

This document defines the technical architecture.

It does not lock a specific ML algorithm prematurely.

The design principle is:

```text
Data
  ↓
Feature
  ↓
Target / Label
  ↓
ML
  ↓
Prediction
  ↓
Recommendation
```

The system must be designed around the objective of the Grid Strategy rather than around a particular AI model.

---

# 2. Technical Objective

# 2. Research Universe — Top 10 Eligible OKX Spot Markets

The initial AI Research Universe is limited to the **Top 10 eligible OKX Spot markets**.

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
      ↓
DATASET / SIMULATION / ML
```

## 2.1 Dynamic Universe

The Top 10 list is dynamic. It must not be a permanently hard-coded list of symbols.

At each observation timestamp `T`:

```text
Eligible Markets at T
      ↓
Rank using information available at T
      ↓
Top 10 at T
```

Historical training must reconstruct the Top 10 membership at each historical observation. The current Top 10 must never be backfilled into all prior history.

## 2.2 Eligibility

Eligibility is deterministic and versioned. Potential criteria include:

```text
Spot market
Tradable
Supported quote asset
Sufficient liquidity
Sufficient volume
Sufficient historical data
Minimum market quality
```

Exact thresholds are defined by the Research Universe policy.

## 2.3 Ranking

After eligibility, markets are ranked using a deterministic Universe Ranking policy. Potential inputs include:

```text
Liquidity
Volume
Execution Quality
Data Quality
Market Availability
```

The ranking policy must be versioned.

## 2.4 Scope Boundary

Top 10 limits the **AI Research universe**. It does not redefine the feature layers. Market State, Execution Economics, Grid Behavior, and Derived ML specifications remain reusable and provider-independent.

The AI Research system must answer:

> **Which available market is most suitable for our Grid Strategy under the current and historically observed market conditions?**

It must combine:

```text
Market Data
+
Multi-Timeframe Structure
+
Realtime Price Context
+
Trend
+
Volatility
+
Liquidity
+
Execution Economics
+
Historical Grid Simulation
+
Historical Outcomes
+
ML
```

The final output is a ranked Market Recommendation.

---

# 3. High-Level Architecture

```text
                         MARKET UNIVERSE
                               |
                               v
                     +-------------------+
                     |  DATA INGESTION   |
                     +---------+---------+
                               |
                               v
                     +-------------------+
                     | DATA NORMALIZER   |
                     +---------+---------+
                               |
                               v
                     +-------------------+
                     |  FEATURE ENGINE   |
                     +---------+---------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
        STRUCTURE          TREND           VOLATILITY
              |                |                |
              +----------------+----------------+
                               |
                               v
                     +-------------------+
                     | PROXIMITY ENGINE  |
                     +---------+---------+
                               |
                               v
                     +-------------------+
                     | MARKET ANALYSIS   |
                     +---------+---------+
                               |
                               v
                  +---------------------------+
                  | EXECUTION ECONOMICS       |
                  +-------------+-------------+
                                |
                                v
                  +---------------------------+
                  | HISTORICAL GRID SIMULATOR |
                  +-------------+-------------+
                                |
                                v
                  +---------------------------+
                  | ML / RESEARCH ENGINE      |
                  +-------------+-------------+
                                |
                                v
                  +---------------------------+
                  | SUITABILITY ENGINE        |
                  +-------------+-------------+
                                |
                                v
                  +---------------------------+
                  | RECOMMENDATION + RANKING  |
                  +-------------+-------------+
                                |
                                v
                    REALTIME AI / BLUEPRINT
```

---

# 4. Design Principle: Modular Research Pipeline

AI Research must not be implemented as one monolithic AI model.

Each stage has a clear responsibility.

```text
Data Ingestion
    ↓
Normalization
    ↓
Feature Extraction
    ↓
Market Context
    ↓
Historical Simulation
    ↓
ML Research
    ↓
Suitability
    ↓
Recommendation
```

This makes the system:

- Testable
- Explainable
- Replaceable
- Versionable
- Backtestable
- Provider independent

---

# 5. Component 01 — Data Ingestion

Data Ingestion collects market and execution-related data.

## Market Data

Minimum conceptual data:

```text
OHLCV
Trades
Ticker
Order Book
Spread
Volume
Liquidity
```

## Timeframes

Core research timeframes:

```text
Monthly
Weekly
Daily
```

Additional lower timeframes may be collected for historical simulation and execution analysis.

## Exchange Data

The system should collect exchange-specific:

- Trading pair availability
- Trading rules
- Fee information
- Tick size
- Lot size
- Minimum order size
- Market depth
- Execution characteristics

The research layer must remain provider independent.

---

# 6. Component 02 — Data Normalizer

Different exchanges may represent data differently.

The Normalizer converts raw provider data into a common internal representation.

```text
Exchange Data
     ↓
Provider Adapter
     ↓
Normalized Market Data
```

The internal model must not depend on exchange-specific field names.

Examples:

```text
symbol
timestamp
open
high
low
close
volume
bid
ask
spread
depth
fee
```

The same normalized structure can then feed different exchanges.

---

# 7. Component 03 — Feature Engine

The Feature Engine converts raw market data into structured features.

Feature categories:

```text
Structure
Trend
Volatility
Price Position
Proximity
Liquidity
Execution Economics
Historical Grid Behavior
```

---

# 8. Multi-Timeframe Feature Set

## Monthly Features

```text
monthly_open
monthly_high
monthly_low
monthly_close
monthly_range
monthly_body
monthly_upper_wick
monthly_lower_wick
monthly_volatility
monthly_structure
```

## Weekly Features

```text
weekly_open
weekly_high
weekly_low
weekly_close
weekly_range
weekly_body
weekly_upper_wick
weekly_lower_wick
weekly_volatility
weekly_structure
```

## Daily Features

```text
daily_open
daily_high
daily_low
daily_close
daily_range
daily_body
daily_upper_wick
daily_lower_wick
daily_volatility
daily_structure
```

Exact feature formulas are defined in the Feature Specification stage.

---

# 9. Component 04 — Proximity Engine

The Proximity Engine determines where realtime price sits relative to important timeframe levels.

Example:

```text
Monthly Low = 90
Realtime Price = 92
```

The engine calculates:

```text
distance_to_monthly_low
```

Likewise:

```text
distance_to_monthly_high
distance_to_weekly_low
distance_to_weekly_high
distance_to_daily_low
distance_to_daily_high
```

A normalized representation may also be produced:

```text
distance_percent
distance_in_range
distance_in_volatility_units
```

The purpose is to answer:

> **How close is current price to an important structural reference?**

---

# 10. Monthly → Weekly → Daily Resolution Logic

This is a core strategy principle.

The system should not treat the three timeframes as independent signals.

Conceptually:

```text
MONTHLY CONTEXT
      ↓
REALTIME PRICE
      ↓
PROXIMITY TO MONTHLY LEVEL
      ↓
WEEKLY REFINEMENT
      ↓
DAILY REFINEMENT
```

When price approaches an important Monthly level, Weekly structure becomes increasingly important.

Daily then provides operational resolution.

Example:

```text
Monthly Low = 90
Price = 92
       ↓
Near Monthly Low
       ↓
Analyze Weekly structure
       ↓
Analyze Daily structure
       ↓
Research / Blueprint context
```

The exact proximity thresholds are implementation parameters and must be tested rather than assumed.

---

# 11. Component 05 — Market Structure Engine

Market Structure Engine transforms timeframe data into structural states.

Potential conceptual outputs:

```text
BULLISH
BEARISH
NEUTRAL
CORRECTIVE
EXPANDING
COMPRESSING
```

It may also identify:

- Swing highs
- Swing lows
- Structural ranges
- Breaks
- Rejections
- Expansion
- Compression

The engine should preserve raw measurements alongside interpreted states.

This allows ML to use either representation.

---

# 12. Component 06 — Trend Engine

Trend Engine evaluates:

```text
Monthly Trend
Weekly Trend
Daily Trend
```

Conceptual outputs:

```text
Trend Direction
Trend Strength
Trend Alignment
```

Example:

```text
Monthly = Bullish
Weekly  = Bearish
Daily   = Bearish

Alignment = Mixed
```

Trend is a confirmation/context feature.

It must not automatically produce:

```text
NO GRID
```

Instead it influences market suitability and blueprint recommendations.

The exact trend methodology remains open until the Trend Feature Specification is defined.

---

# 13. Component 07 — Volatility Engine

The Volatility Engine evaluates current and historical volatility.

Conceptual outputs:

```text
Current Volatility
Historical Volatility
Volatility Regime
Expansion
Compression
Volatility Percentile
```

Volatility is important because the strategy needs sufficient price movement to create grid opportunities while avoiding execution costs that consume the expected edge.

---

# 14. Component 08 — Liquidity and Execution Economics

The research engine must evaluate the actual economics of immediate execution.

Required concepts:

```text
Buy Cost
Buy Fee
Sell Cost
Sell Fee
Spread
Slippage
Other Execution Costs
```

The strategy's Net P&L model is:

```text
Net P&L =
Sell Proceeds
− Buy Cost
− Buy Fee
− Sell Cost
− Sell Fee
− Spread Cost
− Slippage
− Other Execution Costs
```

The implementation must avoid double-counting spread or slippage when they are already embedded in transaction prices.

---

# 15. Execution Opportunity Model

For research purposes, the system estimates:

```text
Expected Gross Opportunity
        ↓
Expected Execution Costs
        ↓
Expected Net Opportunity
```

This becomes an important market suitability factor.

A market can have:

```text
High Volatility
```

but still be unsuitable if:

```text
Execution Cost
>
Expected Grid Opportunity
```

---

# 16. Component 09 — Historical Grid Simulation Engine

This is a critical component.

AI Research must be able to test how the actual Grid Strategy would have behaved historically.

The simulator must understand:

```text
Sections
Uniform Grid Spacing
Section Gaps
Capital Allocation
Immediate BUY
Immediate SELL
Fees
Spread
Slippage
Other Execution Costs
```

The simulator must reproduce the strategy's economic behavior rather than using a generic grid model.

---

# 17. Section Model

Each Section contains:

```text
Section Range
Capital Allocation
Grid Count
Uniform Grid Spacing
```

Example:

```text
Section 1
Range: X → Y
Grid Spacing: Uniform

Section 2
Range: A → B
Grid Spacing: Uniform
```

Grid spacing inside a Section must remain uniform.

---

# 18. Section Gap Model

Section Gaps are independent from grid spacing.

```text
Section 1
    ↓
Section Gap 1
    ↓
Section 2
    ↓
Section Gap 2
    ↓
Section 3
```

Section Gaps may differ.

This allows deeper capital deployment when market price moves farther away from the original entry area.

Historical simulation must preserve this characteristic.

---

# 19. Immediate Execution Simulation

The simulator must model:

```text
BUY → immediate execution
SELL → immediate execution
```

It must not assume that an order waits passively in the order book like a conventional limit-order grid.

This distinction is essential because it directly affects:

- Execution price
- Spread
- Slippage
- Fees
- Net P&L

---

# 20. Historical Simulation Outputs

Minimum outputs should include:

```text
Net P&L
Gross P&L
Fees
Spread Cost
Slippage
Other Costs
Max Drawdown
Capital Utilization
Peak Exposure
Coin Accumulation
Average Acquisition Cost
Number of BUYs
Number of SELLs
Recovery Time
```

Additional metrics may be added during technical refinement.

---

# 21. ML Target Design

The ML model must not be selected before defining what it is supposed to learn.

Potential targets include:

## Target A — Grid Suitability

```text
Suitability Score
```

## Target B — Positive Net P&L Probability

```text
P(Net P&L > 0)
```

## Target C — Expected Net P&L

```text
Expected Net P&L
```

## Target D — Expected Drawdown

```text
Expected Maximum Drawdown
```

## Target E — Capital Efficiency

```text
Expected Capital Efficiency
```

The final target set must be validated experimentally.

Multiple targets may be modeled separately rather than forcing all objectives into one model.

---

# 22. Labeling Principle

Labels must be derived from actual historical outcomes of the Grid Strategy.

The system should not label a market as:

```text
GOOD
```

simply because price increased.

Instead:

```text
Market Condition
      ↓
Historical Grid Simulation
      ↓
Actual Strategy Outcome
      ↓
Label
```

Possible labels may incorporate:

```text
Positive Net P&L
Acceptable Drawdown
Execution Cost
Capital Utilization
Recovery
```

The exact labeling formula belongs to the ML Feature and Label Specification.

---

# 23. Avoiding Data Leakage

Historical ML research must prevent future information from entering historical decisions.

At time `T`, the model may only use information available at or before `T`.

Invalid:

```text
Features at T
+
Outcome from T+30
used as a feature
```

Valid:

```text
Features at T
        ↓
Predict future outcome
        ↓
Compare against actual future outcome
```

This is mandatory.

---

# 24. Avoiding Look-Ahead Bias

Multi-timeframe candle features must respect candle completion.

For example:

- A completed Monthly candle may be used after its close.
- An incomplete current Monthly candle must be treated as realtime/in-progress data.
- Future Weekly or Daily closes must never be available to a historical decision point.

The dataset must distinguish:

```text
CLOSED CANDLE
vs
IN-PROGRESS CANDLE
```

---

# 25. Dataset Architecture

Conceptually:

```text
RAW DATA
   ↓
NORMALIZED DATA
   ↓
FEATURE DATASET
   ↓
SIMULATION DATASET
   ↓
TRAINING DATASET
   ↓
VALIDATION DATASET
   ↓
TEST DATASET
```

Dataset versions must be reproducible.

Every training run should identify:

```text
Dataset Version
Feature Version
Label Version
Model Version
Experiment Version
```

---

# 26. Time-Based Dataset Splitting

Because trading data is temporal, random shuffling must not be the default evaluation method.

Conceptually:

```text
PAST
  ↓
TRAIN

LATER PERIOD
  ↓
VALIDATION

FUTURE PERIOD
  ↓
TEST
```

Walk-forward evaluation should be considered for later technical implementation.

The purpose is to simulate how the model would perform on genuinely unseen future market conditions.

---

# 27. ML / Research Engine

The ML Research Engine consumes:

```text
Features
+
Labels
+
Historical Outcomes
```

and produces:

```text
Predictions
+
Probability
+
Expected Outcomes
+
Model Diagnostics
```

The first implementation should favor interpretable and robust models before introducing complex deep learning.

The exact model family remains intentionally undecided at this stage.

---

# 28. Model Evaluation

Model evaluation must focus on usefulness to the Grid Strategy.

Generic classification accuracy is insufficient.

Evaluation should consider:

```text
Prediction Quality
+
Net P&L Impact
+
Drawdown Impact
+
Ranking Quality
+
Calibration
+
Stability
+
Out-of-Sample Performance
```

A model that predicts well statistically but does not improve market selection is not useful.

---

# 29. Suitability Engine

The Suitability Engine combines deterministic research metrics and ML outputs.

Conceptually:

```text
Liquidity
      +
Volatility
      +
Structure
      +
Trend
      +
Proximity
      +
Execution Economics
      +
Historical Grid Performance
      +
ML Prediction
      ↓
GRID SUITABILITY
```

The exact weighting must be determined through research.

AI should not be allowed to hide poor execution economics behind a high ML score.

---

# 30. Recommendation Engine

The Recommendation Engine converts suitability analysis into a human-readable recommendation.

Example:

```text
Market: BTC/USDT

Suitability: HIGH
Confidence: HIGH
Priority: #1

Market Regime:
Corrective Bullish

Structure:
Near Monthly Low

Trend:
Weekly Bearish
Daily Bearish

Volatility:
Favorable

Execution Economics:
Favorable

Historical Grid Behavior:
Positive

Reason:
Price is near a major monthly reference while
weekly/daily structure provides a deeper accumulation
context and execution economics remain acceptable.
```

The recommendation must include reasons, not only a score.

---

# 31. Ranking Engine

The Ranking Engine compares candidate markets.

Example:

```text
BTC/USDT   91
ETH/USDT   87
SOL/USDT   78
BNB/USDT   74
XRP/USDT   61
```

Ranking should be based on Grid Suitability.

It must not be interpreted as a general investment ranking.

---

# 32. Confidence

Recommendation confidence should reflect the quality and agreement of evidence.

Potential contributors:

```text
Data Quality
Model Confidence
Historical Sample Size
Feature Stability
Market Liquidity
Research Agreement
```

Confidence must not simply be a subjective AI-generated number.

Its calculation must eventually be deterministic or statistically grounded.

---

# 33. Explainability

Every recommendation should be explainable.

The system should be able to answer:

```text
Why was this market recommended?
Why was another market ranked lower?
Which factors contributed?
Which factors reduced the score?
How confident is the system?
```

This is especially important when ML is involved.

---

# 34. Experiment Management

AI Research requires experiment tracking.

Each experiment should record:

```text
Experiment ID
Dataset Version
Feature Version
Label Version
Model Version
Training Period
Validation Period
Test Period
Markets
Hyperparameters
Metrics
Backtest Results
Conclusion
```

This allows research to be reproducible.

---

# 35. Model Versioning

Models must be versioned.

Example:

```text
Model:
market-suitability-v001
market-suitability-v002
market-suitability-v003
```

A production recommendation must always identify the model version that generated it.

---

# 36. Feedback Loop

The research feedback loop is:

```text
Market Data
      ↓
Research
      ↓
Recommendation
      ↓
Blueprint
      ↓
Execution
      ↓
Actual Result
      ↓
Outcome Dataset
      ↓
Model Evaluation
      ↓
New Research
```

The feedback loop must compare:

```text
Prediction
vs
Actual Outcome
```

This allows continuous evaluation.

---

# 37. Research Findings vs Production Changes

A research result is not automatically a production strategy change.

Example:

```text
Research Finding:
Large weekly volatility historically benefits
from wider Section Gaps.
```

This becomes:

```text
Candidate Strategy Change
```

Then:

```text
Backtest
      ↓
Simulation
      ↓
Risk Validation
      ↓
Approval
      ↓
Production
```

No automatic silent strategy mutation is permitted.

---

# 38. Research API Boundary

Conceptually, AI Research exposes:

```text
getMarketUniverse()
researchMarket()
rankMarkets()
getMarketRecommendation()
getResearchExplanation()
getModelVersion()
getResearchMetrics()
```

These are conceptual interfaces.

Actual API contracts belong to the implementation phase.

---

# 39. Output Contract to Realtime AI

AI Research should provide a structured Market Recommendation.

Conceptually:

```text
{
    market,
    suitability_score,
    recommendation,
    confidence,
    market_regime,
    trend_context,
    volatility_context,
    structure_context,
    proximity_context,
    execution_economics,
    historical_grid_context,
    research_reasons,
    model_version,
    dataset_version
}
```

This output should not directly contain an unconditional Buy/Sell command.

---

# 40. Failure Handling

Research must be able to return:

```text
INSUFFICIENT DATA
LOW CONFIDENCE
NO SUITABLE MARKET
```

The system must not force a recommendation when evidence is inadequate.

Example:

```text
Market Universe
      ↓
No market meets minimum suitability
      ↓
NO RECOMMENDATION
```

---

# 41. Research Safety Boundaries

AI Research must not:

- Directly execute trades
- Bypass risk validation
- Bypass deterministic calculation
- Modify production strategy silently
- Treat ML output as guaranteed profit
- Ignore execution costs
- Use future data in historical research
- Hide uncertainty
- Convert recommendation into an unconditional Buy/Sell command

---

# 42. Initial Technical Modules

The technical implementation should be organized around:

```text
01. Data Ingestion
02. Data Normalization
03. Feature Engine
04. Proximity Engine
05. Market Structure Engine
06. Trend Engine
07. Volatility Engine
08. Liquidity / Execution Economics Engine
09. Historical Grid Simulation Engine
10. Dataset Builder
11. ML Research Engine
12. Suitability Engine
13. Recommendation Engine
14. Ranking Engine
15. Experiment Manager
16. Model Registry
17. Evaluation Engine
18. Feedback / Outcome Pipeline
```

The final repository structure may map these responsibilities differently; the conceptual boundaries should remain stable.

---

# 43. Technical Design Principles

## Principle 1 — Strategy First

The ML system must serve the Grid Strategy, not the other way around.

## Principle 2 — Provider Independent

Exchange-specific details remain behind provider adapters.

## Principle 3 — Deterministic Economics

Fees, spread, slippage, cost, and Net P&L calculations must remain deterministic.

## Principle 4 — Historical Integrity

No future information may leak into historical research.

## Principle 5 — Explainability

Recommendations must have traceable reasons.

## Principle 6 — Reproducibility

Research results must be reproducible through dataset, feature, label, model, and experiment versions.

## Principle 7 — Separation

Research, prediction, recommendation, validation, and execution remain separate concerns.

## Principle 8 — No Forced Trading

The correct recommendation can be:

```text
NO SUITABLE MARKET
```

---

# 44. Recommended Technical Development Order

The implementation should proceed in this order:

```text
1. Market Data Contract
        ↓
2. Normalized Data Model
        ↓
3. Feature Specification
        ↓
4. Proximity Specification
        ↓
5. Structure / Trend / Volatility Specification
        ↓
6. Execution Economics Specification
        ↓
7. Historical Grid Simulator
        ↓
8. Dataset Builder
        ↓
9. Label Definition
        ↓
10. Baseline ML Model
        ↓
11. Suitability Engine
        ↓
12. Recommendation Engine
        ↓
13. Ranking Engine
        ↓
14. Walk-Forward Evaluation
        ↓
15. Feedback Loop
```

---

# 45. Next Technical Documents

The next documents should be created only after this architecture is accepted.

Recommended sequence:

```text
01. AI_RESEARCH_FEATURE_SPEC.md

02. AI_RESEARCH_LABEL_SPEC.md

03. AI_RESEARCH_DATASET_SPEC.md

04. AI_RESEARCH_GRID_SIMULATOR_SPEC.md

05. AI_RESEARCH_ML_MODEL_SPEC.md

06. AI_RESEARCH_RECOMMENDATION_SPEC.md

07. AI_RESEARCH_EVALUATION_SPEC.md
```

The most important next document is:

> **`AI_RESEARCH_FEATURE_SPEC.md`**

because the ML design should be driven by clearly defined, measurable features.

---

# 46. Final Technical Definition

AI Research is technically designed as a modular research pipeline:

```text
MARKET DATA
    ↓
NORMALIZATION
    ↓
FEATURE ENGINE
    ↓
MULTI-TIMEFRAME CONTEXT
    ↓
PROXIMITY
    ↓
TREND / VOLATILITY
    ↓
EXECUTION ECONOMICS
    ↓
HISTORICAL GRID SIMULATION
    ↓
DATASET + LABELS
    ↓
ML RESEARCH
    ↓
SUITABILITY
    ↓
RECOMMENDATION
    ↓
RANKING
    ↓
REALTIME AI
```

The technical objective is not to create a generic market prediction model.

The objective is:

> **Build a research and ML system that learns which market conditions are most compatible with our specific immediate-execution, Section-based Grid Strategy, and converts that knowledge into explainable Market Recommendations.**

The system remains separated from production execution and all strategy changes remain subject to deterministic validation, simulation, and approval.
