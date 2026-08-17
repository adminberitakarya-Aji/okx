# AI Research ML Model Specification

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
- `AI_RESEARCH_GRID_SIMULATOR_SPEC.md`

---

# 1. Purpose

This document defines the technical architecture for the ML layer of AI Research.

The ML system is designed to learn:

> **How likely a specific market + current market context + execution economics + candidate Grid Blueprint are to produce a healthy Grid Strategy outcome over a defined future horizon.**

The ML system is NOT primarily a market-price direction predictor.

Its primary purpose is:

```text
Market
+
Market State
+
Execution Economics
+
Historical Grid Behavior
+
Derived ML
+
Candidate Blueprint
        ↓
ML Prediction
        ↓
Grid Suitability
        ↓
Market Recommendation
```

---

# 2. Research Universe Constraint

The ML system operates on the defined AI Research Universe:

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
ML
```

This is a mandatory v1 constraint.

The model MUST NOT be designed around all OKX markets.

The Top 10 universe is dynamic and must be reconstructed historically for training data.

Therefore:

```text
Top 10 at T
```

must be determined from information available at T.

The current Top 10 must never be applied retroactively to all historical periods.

---

# 3. What the Model Predicts

The prediction unit is:

```text
MARKET
+
OBSERVATION TIME T
+
FEATURE SNAPSHOT AT T
+
CANDIDATE GRID BLUEPRINT
+
HORIZON H
        ↓
FUTURE GRID OUTCOME
```

The model predicts the future outcome of the Grid Strategy, not merely future price direction.

---

# 4. Primary Model Target

Primary target:

```text
Probability of Positive Net P&L
```

Concept:

```text
P(Net P&L > 0 | Features, Blueprint, Horizon)
```

Output:

```text
0.00 → 1.00
```

Example:

```text
BTC/USDT
Blueprint BP-0042
Horizon 30D

Probability of Positive Net P&L:
0.82
```

---

# 5. Secondary Model Targets

Secondary outputs:

```text
Expected Net P&L
Expected Maximum Drawdown
Peak Capital Utilization
Recovery Probability
Maximum Section Depth
Capital Exhaustion Probability
```

Optional future targets:

```text
Recovery Time
Coin Accumulation
Cost-Basis Improvement
Outcome Stability
```

The initial model architecture should remain manageable.

---

# 6. Multi-Model Architecture

The preferred v1 design is modular.

```text
                    FEATURE VECTOR
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
      CLASSIFIER       REGRESSOR       RISK MODEL
          |               |               |
          v               v               v
   P(Positive P&L)   Expected P&L    Expected DD
          |               |               |
          +---------------+---------------+
                          |
                          v
                 SUITABILITY ENGINE
                          |
                          v
                 MARKET RANKING
                          |
                          v
                 RECOMMENDATION
```

Separate models allow:

- independent evaluation
- different loss functions
- independent calibration
- easier debugging
- replacement without redesigning the whole system

---

# 7. Primary Classifier

The primary classifier predicts:

```text
P(Net P&L > 0)
```

Training label:

```text
1 = positive Net P&L
0 = non-positive Net P&L
```

The model should provide:

```text
probability
class
confidence/calibration metrics
```

Do not treat the raw probability as guaranteed probability of future profit.

---

# 8. Expected Net P&L Model

The regression model predicts:

```text
Expected Net P&L Return
```

Recommended normalized target:

```text
Future Net P&L / Starting Capital
```

Example:

```text
+0.034
```

means approximately:

```text
+3.4%
```

The model should support both:

```text
expected_value
prediction_interval
```

where technically feasible.

---

# 9. Drawdown Model

The Drawdown model predicts:

```text
Expected Maximum Strategy Drawdown
```

Output:

```text
expected_max_drawdown
```

A useful model should distinguish:

```text
high expected return
```

from:

```text
high expected return with extreme drawdown
```

---

# 10. Capital Utilization Model

Predict:

```text
Peak Capital Utilization
```

Normalized:

```text
Peak Deployed Capital
/
Starting Capital
```

Example:

```text
0.64
```

means approximately:

```text
64% peak capital utilization
```

This is directly relevant to Section reserve logic.

---

# 11. Recovery Model

Primary recovery prediction:

```text
P(Recovery within H)
```

Input/output must use the deterministic recovery definition from the Label Specification.

Optional future architecture:

```text
Survival / Time-to-Event Model
```

for:

```text
Time to Recovery
```

---

# 12. Capital Exhaustion Model

Predict:

```text
P(Capital Exhaustion within H)
```

This is a risk model.

Example:

```text
Capital Exhaustion Probability = 0.12
```

A market may have high positive-P&L probability but still deserve lower recommendation priority if capital exhaustion probability is too high.

---

# 13. Maximum Section Depth Model

Predict:

```text
Expected / Probability Distribution of Maximum Section Depth
```

Example:

```text
P(Section 1 only) = 0.32
P(Section 2)      = 0.51
P(Section 3)      = 0.17
```

This is particularly useful for the Section Gap strategy.

---

# 14. Input Feature Architecture

The ML input is assembled from:

```text
LAYER 1
Market State
      +
