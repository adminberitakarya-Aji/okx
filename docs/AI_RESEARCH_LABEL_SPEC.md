# AI Research Label Specification

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`
- `AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md`
- `AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md`
- `AI_RESEARCH_FEATURE_SPEC_GRID_BEHAVIOR.md`
- `AI_RESEARCH_FEATURE_SPEC_DERIVED_ML.md`

---

# 1. Purpose

This document defines the targets and labels that AI Research + ML must learn.

The primary objective is NOT to predict whether the market price will rise or fall.

The objective is:

> **Predict how suitable a market and candidate Grid Blueprint are for the actual Grid Strategy over a defined future horizon.**

The prediction unit is therefore:

```text
MARKET
+
MARKET STATE AT T
+
EXECUTION ECONOMICS AT T
+
CANDIDATE GRID BLUEPRINT
        ↓
FUTURE STRATEGY OUTCOME
```

This is a fundamental design decision.

---

# 2. Research Universe

AI Research does not research every market on OKX.

Initial universe:

```text
OKX SPOT
    ↓
Eligibility Filter
    ↓
Ranking
    ↓
TOP 10 ELIGIBLE MARKETS
    ↓
AI RESEARCH
```

The universe is dynamic and may be refreshed periodically.

The label system must identify:

```text
market_id
universe_snapshot_id
```

so historical experiments know which markets were eligible at the time.

---

# 3. Core Label Philosophy

The ML system must learn:

```text
Market Condition
      +
Execution Economics
      +
Grid Blueprint
      ↓
Strategy Outcome
```

It must NOT primarily learn:

```text
Market Condition
      ↓
