# AI Research Dataset Specification

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

---

# 1. Purpose

This document defines the dataset architecture for AI Research + ML.

The dataset must preserve the causal relationship:

```text
INFORMATION AVAILABLE AT T
        +
CANDIDATE GRID BLUEPRINT
        ↓
FUTURE MARKET WINDOW
        ↓
GRID SIMULATION
        ↓
ACTUAL OUTCOME
        ↓
LABEL
```

The primary purpose is to create a reproducible dataset in which ML learns whether a specific market and candidate Grid Blueprint are likely to produce a healthy Grid outcome.

The dataset must prioritize:

- Temporal integrity
- Causal correctness
- Reproducibility
- Provider independence
- Blueprint traceability
- Execution-economic accuracy
- Historical realism
- Leakage prevention

---

# 2. Core Dataset Unit

The fundamental dataset observation is:

```text
MARKET
+
OBSERVATION TIMESTAMP
+
MARKET STATE
+
EXECUTION ECONOMICS
+
PAST GRID BEHAVIOR
+
DERIVED ML FEATURES
+
CANDIDATE GRID BLUEPRINT
+
FUTURE OUTCOME LABELS
```

A dataset row therefore represents:

> **What was knowable at time T about market M and Blueprint B, and what actually happened after T over horizon H.**

---

# 3. Dataset Row Identity

Every observation must have a unique identity.

Minimum identity:

```text
dataset_row_id
market_id
exchange_id
observation_timestamp
blueprint_id
horizon
universe_snapshot_id
```

Recommended additional identifiers:

```text
feature_snapshot_id
label_snapshot_id
simulation_run_id
```

---

# 4. Research Universe

Initial Research Universe:

```text
OKX SPOT MARKETS
        ↓
ELIGIBILITY FILTER
        ↓
RANKING
        ↓
TOP 10 ELIGIBLE MARKETS
```

The Top 10 list is dynamic.

It MUST NOT be treated as a fixed list throughout history.

For historical observations at timestamp T:

```text
Eligible Markets at T
        ↓
Ranking at T
        ↓
Top 10 at T
```

This prevents survivorship bias.

---

# 5. Universe Snapshot

Each research period must have a universe snapshot.

Conceptual:

```text
UniverseSnapshot
│
├── snapshot_id
├── timestamp
├── provider
├── market_count
├── ranking_method_version
├── eligibility_rule_version
└── members
```

Each member:

```text
market_id
rank
eligibility_status
eligibility_reason
```

---

# 6. Eligibility Filter

Before ranking markets, apply deterministic eligibility rules.

Possible criteria:

```text
Spot Market
Supported Quote Asset
Minimum Liquidity
Minimum Volume
Tradable Status
Historical Data Availability
Minimum Market Age
Market Rule Compatibility
```

Exact thresholds belong to the Research Universe specification.

Important:

Eligibility must be deterministic and versioned.

---

# 7. Universe Ranking

After eligibility:

```text
Eligible Markets
       ↓
Universe Ranking
       ↓
Top 10
```

Ranking can consider:

```text
Liquidity
Volume
Execution Quality
Data Quality
Market Availability
```

The ranking method must be versioned:

```text
universe_ranking_version
```

No future information may be used to construct a historical universe snapshot.

---

# 8. Observation Timestamp

The observation timestamp is the causal boundary.

At:

```text
T
```

the dataset may use only information available up to T.

Conceptually:

```text
DATA <= T
```

Future data:

```text
DATA > T
```

must not appear in the input feature vector.

---

# 9. Feature Snapshot

All input features should belong to a versioned feature snapshot.

Conceptual:

```text
FeatureSnapshot
│
├── snapshot_id
├── observation_timestamp
├── market_id
├── market_state_version
├── execution_economics_version
├── grid_behavior_version
├── derived_ml_version
└── feature_values
```

This allows exact reconstruction of what the model saw.

---

# 10. Feature Layers

Dataset inputs are organized into four layers.