LAYER 2
Execution Economics
      +
LAYER 3
Past Grid Behavior
      +
LAYER 4
Derived ML
      +
BLUEPRINT CONTEXT
```

Blueprint context includes:

```text
section_count
capital_allocation
uniform_grid_spacing_per_section
section_gap_per_transition
grid_count_per_section
price_range_per_section
```

Future outcome data MUST NOT be part of the input vector.

---

# 15. Market Identity Treatment

`market_id` and `exchange_id` should not automatically be fed as raw categorical values.

Potential approaches:

```text
one-hot
embedding
market-independent normalization
```

The preferred approach should be selected experimentally.

The model must avoid simply memorizing:

```text
BTC = good
SOL = bad
```

The goal is to learn:

```text
market characteristics
```

rather than market name alone.

---

# 16. Top 10 Research Universe and Model Bias

The Top 10 constraint reduces computational load but introduces a critical dataset consideration.

The model must learn from:

```text
markets eligible at T
```

rather than:

```text
markets that are currently successful
```

Historical universe reconstruction is therefore part of the ML data pipeline.

The model should support market turnover:

```text
Market enters Top 10
Market remains Top 10
Market leaves Top 10
```

---

# 17. Feature Versioning

Every training job references:

```text
feature_version
```

Example:

```text
feature-v001
```

A feature formula change requires a new feature version.

The model registry must store the feature version used during training.

---

# 18. Label Versioning

Every model references:

```text
label_version
```

Example:

```text
label-v001
```

A change to:

```text
horizon
recovery definition
profit threshold
outcome calculation
```

requires a new label version.

---

# 19. Dataset Versioning

Every training experiment must reference:

```text
dataset_version
```

Example:

```text
dataset-v001
```

A model without a recorded dataset version is not considered reproducible.

---

# 20. Simulator Version

Because labels originate from simulation:

```text
simulator_version
```

must be stored.

Changing:

```text
execution logic
Section activation
Grid cycle matching
P&L logic
```

may materially change labels and therefore requires retraining.

---

# 21. Execution Model Version

Training data must reference:

```text
execution_model_version
```

This guarantees the model learned from a known:

```text
fee
spread
slippage
liquidity
price impact
```

model.

---

# 22. Blueprint Encoding

Blueprint context must preserve:

```text
section_count
section_allocation
uniform_grid_spacing
section_gap
grid_count
price_ranges
```

The model should not receive only:

```text
blueprint_id
```

because this would allow memorization without understanding the actual strategy configuration.

A deterministic Blueprint ID remains useful for traceability.

---

# 23. Blueprint Feature Representation

Numerical blueprint parameters should generally be normalized.

Example:

```text
capital_allocation_section_1 = 0.30
capital_allocation_section_2 = 0.35

grid_spacing_section_1 = 0.01
grid_spacing_section_2 = 0.015