Price Direction
```

A price increase is not automatically a successful Grid outcome.

A market can decline substantially and still produce a good spot Grid result if:

- Sections accumulate coin at progressively lower prices
- Capital remains available
- Recovery occurs within the relevant horizon
- Net P&L becomes positive
- Execution costs remain economically viable

Therefore labels must be tied to actual Grid Strategy outcomes.

---

# 4. Observation Time and Prediction Horizon

Every label starts from an observation timestamp:

```text
T0
```

At T0, the model may use only information available at or before T0.

Then the strategy is evaluated over a future horizon:

```text
T0 → T1
```

Possible horizons:

```text
7D
30D
60D
90D
```

These are initial candidate horizons.

The final production horizon must be selected through validation.

A single market observation may therefore have multiple future labels:

```text
7D outcome
30D outcome
60D outcome
90D outcome
```

---

# 5. Primary Target

## LBL-001 — Probability of Positive Net P&L

Target concept:

```text
P(Net P&L > 0 | Market State, Execution Economics, Blueprint)
```

Binary outcome used for training:

```text
1 = Net P&L > 0
0 = Net P&L <= 0
```

The model predicts probability:

```text
0.00 → 1.00
```

Example:

```text
BTC + Blueprint A
P(Positive Net P&L, 30D) = 0.82
```

This is the primary target because it directly answers:

> **How likely is this market + Blueprint combination to produce a profitable Grid outcome?**

---

# 6. Why Positive Net P&L Is the Primary Target

The primary target uses:

```text
Net P&L
```

not:

```text
Gross Price Change
```

and not:

```text
Sell Price > Buy Price
```

The underlying outcome must follow the canonical Execution Economics model:

```text
Net P&L
=
Sell Proceeds
− Buy Cost
− Buy Fee
− Sell Cost
− Spread Cost
− Slippage
− Other Execution Costs
```

The actual simulator implementation must avoid double-counting costs.

---

# 7. Secondary Target — Expected Net P&L

## LBL-002 — Expected Net P&L

Target:

```text
Future Net P&L
```

Measured over the selected horizon.

Possible representations:

```text
absolute_currency
percentage_return
```

Primary normalized representation:

```text
Net P&L / Starting Capital
```

Example:

```text
Expected Net P&L Return = +3.4%
```

Purpose:

Probability alone does not describe the magnitude of the opportunity.

---

# 8. Secondary Target — Expected Maximum Drawdown

## LBL-003 — Expected Maximum Strategy Drawdown

Target:

```text
maximum_strategy_drawdown
```

during the future horizon.

Normalized as:

```text
percentage of starting capital
```

Example:

```text
Expected Maximum Drawdown = 8.2%
```

Purpose:

A market with high positive-P&L probability but extreme drawdown may be less suitable than a more stable alternative.

---

# 9. Secondary Target — Capital Utilization

## LBL-004 — Future Peak Capital Utilization

Target:

```text
peak_capital_deployment
/
starting_capital
```

Example:

```text
Peak Capital Utilization = 64%
```

Purpose:

Estimates how much reserve capital the candidate strategy is likely to consume.

This is critical because the Grid Strategy intentionally keeps capital for deeper Sections.

---

# 10. Secondary Target — Recovery Probability

## LBL-005 — Recovery Probability

Binary future outcome:

```text
1 = defined recovery condition achieved within horizon
0 = recovery condition not achieved
```

Probability output:

```text
P(Recovery within H)
```

The recovery condition must be deterministic and defined in the simulator.

Possible recovery conditions may include:

```text
Position reaches break-even
Position reaches minimum profitable exit
Portfolio reaches positive Net P&L
```

The exact production label must be selected explicitly.

---

# 11. Secondary Target — Recovery Time

## LBL-006 — Time to Recovery

Continuous target:

```text
time from defined drawdown/activation event
to defined recovery condition
```

Possible units:

```text
hours
days
```

If recovery does not occur within the horizon:

```text
censored / unavailable
```

must be represented explicitly.

Do NOT encode missing recovery as zero.

---

# 12. Secondary Target — Maximum Section Depth

## LBL-007 — Maximum Section Depth Reached

Target:

```text
deepest Section reached
```

Example:

```text
Section 1
Section 2
Section 3
```

Purpose:

Predicts how deeply capital may need to be deployed.

This target is especially relevant to the adaptive Section Gap architecture.

---

# 13. Secondary Target — Capital Exhaustion Probability

## LBL-008 — Probability of Capital Exhaustion

Binary future outcome:

```text
1 = deployable capital exhausted
0 = capital remained available
```

ML output:

```text
P(Capital Exhaustion)
```

This is a critical risk-oriented target.

A profitable strategy that frequently exhausts capital under adverse scenarios may be unsuitable.

---

# 14. Secondary Target — Positive Recovery After Deep Section

## LBL-009 — Deep-Section Recovery Probability

Target:

```text
P(Positive Net Outcome | Section N activated)
```

This target specifically studies the strategy's core philosophy:

```text
Market declines
    ↓
Deeper Section activates
    ↓
Cheaper coin accumulation
    ↓