```text
LAYER 1
Market State

LAYER 2
Execution Economics

LAYER 3
Historical Grid Behavior

LAYER 4
Derived ML
```

Conceptually:

```text
Market State
      +
Execution Economics
      +
Past Grid Behavior
      ↓
Derived ML
      ↓
MODEL INPUT VECTOR
```

Future outcomes remain labels, not input features.

---

# 11. Historical Grid Behavior Rule

Grid Behavior can only be used as an ML input when it is derived from data available before observation time T.

Valid:

```text
Past 90D Grid Performance
      ↓
Observation at T
```

Invalid:

```text
Future 30D Grid Performance
      ↓
Feature at T
```

This distinction is mandatory.

---

# 12. Blueprint Dataset

The candidate Grid Blueprint is part of the model context.

Minimum blueprint parameters:

```text
blueprint_id
capital
section_count
section_allocation
uniform_grid_spacing_per_section
section_gap_per_transition
section_price_range
grid_count_per_section
```

Additional deterministic parameters may be included.

---

# 13. Blueprint Versioning

Every candidate Blueprint must have:

```text
blueprint_id
blueprint_version
blueprint_configuration_hash
```

This ensures that the same Blueprint can be reproduced exactly.

Example:

```text
BP-001
version 1
hash abc123...
```

---

# 14. Blueprint Validity

Before a Blueprint becomes a dataset observation, it must pass deterministic validation.

```text
Candidate Blueprint
        ↓
Calculation
        ↓
Validation
        ↓
VALID
```

Invalid Blueprints:

```text
simulation_status = INVALID_BLUEPRINT
```

must not be silently treated as negative outcomes.

---

# 15. Grid Structure Constraint

Dataset generation MUST preserve the actual Grid Strategy:

```text
Within Section:
Uniform Grid Spacing

Between Sections:
Section Gap may differ
```

Valid:

```text
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

Invalid for this strategy:

```text
1%
1.2%
1.5%
1.8%
```

inside the same Section.

---

# 16. Immediate Execution Rule

All strategy outcomes used for labeling must be generated from the immediate-execution model:

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

The dataset must not mix:

```text
Limit-order queue simulation
```

with:

```text
Immediate execution simulation
```

unless a separate experiment explicitly defines that as a different strategy.

---

# 17. Execution Economics Dependency

Simulation and labels must use the canonical execution economics:

```text
Buy Cost
Buy Fee
Sell Cost
Sell Fee
Spread
Slippage
Other Execution Costs
```

No double counting is allowed.

The same execution model version must be referenced by:

```text
feature snapshot
simulation
labels
```

---

# 18. Timeframe Data

Core market-state timeframes:

```text
Monthly
Weekly
Daily
```

Additional lower timeframes may be included for:

```text
Historical Simulation
Execution Modeling
Fine-Grained Event Reconstruction
```

Additional timeframes must not replace the core Monthly → Weekly → Daily hierarchy.

---

# 19. Candle State

Historical dataset generation must distinguish:

```text
CLOSED
IN_PROGRESS
```

For an observation at T:

```text
Current Monthly Candle
Current Weekly Candle
Current Daily Candle
```

must represent only information available through T.

The dataset must preserve candle state.

---

# 20. Current vs Previous Candle References

The dataset should support both:

```text
Current In-Progress Candle
```

and:

```text
Previous Closed Candle
```

This is especially important for Monthly Low and Monthly High references.

Example:

```text
current_monthly_low
previous_monthly_low
```

must remain distinct fields.

---

# 21. Monthly → Weekly → Daily Context

Dataset generation must preserve the strategic resolution principle:

```text
Monthly Context
      ↓
Realtime Price Proximity
      ↓
Weekly Refinement
      ↓
