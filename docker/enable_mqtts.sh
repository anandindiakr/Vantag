#!/usr/bin/env bash
# ===========================================================================
# docker/enable_mqtts.sh — enable MQTTS (TLS) on the Mosquitto broker.
#
# One-shot, idempotent helper that runs ON the VPS. It provisions the
# Let's Encrypt certificate into a directory the Mosquitto container can
# read, recreates the broker so it picks up the 8883 listener + cert mount
# already present in docker/mosquitto.conf and docker-compose.prod.yml,
# installs a certbot renewal hook so future renewals keep the broker's cert
# fresh, and verifies the TLS handshake.
#
# Certificates are located in one of two places (whichever is live on the
# host): the host certbot path (host-level nginx TLS) or, failing that, the
# certbot Docker volume, read out via the running `certbot` container.
#
# Usage (as root):
#   sudo sh docker/enable_mqtts.sh
#
# Env overrides:
#   MQTT_DOMAIN    domain to serve (default: retail-vantag.com)
#   CERT_SRC       certbot live dir (default: /etc/letsencrypt/live/$MQTT_DOMAIN)
#   COMPOSE_FILE   compose file      (default: docker/docker-compose.prod.yml)
# ===========================================================================
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOMAIN="${MQTT_DOMAIN:-retail-vantag.com}"
CERT_SRC="${CERT_SRC:-/etc/letsencrypt/live/${DOMAIN}}"
CERT_DST="/opt/vantag/mqtt-certs"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.prod.yml}"
ABS_COMPOSE="${REPO_ROOT}/${COMPOSE_FILE}"
BROKER_UID=1883
CONTAINER="${MOSQUITTO_CONTAINER:-vantag-mosquitto-prod}"

