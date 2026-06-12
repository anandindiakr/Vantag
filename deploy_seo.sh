#!/bin/bash
set -e
cd /var/www/vantag
git pull origin master
cd frontend/web
npm run build 2>&1 | tail -5
cd /var/www/vantag
systemctl restart vantag

# Patch nginx to route /robots.txt and /sitemap.xml to the backend
NGINX_FILE=$(grep -l 'retail-vantag' /etc/nginx/sites-enabled/* | head -1)
echo "Nginx file: $NGINX_FILE"

if ! grep -q 'location = /sitemap.xml' "$NGINX_FILE"; then
  # Insert before "location /api/"
  python3 -c "
import re,sys
p='$NGINX_FILE'
s=open(p).read()
ins='''    location = /robots.txt {
        proxy_pass http://127.0.0.1:8000/robots.txt;
        proxy_set_header Host \$host;
    }

    location = /sitemap.xml {
        proxy_pass http://127.0.0.1:8000/sitemap.xml;
        proxy_set_header Host \$host;
    }

'''
s=s.replace('    location /api/',ins+'    location /api/',1)
open(p,'w').write(s)
print('nginx patched')
"
  nginx -t
  systemctl reload nginx
else
  echo "nginx already patched"
fi

# Quick self-test
echo "--- robots.txt (retail-vantag.com) ---"
curl -s -H "Host: retail-vantag.com" http://127.0.0.1/robots.txt | head -8
echo "--- sitemap.xml (retailnazar.com) ---"
curl -s -H "Host: retailnazar.com" http://127.0.0.1/sitemap.xml | head -12
echo "=== DEPLOY DONE ==="
