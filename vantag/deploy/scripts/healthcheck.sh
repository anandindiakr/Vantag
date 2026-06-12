#!/usr/bin/env bash
# Health check all Vantag services
set -euo pipefail

REGION="${1:-india}"

declare -A BACKEND_URL=(
    [india]="https://retailnazar.vantag.io/health"
    [singapore]="https://sg.vantag.io/health"
    [malaysia]="https://my.vantag.io/health"
)

declare -A CONTAINERS=(
    [india]="vantag_postgres_in vantag_redis_in vantag_mqtt_in vantag_backend_in vantag_nginx_in"
    [singapore]="vantag_postgres_sg vantag_redis_sg vantag_mqtt_sg vantag_backend_sg vantag_nginx_sg"
    [malaysia]="vantag_postgres_my vantag_redis_my vantag_mqtt_my vantag_backend_my vantag_nginx_my"
)

echo "=============================="
echo "  Vantag Health Check: $REGION"
echo "=============================="

# Check containers
echo ""
echo "Containers:"
for container in ${CONTAINERS[$REGION]}; do
    STATUS=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || echo "not found")
    HEALTH=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo "n/a")
    printf "  %-30s status=%-10s health=%s\n" "$container" "$STATUS" "$HEALTH"
done

# Check API health
echo ""
echo "API health endpoint:"
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BACKEND_URL[$REGION]}" --max-time 10 2>/dev/null || echo "000")
if [[ "$HTTP_STATUS" == "200" ]]; then
    echo "  ✓ ${BACKEND_URL[$REGION]} → HTTP $HTTP_STATUS"
else
    echo "  ✗ ${BACKEND_URL[$REGION]} → HTTP $HTTP_STATUS"
fi

echo ""
echo "Done."