section_gap_1 = 0.05
section_gap_2 = 0.10
```

The exact encoding should preserve:

```text
Section order
Section relationships
Uniform spacing within each Section
Different Section Gaps
```

---

# 24. Candidate Blueprint Evaluation

For one observation:

```text
Market + T
```

the system may evaluate multiple Blueprints:

```text
BP-001
BP-002
BP-003
...
```

ML predicts each separately:

```text
BTC + BP-001 → 0.81
BTC + BP-002 → 0.67
BTC + BP-003 → 0.84
```

This enables:

```text
Blueprint comparison
```

without confusing market suitability with one fixed configuration.

---

# 25. Model Objective

The overall model system should optimize for:

```text
Useful Market Selection
+
Useful Blueprint Selection
+
Positive Net Economics
+
Controlled Risk
```

It should NOT optimize simply for:

```text
prediction accuracy
```

A model can have high statistical accuracy but poor trading utility.

---

# 26. Evaluation Metrics — Classifier

Primary:

```text
ROC-AUC
PR-AUC
Log Loss
Brier Score
Calibration Error
```

Additional:

```text
Precision
Recall
F1
```

But trading usefulness is ultimately evaluated through:

```text
out-of-sample Grid performance
```

---

# 27. Evaluation Metrics — Regressors

For Expected Net P&L:

```text
MAE
RMSE
R²
Spearman Rank Correlation
```

For Drawdown:

```text
MAE
RMSE
Rank Correlation
```

The model should also be evaluated on whether ranking by predicted value improves real Grid outcomes.

---

# 28. Ranking Evaluation

Because AI Research eventually ranks the Top 10 markets, ranking quality matters.

Possible metrics:

```text
NDCG
Spearman Rank Correlation
Top-K Precision
Top-K Outcome Lift
```

Example question:

> Does selecting the model's Top 3 markets produce better future Grid outcomes than selecting random or volume-only markets?

This is more meaningful than classification accuracy alone.

---

# 29. Calibration

The primary probability model must be calibrated.

If the model predicts:

```text
0.80
```

for many observations, the actual positive rate should be reasonably close to:

```text
80%
```

over sufficiently large samples.

Potential calibration methods can be evaluated later.

---

# 30. Baseline Models

Before sophisticated ML, establish baselines.

Possible baseline:

```text
Rule-based suitability
```

and simple statistical models such as:

```text
Logistic Regression
Linear Regression
Decision Tree
```

The purpose is to determine whether ML provides meaningful improvement.

Do not assume a complex model is better.

---

# 31. Candidate Model Families

Potential model families:

```text
Linear / Generalized Linear
Tree-Based
Gradient Boosting
Random Forest
XGBoost / LightGBM-like
Neural Network
```

The model family is intentionally NOT locked by this document.

Selection must follow:

```text
Feature Quality
+
Dataset Size
+
Target Quality
+
Validation Results
+
Interpretability
+
Operational Cost
```

---

# 32. Recommended Model Development Order

```text
Baseline
   ↓
Simple Linear / Logistic
   ↓
Tree-Based Baseline
   ↓
Gradient Boosting
   ↓
Advanced Model if justified
```

Do not jump directly to deep learning.

---

# 33. Cross-Market Generalization

The model should be evaluated for:

```text
Seen Markets
```

and:

```text
Held-Out Markets
```

where possible.

Example:

```text
Train:
8 markets

Test:
2 unseen markets
```

This can reveal whether the model learned:

```text
general market characteristics
```

or:

```text
market-specific memorization
```

---

# 34. Time-Based Validation

Default validation:

```text
PAST → TRAIN
LATER → VALIDATION
FUTURE → TEST
```

Random shuffle is not the default.

This preserves temporal causality.

---

# 35. Walk-Forward Validation

The model must support:

```text
TRAIN 1 → TEST 1
TRAIN 2 → TEST 2
TRAIN 3 → TEST 3
...
```

This simulates repeated future deployment.

Walk-forward results should become a major criterion for model acceptance.

---

# 36. Hyperparameter Tuning

Hyperparameter tuning must use:

```text
training
+
validation
```

and NOT the final test set.

The test set remains unseen until final evaluation.

---

# 37. Feature Importance

The model system should provide feature importance or equivalent interpretability.

Possible methods:

```text
Permutation Importance
Tree Importance
SHAP-like explanations
Model Coefficients
```

The exact method is model-dependent.

---

# 38. Recommendation Explainability

For one recommendation:

```text
BTC
```

the system should eventually explain:

```text
Positive P&L Probability: High
Expected Net P&L: Favorable
Expected Drawdown: Moderate
Execution Economics: Strong
Grid Compatibility: High
Capital Consumption Risk: Moderate
```

The explanation must map back to:

```text
features
model outputs
```

rather than fabricated LLM reasoning.

---

# 39. Overfitting Controls

Required safeguards:

```text
Time-based split
Walk-forward testing
Feature versioning
Model versioning
Regularization
Feature selection
Early stopping where applicable
Unseen-market tests
```

Potential additional methods:

```text
dropout
bagging
cross-validation within training period
```

depending on model family.

---

# 40. Feature Selection

Feature selection should consider:

```text
Predictive value
Stability
Redundancy
Causality
Interpretability
Compute cost
```

Highly correlated derived features should not automatically all be retained.

Feature selection must be performed using training/validation data only.

---

# 41. Class Imbalance

The system must measure:

```text
positive label rate
negative label rate
```

before selecting imbalance strategies.

Possible techniques:

```text
class weights
threshold optimization
sampling
```

No technique is mandatory until empirical imbalance is known.

---

# 42. Prediction Confidence

The model should provide confidence or uncertainty where supported.

Important distinction:

```text
Model probability
```

is not identical to:

```text
business confidence
```

Recommendation confidence should be constructed by the Suitability/Recommendation layer using:

```text
model quality
calibration
sample size
data quality
market coverage
```

---

# 43. Model Output Contract

Conceptual:

```text
MLPrediction
│
├── market_id
├── blueprint_id
├── observation_timestamp
├── horizon
├── model_version
├── feature_version
├── dataset_version
│
├── positive_pnl_probability
├── expected_net_pnl
├── expected_max_drawdown
├── peak_capital_utilization
├── recovery_probability
├── maximum_section_depth_distribution
└── capital_exhaustion_probability
```

Optional future:

```text
expected_recovery_time
coin_accumulation_prediction
cost_basis_improvement_prediction
uncertainty_interval
```

---

# 44. Suitability Engine Boundary

The ML model produces predictions.

The Suitability Engine interprets them.

Conceptually:

```text
ML Predictions
      +
