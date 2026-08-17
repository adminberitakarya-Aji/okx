# AGENTS.md — AI Coding Agent Guide

This document provides context and guidelines for AI coding agents (Claude, Cline, Copilot, etc.) working on this project.

---

## 1. Project Overview

**Trading Grid AI System** — An AI-assisted trading platform that:
- Uses ML to rank Spot markets by grid trading suitability
- Generates hierarchical grid blueprints (Sections + uniform spacing + adaptive gaps)
- Executes trades with immediate execution (not passive limit orders)
- Supports multiple exchanges: **OKX, Binance, Bybit** (via ExchangeAdapter interface)
- Enforces deterministic risk limits and requires human approval for live trading

**Key Principle:** AI provides intelligence. Deterministic systems provide correctness. Humans provide approval.

---

## 2. Architecture Summary

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER INTERFACES                          │
│              Telegram / Web (future) / CLI                      │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                   APPLICATION CONTROL API                       │
│              FastAPI + Auth + Authorization                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
┌───────▼───────┐   ┌───────▼───────┐   ┌───────▼───────┐
│  AI RESEARCH  │   │  REALTIME AI  │   │  GRID ENGINE  │
│  ML Pipeline  │   │  Blueprint    │   │  State Machine│
└───────┬───────┘   └───────┬───────┘   └───────┬───────┘
        │                   │                   │
        └───────────────────┼───────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    DETERMINISTIC CORE                           │
│         Risk Validation + Economic Validation                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                    EXECUTION ENGINE                             │
│              Order Management + Tracking                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                      OKX ADAPTER                                │
│           REST + WebSocket + Reconciliation                     │
└───────────────────────────┬─────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────┐
│                         OKX API                                 │
│                    Demo / Live Trading                          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Package Manager | uv |
| API | FastAPI + Pydantic v2 |
| Database (Dev) | Supabase (PostgreSQL 15+) |
| Database (Prod) | PostgreSQL 15 + TimescaleDB (VPS) |
| ORM | SQLAlchemy 2.0 (async) |
| Telegram | aiogram 3.x |
| ML | scikit-learn + LightGBM |
| Data | pandas + polars + Parquet |
| Scheduler (Phase 0-2) | APScheduler |
| Task Queue (Phase 3+) | ARQ + Redis 7 |
| Testing | pytest + pytest-asyncio |
| Linting | ruff |
| Type Check | mypy (strict) |
| Deployment | Docker + docker-compose (VPS only) |

---

## 4. Project Structure

> **Note:** Reflects actual codebase as of 2026-08-17 (Phase 7 M7.1-M7.4 complete).