Recovery
```

The model can learn whether deeper accumulation historically produces useful outcomes.

---

# 15. Secondary Target — Coin Accumulation

## LBL-010 — Future Net Coin Accumulation

Target:

```text
net coin quantity accumulated
```

over the prediction horizon.

This is relevant because the strategy is spot-based and intentionally uses lower prices to acquire more coin.

Possible normalized representation:

```text
coin_accumulated
/
capital_deployed
```

This target should not replace Net P&L.

It is a strategic outcome metric.

---

# 16. Secondary Target — Cost-Basis Improvement

## LBL-011 — Cost-Basis Improvement

Target:

```text
initial_average_cost
-
future_average_cost
```

normalized appropriately.

Purpose:

Measures whether deeper Sections actually improve the portfolio's acquisition cost.

---

# 17. Secondary Target — Strategy Stability

## LBL-012 — Outcome Stability

Measures consistency of future strategy outcomes over the horizon.

Possible formulation:

```text
variance of cycle/period outcomes
```

or:

```text
dispersion of realized Net P&L outcomes
```

The exact production formula is deferred to evaluation design.

Purpose:

Distinguishes:

```text
high average return with unstable outcomes
```

from:

```text
moderate return with consistent outcomes
```

---

# 18. Target Classes

Labels should be divided into three technical classes.

## Class A — Primary Decision Target

```text
LBL-001 Positive Net P&L Probability
```

This is the main market/Blueprint suitability target.

---

## Class B — Economic Targets

```text
LBL-002 Expected Net P&L
LBL-004 Capital Utilization
LBL-010 Coin Accumulation
LBL-011 Cost-Basis Improvement
```

These describe economic outcomes.

---

## Class C — Risk / Recovery Targets

```text
LBL-003 Maximum Drawdown
LBL-005 Recovery Probability
LBL-006 Recovery Time
LBL-007 Maximum Section Depth
LBL-008 Capital Exhaustion Probability
LBL-009 Deep-Section Recovery Probability
LBL-012 Outcome Stability
```

These qualify the primary economic prediction.

---

# 19. Multi-Target Architecture

The system should support multiple models or multi-output models.

Conceptually:

```text
                 FEATURES
                    |
          +---------+---------+
          |         |         |
          v         v         v
       SUCCESS    RETURN     RISK
       MODEL      MODEL      MODEL
          |         |         |
          v         v         v
      P(Profit)  Exp. P&L   Exp. DD
          |         |         |
          +---------+---------+
                    |
                    v
             SUITABILITY
                    |
                    v
             RECOMMENDATION
```

The recommendation layer should not depend on one prediction alone.

---

# 20. Blueprint-Conditional Labels

This is mandatory.

The same market can have different outcomes under different Blueprints.

Example:

```text
BTC
+
Blueprint A
→ P(Positive Net P&L) = 82%

BTC
+
Blueprint B
→ P(Positive Net P&L) = 61%
```

Therefore labels must preserve:

```text
market_id
blueprint_id
```

or a deterministic blueprint configuration signature.

---

# 21. Candidate Blueprint

The Candidate Blueprint contains at minimum:

```text
capital
section_count
section_allocation
uniform_grid_spacing_per_section
section_gap_per_transition
section_price_range
grid_count_per_section
```

The label belongs to this specific candidate configuration.

---

# 22. Immediate Execution in Label Generation

Labels must be generated using the real execution model:

```text
BUY
→ immediate execution
→ position
→ SELL
→ immediate execution
```

Not:

```text
limit order placed
→ wait for fill
```

This is mandatory because execution economics materially changes the label.

---

# 23. Fees and Costs in Label Generation

The simulator must include:

```text
Buy Cost
Buy Fee
Sell Cost
Sell Fee
Spread
Slippage
Other Execution Costs
```

The canonical accounting principle applies:

```text
No double counting.
```

The same execution model used in research labels must be used in later backtesting.

---

# 24. Label Horizon

Every target must specify:

```text
horizon
```

Example:

```text
7D
30D
60D
90D
```

A target must never mix horizons inside one training definition.

Example invalid:

```text
Positive P&L within
7–30 days
```

without explicitly defining the event timing.

Better:

```text
P(Net P&L > 0 by Day 30)
```

or:

```text
Net P&L at Day 30
```

---

# 25. Event vs End-of-Horizon Labels

The system should distinguish two label types.

## Event Label

Question:

> Did the event happen at any time during the horizon?

Example:

```text
P(Net P&L > 0 at any point within 30D)
```

## End-of-Horizon Label

Question:

> What was the final strategy state at horizon end?

Example:

```text
Net P&L at Day 30
```

These are not equivalent.

Both may be useful.

The distinction must be encoded in the label definition.

---

# 26. Recommended Initial Label Set

For the first ML research version, keep the primary set manageable.

Recommended:

```text
PRIMARY
LBL-001 Positive Net P&L Probability

