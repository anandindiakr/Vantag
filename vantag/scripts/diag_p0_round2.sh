#!/usr/bin/env bash
# Vantag - diagnose & fix round 2 for P0 blockers.
# Addresses: backend 502, /downloads 404, server_tokens leak, mosquitto TLS failure.
set -u
echo "====================================================="
echo "  Vantag P0 diagnostic + fix round 2"
echo "  Started: $(date)"
echo "====================================================="

# ── Backend 502 diagnosis ─────────────────────────────────────────────
echo ""
echo "[A] Backend 502 check"
BACKEND_SVC=""
for cand in vantag vantag-backend vantag-api vantag-web; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^${cand}.service"; then
    BACKEND_SVC="$cand"; break
  fi
done
echo "  service: ${BACKEND_SVC:-NOT FOUND}"
echo "  status: $(systemctl is-active $BACKEND_SVC 2>/dev/null)"
echo "  last 25 log lines:"
journalctl -u "$BACKEND_SVC" -n 25 --no-pager 2>&1 | sed 's/^/    /'

# If backend is not active, try to show the failing import
if [ "$(systemctl is-active $BACKEND_SVC 2>/dev/null)" != "active" ]; then
  echo ""
  echo "  backend NOT active. Attempting direct python import check..."
  cd /var/www/vantag
  # Try to import cameras_router to catch syntax/import errors early
  python3 -c "from backend.api import cameras_router; print('  cameras_router imports OK')" 2>&1 | sed 's/^/    /'
  echo ""
  echo "  Attempting restart..."
  systemctl restart "$BACKEND_SVC"
  sleep 5
  systemctl is-active "$BACKEND_SVC" && echo "  backend now: OK" || echo "  STILL FAILING - see log above"
fi