Daily Refinement
```

This is represented through the Market State feature layer.

The dataset should not collapse these timeframes into one generic trend feature.

---

# 22. Top 10 Universe Sampling

The Top 10 universe should be evaluated at the observation timestamp.

Example:

```text
T0
Top 10:
BTC
ETH
SOL
...
```

At a later timestamp:

```text
T1
Top 10:
BTC
ETH
XRP
...
```

A market can enter or leave the research universe.

The historical dataset must preserve that dynamic behavior.

---

# 23. Observation Frequency

The system must separate:

```text
Research Observation Frequency
```

from:

```text
Market Data Update Frequency
```

Market data may update continuously.

AI Research observations may be sampled at a configured interval.

Possible research observation intervals:

```text
1H
4H
12H
1D
```

These are examples only.

The final interval should be chosen based on:

- Compute capacity
- Label redundancy
- Strategy reaction speed
- Dataset size
- Research objective

---

# 24. Avoiding Duplicate Observations

Highly frequent sampling may produce many nearly identical observations.

The dataset should support:

```text
minimum_observation_spacing
```

or an equivalent sampling policy.

Purpose:

Avoid excessive redundancy while preserving meaningful state changes.

---

# 25. Prediction Horizons

Initial horizons:

```text
7D
30D
90D
```

Optional:

```text
60D
```

Each horizon creates separate label fields.

Example:

```text
positive_pnl_7d
positive_pnl_30d
positive_pnl_90d
```

The same feature observation at T can therefore support multiple target horizons.

---

# 26. Event and End-of-Horizon Labels

The dataset must distinguish:

## Event Label

Example:

```text
positive_pnl_within_30d
```

Meaning:

> Did positive Net P&L occur at any point before the horizon ended?

## End-of-Horizon Label

Example:

```text
net_pnl_at_30d
```

Meaning:

> What was the strategy Net P&L exactly at the horizon boundary?

These are different labels and must not be mixed.

---

# 27. Dataset Schema

Conceptual row:

```text
DatasetRow
│
├── identity
│   ├── dataset_row_id
│   ├── market_id
│   ├── exchange_id
│   ├── observation_timestamp
│   ├── blueprint_id
│   ├── horizon
│   └── universe_snapshot_id
│
├── versioning
│   ├── dataset_version
│   ├── feature_snapshot_id
│   ├── feature_version
│   ├── blueprint_version
│   ├── simulator_version
│   ├── execution_model_version
│   └── label_version
│
├── features
│   ├── market_state
│   ├── execution_economics
│   ├── historical_grid_behavior
│   └── derived_ml
│
├── blueprint_context
│   ├── capital
│   ├── section_count
│   ├── allocation
│   ├── grid_spacing
│   ├── section_gap
│   ├── ranges
│   └── grid_counts
│
└── labels
    ├── positive_net_pnl
    ├── expected_net_pnl
    ├── max_drawdown
    ├── capital_utilization
    ├── recovery_probability
    ├── max_section_depth
    └── capital_exhaustion
```

---

# 28. Data Types

Preferred types:

```text
Identifiers:
string

Timestamp:
datetime UTC

Price:
float64 / decimal where required for exact accounting

Percentage:
float

Probability:
float [0,1]

Boolean:
boolean

Categorical State:
controlled string / enum

Counts:
integer

Duration:
numeric duration
```

Financial accounting and exact order-size calculations may require Decimal or equivalent deterministic numeric handling in implementation.

---

# 29. Dataset Layers

The physical implementation may use separate storage layers.

Conceptually:

```text
RAW
 ↓
NORMALIZED
 ↓
FEATURE
 ↓
SIMULATION
 ↓
LABEL
 ↓
