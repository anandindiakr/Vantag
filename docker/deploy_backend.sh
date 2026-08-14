#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Rebuild + restart ONLY the vantag-backend container, with health check and
# automatic rollback. Runs ON the VPS.
#
# Why this lives in a file instead of inline in deploy-backend.yml:
#   The workflow now makes TWO SSH attempts (GitHub-hosted runner IPs are
#   occasionally dropped upstream before they ever reach sshd — observed as
#   "dial tcp ...:22: i/o timeout" with no corresponding sshd log entry on the
#   VPS). Keeping the deploy logic in one file means the retry attempt cannot
#   drift out of sync with the first attempt.
#
# IMPORTANT: the caller must copy this file to /tmp and run it from there.
#   The deploy does `git reset --hard`, which rewrites files in the repo
#   working tree. bash reads a script incrementally while executing it, so
#   running this file directly out of the repo could corrupt execution
#   mid-deploy if the commit being deployed changes this script.
#
# Usage: bash /tmp/vantag_deploy_backend.sh <repo_path> <prev_sha>
#   <prev_sha> is the commit that was live BEFORE the caller reset the repo
#   to origin/main, i.e. the known-good version to roll back to.
#
# Only the backend container is touched — postgres, mosquitto, nginx and
# certbot keep running untouched.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_PATH="${1:?repo path required}"
PREV_SHA="${2:?previous commit sha required}"
COMPOSE_FILE="docker/docker-compose.prod.yml"
CONTAINER="vantag-backend"

cd "$REPO_PATH"

echo "Deploying $(git rev-parse --short HEAD) (previous known-good: ${PREV_SHA:0:7})"

build_and_start() {
  docker compose -f "$COMPOSE_FILE" build "$CONTAINER"
  docker compose -f "$COMPOSE_FILE" up -d "$CONTAINER"
}

# Health is checked two independent ways:
#  1. the compose healthcheck status reported by docker
#  2. a real dependency-aware HTTP call to /health/ready from INSIDE the container
# It is deliberately NOT checked through the host's nginx: this VPS hosts
# multiple apps, so https://localhost hits a different vhost and returns 404,
# which previously caused false rollbacks of a perfectly healthy backend.
check_health() {
  local status="starting" http_code="000" i

  echo "Waiting for container health..."
  for i in $(seq 1 60); do
    status=$(docker inspect --format='{{.State.Health.Status}}' "$CONTAINER" 2>/dev/null || echo "starting")
    [ "$status" = "healthy" ] && break
    sleep 6
  done

  for i in $(seq 1 15); do
    http_code=$(docker exec "$CONTAINER" curl -s -o /dev/null -w "%{http_code}" http://localhost:8800/health/ready || echo "000")
    [ "$http_code" = "200" ] && break
    sleep 6
  done

  echo "Health result: container status=$status /health/ready HTTP=$http_code"
  [ "$status" = "healthy" ] && [ "$http_code" = "200" ]
}

# Nginx resolves the Docker service name when its worker starts. Recreating
# vantag-backend changes that container IP, so leaving nginx untouched can
# leave it pointing at the old IP and return 502 for every /api request even
# though the backend's own healthcheck is green. Restart nginx after the
# backend is healthy so its upstream is resolved against the new container.
refresh_nginx_upstream() {
  echo "Refreshing nginx backend upstream after container replacement..."
  docker compose -f "$COMPOSE_FILE" restart nginx

  local nginx_status="starting" i
  for i in $(seq 1 20); do
    nginx_status=$(docker inspect --format='{{.State.Health.Status}}' vantag-nginx 2>/dev/null || echo "starting")
    [ "$nginx_status" = "healthy" ] && break
    sleep 3
  done

  docker exec vantag-nginx nginx -t
  docker exec vantag-nginx wget -q -O /dev/null http://vantag-backend:8800/health
  echo "Nginx upstream refresh successful (status=$nginx_status)."
}

# Mosquitto config + password file are bind-mounted, so changing them in the
# repo does not take effect until the broker restarts. Restart it AFTER the
# backend is healthy so the backend (already running with credentials) keeps
# its MQTT connection across the auth switch.
restart_mosquitto() {
  echo "Restarting Mosquitto to reload authentication config..."
  docker compose -f "$COMPOSE_FILE" restart mosquitto

  local mq_status="starting" i
  for i in $(seq 1 20); do
    mq_status=$(docker inspect --format='{{.State.Health.Status}}' vantag-mosquitto-prod 2>/dev/null || echo "starting")
    [ "$mq_status" = "healthy" ] && break
    sleep 3
  done
  echo "Mosquitto restart status=$mq_status"
  if [ "$mq_status" != "healthy" ]; then
    echo "WARNING: Mosquitto did not become healthy — inspect docker logs vantag-mosquitto-prod"
  fi
}

if build_and_start && check_health && refresh_nginx_upstream; then
  restart_mosquitto
  echo "Backend deploy successful and healthy."
  docker image prune -f
  exit 0
fi

echo "Backend unhealthy — rolling back to $PREV_SHA"
git reset --hard "$PREV_SHA"
build_and_start
if check_health && refresh_nginx_upstream; then
  restart_mosquitto
  echo "Rolled back to previous version and it is healthy."
else
  echo "WARNING: rollback target is ALSO unhealthy — backend needs manual attention."
fi
echo "Failing job for visibility."
exit 1
