# ML Training Pipeline Specification

Version: 1.0

Status: Foundation

Parent Documents:
- `AI_RESEARCH.md`
- `AI_RESEARCH_TECHNICAL_DESIGN.md`
- `AI_RESEARCH_ML_MODEL_SPEC.md`
- `AI_RESEARCH_DATASET_SPEC.md`
- `AI_RESEARCH_FEATURE_SPEC_MARKET_STATE.md`
- `AI_RESEARCH_FEATURE_SPEC_EXECUTION_ECONOMICS.md`
- `AI_RESEARCH_FEATURE_SPEC_GRID_BEHAVIOR.md`
- `AI_RESEARCH_FEATURE_SPEC_DERIVED_ML.md`
- `AI_RESEARCH_LABEL_SPEC.md`

---

# 1. Purpose

This document defines the end-to-end ML training pipeline for the Trading Grid AI System.

The ML training pipeline is responsible for:

```text
Historical Data Ingestion
        ↓
Feature Engineering
        ↓
Blueprint Generation
        ↓
Grid Simulation
        ↓
Label Generation
        ↓
Dataset Building
        ↓
Model Training
        ↓
Model Validation
        ↓
Model Promotion
        ↓
Production Inference
```

**Key Principle:** The ML pipeline runs **offline** (developer/scheduled), not at runtime. Users of the Telegram bot do NOT need to train models — they use pre-trained models that are deployed with the system.

---

# 2. Technology Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| ML Framework | scikit-learn >= 1.5.0 | Baseline models, metrics, validation |
| Gradient Boosting | LightGBM >= 4.5.0 | Primary model family (recommended) |
| Data Processing | pandas >= 2.2.0 | Feature engineering, dataset building |
| Fast Data Processing | polars >= 1.8.0 | Large-scale data operations |
| Storage Format | pyarrow >= 17.0.0 | Parquet files for data & features |
| Model Serialization | pickle (stdlib) | Model persistence |
| Metadata | json (stdlib) | Model metadata & versioning |

**Why NOT Third-Party AI (LLM APIs)?**

| Aspect | Local ML (LightGBM) | Third-Party AI (LLM) |
|--------|---------------------|----------------------|
| Latency | ~1-10ms per prediction | ~500-2000ms per request |
| Cost | Free (own compute) | Per-token/per-request |
| Data Privacy | ✅ Data stays on server | ❌ Data sent externally |
| Deterministic | ✅ Consistent results | ❌ Can vary |
| Training | ✅ Train on own data | ❌ Cannot fine-tune for this use case |
| Offline | ✅ Works without internet | ❌ Requires API access |
| Use Case Fit | ✅ Tabular/numerical data | ❌ LLMs are for text, not time series |

---

# 3. Pipeline Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    ML TRAINING PIPELINE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. DATA INGESTION                                       │   │
│  │    ├── Fetch candles (OHLCV) from exchanges             │   │
│  │    ├── Fetch order book snapshots                       │   │
│  │    ├── Fetch ticker data                                │   │
│  │    └── Store to Parquet files                           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 2. FEATURE ENGINEERING                                  │   │
│  │    ├── Market State features (volatility, momentum)     │   │
│  │    ├── Execution Economics features (spread, slippage)  │   │
│  │    ├── Grid Behavior features (historical performance)  │   │
│  │    └── Derived ML features (regime, rolling stats)      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 3. BLUEPRINT GENERATION                                 │   │
│  │    └── Generate candidate blueprints per market         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 4. GRID SIMULATION                                      │   │
│  │    ├── Simulate grid on historical data                 │   │
│  │    └── Generate outcome metrics                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 5. LABEL GENERATION                                     │   │
│  │    └── Convert simulation results → labels              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 6. DATASET BUILDING                                     │   │
│  │    ├── Join features + labels                           │   │
│  │    ├── Validate causal integrity                        │   │
│  │    └── Time-based split (train/val/test)                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 7. MODEL TRAINING                                       │   │
│  │    ├── Train 6 models (LightGBM/sklearn)                │   │
│  │    └── Walk-forward validation                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ↓                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 8. MODEL PROMOTION                                      │   │
│  │    ├── Evaluate against baseline                        │   │
│  │    ├── Promote best model to production                 │   │
│  │    └── ResearchService auto-switch to ML mode           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

# 4. Data Ingestion

## 4.1 Data Requirements

