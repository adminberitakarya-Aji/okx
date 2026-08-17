# Admin Dashboard Specification

Version: 1.0

Status: Foundation

Parent Documents:
- `APPLICATION_CONTROL_API_SPEC.md`
- `TELEGRAM_GATEWAY_SPEC.md`
- `SECURITY_AUTHORIZATION_SPEC.md`
- `ML_TRAINING_PIPELINE_SPEC.md`

---

# 1. Purpose

This document defines the Admin Dashboard for monitoring ML models, training pipelines, and overall bot performance.

The Admin Dashboard provides developers/administrators with:

```text
┌─────────────────────────────────────────────────────────────────┐
│                    ADMIN DASHBOARD                              │
├─────────────────────────────────────────────────────────────────┤
│ 1. ML model status monitoring (active/inactive, version, perf)  │
│ 2. Training pipeline monitoring (progress, status, errors)      │
│ 3. Bot performance monitoring (ranking accuracy, grid perf)     │
│ 4. Manual retraining trigger or view scheduled runs             │
│ 5. Audit trail for all ML operations                            │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principle:** The dashboard is for **developers/admins only**, not end users. It provides observability into the ML system and bot performance.

---

# 2. Dashboard Features

## 2.1 ML Model Status

| Information | Description |
|-------------|-------------|
| Active model | Model ID, version, when promoted |
| Ranking mode | ML or Heuristic |
| Model metrics | ROC-AUC, Precision, Recall, F1 |
| Feature importance | Most influential features |
| Last prediction | When last inference occurred |
| Prediction distribution | Suitability score distribution |

**Example Display:**

```text
┌─────────────────────────────────────────────────────────────────┐
│  ML MODEL STATUS                                                │
├─────────────────────────────────────────────────────────────────┤
│  Active Model: model-primary_classifier-20260815-a1b2c3d4       │
│  Mode: ML (not heuristic)                                       │
│  Promoted: 2026-08-15 10:30 UTC                                 │
│  ROC-AUC: 0.82 | Precision: 0.78 | Recall: 0.75                 │
│  Last Inference: 2026-08-17 11:30 UTC                           │
│  Predictions Today: 145                                         │
└─────────────────────────────────────────────────────────────────┘
```

## 2.2 Training Pipeline Status

| Information | Description |
|-------------|-------------|
| Last training run | When, duration, status |
| Training data | Sample count, period |
| Validation metrics | Train vs val comparison |
| Walk-forward results | Per-fold performance |
| Error log | If training failed |
| Next scheduled run | When next retraining |

**Example Display:**

```text
┌─────────────────────────────────────────────────────────────────┐
│  TRAINING PIPELINE                                              │
├─────────────────────────────────────────────────────────────────┤
│  Last Run: 2026-08-15 08:00 UTC (SUCCESS)                       │
│  Duration: 45 minutes                                           │
│  Training Samples: 12,500 | Validation: 3,125                   │
│  Data Period: 2026-02-01 → 2026-08-01                           │
│  Walk-Forward: 5 folds, mean ROC-AUC 0.80 ± 0.03                │
│  Next Scheduled: 2026-09-15 08:00 UTC                           │
│                                                                 │
│  [🔄 RUN TRAINING NOW]  [📋 VIEW LOGS]  [⏸ PAUSE SCHEDULE]      │
└─────────────────────────────────────────────────────────────────┘
```

## 2.3 Performance Monitoring (Drift Detection)

| Metric | Alert If |
|--------|----------|
| Prediction accuracy | Drops > 10% from baseline |
| Data drift | Feature distribution changes significantly |
| Concept drift | Feature→label relationship changes |
| Latency | Inference > 100ms |
| Error rate | > 5% predictions fail |

**Example Display:**

```text
┌─────────────────────────────────────────────────────────────────┐
│  PERFORMANCE MONITORING                                         │
├─────────────────────────────────────────────────────────────────┤
│  Prediction Accuracy (7d): 76% ✅ (baseline: 78%)               │
│  Data Drift Score: 0.12 ✅ (threshold: 0.30)                    │
│  Avg Inference Latency: 45ms ✅                                 │
│  Error Rate: 0.8% ✅                                            │
│                                                                 │
│  ⚠️ ALERTS: None                                                │
└─────────────────────────────────────────────────────────────────┘
```

## 2.4 Grid Performance (Business Metrics)

| Metric | Description |
|--------|-------------|
| Active grids | Number of running grids |
| Win rate | % of profitable grids |
| Avg P&L | Average return per grid |
| Max drawdown | Worst DD occurred |
| Recommendation accuracy | Did TOP 10 actually perform |

**Example Display:**

```text
┌─────────────────────────────────────────────────────────────────┐
│  GRID PERFORMANCE (Last 30 days)                                │
├─────────────────────────────────────────────────────────────────┤
│  Total Grids Started: 45                                        │
│  Win Rate: 71% (32 profit, 13 loss)                             │
│  Avg Net P&L: +2.3% per grid                                    │
│  Max Drawdown: -8.5%                                            │
│  TOP 10 Accuracy: 68% (market recommended → profit)             │
└─────────────────────────────────────────────────────────────────┘
```

## 2.5 Data Ingestion Status

| Information | Description |
|-------------|-------------|
| Last data fetch | When last data was fetched |
| Data completeness | % data available vs expected |
| Storage usage | How much data stored |
| Missing data alerts | Markets/periods with gaps |

---

# 3. Dashboard Architecture

```text
┌─────────────────────────────────────────────────────────────────┐
│                    DEVELOPER DASHBOARD                          │
│                    (Web UI - Admin Only)                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                   Application Control API                       │
│              /api/v1/admin/* (admin endpoints)                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼───────┐   ┌───────▼───────┐   ┌───────▼───────┐
│  ML Service   │   │ Training Svc  │   │ Monitoring Svc│
│  (inference)  │   │ (pipeline)    │   │ (metrics)     │
└───────────────┘   └───────────────┘   └───────────────┘
```

---

# 4. Admin API Endpoints

## 4.1 ML Model Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/ml/status` | Active model status |
| GET | `/api/v1/admin/ml/metrics` | Performance metrics |
| GET | `/api/v1/admin/ml/feature-importance` | Feature importance |
| GET | `/api/v1/admin/ml/predictions` | Recent predictions |

## 4.2 Training Pipeline Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/training/status` | Training pipeline status |
| GET | `/api/v1/admin/training/history` | Training run history |
| GET | `/api/v1/admin/training/logs` | Training logs |
| POST | `/api/v1/admin/training/run` | Trigger training run |
| POST | `/api/v1/admin/training/pause` | Pause scheduled training |
| POST | `/api/v1/admin/training/resume` | Resume scheduled training |

## 4.3 Performance Monitoring Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/performance/grids` | Grid performance |
| GET | `/api/v1/admin/performance/drift` | Drift detection |
| GET | `/api/v1/admin/performance/alerts` | Active alerts |

## 4.4 Data Ingestion Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/ingestion/status` | Ingestion status |
| GET | `/api/v1/admin/ingestion/completeness` | Data completeness |
| POST | `/api/v1/admin/ingestion/run` | Trigger data fetch |

## 4.5 Model Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/admin/models` | List all models |
| GET | `/api/v1/admin/models/{model_id}` | Model details |
| POST | `/api/v1/admin/models/{model_id}/promote` | Promote model |
| POST | `/api/v1/admin/models/{model_id}/archive` | Archive model |

---

# 5. Telegram Admin Commands

Quick monitoring via Telegram (before web dashboard):

| Command | Description |
|---------|-------------|
| `/admin ml_status` | ML model status |
| `/admin training` | Training pipeline status |
| `/admin performance` | Grid performance summary |
| `/admin retrain` | Trigger retraining |
| `/admin alerts` | View active alerts |
| `/admin ingestion` | Data ingestion status |

**Example Response:**

```text
🤖 ML STATUS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Mode: ML ✅
Model: primary_classifier-v001
Promoted: 2026-08-15 10:30 UTC
ROC-AUC: 0.82
Predictions Today: 145

[📊 Details] [🔄 Retrain] [📋 Logs]
```

---

# 6. Security & Authorization

| Aspect | Implementation |
|--------|----------------|
| Access | Only ADMIN_USER_ID |
| Auth | JWT/API Key + role check |
| Audit | All operations logged |
| Rate limit | Stricter than user API |

## 6.1 Authorization Levels

| Level | Access |
|-------|--------|
| ADMIN | Full dashboard access, trigger training, promote models |
| OPERATOR | View-only access (future) |
| USER | No dashboard access |

## 6.2 Audit Logging

All admin operations must be audit logged:

```python
logger.info(
    "admin_operation",
    admin_user_id=user_id,
    operation="trigger_training",
    timestamp=datetime.now(UTC),
)
```

---

# 7. Implementation Roadmap

## Phase 1: Quick Win (Telegram Admin Commands)

**Timeline:** 1-2 weeks

| Feature | Status |
|---------|--------|
| `/admin ml_status` command | ❌ To implement |
| `/admin training` command | ❌ To implement |
| `/admin performance` command | ❌ To implement |
| `/admin retrain` command | ❌ To implement |
| `/admin alerts` command | ❌ To implement |

## Phase 2: Admin API Endpoints

**Timeline:** 2-3 weeks

| Feature | Status |
|---------|--------|
| ML status endpoints | ❌ To implement |
| Training pipeline endpoints | ❌ To implement |
| Performance monitoring endpoints | ❌ To implement |
| Model management endpoints | ❌ To implement |

## Phase 3: Web Dashboard / Grafana

**Timeline:** 4-6 weeks (future)

| Option | Pros | Cons |
|--------|------|------|
| **Web UI (React/Vue)** | Full control, interactive | More development needed |
| **Grafana + Prometheus** | Fast setup, good visualization | Less flexible for actions |

**Recommendation:** Start with Grafana for metrics visualization, custom web UI later if needed.

---

# 8. Alert System

## 8.1 Alert Types

| Alert | Trigger | Severity |
|-------|---------|----------|
| Model accuracy drop | Accuracy < baseline - 10% | HIGH |
| Data drift | Drift score > threshold | MEDIUM |
| Training failure | Training job failed | HIGH |
| Ingestion failure | Data fetch failed | MEDIUM |
| High error rate | > 5% predictions fail | HIGH |
| High latency | Inference > 100ms | LOW |

## 8.2 Alert Delivery

```text
Alert Triggered
      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 1. Log to database                                              │
│ 2. Send Telegram notification to ADMIN_USER_ID                  │
│ 3. Display in dashboard alerts panel                            │
└─────────────────────────────────────────────────────────────────┘
```

**Example Telegram Alert:**

```text
⚠️ ML ALERT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Type: Model Accuracy Drop
Severity: HIGH
Details: Prediction accuracy dropped to 65%
         (baseline: 78%, threshold: 70%)
Time: 2026-08-17 14:30 UTC

[📊 View Dashboard] [🔄 Retrain Model]
```

---

# 9. Metrics Storage

## 9.1 Metrics to Store

| Metric Category | Storage |
|-----------------|---------|
| Model predictions | Database (predictions table) |
| Training runs | Database (training_runs table) |
| Performance metrics | TimescaleDB (time-series) |
| Alerts | Database (alerts table) |
| Audit logs | Database (audit_logs table) |

## 9.2 Database Tables (Future)

```sql
-- ML predictions log
CREATE TABLE ml_predictions (
    id UUID PRIMARY KEY,
    model_id VARCHAR(255),
    market_id VARCHAR(50),
    prediction_time TIMESTAMPTZ,
    suitability_score DECIMAL(5,4),
    features_used JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Training runs
CREATE TABLE training_runs (
    id UUID PRIMARY KEY,
    run_id VARCHAR(255),
    status VARCHAR(50),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    train_samples INTEGER,
    val_samples INTEGER,
    metrics JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Alerts
CREATE TABLE alerts (
    id UUID PRIMARY KEY,
    alert_type VARCHAR(100),
    severity VARCHAR(20),
    message TEXT,
    details JSONB,
    acknowledged BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 10. Current Status

| Component | Status | Notes |
|-----------|--------|-------|
| Telegram admin commands | ❌ Not yet | Phase 1 priority |
| Admin API endpoints | ❌ Not yet | Phase 2 |
| Web dashboard | ❌ Not yet | Phase 3 (future) |
| Alert system | ❌ Not yet | Phase 2 |
| Metrics storage | ❌ Not yet | Phase 2 |

---

# 11. Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-08-17 | Initial Admin Dashboard specification |