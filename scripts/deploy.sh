#!/usr/bin/env bash
# ============================================================================
# OKX AI Trading Grid System - Deployment Script (Proxmox LXC)
# ============================================================================
# Usage:
#   Run this script INSIDE the LXC container (Ubuntu 24.04)
#
#   bash scripts/deploy.sh
#
# This script:
#   1. Installs Docker + Docker Compose
#   2. Clones the repository
#   3. Creates .env from .env.example
#   4. Builds and starts all services
#   5. Verifies deployment
# ============================================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# ============================================================================
# CONFIGURATION
# ============================================================================
REPO_URL="https://github.com/adminberitakarya-Aji/okx.git"
APP_DIR="/opt/okx"
COMPOSE_FILE="deploy/docker/docker-compose.prod.yml"
ENV_FILE="$APP_DIR/.env"
COMPOSE_CMD="docker compose --env-file $ENV_FILE -f $COMPOSE_FILE"

# ============================================================================
# 1. CHECK ROOT
# ============================================================================
if [[ $EUID -ne 0 ]]; then
    log_error "This script must be run as root (sudo)."
    exit 1
fi

# ============================================================================
# 2. INSTALL DOCKER
# ============================================================================
log_info "Installing Docker..."

if command -v docker &>/dev/null; then
    log_info "Docker already installed: $(docker --version)"
else
    curl -fsSL https://get.docker.com | sh
    systemctl enable docker
    systemctl start docker
    log_info "Docker installed."
fi

# Install docker compose plugin
if ! docker compose version &>/dev/null; then
    log_info "Installing docker compose plugin..."
    apt-get update
    apt-get install -y docker-compose-plugin
fi

log_info "Docker Compose: $(docker compose version)"

# ============================================================================
# 3. CLONE REPOSITORY
# ============================================================================
log_info "Cloning repository..."

if [[ -d "$APP_DIR/.git" ]]; then
    log_info "Repository already exists. Pulling latest..."
    cd "$APP_DIR"
    git pull
else
    mkdir -p "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

# ============================================================================
# 4. CREATE .env
# ============================================================================
if [[ ! -f "$APP_DIR/.env" ]]; then
    log_warn "Creating .env from .env.example..."
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    log_warn "IMPORTANT: Edit $APP_DIR/.env with your credentials!"
    log_warn "Run: nano $APP_DIR/.env"
    log_warn "Then re-run this script."
    exit 1
else
    log_info ".env already exists."
fi

# ============================================================================
# 5. VALIDATE .env
# ============================================================================
log_info "Validating .env..."

# Check required variables
REQUIRED_VARS=(
    "DATABASE_URL"
    "TELEGRAM_BOT_TOKEN"
    "TELEGRAM_ADMIN_USER_ID"
    "CREDENTIAL_ENCRYPTION_KEY"
)

MISSING_VARS=()
for var in "${REQUIRED_VARS[@]}"; do
    if ! grep -q "^${var}=.\+" "$APP_DIR/.env"; then
        MISSING_VARS+=("$var")
    fi
done

if [[ ${#MISSING_VARS[@]} -gt 0 ]]; then
    log_error "Missing required variables in .env:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    log_error "Edit $APP_DIR/.env and re-run this script."
    exit 1
fi

log_info ".env validation passed."

# ============================================================================
# 6. BUILD & START
# ============================================================================
log_info "Building Docker images (this may take a few minutes)..."

cd "$APP_DIR"
$COMPOSE_CMD build

log_info "Starting services..."
$COMPOSE_CMD up -d

# ============================================================================
# 7. VERIFY
# ============================================================================
log_info "Verifying deployment..."

# Wait for services to start
sleep 10

# Check container status
log_info "Container status:"
$COMPOSE_CMD ps

# Check API health
log_info "Checking API health..."
if curl -sf http://localhost:8000/health >/dev/null 2>&1; then
    log_info "API health: OK"
else
    log_warn "API health: Not responding yet (may still be starting)"
fi

# Check telegram bot logs
log_info "Telegram bot logs (last 20 lines):"
docker logs --tail 20 okx-trading-telegram 2>&1 || true

# ============================================================================
# 8. SUMMARY
# ============================================================================
echo ""
echo "============================================================"
echo "  DEPLOYMENT COMPLETE"
echo "============================================================"
echo ""
echo "  Services:"
echo "    - API:          http://localhost:8000"
echo "    - Telegram Bot: @gridtrade6_bot"
echo ""
echo "  Management:"
echo "    - Logs:         $COMPOSE_CMD logs -f"
echo "    - Restart:      $COMPOSE_CMD restart"
echo "    - Stop:         $COMPOSE_CMD down"
echo "    - Update:       cd $APP_DIR && git pull && $COMPOSE_CMD up -d --build"
echo ""
echo "  Test:"
echo "    - Buka Telegram → @gridtrade6_bot → /start"
echo ""
echo "============================================================"