```
TradingGrid/
├── src/trading_grid/
│   ├── domain/              # Pure business logic (NO framework imports)
│   │   ├── grid/            # models.py, calculator.py
│   │   ├── market/          # models.py (Market, Candle, OrderBook)
│   │   ├── execution/       # models.py (Order, Fill, Position)
│   │   ├── risk/            # models.py (RiskLimits, RiskCheckResult)
│   │   ├── exchange/        # interface.py (ExchangeAdapter ABC), errors.py
│   │   └── shared/          # types.py, errors.py
│   │
│   ├── research/            # AI Research pipeline
│   │   ├── ingestion/       # okx_client.py, binance_client.py, bybit_client.py,
│   │   │                    # storage.py (Parquet)
│   │   ├── features/        # market_state.py, execution_economics.py,
│   │   │                    # grid_behavior.py, derived_ml.py
│   │   ├── simulator/       # grid_simulator.py (deterministic)
│   │   ├── dataset/         # builder.py
│   │   ├── labels/          # generator.py
│   │   └── models/          # trainer.py, ranking.py, registry.py,
│   │                        # blueprint_generator.py
│   │
│   ├── application/         # Use cases
│   │   ├── commands/        # (reserved, currently empty)
│   │   ├── queries/         # (reserved, currently empty)
│   │   └── services/        # authorization.py, approval.py, audit.py,
│   │                        # user_service.py, grid_engine.py,
│   │                        # execution_engine.py, demo_trading.py,
│   │                        # monitoring.py, price_monitor.py,
│   │                        # research_service.py, credential_service.py,
│   │                        # exchange_factory.py, tenant_limits.py,
│   │                        # risk_validation.py, service_container.py
│   │
│   ├── infrastructure/      # External integrations
│   │   ├── exchange/        # symbols.py (market symbol normalization)
│   │   ├── okx/             # rest_client.py, websocket_client.py, adapter.py
│   │   ├── binance/         # rest_client.py, websocket_client.py, adapter.py
│   │   ├── bybit/           # rest_client.py, websocket_client.py, adapter.py
│   │   ├── telegram/        # bot.py, handlers.py, formatters.py, keyboards.py
│   │   ├── database/        # base.py, engine.py, models.py, migrations/
│   │   └── secrets/         # (reserved)
│   │
│   ├── api/                 # FastAPI application
│   │   ├── app.py           # App factory
│   │   ├── routes/          # health.py, system.py, demo.py, account.py,
│   │   │                    # approvals.py, blueprints.py, grid.py, markets.py,
│   │   │                    # orders.py, pnl.py, positions.py, research.py,
│   │   │                    # risk.py, simulations.py, dependencies.py
│   │   ├── middleware/      # auth.py, audit.py
│   │   └── schemas/         # common.py, grid.py, research.py, system.py,
│   │                        # demo.py, account.py, approvals.py, markets.py,
│   │                        # orders.py, pnl.py, positions.py, risk.py,
│   │                        # simulations.py
│   │
│   ├── workers/             # Background tasks (reserved, currently empty)
│   └── config/              # settings.py (pydantic-settings)
│
├── tests/
│   ├── unit/                # domain/, research/, application/, api/,
│   │                        # infrastructure/, config/
│   ├── integration/         # api/, database/, okx/, binance/, bybit/
│   └── e2e/
│
├── alembic/                 # Database migrations (6 migrations)
├── docs/                    # All specification documents (incl.
│                            # ML_TRAINING_PIPELINE_SPEC.md,
│                            # ADMIN_DASHBOARD_SPEC.md, DEPLOYMENT_PROXMOX.md)
├── data/                    # Research data (gitignored): pipeline_state.json,
│                            # research/v1/BINANCE/ (9 markets, 38,880 candles)
├── models/                  # Trained ML models (gitignored): 6 LightGBM
│                            # models DEPLOYED + registry/index.json
├── scripts/                 # test_db_connection.py, test_ws_connection.py,
│                            # verify_tables.py, debug_features.py,
│                            # run_telegram_bot.py, run_ml_training.py,
│                            # run_ml_scheduler.py, deploy.sh
└── deploy/docker/           # Dockerfile, docker-compose.prod.yml (VPS only)
```

---

## 5. Dependency Rules (CRITICAL)

```
domain/ ← MUST NOT import from any other layer
research/ ← may import domain/
application/ ← may import domain/, research/
infrastructure/ ← implements interfaces from domain/application
api/ ← may import application/ ONLY
workers/ ← may import application/, research/
```

**NEVER:**
- Import FastAPI in domain/
- Import SQLAlchemy in domain/
- Import OKX adapter in domain/
- Let api/ call domain/ directly (go through application/)

---

## 6. Non-Negotiable Domain Rules

### Grid Strategy Rules
1. Grid spacing is **uniform within each Section**
2. Section Gaps **may differ** between Sections
3. BUY and SELL use **immediate execution** (not passive limit orders)
4. Spot-only: **no shorting, no leverage**
5. Net P&L = truth (fees + spread + slippage always modeled)

### Causal Integrity Rules
6. **No future data leakage** — features at time T use only data ≤ T
7. Labels come from **VALID simulations only**
8. Historical reconstruction must be **causal**
9. Missing data ≠ zero (use availability flags)

### Execution Rules
10. Spread and slippage are **never double-counted**
11. Buy cost and sell cost are **modeled separately**
12. Reconciliation required after **any disconnect**
13. Ambiguous order state → **reconcile before retry**