| Data Type | Source | Interval | Minimum History |
|-----------|--------|----------|-----------------|
| Candles (OHLCV) | TradingGrid/Binance/Bybit API | 1H (primary), 1D (regime) | 6 months (ideal: 1-2 years) |
| Order Book Snapshots | Exchange API | Periodic snapshots | 3 months |
| Ticker Data | Exchange API | Real-time + historical | 6 months |
| Market Metadata | Exchange API | Static + updates | Current |

## 4.2 Data Volume Estimation

```text
10 markets × 24 hours × 180 days = ~43,200 candles per market
Total: ~432,000 candles for 6 months
Storage: ~1-5 GB (Parquet, compressed)
```

## 4.3 Ingestion Clients

Located in `src/trading_grid/research/ingestion/`:

| File | Purpose |
|------|---------|
| `okx_client.py` | Fetch data from OKX |
| `binance_client.py` | Fetch data from Binance |
| `bybit_client.py` | Fetch data from Bybit |
| `storage.py` | Store to Parquet files |

## 4.4 API Keys for Ingestion

API keys are configured in `.env` for **system/developer use**, not for end users:

```bash
# .env (system credentials for data ingestion & trading)
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
OKX_DEMO_MODE=true

BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET_MODE=true

BYBIT_API_KEY=...
BYBIT_API_SECRET=...
BYBIT_TESTNET_MODE=true
```

---

# 5. Feature Engineering

## 5.1 Feature Categories

Located in `src/trading_grid/research/features/`:

| Category | File | Example Features |
|----------|------|------------------|
| Market State | `market_state.py` | Volatility, momentum, volume ratio, price position |
| Execution Economics | `execution_economics.py` | Spread, slippage estimate, fee impact |
| Grid Behavior | `grid_behavior.py` | Historical grid performance metrics |
| Derived ML | `derived_ml.py` | Regime detection, rolling statistics |

## 5.2 Feature Count

Total features per observation: **~60+ features**

## 5.3 Causal Integrity

**CRITICAL:** All features at time T must use only data available at or before T.

```text
✅ CORRECT: Feature at T uses data [T-lookback, T]
❌ WRONG: Feature at T uses data from T+1 or later
```

---

# 6. Blueprint Generation

Located in `src/trading_grid/research/models/blueprint_generator.py`

For each market at each observation time, generate candidate Grid Blueprints:

```text
Market at T
    ↓
Blueprint Generator
    ↓
Candidate Blueprints:
├── Conservative (fewer levels, wider spacing)
├── Moderate (balanced)
└── Aggressive (more levels, tighter spacing)
```

---

# 7. Grid Simulation

Located in `src/trading_grid/research/simulator/grid_simulator.py`

The Grid Simulator runs deterministic simulations:

```text
Historical Candles + Blueprint
            ↓
      Grid Simulator
            ↓
Simulation Results:
├── Net P&L
├── Max Drawdown
├── Completed Cycles
├── Capital Utilization
├── Recovery Status
└── Capital Exhaustion Status
```

**Principle:** The simulator is deterministic — same input produces same output.

---

# 8. Label Generation

Located in `src/trading_grid/research/labels/generator.py`

## 8.1 Label Types

| Label | Type | Description |
|-------|------|-------------|
| `positive_pnl` | Binary (0/1) | Did the grid profit? |
| `net_pnl_return` | Continuous | What % return? |
| `max_drawdown` | Continuous | What % max drawdown? |
| `capital_utilization` | Continuous | What % capital used? |
| `recovered` | Binary (0/1) | Did grid recover from DD? |
| `capital_exhausted` | Binary (0/1) | Did capital run out? |

## 8.2 Label Horizon

Labels are generated over a defined future horizon H (e.g., 30 days):

```text
Observation at T
    ↓
Future Window [T, T+H]
    ↓
Grid Simulation on Future Window
    ↓
Outcome → Label
```

---

# 9. Dataset Building

Located in `src/trading_grid/research/dataset/builder.py`

## 9.1 Dataset Row Structure

```text
dataset_row_id
market_id
exchange_id
observation_timestamp
blueprint_id
horizon
universe_snapshot_id
feature_snapshot_id
label_snapshot_id
simulation_run_id
[60+ feature columns]
[6 label columns]
```

## 9.2 Time-Based Split

**CRITICAL:** Never use random shuffle. Always split by time:

```text
┌─────────────────────────────────────────────────────────────────┐
│  Timeline                                                       │
├─────────────────────────────────────────────────────────────────┤
│  [TRAIN: T0 → T1] [VALIDATION: T1 → T2] [TEST: T2 → T3]        │
│                                                                 │
│  Example (6 months data):                                       │
│  TRAIN: Months 1-4 (67%)                                        │
│  VALIDATION: Month 5 (16%)                                      │
│  TEST: Month 6 (17%)                                            │
└─────────────────────────────────────────────────────────────────┘
```