SECONDARY
LBL-002 Expected Net P&L
LBL-003 Expected Maximum Drawdown
LBL-004 Peak Capital Utilization
LBL-005 Recovery Probability
LBL-008 Capital Exhaustion Probability
LBL-007 Maximum Section Depth
```

Additional labels can be added after baseline evaluation.

This avoids unnecessary model complexity at the beginning.

---

# 27. Recommended Initial Horizon Set

For initial research:

```text
SHORT   = 7D
MEDIUM  = 30D
LONG    = 90D
```

The 60D horizon may be added if experiments show value.

The production default should not be assumed until evaluated.

---

# 28. Label Generation Pipeline

```text
OBSERVATION TIME T
        |
        v
Market State at T
        +
Execution Economics at T
        +
Candidate Blueprint
        |
        v
Historical Grid Simulator
        |
        v
Future Market Window
T → T+H
        |
        v
Strategy Outcomes
        |
        v
Label Generation
```

---

# 29. Label Generation Rules

1. The simulator must start from a clearly defined initial portfolio state.
2. The candidate Blueprint must be fixed for the label window unless the experiment explicitly models dynamic reconfiguration.
3. Immediate BUY and SELL must be used.
4. Execution economics must be applied consistently.
5. Future market data may be used only for generating the label, never for input features at T.
6. Every label must reference its observation timestamp.
7. Every label must reference its prediction horizon.
8. Every label must reference its blueprint configuration.

---

# 30. Censoring

Some outcomes may not occur within the selected horizon.

Examples:

```text
Recovery did not happen within 30D
```

This is not equivalent to:

```text
Recovery Time = 0
```

The dataset should represent:

```text
event_occurred = false
observed_until = horizon_end
```

or an equivalent censored representation.

Survival-analysis methods may be considered later for recovery-time targets.

---

# 31. Class Imbalance

Positive Net P&L may not occur with equal frequency across:

```text
markets
horizons
blueprints
regimes
```

The dataset must measure class balance before model selection.

Potential techniques such as:

```text
class weighting
resampling
threshold tuning
```

should be considered only after examining the actual data.

Do not assume imbalance before measuring it.

---

# 32. Label Quality

A label is valid only when:

```text
Input data complete enough
+
Execution model valid
+
Blueprint valid
+
Simulation completed
+
Outcome calculation valid
```

Invalid simulation runs must be marked explicitly.

Do not silently convert failed simulations into negative labels.

---

# 33. Universe Constraint

Labels are generated only for the active Research Universe:

```text
OKX Spot
    ↓
Eligibility Filter
    ↓
Top 10
```

The universe snapshot must be stored.

This prevents historical research from assuming today's Top 10 was always the Top 10.

---

# 34. Universe Membership Leakage

Care must be taken with dynamic Top 10 selection.

Incorrect:

```text
Use today's Top 10
to backtest all historical years
```

This creates survivorship bias.

Correct:

```text
Historical date T
    ↓
Reconstruct eligible OKX Spot universe at T
    ↓
Rank
    ↓
Determine Top 10 at T
    ↓
Generate research observations
```

This is mandatory for robust historical research.

---

# 35. Label Metadata

Every generated label record should include:

```text
label_id
market_id
universe_snapshot_id
observation_timestamp
blueprint_id
horizon
label_type
label_value
simulation_status
simulation_version
execution_model_version
grid_strategy_version
```

For probabilistic targets:

```text
probability
```

is the model output.

The raw historical label is usually the underlying future outcome.

---

# 36. Prediction vs Label

Important distinction:

```text
LABEL
=
actual future outcome
```

Example:

```text
Net P&L over next 30D = +4.2%
```

The ML model learns:

```text
P(Net P&L > 0)
```

or:

```text
Expected Net P&L
```

Do not store a model prediction as if it were a ground-truth label.

---

# 37. Primary Label Example

Observation:

```text
Timestamp:
2026-08-15 12:00

Market:
BTC/USDT

Blueprint:
BP-001