### Security Rules
14. Secrets **never in logs, responses, or datasets**
15. OKX API keys: **Read + Trade only, Withdraw DISABLED**
16. DEMO and LIVE use **separate credentials**
17. Live trading requires **explicit approval**
18. All operations are **audit logged**

---

## 7. Coding Conventions

### Style
- Follow PEP 8 (enforced by ruff)
- Type hints on all functions (mypy strict)
- Docstrings on public functions
- No mutable default arguments
- Prefer dataclasses/Pydantic models over dicts

### Naming
- Classes: `PascalCase` (e.g., `GridSimulator`)
- Functions: `snake_case` (e.g., `calculate_grid_prices`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `MAX_SECTIONS`)
- Files: `snake_case.py` (e.g., `grid_calculator.py`)
- Tests: `test_<module>.py` with `test_<behavior>` functions

### Error Handling
- Domain errors in `domain/shared/errors.py`
- Infrastructure errors mapped to domain errors
- Never swallow exceptions silently
- Log with context (structlog)

### Logging
```python
import structlog
logger = structlog.get_logger()

# Good
logger.info("order_submitted", order_id=order.id, market=market.id)

# Bad (no context)
logger.info("Order submitted")
```

---

## 8. Testing Guidelines

### Coverage Targets
- `domain/`: > 90%
- `research/`: > 80%
- `application/`: > 80%
- `infrastructure/`: > 70%

### Test Structure
```python
# tests/unit/domain/test_grid_calculator.py

def test_grid_prices_are_uniform_within_section():
    """Grid spacing must be uniform within a Section."""
    # Arrange
    blueprint = create_test_blueprint()
    
    # Act
    prices = calculate_grid_prices(blueprint)
    
    # Assert
    for section in prices.sections:
        spacings = [p2 - p1 for p1, p2 in zip(section.prices, section.prices[1:])]
        assert all_equal(spacings)
```

### Determinism Tests
```python
def test_simulator_is_deterministic():
    """Same input must produce same output."""
    result1 = run_simulation(input_data)
    result2 = run_simulation(input_data)
    assert result1 == result2
```

---

## 9. Common Tasks

### Add a New Feature (ML Feature)
1. Define feature in `research/features/<layer>.py`
2. Add feature ID (e.g., `F-MKT-061`)
3. Implement causal cutoff
4. Add unit tests
5. Register in feature registry
6. Update documentation

### Add a New API Endpoint
1. Define schema in `api/schemas/`
2. Add route in `api/routes/`
3. Implement use case in `application/`
4. Add authorization check
5. Add audit logging
6. Write integration tests

### Add a New Telegram Command
1. Add handler in `infrastructure/telegram/handlers.py`
2. Map to Application API call
3. Add authorization level check
4. Add formatter in `formatters.py`
5. Write tests

---

## 10. Common Pitfalls to Avoid

| Pitfall | Correct Approach |
|---|---|
| Using future data in features | Strict causal cutoff at time T |
| Double-counting spread + slippage | Model once, explicitly |
| Assuming demo = live behavior | Document limitations |
| Logging secrets | Never log credentials |
| Bypassing risk validation | All orders go through risk check |
| Silent error swallowing | Log + propagate or handle explicitly |
| Mutable class attributes | Use instance attributes |
| Blocking async code | Use async libraries or run_in_executor |

---

## 11. Reference Documents

