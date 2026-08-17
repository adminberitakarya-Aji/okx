# ============================================================================
# Trading Grid AI System - Makefile
# ============================================================================
# Usage: make <command>
# Note: On Windows, use 'make' via Git Bash, WSL, or use commands directly
# ============================================================================

.PHONY: install install-dev install-prod test test-unit test-integration test-e2e test-coverage lint format typecheck check dev migrate migrate-create clean help

# ============================================================================
# INSTALLATION
# ============================================================================

## Install all dependencies (base + dev)
install: install-dev

## Install base dependencies only
install-base:
	uv sync

## Install development dependencies
install-dev:
	uv sync --extra dev

## Install production dependencies
install-prod:
	uv sync --extra prod

# ============================================================================
# TESTING
# ============================================================================

## Run all tests
test:
	uv run pytest

## Run unit tests only
test-unit:
	uv run pytest tests/unit -v

## Run integration tests only
test-integration:
	uv run pytest tests/integration -v

## Run e2e tests only
test-e2e:
	uv run pytest tests/e2e -v

## Run tests with coverage report
test-coverage:
	uv run pytest --cov=trading_grid --cov-report=html --cov-report=term

## Run tests in watch mode (requires pytest-watch)
test-watch:
	uv run pytest --looponfail

# ============================================================================
# CODE QUALITY
# ============================================================================

## Run linting (ruff check)
lint:
	uv run ruff check src tests

## Fix linting issues automatically
lint-fix:
	uv run ruff check src tests --fix

## Format code (ruff format)
format:
	uv run ruff format src tests

## Check formatting without changing
format-check:
	uv run ruff format src tests --check

## Run type checking (mypy)
typecheck:
	uv run mypy src

## Run all checks (lint + format-check + typecheck + test)
check: lint format-check typecheck test

# ============================================================================
# DEVELOPMENT
# ============================================================================

## Start development server
dev:
	uv run uvicorn trading_grid.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

## Start Telegram bot
telegram:
	uv run python scripts/run_telegram_bot.py

## Start development server with specific port
dev-port:
	uv run uvicorn trading_grid.api.app:create_app --factory --reload --host 0.0.0.0 --port $(PORT)

## Run database migrations
migrate:
	uv run alembic upgrade head

## Create new migration
migrate-create:
	uv run alembic revision --autogenerate -m "$(msg)"

## Rollback last migration
migrate-rollback:
	uv run alembic downgrade -1

## Open IPython shell
shell:
	uv run ipython

# ============================================================================
# SCRIPTS
# ============================================================================

## Test database connection
test-db:
	uv run python scripts/test_db_connection.py

## Verify database tables
verify-tables:
	uv run python scripts/verify_tables.py

# ============================================================================
# DOCKER (VPS/Production only)
# ============================================================================

## Build Docker image
docker-build:
	docker build -t trading-grid .

## Start production services
docker-up:
	docker-compose -f deploy/docker/docker-compose.prod.yml up -d

## Stop production services
docker-down:
	docker-compose -f deploy/docker/docker-compose.prod.yml down

## View production logs
docker-logs:
	docker-compose -f deploy/docker/docker-compose.prod.yml logs -f

# ============================================================================
# CLEANUP
# ============================================================================

## Clean build artifacts and caches
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ============================================================================
# HELP
# ============================================================================

## Show this help
help:
	@echo "Trading Grid AI System - Available Commands:"
	@echo ""
	@echo "Installation:"
	@echo "  make install          Install all dependencies (base + dev)"
	@echo "  make install-dev      Install development dependencies"
	@echo "  make install-prod     Install production dependencies"
	@echo ""
	@echo "Testing:"
	@echo "  make test             Run all tests"
	@echo "  make test-unit        Run unit tests"
	@echo "  make test-integration Run integration tests"
	@echo "  make test-coverage    Run tests with coverage"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             Run linting"
	@echo "  make lint-fix         Fix linting issues"
	@echo "  make format           Format code"
	@echo "  make typecheck        Run type checking"
	@echo "  make check            Run all checks"
	@echo ""
	@echo "Development:"
	@echo "  make dev              Start dev server"
	@echo "  make migrate          Run migrations"
	@echo "  make migrate-create   Create new migration (msg='...')"
	@echo ""
	@echo "Docker (VPS only):"
	@echo "  make docker-build     Build Docker image"
	@echo "  make docker-up        Start production services"
	@echo "  make docker-down      Stop production services"