Execution Economics
      +
Grid Behavior
      ↓
SUITABILITY
```

Example:

```text
Positive P&L Probability = 0.82
Expected Net P&L = +3.4%
Expected DD = 8.0%
Capital Utilization = 64%
Capital Exhaustion = 0.10
```

The Suitability Engine may classify:

```text
HIGH
```

but the exact thresholds belong to a separate Recommendation specification.

---

# 45. Market Ranking Boundary

Ranking occurs after prediction.

```text
Top 10 Market Universe
        ↓
ML Predictions
        ↓
Suitability
        ↓
Ranking
        ↓
Market Recommendation
```

Ranking should not simply sort by:

```text
positive_pnl_probability
```

alone.

It should consider the complete suitability profile.

---

# 46. Top 10 Ranking Example

Conceptual:

```text
BTC
P(Positive) = 0.82
Expected P&L = 3.4%
DD = 8.0%

ETH
P(Positive) = 0.79
Expected P&L = 3.1%
DD = 6.5%

SOL
P(Positive) = 0.56
Expected P&L = 5.1%
DD = 15.0%
```

The final ranking may prefer BTC or ETH despite SOL's higher expected return because risk-adjusted suitability may be stronger.

The final ranking formula is a separate specification.

---

# 47. Training Pipeline

```text
VERSIONED DATASET
        ↓
TRAIN / VALIDATION / TEST SPLIT
        ↓
FEATURE PREPARATION
        ↓
MODEL TRAINING
        ↓
VALIDATION
        ↓
CALIBRATION
        ↓
WALK-FORWARD TEST
        ↓
OUT-OF-SAMPLE GRID EVALUATION
        ↓
MODEL ACCEPTANCE
        ↓
MODEL REGISTRY
```

---

# 48. Model Registry

Every model must store:

```text
model_version
model_family
dataset_version
feature_version
label_version
simulator_version
execution_model_version
training_period
validation_period
test_period
hyperparameters
evaluation_metrics
calibration_metrics
status
```

Possible status:

```text
EXPERIMENTAL
CANDIDATE
VALIDATED
PRODUCTION
RETIRED
```

---

# 49. Model Promotion

A model should not become production merely because it has a good validation score.

Promotion requires:

```text
Out-of-Sample Performance
+
Walk-Forward Stability
+
Calibration
+
Market Coverage
+
Risk Behavior
+
Grid Outcome Improvement
```

The acceptance process should be deterministic and versioned.

---

# 50. Model Monitoring

Production model monitoring should track:

```text
Prediction Distribution
Probability Calibration
Feature Distribution Shift
Market Universe Shift
Outcome Drift
Net P&L Impact
Drawdown Impact
Ranking Quality
```

---

# 51. Data Drift

Examples:

```text
Volatility regime changes
Liquidity changes
Fee changes
Market composition changes
Top 10 composition changes
```

A model trained on one regime may degrade under another.

The system must monitor feature distribution changes.

---

# 52. Concept Drift

The relationship:

```text
Market State
→
Grid Outcome
```

may change over time.

Therefore the model must support:

```text
retraining
revalidation
rollback
```

but never silent model replacement without governance.

---

# 53. Retraining

Retraining should be triggered by policy.

Possible triggers:

```text
scheduled retraining
performance degradation
concept drift
universe change
execution-model change
feature-model change
```

The exact policy belongs to the model operations specification.

---

# 54. Model Rollback

The system must support returning to a previous validated model.

Example:

```text
Production:
model-v003