TRAINING
```

This separation makes debugging and auditing easier.

---

# 30. Raw Data Layer

Raw data must preserve provider-origin information where legally and operationally appropriate.

Examples:

```text
raw_ohlcv
raw_trades
raw_orderbook
raw_ticker
raw_fee_schedule
raw_market_metadata
```

Raw data should be immutable once ingested, except through explicitly versioned correction processes.

---

# 31. Normalized Data Layer

Normalized data converts provider-specific representations into a common schema.

Example:

```text
market_id
timestamp
open
high
low
close
volume
bid
ask
depth
```

Provider-specific adapters feed this layer.

---

# 32. Feature Data Layer

The Feature Data Layer contains:

```text
Market State
Execution Economics
Historical Grid Behavior
Derived ML
```

Feature versions must be explicit.

Example:

```text
feature_version = v1.0
```

A changed formula requires a new version.

---

# 33. Simulation Data Layer

Simulation records:

```text
simulation_run_id
market_id
observation_timestamp
blueprint_id
simulation_horizon
simulation_version
execution_model_version
initial_capital
initial_state
events
final_state
```

This allows label results to be traced back to actual simulated execution.

---

# 34. Label Data Layer

Labels should be stored separately from input features.

Conceptual:

```text
LabelRecord
│
├── label_id
├── dataset_row_id
├── label_version
├── horizon
├── label_type
├── value
├── event_occurred
├── simulation_status
└── generated_at
```

This separation prevents accidental use of future outcomes as input features.

---

# 35. Training Dataset

Training dataset is generated from approved Feature + Label versions.

Conceptual:

```text
Feature Version
+
Label Version
+
Universe Rule Version
+
Blueprint Rule Version
        ↓
Training Dataset Version
```

Example:

```text
dataset_version = train-v001
```

---

# 36. Validation Dataset

Validation data is temporally later than training data.

Conceptual:

```text
TRAIN
Past Period
      ↓
VALIDATION
Later Period
      ↓
TEST
Future Period
```

The exact periods are defined by experiment configuration.

---

# 37. Test Dataset

Test data is treated as unseen evidence.

The test set MUST NOT be used to:

- tune hyperparameters
- choose features
- choose model architecture
- select thresholds

unless a new experiment explicitly redefines the test set and versions the change.

---

# 38. Time-Based Splitting

Random train/test shuffling is not the default.

Preferred:

```text
TIME
──────────────────────────────────→

TRAIN
██████████

VALIDATION
          █████

TEST
               █████
```

This better represents forward trading deployment.

---

# 39. Walk-Forward Dataset

The dataset must support walk-forward evaluation.

Conceptually:

```text
TRAIN 1 → TEST 1
TRAIN 2 → TEST 2
TRAIN 3 → TEST 3
...
```

Each fold must preserve temporal causality.

---

# 40. Historical Universe Bias

Avoid:

```text
Current Top 10
    ↓
Historical Training Dataset
```

Instead:

```text
Historical T
    ↓
Historical Eligibility
    ↓
Historical Ranking
    ↓
Historical Top 10
    ↓
Observation
```

This prevents survivorship bias.

---

# 41. Delisted / Removed Markets

If a market disappears from the active universe:

```text
market remains in historical data
```

if the historical data genuinely existed.

Do not delete historical market observations merely because the market is no longer active.

This prevents survivorship distortion.

---

# 42. Missing Data Policy

Dataset records must distinguish:

```text
missing
unavailable
zero
not applicable
```

Recommended representation:

```text
value
availability_flag
```

where necessary.

---

# 43. Invalid Observation Policy

An observation may be invalid because:

```text
insufficient market data
missing critical candle
missing execution data
invalid blueprint
failed simulation
```

Invalidity must be represented explicitly.

Do not silently remove records without documenting the exclusion.

---

# 44. Simulation Failure vs Negative Outcome

These are different.

```text
INVALID_SIMULATION
```

means:

> The outcome could not be reliably calculated.

```text
NEGATIVE_OUTCOME
```

means:

> The strategy was successfully simulated and produced a negative result.

This distinction is mandatory.

---

# 45. Data Quality Flags

Each dataset row should support:

```text
data_quality_score
market_data_complete
execution_data_complete
feature_complete
simulation_complete
label_complete
```

These flags allow research to filter low-quality observations.

---

# 46. Feature Leakage Audit

Before a dataset version becomes trainable, it must pass leakage validation.

Check:

```text
Feature Timestamp <= Observation Timestamp
Feature Source Window <= Observation Timestamp
No Future Outcome in Feature Layer
No Test Information in Training
No Post-T Cutoff Market Data
```

---

# 47. Label Alignment Audit

Verify:

```text
Label Start = Observation Timestamp
Label End = Observation Timestamp + Horizon
```

Example:

```text
T = 2026-08-15 12:00
H = 30D

