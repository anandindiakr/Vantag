#!/usr/bin/env bash
# Usage: ./deploy.sh [india|singapore|malaysia]
set -euo pipefail

REGION="${1:-india}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(dirname "$SCRIPT_DIR")"

declare -A COMPOSE_FILE=(
    [india]="docker-compose.india.yml"
    [singapore]="docker-compose.singapore.yml"
    [malaysia]="docker-compose.malaysia.yml"
)

declare -A ENV_FILE=(
    [india]="env/india.env"
    [singapore]="env/singapore.env"
    [malaysia]="env/malaysia.env"
)

COMPOSE="${COMPOSE_FILE[$REGION]:-}"
ENV="${ENV_FILE[$REGION]:-}"

if [[ -z "$COMPOSE" ]]; then
    echo "ERROR: Unknown region '$REGION'. Use: india, singapore, or malaysia"
    exit 1
fi

if [[ ! -f "$DEPLOY_DIR/$ENV" ]]; then
    echo "ERROR: Env file not found: $DEPLOY_DIR/$ENV"
    echo "  Copy from: $DEPLOY_DIR/env/${REGION}.env.example"
    exit 1
fi

echo "========================================"
echo "  Deploying Vantag — Region: $REGION"
echo "========================================"
echo "Compose: $COMPOSE"
echo "Env:     $ENV"
echo ""

cd "$DEPLOY_DIR"

# Pull latest images
echo "[1/4] Pulling latest images..."
docker compose -f "$COMPOSE" --env-file "$ENV" pull

# Run DB migrations
echo "[2/4] Running database migrations..."
docker compose -f "$COMPOSE" --env-file "$ENV" run --rm backend_${REGION:0:2} \
    python -m alembic upgrade head 2>/dev/null || true

# Start all services
echo "[3/4] Starting services..."
docker compose -f "$COMPOSE" --env-file "$ENV" up -d

# Health check
echo "[4/4] Checking health..."
sleep 10
docker compose -f "$COMPOSE" --env-file "$ENV" ps

echo ""
echo "Deployment complete!"
echo "Dashboard: https://${REGION_DOMAIN:-$REGION.vantag.io}"