Rollback:
model-v002
```

All model-dependent recommendations must identify the active model version.

---

# 55. Research vs Production Model

Research may evaluate:

```text
model-v004-experimental
```

while production continues using:

```text
model-v003
```

Experimental models must not affect production execution automatically.

---

# 56. No Direct Execution

ML model output MUST NOT directly call:

```text
BUY API
SELL API
```

The architecture remains:

```text
ML
 ↓
Suitability
 ↓
Recommendation
 ↓
Realtime AI / Blueprint
 ↓
Deterministic Validation
 ↓
Execution Engine
```

---

# 57. No Silent Strategy Modification

ML may identify:

```text
Section Gap pattern
Grid spacing pattern
Capital allocation pattern
```

But those findings remain research recommendations.

Any change to the production Grid Strategy must pass:

```text
Research
↓
Backtest
↓
Simulation
↓
Validation
↓
Approval / Policy
↓
Production
```

---

# 58. Explainable Failure

The ML system may output:

```text
LOW CONFIDENCE
INSUFFICIENT DATA
OUT-OF-DISTRIBUTION
NO RELIABLE PREDICTION
```

It must not force a numerical recommendation when evidence is inadequate.

---

# 59. Initial ML Development Strategy

Recommended v1 sequence:

```text
1. Build deterministic dataset
2. Build primary classification baseline
3. Build Expected Net P&L regression baseline
4. Build Drawdown regression baseline
5. Evaluate calibration
6. Evaluate ranking
7. Evaluate out-of-sample Grid outcomes
8. Add secondary models
9. Compare candidate model families
10. Select validated model set
```

---

# 60. First Model Goal

The first successful ML experiment does NOT need to be the most sophisticated.

Success means:

> **The ML-ranked Top 10 markets produce measurably better out-of-sample Grid outcomes than a reasonable non-ML baseline.**

Potential baselines:

```text
volume ranking
liquidity ranking
rule-based Grid Suitability
random eligible market selection
```

This provides a meaningful benchmark.

---

# 61. Non-Negotiable Rules

1. ML Research operates on the dynamic Top 10 eligible OKX Spot universe.
2. Historical Top 10 membership must be reconstructed at each historical observation.
3. ML predicts Grid Strategy outcomes, not generic price direction as the primary objective.
4. Prediction is conditional on a specific valid Candidate Blueprint.
5. Positive Net P&L Probability is the primary target.
6. Expected Net P&L and Expected Drawdown are key secondary targets.
7. Training inputs may only contain information available at or before observation time T.
8. Future simulation outcomes are labels, never input features.
9. Immediate BUY/SELL execution is part of label generation.
10. Execution economics must be consistent between training and later evaluation.
11. Grid spacing remains uniform inside each Section.
12. Section Gaps may differ.
13. Model versions must reference all upstream data, feature, label, simulator, and execution versions.
14. Test data must remain unseen during model selection.
15. Walk-forward evaluation is required.
16. Model probability must be calibrated or explicitly treated as uncalibrated.
17. ML outputs do not directly execute trades.
18. ML outputs do not silently modify production strategy.
19. Model promotion requires out-of-sample evidence.
20. The system may return no reliable prediction when evidence is insufficient.

---

# 62. Final Definition

The AI Research ML Model Layer is:

> **A modular predictive layer that learns the relationship between market conditions, immediate-execution economics, historical Grid behavior, derived strategy features, and candidate Grid Blueprints in order to estimate future Grid Strategy outcomes for the dynamic Top 10 OKX Spot Research Universe.**

The final architecture is:

```text
TOP 10 OKX SPOT UNIVERSE
          ↓
MARKET STATE
          +
EXECUTION ECONOMICS
          +
PAST GRID BEHAVIOR
          +
DERIVED ML
          +
CANDIDATE BLUEPRINT
          ↓
VERSIONED DATASET
          ↓
GRID SIMULATION LABELS
          ↓
ML MODELS
          ↓
PREDICTIONS
          ↓
SUITABILITY ENGINE
          ↓
MARKET RANKING
          ↓
MARKET RECOMMENDATION
          ↓
REALTIME AI / GRID BLUEPRINT
```

The ML layer provides intelligence.

It does not own execution.

The deterministic Grid Engine and risk/validation layers remain the final guardians of mathematical correctness and execution safety.
