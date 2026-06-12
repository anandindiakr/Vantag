#!/bin/bash
python3 <<'PY'
p = "/etc/nginx/sites-enabled/vantag"
s = open(p).read()
s = s.replace("X-Forwarded-Proto ;", "X-Forwarded-Proto $scheme;")
open(p, "w").write(s)
print("patched")
PY
nginx -t && systemctl reload nginx
echo "---"
curl -sk https://retailnazar.com/sitemap.xml | head -6
