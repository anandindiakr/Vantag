#!/bin/bash
echo "=== JSON-LD count ==="
grep -c 'application/ld' /tmp/page.html
echo "=== Schema types ==="
grep -oE '"@type"[^,]*' /tmp/page.html | head -10
echo "=== HTTP headers ==="
curl -skI https://retail-vantag.com/ 2>&1
echo "=== robots.txt ==="
curl -sk https://retail-vantag.com/robots.txt | head -6
echo "=== sitemap first URL ==="
curl -sk https://retail-vantag.com/sitemap.xml | head -7