# Re-check camera endpoint
sleep 2
CODE=$(curl -sS -o /dev/null -w "%{http_code}" https://retail-vantag.com/api/cameras)
echo "  /api/cameras now returns: $CODE (expect 401)"

# ── /downloads 404 diagnosis ──────────────────────────────────────────
echo ""
echo "[B] /downloads route check"
SITE=/etc/nginx/sites-enabled/vantag
[ -f "$SITE" ] || SITE="/etc/nginx/sites-enabled/$(ls /etc/nginx/sites-enabled/ | head -1)"
echo "  site file: $SITE"
echo "  agents folder:"; ls -la /var/www/vantag/agents 2>&1 | sed 's/^/    /'
echo "  nginx /downloads block(s):"
grep -nA 5 "location /downloads" "$SITE" | sed 's/^/    /' || echo "    NOT FOUND in site"

# Test with the real filename
CODE=$(curl -sS -o /dev/null -w "%{http_code}" https://retail-vantag.com/downloads/vantag-agent-windows.zip)
echo "  /downloads/vantag-agent-windows.zip returns: $CODE"

# If 404, the alias may be conflicting with a catch-all React SPA fallback.
# Fix: move /downloads BEFORE any `location /` or `try_files` block.
if [ "$CODE" != "200" ] && [ "$CODE" != "302" ]; then
  echo "  /downloads still 404. Injecting as FIRST location rule..."
  cp "$SITE" "$SITE.bak.round2.$(date +%s)"
  # Remove any existing /downloads block and re-inject at top of server {}
python3 - <<PYEOF
import re
p = "$SITE"
s = open(p).read()
# Strip old /downloads block
s = re.sub(r'\n\s*location /downloads/[^}]*\}\s*', '\n', s, flags=re.DOTALL)
# Find FIRST server { and inject right after its opening brace
inject = '''
    location /downloads/ {
        alias /var/www/vantag/agents/;
        autoindex off;
        add_header Content-Disposition "attachment";
        add_header X-Content-Type-Options nosniff;
        try_files \$uri =404;
    }
'''
s = re.sub(r'(server\s*\{)', r'\1' + inject, s, count=1)
open(p,'w').write(s)
print("  nginx /downloads re-injected at top of server block")
PYEOF
  nginx -t && systemctl reload nginx
  sleep 1
  CODE=$(curl -sS -o /dev/null -w "%{http_code}" https://retail-vantag.com/downloads/vantag-agent-windows.zip)
  echo "  after re-inject: $CODE"
fi

# ── server_tokens diagnosis ───────────────────────────────────────────
echo ""
echo "[C] server_tokens check"
grep -n "server_tokens" /etc/nginx/nginx.conf | sed 's/^/    /'
# If still leaking, also set in site
if curl -sS -I https://retail-vantag.com/ 2>/dev/null | grep -qi 'server: nginx/'; then
  echo "  still leaking — adding server_tokens off to site file..."
  if ! grep -q "server_tokens off" "$SITE"; then
    sed -i '/server\s*{/a \    server_tokens off;' "$SITE"
    nginx -t && systemctl reload nginx
  fi
  # Full restart instead of reload if still leaking
  systemctl restart nginx
  sleep 1
fi
echo "  server header now: $(curl -sS -I https://retail-vantag.com/ 2>/dev/null | grep -i '^server:' | head -1)"

# ── Mosquitto TLS fix ─────────────────────────────────────────────────
echo ""
echo "[D] Mosquitto TLS diagnosis"
echo "  last 20 mosquitto log lines:"
journalctl -u mosquitto -n 20 --no-pager 2>&1 | sed 's/^/    /'

echo ""
echo "  Fixing TLS cert permissions..."
# Let's Encrypt privkey.pem is a symlink into archive/ — chmod the real file
REAL_KEY=$(readlink -f /etc/letsencrypt/live/retail-vantag.com/privkey.pem)
REAL_CHAIN=$(readlink -f /etc/letsencrypt/live/retail-vantag.com/chain.pem)
REAL_CERT=$(readlink -f /etc/letsencrypt/live/retail-vantag.com/cert.pem)
echo "    real key:   $REAL_KEY"
echo "    real chain: $REAL_CHAIN"
echo "    real cert:  $REAL_CERT"

# Give mosquitto group read access to the archive directory + key files
chmod 755 /etc/letsencrypt/archive 2>/dev/null || true
chmod 755 /etc/letsencrypt/live 2>/dev/null || true
chgrp mosquitto "$REAL_KEY" "$REAL_CHAIN" "$REAL_CERT" 2>/dev/null || true
chmod 640 "$REAL_KEY" 2>/dev/null || true
chmod 644 "$REAL_CHAIN" "$REAL_CERT" 2>/dev/null || true

# Traverse: mosquitto user must be able to READ through the symlinks
usermod -a -G mosquitto mosquitto 2>/dev/null || true

systemctl restart mosquitto
sleep 3
if systemctl is-active mosquitto >/dev/null; then
  echo "  mosquitto: OK"
else
  echo "  mosquitto still failing. Trying fallback: copy certs to /etc/mosquitto/certs"
  mkdir -p /etc/mosquitto/certs
  cp -L /etc/letsencrypt/live/retail-vantag.com/chain.pem   /etc/mosquitto/certs/chain.pem
  cp -L /etc/letsencrypt/live/retail-vantag.com/cert.pem    /etc/mosquitto/certs/cert.pem
  cp -L /etc/letsencrypt/live/retail-vantag.com/privkey.pem /etc/mosquitto/certs/privkey.pem
  chown -R mosquitto:mosquitto /etc/mosquitto/certs
  chmod 640 /etc/mosquitto/certs/privkey.pem
  chmod 644 /etc/mosquitto/certs/cert.pem /etc/mosquitto/certs/chain.pem

  cat > /etc/mosquitto/conf.d/vantag.conf <<'EOF'
listener 1883 127.0.0.1
protocol mqtt

listener 8883
protocol mqtt
cafile   /etc/mosquitto/certs/chain.pem
certfile /etc/mosquitto/certs/cert.pem
keyfile  /etc/mosquitto/certs/privkey.pem

allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
  systemctl restart mosquitto
  sleep 3
  systemctl is-active mosquitto >/dev/null && echo "  mosquitto NOW OK (via cert copy)" \
    || { echo "  STILL FAILING. Log:"; journalctl -u mosquitto -n 10 --no-pager | sed 's/^/    /'; }
fi

ss -tlnp 2>/dev/null | grep -E '8883|1883' | sed 's/^/    /' || echo "    no mqtt ports listening"

# ── Final verification ────────────────────────────────────────────────
echo ""
echo "====================================================="
echo "  FINAL VERIFICATION"
echo "====================================================="
curl -sS -o /dev/null -w "  cameras no-token   : %{http_code} (expect 401)\n" https://retail-vantag.com/api/cameras
curl -sS -o /dev/null -w "  /privacy           : %{http_code} (expect 200)\n" https://retail-vantag.com/privacy
curl -sS -o /dev/null -w "  /terms             : %{http_code} (expect 200)\n" https://retail-vantag.com/terms
curl -sS -o /dev/null -w "  /downloads/windows : %{http_code} (expect 200)\n" https://retail-vantag.com/downloads/vantag-agent-windows.zip
echo -n "  server header      : "; curl -sS -I https://retail-vantag.com/ 2>/dev/null | grep -i '^server:' | head -1
echo "====================================================="
echo "  === DONE ==="