## 9.3 Dataset Versioning

Each dataset has a version identifier:

```text
dataset_version = "dataset-v001"
```

---

# 10. Model Training

Located in `src/trading_grid/research/models/trainer.py`

## 10.1 Models to Train

| Model | Type | Target |
|-------|------|--------|
| Primary Classifier | Classification | P(Net P&L > 0) |
| Net P&L Regressor | Regression | Expected return % |
| Drawdown Regressor | Regression | Expected max DD % |
| Capital Utilization Regressor | Regression | Expected utilization % |
| Recovery Classifier | Classification | P(Recovery) |
| Capital Exhaustion Classifier | Classification | P(Exhaustion) |

## 10.2 Model Families

| Family | Library | Status |
|--------|---------|--------|
| **LightGBM** | `lightgbm` | ✅ **Recommended** |
| Gradient Boosting | `sklearn` | ✅ Fallback |
| Random Forest | `sklearn` | ✅ Available |
| Decision Tree | `sklearn` | ✅ Available |
| Logistic Regression | `sklearn` | ✅ Baseline |
| Linear Regression | `sklearn` | ✅ Baseline |

## 10.3 Training Configuration

```python
ModelConfig(
    model_type=ModelType.PRIMARY_CLASSIFIER,
    model_family=ModelFamily.LIGHTGBM,
    feature_version="fml-v001",
    label_version="label-v001",
    dataset_version="dataset-v001",
    simulator_version="sim-v001",
    execution_model_version="exec-v001",
    horizon="30D",
    hyperparameters={
        "n_estimators": 100,
        "learning_rate": 0.1,
        "max_depth": 6,
        "num_leaves": 31,
    },
    random_seed=42,
    calibration_enabled=True,
)
```

## 10.4 Walk-Forward Validation

Per spec §35: Simulates repeated future deployment.

```text
Fold 1: Train [T0, T1] → Test [T1, T2]
Fold 2: Train [T0, T2] → Test [T2, T3]
Fold 3: Train [T0, T3] → Test [T3, T4]
...
Aggregate: Mean ± Std of metrics across folds
```

## 10.5 Evaluation Metrics

**Classification:**
- ROC-AUC
- PR-AUC
- Log Loss
- Brier Score
- Precision, Recall, F1
- Calibration Error

**Regression:**
- MAE
- RMSE
- R²
- Spearman Correlation

---

# 11. Model Registry

Located in `src/trading_grid/research/models/registry.py`

## 11.1 Model Lifecycle

```text
TRAINING → TRAINED → VALIDATED → DEPLOYED → ARCHIVED
                ↘ FAILED
```

## 11.2 Model Storage

```text
models/
├── model-primary_classifier-20260815-a1b2c3d4.pkl      # Model weights
├── model-primary_classifier-20260815-a1b2c3d4.meta.json # Metadata
└── ...
```

## 11.3 Model Promotion

```text
1. Train new model
2. Evaluate on validation set
3. Compare with current production model
4. If better → promote to production
5. ResearchService auto-detects and switches to ML mode
```

---

# 12. Deployment Flow

## 12.1 Developer vs User Responsibilities

| Aspect | Developer | End User |
|--------|-----------|----------|
| API Key Exchange | ✅ In system .env | ❌ Not needed (or via /connect for trading) |
| ML Training | ✅ Run once (or scheduled) | ❌ Not needed |
| Historical Data | ✅ Fetch once | ❌ Not needed |
| Model Files | ✅ Include in deployment | ❌ Not visible |
| Use Bot | - | ✅ Use directly |

## 12.2 Production Deployment

```text
┌─────────────────────────────────────────────────────────────────┐
│                    DEVELOPMENT PHASE (Offline)                  │
├─────────────────────────────────────────────────────────────────┤
│ 1. Developer sets API keys in .env                              │
│ 2. Run data ingestion → collect historical data                 │
│ 3. Run ML training pipeline → produce models                    │
│ 4. Models saved to models/ folder or database                   │
│ 5. Models promoted to production                                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    PRODUCTION PHASE (Live Bot)                  │
├─────────────────────────────────────────────────────────────────┤
│ 1. Deploy Telegram bot + trained models                         │
│ 2. Bot immediately uses ML mode (not heuristic)                 │
│ 3. Users DO NOT need to:                                        │
│    ❌ Train models again                                        │
│    ❌ Fetch historical data again                               │
│    ❌ Setup ML pipeline                                         │
│ 4. Users ONLY need to:                                          │
│    ✅ /start → create account                                   │
│    ✅ Connect exchange (if want to trade)                       │
│    ✅ Use TOP 10, Blueprint, Grid features                      │
└─────────────────────────────────────────────────────────────────┘
```

