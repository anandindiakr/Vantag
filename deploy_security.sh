#!/bin/bash
set -e
cd /var/www/vantag
git pull origin master
cd frontend/web
npm run build 2>&1 | tail -3
cd /var/www/vantag
systemctl restart vantag

NGINX_FILE=$(grep -l 'retail-vantag' /etc/nginx/sites-enabled/* | head -1)
echo "Patching: $NGINX_FILE"

# Add security headers inside each server { } block — idempotent
python3 <<'PY'
p = "/etc/nginx/sites-enabled/vantag"
s = open(p).read()

headers = """    # ── SEO / security headers ──
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(self), microphone=(), geolocation=(self)" always;
"""

if "X-Content-Type-Options" not in s:
    # Insert the headers block right after each "server_name" line
    import re
    def inject(m):
        return m.group(0) + "\n" + headers
    s = re.sub(r"(server_name[^;]+;)", inject, s)
    open(p, "w").write(s)
    print("security headers added")
else:
    print("security headers already present")
PY

nginx -t && systemctl reload nginx

echo "=== verify ==="
curl -skI https://retail-vantag.com/ | grep -iE "strict-transport|x-content-type|x-frame|referrer|permissions"
echo "=== og-cover ==="
curl -skI https://retail-vantag.com/og-cover.png | head -3
echo "=== DONE ==="