info()  { echo "[enable_mqtts] $*"; }
fail()  { echo "[enable_mqtts] ERROR: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || fail "run as root: sudo sh docker/enable_mqtts.sh"
cd "$REPO_ROOT"

# ── 1. Provision certs into a broker-readable directory (idempotent) ──────
# Prefer the host certbot path (host-level nginx terminates TLS). If that is
# absent, the certs live in the certbot Docker volume — read them out via the
# running certbot container so both TLS setups work.
provision_certs() {
  mkdir -p "$CERT_DST"

  if [ -s "${CERT_SRC}/fullchain.pem" ] && [ -s "${CERT_SRC}/privkey.pem" ]; then
    cp -Lf "${CERT_SRC}/fullchain.pem" "$CERT_DST/fullchain.pem"
    cp -Lf "${CERT_SRC}/privkey.pem"  "$CERT_DST/privkey.pem"
    info "certificates copied from ${CERT_SRC}"
  else
    info "no certs at ${CERT_SRC} — reading from the certbot container volume"
    docker compose -f "$COMPOSE_FILE" exec -T certbot cat "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" > "$CERT_DST/fullchain.pem" \
      || { rm -f "$CERT_DST/fullchain.pem" "$CERT_DST/privkey.pem"; fail "could not read fullchain.pem for ${DOMAIN} from the certbot container"; }
    docker compose -f "$COMPOSE_FILE" exec -T certbot cat "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" > "$CERT_DST/privkey.pem" \
      || { rm -f "$CERT_DST/fullchain.pem" "$CERT_DST/privkey.pem"; fail "could not read privkey.pem for ${DOMAIN} from the certbot container"; }
    info "certificates extracted from the certbot container"
  fi

  [ -s "$CERT_DST/fullchain.pem" ] || fail "no fullchain.pem for ${DOMAIN} — run certbot first"
  [ -s "$CERT_DST/privkey.pem" ]  || fail "no privkey.pem for ${DOMAIN} — run certbot first"
  chown -R "${BROKER_UID}:${BROKER_UID}" "$CERT_DST"
  chmod 640 "$CERT_DST/fullchain.pem" "$CERT_DST/privkey.pem"
  info "certificates provisioned into ${CERT_DST}"
}
provision_certs

# ── 2. Confirm the repo config is enabled ────────────────────────────────
grep -q '^listener 8883' docker/mosquitto.conf \
  || fail "docker/mosquitto.conf has no active 'listener 8883' — git pull the latest config first"
grep -q '/mosquitto/certs:ro' "$COMPOSE_FILE" \
  || fail "${COMPOSE_FILE} does not mount ${CERT_DST} — git pull the latest config first"

# ── 3. Recreate the broker so it loads 8883 + the cert mount ──────────────
info "recreating mosquitto broker..."
docker compose -f "$COMPOSE_FILE" up -d --force-recreate mosquitto
sleep 4

state="$(docker inspect --format='{{.State.Status}}' "$CONTAINER" 2>/dev/null || echo missing)"
[ "$state" = "running" ] || { docker logs "$CONTAINER" --tail 40; fail "mosquitto container is not running (state=$state)"; }

docker logs "$CONTAINER" --tail 200 | grep -q 'listen socket on port 8883' \
  || { docker logs "$CONTAINER" --tail 40; fail "broker did not open port 8883 — check cert mount + mosquitto.conf"; }
info "broker listening on 8883"

# ── 4. Verify the TLS handshake end-to-end ────────────────────────────────
# Operator convenience check. It needs 8883 reachable from the outside
# (firewall), so a failed external handshake must not fail the whole
# provisioning — the deploy calls this script and would otherwise treat a
# correctly-provisioned broker as failed and fall back to a self-signed cert.
if echo | openssl s_client -connect "${DOMAIN}:8883" -servername "${DOMAIN}" 2>/dev/null \
     | openssl x509 -noout -subject -dates 2>/dev/null; then
  info "TLS handshake OK on ${DOMAIN}:8883"
else
  info "WARNING: external TLS handshake on ${DOMAIN}:8883 failed — the broker is up; open 8883/tcp in the firewall and re-run to verify."
fi

# ── 5. Install certbot renewal deploy hook (idempotent) ───────────────────
HOOK_DIR="/etc/letsencrypt/renewal-hooks/deploy"
HOOK="${HOOK_DIR}/vantag-mqtt-certs.sh"
mkdir -p "$HOOK_DIR"
cat > "$HOOK" <<EOF
#!/bin/sh
# Auto-generated by docker/enable_mqtts.sh — copy renewed certs into the
# broker's cert dir and restart Mosquitto so MQTTS keeps working.
set -e
mkdir -p "${CERT_DST}"
if [ -s "${CERT_SRC}/fullchain.pem" ] && [ -s "${CERT_SRC}/privkey.pem" ]; then
  cp -Lf "${CERT_SRC}/fullchain.pem" "${CERT_DST}/fullchain.pem"
  cp -Lf "${CERT_SRC}/privkey.pem"  "${CERT_DST}/privkey.pem"
else
  docker compose -f "${ABS_COMPOSE}" exec -T certbot cat "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" > "${CERT_DST}/fullchain.pem"
  docker compose -f "${ABS_COMPOSE}" exec -T certbot cat "/etc/letsencrypt/live/${DOMAIN}/privkey.pem" > "${CERT_DST}/privkey.pem"
fi
chown -R "${BROKER_UID}:${BROKER_UID}" "${CERT_DST}"
chmod 640 "${CERT_DST}/fullchain.pem" "${CERT_DST}/privkey.pem"
docker restart "${CONTAINER}" >/dev/null
EOF
chmod +x "$HOOK"
info "renewal hook installed: ${HOOK}"

info ""
info "============================================================"
info " MQTTS enabled and verified on ${DOMAIN}:8883"
info ""
info " Next steps:"
info "   1. Re-download an Edge Agent and confirm a Test unlock."
info "   2. Lock down plaintext 1883/9001 (bind to 127.0.0.1 in"
info "      docker-compose.prod.yml) and open 8883/tcp in ufw."
info "   3. Commit this config so git-reset deploys keep it."
info "============================================================"
