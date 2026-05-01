#!/usr/bin/env bash
# Vantag - fix all P0 blockers on production VPS.
# Safe to re-run: every step is idempotent.
set -e
echo "====================================================="
echo "  Vantag P0 blocker auto-fix"
echo "  Started: $(date)"
echo "====================================================="

cd /var/www/vantag

echo ""
echo "[1/6] Pull latest code from GitHub..."
git pull origin master

echo ""
echo "[2/6] Rebuild frontend (this takes 1-2 minutes)..."
cd frontend/web
npm run build
cd /var/www/vantag

echo ""
echo "[3/6] Restart backend (applies /api/cameras auth fix)..."
systemctl restart vantag-backend
sleep 3
systemctl is-active vantag-backend && echo "  backend: OK" || echo "  backend: FAILED - check 'journalctl -u vantag-backend -n 50'"

echo ""
echo "[4/6] Create Edge Agent downloads directory..."
mkdir -p /var/www/vantag/agents
for p in windows android linux; do
  f="/var/www/vantag/agents/vantag-agent-$p.zip"
  if [ ! -f "$f" ]; then
    echo "Vantag Edge Agent placeholder for $p - replace with real signed build" > "$f"
    echo "  created: $f"
  fi
done
chown -R www-data:www-data /var/www/vantag/agents

echo ""
echo "[5/6] Patch nginx (downloads route + rate limit + hide version)..."
grep -q "server_tokens off" /etc/nginx/nginx.conf || \
  sed -i '/http {/a \    server_tokens off;' /etc/nginx/nginx.conf
grep -q "vantag_login" /etc/nginx/nginx.conf || \
  sed -i '/http {/a \    limit_req_zone $binary_remote_addr zone=vantag_login:10m rate=5r/m;' /etc/nginx/nginx.conf

SITE=/etc/nginx/sites-enabled/vantag
if [ ! -f "$SITE" ]; then
  FIRST=$(ls /etc/nginx/sites-enabled/ 2>/dev/null | head -1)
  SITE="/etc/nginx/sites-enabled/$FIRST"
fi
echo "  patching nginx site: $SITE"

if ! grep -q "location /downloads/" "$SITE"; then
  cp "$SITE" "$SITE.bak.$(date +%s)"
  python3 - <<PYEOF
import re
p = "$SITE"
s = open(p).read()
inject = '''
    location /downloads/ {
        alias /var/www/vantag/agents/;
        autoindex off;
        add_header Content-Disposition "attachment";
        add_header X-Content-Type-Options nosniff;
    }
    location = /api/auth/login {
        limit_req zone=vantag_login burst=3 nodelay;
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
'''
new = re.sub(r'(server\s*\{[^}]*?)(\n\})', r'\1' + inject + r'\2', s, count=1, flags=re.DOTALL)
open(p,'w').write(new)
print("  nginx config patched")
PYEOF
fi

nginx -t && systemctl reload nginx && echo "  nginx: OK"

echo ""
echo "[6/6] Configure MQTT TLS 8883 + open firewall..."
ufw allow 8883/tcp 2>/dev/null || true
MQTT_CONF=/etc/mosquitto/conf.d/vantag.conf
if ! grep -q "listener 8883" "$MQTT_CONF" 2>/dev/null; then
cat > "$MQTT_CONF" <<'EOF'
listener 1883 127.0.0.1
protocol mqtt

listener 8883
protocol mqtt
cafile   /etc/letsencrypt/live/retail-vantag.com/chain.pem
certfile /etc/letsencrypt/live/retail-vantag.com/cert.pem
keyfile  /etc/letsencrypt/live/retail-vantag.com/privkey.pem

allow_anonymous false
password_file /etc/mosquitto/passwd
EOF
  echo "  mosquitto config written"
  chgrp mosquitto /etc/letsencrypt/live/retail-vantag.com/privkey.pem 2>/dev/null || true
  chmod 640 /etc/letsencrypt/live/retail-vantag.com/privkey.pem 2>/dev/null || true
fi

if [ ! -f /etc/mosquitto/passwd ]; then
  mosquitto_passwd -c -b /etc/mosquitto/passwd vantag_edge ChangeMe_EdgePass_2026
  chmod 640 /etc/mosquitto/passwd
  chown root:mosquitto /etc/mosquitto/passwd
  echo "  mosquitto password file created (user=vantag_edge)"
fi

systemctl restart mosquitto
sleep 2
systemctl is-active mosquitto && echo "  mosquitto: OK" || echo "  mosquitto: FAILED - check 'journalctl -u mosquitto -n 30'"

echo ""
echo "====================================================="
echo "  VERIFICATION"
echo "====================================================="
curl -sS -o /dev/null -w "  cameras no-token   : %{http_code} (expect 401)\n" https://retail-vantag.com/api/cameras
curl -sS -o /dev/null -w "  /privacy           : %{http_code} (expect 200)\n" https://retail-vantag.com/privacy
curl -sS -o /dev/null -w "  /terms             : %{http_code} (expect 200)\n" https://retail-vantag.com/terms
curl -sS -o /dev/null -w "  /downloads/win.zip : %{http_code} (expect 200)\n" https://retail-vantag.com/downloads/vantag-agent-windows.zip
echo -n "  server header      : "; curl -sS -I https://retail-vantag.com/ 2>/dev/null | grep -i '^server:' | head -1
echo "  listening ports:"; ss -tlnp | grep -E '8883|1883' | sed 's/^/    /' || true

echo ""
echo "====================================================="
echo "  === DONE === at $(date)"
echo "====================================================="
