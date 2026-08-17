# OKX AI Trading Grid System

AI-assisted trading platform for Spot grid trading on **OKX, Binance, and Bybit**.

## Overview

This system uses machine learning to rank Spot markets by grid trading suitability, generates hierarchical grid blueprints, and executes trades with deterministic risk controls. It supports multiple exchanges through a unified `ExchangeAdapter` interface.

**Key Principle:** AI provides intelligence. Deterministic systems provide correctness. Humans provide approval.

## Features

- **Multi-Exchange Support**: OKX, Binance, and Bybit via a unified `ExchangeAdapter` interface
- **ML Market Ranking**: Ranks 100+ Spot markets by grid trading suitability
- **Hierarchical Grid Blueprints**: Sections with uniform spacing + adaptive gaps
- **Immediate Execution**: BUY/SELL orders executed immediately (not passive)
- **Risk Controls**: Deterministic risk limits, human approval for live trading
- **Telegram Interface**: Control and monitor via Telegram bot
- **Demo Trading Validation**: Full grid lifecycle in Demo/Testnet environments (create, start, pause, resume, stop, emergency stop) with live-readiness validation report
- **Monitoring & Alerts**: Configurable alert rules with severity levels, health checks per component, and dashboard data

## Supported Exchanges

| Exchange | Demo/Testnet | Live | Symbol Format |
|---|---|---|---|
| OKX | ✅ Demo Trading (`x-simulated-trading: 1`) | ⬜ Phase 6 | `BTC-USDT` |
| Binance | ✅ Testnet (`testnet.binance.vision`) | ⬜ Phase 6 | `BTCUSDT` |
| Bybit | ✅ Testnet (`api-testnet.bybit.com`) | ⬜ Phase 6 | `BTCUSDT` |

All exchanges share the same domain model (`MarketId = "BTC-USDT"`). Symbol conversion is handled automatically by each adapter.

## Architecture

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
└───────────────┘   └───────────────┘   └───────────────┘
```

## Tech Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| Package Manager | uv |
| API | FastAPI + Pydantic v2 |
| Database (Dev) | Supabase (PostgreSQL 15+) |
| Database (Prod) | PostgreSQL 15 + TimescaleDB |
| ML | scikit-learn + LightGBM |
| Telegram | aiogram 3.x |

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Supabase account (free tier works)

### Installation

```bash
# Clone repository
git clone <repo-url>
cd OKX

# Install dependencies
uv sync --extra dev

# Copy environment file
cp .env.example .env
# Edit .env with your Supabase connection string

# Run migrations
uv run alembic upgrade head

# Run tests
uv run pytest

# Start development server
uv run uvicorn okx_trading.api.app:create_app --factory --reload
```

### Development Commands

```bash
# Install dependencies
uv sync --extra dev

# Run tests
uv run pytest

# Run linting
uv run ruff check src tests

# Format code
uv run ruff format src tests

# Type checking
uv run mypy src
```

## Project Structure

```
OKX/
├── src/okx_trading/
│   ├── domain/          # Pure business logic (NO framework imports)
│   ├── research/        # AI Research pipeline
│   ├── application/     # Use cases
│   ├── infrastructure/  # External integrations
│   ├── api/             # FastAPI routes
│   ├── workers/         # Background tasks
│   └── config/          # Settings
├── tests/               # Test suite
├── docs/                # Specification documents
├── scripts/             # Development scripts
└── deploy/              # Docker deployment (VPS only)
```

## Documentation

| Document | Purpose |
|---|---|
| [PRD.md](PRD.md) | Product requirements |
| [ROADMAP.md](ROADMAP.md) | Project phases |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Build plan + tech stack |
| [AGENTS.md](AGENTS.md) | AI coding agent guide |
| [docs/](docs/) | Technical specifications |

## Development Phases

| Phase | Description | Status |
|---|---|---|
| Phase 0 | Foundation | ✅ Done |
| Phase 1 | Data & Simulator | ✅ Done |
| Phase 2 | ML Pipeline | ✅ Done |
| Phase 3 | Application Layer | ✅ Done (Price Monitor gap fix pending) |
| Phase 4 | Demo Trading | ✅ Done |
| Phase 5 | Multi-Tenant Beta | ⬜ Not Started |
| Phase 6 | Live Trading | ⬜ Not Started |

**Current test suite:** 721 tests passing.

## Demo Trading API

Demo trading endpoints are available under `/api/v1/demo/`:

| Endpoint | Description |
|---|---|
| `POST /api/v1/demo/sessions` | Create demo grid session |
| `GET /api/v1/demo/sessions` | List all demo sessions |
| `POST /api/v1/demo/sessions/{id}/start` | Start demo grid |
| `POST /api/v1/demo/sessions/{id}/pause` | Pause demo grid |
| `POST /api/v1/demo/sessions/{id}/resume` | Resume demo grid |
| `POST /api/v1/demo/sessions/{id}/stop` | Stop demo grid |
| `POST /api/v1/demo/sessions/{id}/emergency-stop` | Emergency stop single grid |
| `POST /api/v1/demo/emergency-stop-all` | Emergency stop all grids |
| `GET /api/v1/demo/metrics` | Aggregated demo metrics |
| `GET /api/v1/demo/validation-report` | Live readiness report |
| `GET /api/v1/demo/monitoring/dashboard` | Monitoring dashboard |
| `GET /api/v1/demo/monitoring/alerts` | List alerts |

See [docs/OKX_DEMO_TRADING_SPEC.md](docs/OKX_DEMO_TRADING_SPEC.md) for details.

## Security

- Exchange API keys: **Read + Trade only, Withdraw DISABLED**
- Separate credentials for Demo/Testnet and Live per exchange
- Live trading requires explicit human approval
- All operations are audit logged
- Secrets never in logs or responses

## License

MIT