Label Window:
2026-08-15 12:00
→
2026-09-14 12:00
```

No future outcome outside the defined horizon should influence the label.

---

# 48. Blueprint Sampling Strategy

The dataset must define how candidate Blueprints are generated.

Possible sources:

```text
Deterministic Blueprint Generator
Historical Blueprint Templates
Parameter Grid
Research Candidate Generator
```

The system must not randomly generate invalid Blueprints.

All candidate Blueprints pass validation before simulation.

---

# 49. Blueprint Diversity

The dataset should contain enough Blueprint variation for ML to learn:

```text
Different Section Counts
Different Uniform Grid Spacings
Different Section Gaps
Different Capital Allocations
Different Price Ranges
```

However, variation must remain within the actual Grid Strategy's valid constraints.

---

# 50. Dataset Balance Across Blueprints

Do not allow one Blueprint family to dominate the dataset merely because it generates more observations.

Dataset reports should include:

```text
rows by market
rows by blueprint
rows by horizon
rows by regime
rows by outcome class
```

---

# 51. Dataset Balance Across Markets

The Top 10 universe may produce unequal amounts of history.

Research should monitor:

```text
observation_count_by_market
positive_label_rate_by_market
average_outcome_by_market
```

This prevents one highly active market from dominating the entire model.

---

# 52. Storage and Format

The exact storage technology is implementation-dependent.

The dataset format should support:

- Columnar storage
- Efficient historical querying
- Versioning
- Partitioning
- Reproducibility
- Large-scale simulation output

Parquet or an equivalent columnar format is a suitable candidate for research datasets, but the storage technology is not locked by this document.

---

# 53. Partitioning

Recommended conceptual partition keys:

```text
market_id
observation_date
dataset_version
```

Additional partitions may include:

```text
horizon
```

depending on workload.

Do not over-partition the dataset.

---

# 54. Dataset Versioning

Every dataset release must have:

```text
dataset_version
```

Example:

```text
dataset-v001
dataset-v002
```

A new dataset version is required when changing:

- Feature definitions
- Label definitions
- Universe selection rules
- Blueprint generator
- Simulator
- Execution model
- Observation sampling
- Historical correction

---

# 55. Dataset Manifest

Every dataset version should have a manifest.

Conceptual:

```text
DatasetManifest
│
├── dataset_version
├── generated_at
├── date_range
├── markets
├── universe_rule_version
├── feature_version
├── label_version
├── simulator_version
├── execution_model_version
├── blueprint_generator_version
├── row_count
├── valid_row_count
└── invalid_row_count
```

---

# 56. Reproducibility

Given:

```text
Dataset Version
+
Universe Version
+
Feature Version
+
Label Version
+
Blueprint Version
+
Simulator Version
+
Execution Model Version
```

the same dataset row should be reproducible.

This is a core research requirement.

---

# 57. Recommended Initial Dataset Pipeline

```text
OKX RAW DATA
      ↓
NORMALIZATION
      ↓
HISTORICAL UNIVERSE RECONSTRUCTION
      ↓
TOP 10
      ↓
OBSERVATION SAMPLING
      ↓
MARKET STATE
      ↓
EXECUTION ECONOMICS
      ↓
PAST GRID BEHAVIOR
      ↓
DERIVED ML
      ↓
CANDIDATE BLUEPRINTS
      ↓
DETERMINISTIC VALIDATION
      ↓
HISTORICAL GRID SIMULATION
      ↓
LABEL GENERATION
      ↓
