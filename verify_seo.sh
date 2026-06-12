#!/bin/bash
for d in retail-vantag.com retailnazar.com retailnazar.in retailjagajaga.com jagajaga.my; do
  echo "=== $d ==="
  curl -sk "https://$d/robots.txt" | head -2
  curl -sk "https://$d/sitemap.xml" | grep -o "<loc>[^<]*</loc>" | head -1
done