Horizon:
30D
```

Future simulation result:

```text
Net P&L:
+3.8%
```

Then:

```text
LBL-001 positive_net_pnl_30d = 1
LBL-002 net_pnl_return_30d = +0.038
```

If result were:

```text
-1.2%
```

then:

```text
LBL-001 = 0
LBL-002 = -0.012
```

---

# 38. Deeper Section Example

Observation:

```text
Monthly Low = 100
Current Price = 102
```

Blueprint:

```text
Section 1
Range: 102 → 98

Section Gap

Section 2
Range: 92 → 86

Section Gap

Section 3
Range: 78 → 72
```

Future simulation:

```text
Monthly Low breaks
Section 1 activates
Section 2 activates
Section 3 not activated
Recovery occurs
Net P&L positive
```

Labels may include:

```text
Positive Net P&L = 1
Max Section Depth = 2
Recovery = 1
Capital Exhaustion = 0
```

This directly reflects the strategy's intended deeper-accumulation behavior.

---

# 39. No-Trade / Invalid Blueprint

A candidate Blueprint that fails deterministic validation must not become a normal ML label.

It should be stored as:

```text
simulation_status = INVALID_BLUEPRINT
```

or equivalent.

This distinguishes:

```text
strategy failed
```

from:

```text
strategy could not legally/technically be simulated
```

---

# 40. Relationship to Recommendation Engine

The ML labels support prediction.

They do not directly define the final recommendation.

Conceptual:

```text
Predicted Positive P&L Probability
+
Predicted Net P&L
+
Predicted Drawdown
+
Predicted Capital Utilization
+
Predicted Recovery
        ↓
Suitability Engine
        ↓
Market Ranking
        ↓
Recommendation
```

Recommendation thresholds belong to a later specification.

---

# 41. Target Priority

Initial priority:

```text
HIGH
LBL-001 Positive Net P&L Probability
LBL-002 Expected Net P&L
LBL-003 Expected Maximum Drawdown

MEDIUM
LBL-004 Peak Capital Utilization
LBL-005 Recovery Probability
LBL-007 Maximum Section Depth
LBL-008 Capital Exhaustion Probability

FUTURE / OPTIONAL
LBL-006 Recovery Time
LBL-009 Deep-Section Recovery Probability
LBL-010 Coin Accumulation
LBL-011 Cost-Basis Improvement
LBL-012 Outcome Stability
```

Priority can change after empirical testing.

---

# 42. Non-Negotiable Rules

1. ML predicts Grid Strategy outcomes, not generic price direction as the primary objective.
2. The prediction unit is Market + Market Context + Execution Economics + Candidate Blueprint.
3. Positive Net P&L is the primary target.
4. Expected Net P&L and Expected Drawdown are primary secondary targets.
5. Every label has an observation timestamp and explicit horizon.
6. Immediate BUY and SELL execution must be used for label generation.
7. Buy and Sell execution costs must be modeled.
8. Fees, spread, and slippage must not be double-counted.
9. Future data is allowed for generating outcomes but prohibited from input features at observation time.
10. A failed simulation is not automatically a negative trading outcome.
11. Dynamic Top 10 universe selection must be reconstructed historically.
12. Model predictions are not ground-truth labels.
13. Blueprint identity/version must be preserved.
14. Labels do not directly execute trades.
15. Labels do not directly modify production strategy.

---

# 43. Final Definition

The Label System defines:

> **What outcome the ML system is trying to learn when a specific market and candidate Grid Blueprint are evaluated from a known point in time.**

Its fundamental structure is:

```text
MARKET + BLUEPRINT AT T
        ↓
FUTURE MARKET WINDOW
        ↓
GRID SIMULATION
        ↓
ACTUAL STRATEGY OUTCOME
        ↓
LABEL
        ↓
ML MODEL
        ↓
PREDICTION
```

The central target is:

> **Probability that the specific Grid Strategy configuration produces positive Net P&L within the defined future horizon.**

Supporting targets measure:

```text
Expected Net P&L
Expected Drawdown
Capital Utilization
Recovery
Section Depth
Capital Exhaustion
```

This label architecture is designed to make the ML system learn the economics and behavior of the actual Grid Strategy rather than merely predict market direction.