DATA QUALITY / LEAKAGE AUDIT
      ↓
DATASET VERSION
      ↓
TRAIN / VALIDATION / TEST
```

---

# 58. Dataset Row Example

Conceptually:

```text
dataset_row_id:
ROW-000001

market_id:
BTC/USDT

exchange_id:
OKX

observation_timestamp:
2026-08-15T12:00:00Z

universe_snapshot_id:
U-2026-08-15

blueprint_id:
BP-0042

horizon:
30D

market_state:
...

execution_economics:
...

historical_grid_behavior:
...

derived_ml:
...

labels:
    positive_net_pnl_30d = 1
    net_pnl_return_30d = 0.038
    max_drawdown_30d = 0.082
    peak_capital_utilization_30d = 0.64
    recovery_30d = 1
    max_section_depth_30d = 2
    capital_exhaustion_30d = 0
```

---

# 59. Dataset Quality Metrics

Every dataset release should report:

```text
Total Rows
Valid Rows
Invalid Rows
Rows per Market
Rows per Blueprint
Rows per Horizon
Positive Outcome Rate
Negative Outcome Rate
Missing Feature Rate
Simulation Failure Rate
Universe Coverage
```

Also:

```text
Leakage Audit Status
Temporal Integrity Status
```

---

# 60. Initial Dataset Version Strategy

The first dataset should be intentionally simple.

Recommended:

```text
Top 10 OKX Spot Markets
+
Monthly / Weekly / Daily
+
Selected Research Observation Frequency
+
7D / 30D / 90D Horizons
+
Candidate Blueprints
+
Canonical Immediate Execution
+
Complete Execution Economics
```

Do not attempt to cover every possible market or every possible timeframe in the first research dataset.

---

# 61. Dataset Security of Meaning

The dataset must preserve the difference between:

```text
Market State
```

```text
Expected / known execution economics
```

```text
Historical Grid Behavior
```

```text
Future strategy outcome
```

Mixing these concepts can produce invalid models.

---

# 62. Non-Negotiable Rules

1. Every row has a causal observation timestamp.
2. No feature may use information after the observation timestamp.
3. Future data is used only for generating labels.
4. Top 10 universe must be reconstructed historically.
5. Current and historical candle states must be preserved.
6. Candidate Blueprint is part of the prediction context.
7. Grid spacing remains uniform within a Section.
8. Section Gaps may differ between Sections.
9. BUY and SELL use immediate execution in simulation.
10. Execution economics use the canonical cost model.
11. Spread and slippage must not be double-counted.
12. Invalid simulations are not negative labels.
13. Dataset versions must be reproducible.
14. Train/validation/test splitting must respect time.
15. Walk-forward evaluation must be supported.
16. Future strategy outcomes must remain separated from feature inputs.
17. Dynamic market-universe selection must be preserved historically.
18. Missing data must not silently become zero.
19. Blueprint configurations must be versioned.
20. Simulator and execution model versions must be stored with label records.

---

# 63. Final Definition

The AI Research Dataset is:

> **A causally ordered, versioned dataset in which each observation captures what was knowable about an eligible Top-10 OKX spot market and a specific valid Grid Blueprint at time T, while separately storing the future strategy outcome used as the ML label.**

The core structure is:

```text
WHAT WAS KNOWN AT T
        ↓
Market State
        +
Execution Economics
        +
Past Grid Behavior
        +
Derived ML
        +
Candidate Blueprint
        ↓
FUTURE SIMULATION
        ↓
ACTUAL OUTCOME
        ↓
LABEL
```

The dataset is considered valid only when:

```text
Temporal Integrity
+
Causal Features
+
Historical Universe Integrity
+
Valid Blueprint
+
Realistic Simulation
+
Correct Execution Economics
+
Correct Labels
```

are all satisfied.

This dataset becomes the foundation for the next stage:

```text
AI_RESEARCH_GRID_SIMULATOR_SPEC.md
```