| Document | Purpose |
|---|---|
| `PRD.md` | Product requirements |
| `ROADMAP.md` | Project phases |
| `IMPLEMENTATION_PLAN.md` | Build plan + tech stack |
| `docs/AI_RESEARCH.md` | Research pipeline overview |
| `docs/AI_RESEARCH_TECHNICAL_DESIGN.md` | Technical architecture |
| `docs/AI_RESEARCH_GRID_SIMULATOR_SPEC.md` | Simulator specification |
| `docs/AI_TRADING_GRID_WORKFLOW.md` | Grid strategy workflow |
| `docs/APPLICATION_CONTROL_API_SPEC.md` | API specification |
| `docs/EXCHANGE_ADAPTER_SPEC.md` | Multi-exchange integration (OKX, Binance, Bybit) |
| `docs/TELEGRAM_GATEWAY_SPEC.md` | Telegram interface |
| `docs/SECURITY_AUTHORIZATION_SPEC.md` | Security model |
| `docs/OKX_DEMO_TRADING_SPEC.md` | Demo environment |
| `docs/LIVE_TRADING_SPEC.md` | Live operations |
| `docs/ML_TRAINING_PIPELINE_SPEC.md` | ML training pipeline |
| `docs/ADMIN_DASHBOARD_SPEC.md` | Admin dashboard |

**When in doubt, read the relevant spec document first.**

---

## 12. Development Commands

```bash
# Install dependencies
uv sync

# Run tests
make test

# Run linting
make lint

# Run type checking
make typecheck

# Format code
make format

# Start dev server
make dev

# Run migrations (against Supabase)
make migrate
```

**Note:** Local development does NOT use Docker. Database connects to Supabase cloud.
Docker is only used for VPS/production deployment.

---

## 13. Environment Variables

```bash
# Copy .env.example to .env and configure:
APP_ENV=development

# Database (Development: Supabase)
DATABASE_URL=postgresql+asyncpg://postgres:password@db.xxxxx.supabase.co:5432/postgres

# Redis (Phase 3+ only, not needed for Phase 0-2)
# REDIS_URL=redis://localhost:6379/0

# OKX
OKX_API_KEY=...
OKX_API_SECRET=...
OKX_PASSPHRASE=...
OKX_DEMO_MODE=true

# Binance
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
BINANCE_TESTNET_MODE=true

# Bybit
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
BYBIT_TESTNET_MODE=true

# Telegram
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ALLOWED_USER_IDS=123456789
TELEGRAM_ADMIN_USER_ID=123456789
TELEGRAM_OPEN_ACCESS=false  # true = anyone can use (beta trial only)
```

**Never commit .env to git.**

---

## 14. Git Conventions

- Branch naming: `feature/<name>`, `fix/<name>`, `docs/<name>`
- Commit messages: imperative mood, < 72 chars
- One logical change per commit
- Tests must pass before merge

---

## 15. When Unsure

1. **Read the spec documents** in `docs/`
2. **Check existing patterns** in the codebase
3. **Ask for clarification** rather than guessing
4. **Prefer simple solutions** over clever ones
5. **Write tests first** when behavior is unclear

---

## 16. Agent-Specific Notes

### For Claude / Cline
- Always read relevant spec documents before implementing
- Follow the dependency rules strictly
- Add type hints to all new code
- Write tests alongside implementation
- Use structlog for logging

### For Code Generation
- Generate complete, working code (not snippets)
- Include imports
- Include type hints
- Include docstrings
- Include error handling

### For Code Review
- Check causal integrity (no future data)
- Check dependency rules
- Check error handling
- Check test coverage
- Check security (no secrets in code)

---

## 17. Quick Reference: Domain Types

```python
# Core types (domain/shared/types.py)
MarketId = str          # e.g., "BTC-USDT"
Timestamp = datetime    # UTC
Price = Decimal         # Never float for prices
Quantity = Decimal      # Never float for quantities

# Grid types (domain/grid/models.py)
GridSide = Literal["BUY", "SELL"]
GridLevel = int
SectionId = int

# Order types (domain/execution/models.py)
OrderStatus = Literal["SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED", "FILLED", "CANCELLED", "REJECTED"]
```

---

## 18. Version History

| Version | Date | Changes |
|---|---|---|
| 1.0 | 2026-08-15 | Initial AGENTS.md |
| 1.1 | 2026-08-16 | Updated Section 4 (Project Structure) to match actual codebase |
| 1.2 | 2026-08-16 | Added multi-exchange support (OKX, Binance, Bybit) |
