#!/bin/bash
# ===========================================================================
# docker/certbot/init-letsencrypt.sh
# One-time script: issue a Let's Encrypt certificate using the webroot method.
#
# Run ONCE after pointing your domain DNS to this server's IP.
# Usage:
#   chmod +x docker/certbot/init-letsencrypt.sh
#   ./docker/certbot/init-letsencrypt.sh
#
# Prerequisites:
#   - Docker + docker compose installed
#   - Domain DNS already pointing to this server
#   - Ports 80 and 443 open on the firewall
# ===========================================================================

set -e

# ── Configuration — edit these before running ─────────────────────────────────
DOMAIN="YOUR_DOMAIN"           # e.g. retailnazar.in
EMAIL="YOUR_EMAIL"             # e.g. anandindiakr@gmail.com
STAGING=0                      # set to 1 to test with Let's Encrypt staging CA

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_PATH="./certbot"
COMPOSE_FILE="docker/docker-compose.prod.yml"

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Preflight checks ──────────────────────────────────────────────────────────
[[ "$DOMAIN" == "YOUR_DOMAIN" ]] && error "Set DOMAIN at the top of this script."
[[ "$EMAIL"  == "YOUR_EMAIL"  ]] && error "Set EMAIL at the top of this script."

info "Domain : $DOMAIN"
info "Email  : $EMAIL"

# ── Download recommended TLS parameters (if not already present) ──────────────
if [ ! -e "$DATA_PATH/conf/options-ssl-nginx.conf" ]; then
    info "Downloading recommended TLS parameters..."
    mkdir -p "$DATA_PATH/conf"
    curl -s https://raw.githubusercontent.com/certbot/certbot/master/certbot-nginx/certbot_nginx/_internal/tls_configs/options-ssl-nginx.conf \
         -o "$DATA_PATH/conf/options-ssl-nginx.conf"
    openssl dhparam -out "$DATA_PATH/conf/ssl-dhparams.pem" 2048 2>/dev/null
    info "TLS parameters ready."
fi

# ── Create a dummy cert so Nginx can start (needed for webroot challenge) ──────
if [ ! -e "$DATA_PATH/conf/live/$DOMAIN/fullchain.pem" ]; then
    info "Creating temporary self-signed certificate..."
    mkdir -p "$DATA_PATH/conf/live/$DOMAIN"
    docker compose -f "$COMPOSE_FILE" run --rm --entrypoint "\
        openssl req -x509 -nodes -newkey rsa:4096 -days 1 \
            -keyout /etc/letsencrypt/live/$DOMAIN/privkey.pem \
            -out    /etc/letsencrypt/live/$DOMAIN/fullchain.pem \
            -subj   '/CN=localhost'" certbot
    info "Temporary certificate created."
fi

# ── Start Nginx so the webroot challenge can be served ────────────────────────
info "Starting Nginx..."
docker compose -f "$COMPOSE_FILE" up -d nginx
sleep 3

# ── Delete the temporary certificate ─────────────────────────────────────────
info "Removing temporary certificate..."
docker compose -f "$COMPOSE_FILE" run --rm --entrypoint "\
    rm -rf /etc/letsencrypt/live/$DOMAIN && \
    rm -rf /etc/letsencrypt/archive/$DOMAIN && \
    rm -rf /etc/letsencrypt/renewal/$DOMAIN.conf" certbot

# ── Request the real certificate ──────────────────────────────────────────────
STAGING_ARG=""
[ "$STAGING" -eq 1 ] && STAGING_ARG="--staging" && warn "Using Let's Encrypt STAGING server (cert won't be trusted)."

info "Requesting Let's Encrypt certificate for $DOMAIN..."
docker compose -f "$COMPOSE_FILE" run --rm --entrypoint "\
    certbot certonly --webroot \
        --webroot-path=/var/www/certbot \
        --email $EMAIL \
        --agree-tos \
        --no-eff-email \
        $STAGING_ARG \
        -d $DOMAIN -d www.$DOMAIN" certbot

# ── Reload Nginx with the real certificate ───────────────────────────────────
info "Reloading Nginx..."
docker compose -f "$COMPOSE_FILE" exec nginx nginx -s reload

info ""
info "=========================================="
info "  Certificate issued successfully!"
info "  Site: https://$DOMAIN"
info "  Auto-renewal: handled by certbot container"
info "=========================================="