---

# 13. Retraining Schedule

## 13.1 Recommended Schedule

| Frequency | Action |
|-----------|--------|
| Weekly | Fetch new data |
| Monthly | Retrain models with latest data |
| Monthly | Evaluate and compare with current model |
| As needed | Promote if new model is better |

## 13.2 Automated Retraining (Future)

Can be automated with scheduler (APScheduler/ARQ):

```text
Scheduled Job (Monthly):
├── Fetch new data since last training
├── Rebuild dataset
├── Retrain models
├── Evaluate against current production model
├── If better → promote automatically
└── Notify admin via Telegram
```

---

# 14. Training Orchestrator Script

A training orchestrator script coordinates the entire pipeline:

```text
scripts/run_ml_training.py

Usage:
    uv run python scripts/run_ml_training.py --full      # Full pipeline
    uv run python scripts/run_ml_training.py --ingest    # Data ingestion only
    uv run python scripts/run_ml_training.py --features  # Feature engineering only
    uv run python scripts/run_ml_training.py --simulate  # Simulation & labels only
    uv run python scripts/run_ml_training.py --train     # Model training only
    uv run python scripts/run_ml_training.py --evaluate  # Evaluation only
    uv run python scripts/run_ml_training.py --promote   # Promote model
    uv run python scripts/run_ml_training.py --status    # Show pipeline status
    uv run python scripts/run_ml_training.py --force     # Force promote (skip quality gate)

Options:
    --exchange OKX|BINANCE|BYBIT   # Data source (default: OKX)
    --markets BTC-USDT,ETH-USDT    # Comma-separated market list
    --months 6                     # Historical data period
```

**Status:** ✅ Implemented (2026-08-17). See IMPLEMENTATION_PLAN.md Phase 7.

Scheduled retraining is available via `scripts/run_ml_scheduler.py` (APScheduler):
- Weekly data refresh: Sunday 02:00 UTC
- Monthly full retraining: 1st of month 03:00 UTC
- Weekly evaluation report: Monday 08:00 UTC

---

# 15. Current Status

> **Updated:** 2026-08-17

| Component | Status | Location |
|-----------|--------|----------|
| Ingestion clients (OKX, Binance, Bybit) | ✅ Implemented | `research/ingestion/` |
| Storage (Parquet) | ✅ Implemented | `research/ingestion/storage.py` |
| Feature engineering | ✅ Implemented | `research/features/` |
| Blueprint generator | ✅ Implemented | `research/models/blueprint_generator.py` |
| Grid simulator | ✅ Implemented | `research/simulator/grid_simulator.py` |
| Label generator | ✅ Implemented | `research/labels/generator.py` |
| Dataset builder | ✅ Implemented | `research/dataset/builder.py` |
| Model trainer | ✅ Implemented | `research/models/trainer.py` |
| Model registry | ✅ Implemented | `research/models/registry.py` |
| Training orchestrator | ✅ Implemented | `scripts/run_ml_training.py` |
| Scheduled retraining | 🟡 Script exists, deployment pending | `scripts/run_ml_scheduler.py` |
| Historical data | ✅ Fetched (9 markets, 38,880 candles, 6 months) | `data/research/v1/BINANCE/` |
| Trained models | ✅ 6 LightGBM models DEPLOYED (Val ROC-AUC ~0.53, synthetic labels) | `models/` |
| ResearchService ML mode integration | 🟡 Pending — heuristic mode active | `application/services/research_service.py` |

**Notes:**
- Data fetched via Binance public API fallback (`data-api.binance.vision`) due to OKX API DNS issues
- Models promoted with `--force` since synthetic labels produce ~0.5 ROC-AUC (expected baseline)
- Real simulation labels needed to reach target ROC-AUC > 0.75

---

# 16. Security Considerations

1. **API keys** in `.env` are for system use only — never expose to users
2. **Training data** stays on server — never sent to third parties
3. **Model files** do not contain sensitive data — safe to deploy
4. **Audit logging** for all training and promotion operations

---

# 17. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-17 | Initial ML Training Pipeline specification |
| 1.1 | 2026-08-17 | Updated §14-15: Training orchestrator implemented, historical data fetched (9 markets via Binance fallback), 6 models DEPLOYED. Added scheduler script reference. |
