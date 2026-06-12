"""Live tests against all 6 Vantag domains. Writes a JSON result file."""
import json, subprocess, ssl, socket, re, time
from datetime import datetime
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

DOMAINS = [
    ("retail-vantag.com",    "SG"),
    ("retailnazar.com",      "IN"),
    ("retailnazar.in",       "IN"),
    ("retailnazar.info",     "IN"),
    ("jagajaga.my",          "MY"),
    ("retailjagajaga.com",   "MY"),
]

results = {"run_at": datetime.utcnow().isoformat() + "Z", "domains": {}}

def status(ok): return "PASS" if ok else "FAIL"

def dns_ip(host):
    try: return socket.gethostbyname(host)
    except Exception as e: return f"ERR:{e}"

def tls_expiry(host):
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=8) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                exp = cert["notAfter"]
                exp_dt = datetime.strptime(exp, "%b %d %H:%M:%S %Y %Z")
                days = (exp_dt - datetime.utcnow()).days
                return {"expires": exp, "days_left": days, "issuer": dict(x[0] for x in cert["issuer"]).get("organizationName", "?")}
    except Exception as e:
        return {"error": str(e)}

def http_head(url, timeout=10):
    try:
        req = Request(url, method="GET", headers={"User-Agent": "VantagLaunchTester/1.0"})
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        r = urlopen(req, context=ctx, timeout=timeout)
        return {"code": r.status, "headers": dict(r.headers), "body_bytes": len(r.read(32768))}
    except HTTPError as e:
        return {"code": e.code, "headers": dict(e.headers) if e.headers else {}, "error": str(e)}
    except URLError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": str(e)}

def fetch_text(url, timeout=10):
    try:
        req = Request(url, headers={"User-Agent": "VantagLaunchTester/1.0"})
        ctx = ssl.create_default_context()
        r = urlopen(req, context=ctx, timeout=timeout)
        return r.read(262144).decode("utf-8", errors="replace")
    except Exception as e:
        return f"__ERR__:{e}"

for host, region in DOMAINS:
    print(f"\n=== {host} ({region}) ===")
    rec = {"region": region, "checks": {}}
    rec["dns_a"] = dns_ip(host)
    print(f"  DNS A: {rec['dns_a']}")

    tls = tls_expiry(host)
    rec["tls"] = tls
    if "error" in tls:
        print(f"  TLS: FAIL ({tls['error']})")
        rec["checks"]["tls_valid"] = "FAIL"
    else:
        print(f"  TLS: valid, expires in {tls['days_left']} days ({tls['issuer']})")
        rec["checks"]["tls_valid"] = "PASS" if tls["days_left"] > 14 else "WARN"

    # Root page
    root = http_head(f"https://{host}/")
    rec["root"] = root
    code = root.get("code")
    rec["checks"]["root_200"] = status(code == 200)
    print(f"  / → {code}")

    # Headers
    hdrs = {k.lower(): v for k, v in (root.get("headers") or {}).items()}
    rec["checks"]["hsts"]              = status("strict-transport-security" in hdrs)
    rec["checks"]["x_content_type"]    = status(hdrs.get("x-content-type-options", "").lower() == "nosniff")
    rec["checks"]["x_frame_options"]   = status("x-frame-options" in hdrs)
    rec["checks"]["referrer_policy"]   = status("referrer-policy" in hdrs)

    # Health
    health = http_head(f"https://{host}/health")
    rec["health_code"] = health.get("code")
    rec["checks"]["health_200"] = status(health.get("code") == 200)
    print(f"  /health → {health.get('code')}")

    # robots.txt
    rtxt = fetch_text(f"https://{host}/robots.txt")
    rec["robots_head"] = rtxt[:240]
    rec["checks"]["robots_exists"] = status(rtxt and not rtxt.startswith("__ERR__") and "User-agent" in rtxt)
    rec["checks"]["robots_disallow_admin"] = status("Disallow: /admin" in rtxt or "Disallow: /api" in rtxt)

    # sitemap.xml
    smap = fetch_text(f"https://{host}/sitemap.xml")
    rec["sitemap_head"] = smap[:400]
    rec["checks"]["sitemap_exists"] = status(smap.startswith("<?xml") or "<urlset" in smap)
    rec["checks"]["sitemap_https"] = status(f"https://{host}" in smap)

    # og-cover.png
    og = http_head(f"https://{host}/og-cover.png")
    rec["og_cover"] = {"code": og.get("code"),
                      "content_type": og.get("headers", {}).get("Content-Type") or og.get("headers", {}).get("content-type")}
    rec["checks"]["og_image"] = status(
        og.get("code") == 200 and
        "image" in str(rec["og_cover"]["content_type"] or "").lower()
    )

    # SEO basics on homepage HTML
    body = fetch_text(f"https://{host}/")
    if body and not body.startswith("__ERR__"):
        rec["html_bytes"] = len(body)
        title_m = re.search(r"<title>([^<]*)</title>", body, re.I)
        desc_m  = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', body, re.I)
        h1_m    = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", body, re.I)
        title = (title_m.group(1) if title_m else "").strip()
        desc  = (desc_m.group(1)  if desc_m  else "").strip()
        h1    = re.sub(r"\s+", " ", (h1_m.group(1) if h1_m else "")).strip()[:120]
        rec["seo"] = {"title": title, "title_len": len(title),
                      "desc_len": len(desc), "desc_preview": desc[:140],
                      "h1_preview": h1, "h1_present": bool(h1_m)}
        rec["checks"]["seo_title_present"] = status(0 < len(title) <= 60)
        rec["checks"]["seo_desc_len_ok"]   = status(120 <= len(desc) <= 170)
        rec["checks"]["seo_h1_in_raw_html"] = status(bool(h1_m))
        rec["checks"]["privacy_link"] = status("/privacy" in body.lower())
        rec["checks"]["terms_link"]   = status("/terms" in body.lower())
        print(f"  Title ({len(title)} chars): {title[:70]}")
        print(f"  Desc length: {len(desc)}")
        print(f"  H1 in raw HTML: {'yes' if h1_m else 'NO'}")
    else:
        rec["seo"] = {"error": body[:120]}
        for k in ["seo_title_present","seo_desc_len_ok","seo_h1_in_raw_html","privacy_link","terms_link"]:
            rec["checks"][k] = "FAIL"

    results["domains"][host] = rec

# Summary
summary = {}
for host, rec in results["domains"].items():
    for k, v in rec["checks"].items():
        summary.setdefault(k, {"PASS": 0, "FAIL": 0, "WARN": 0})
        summary[k][v] = summary[k].get(v, 0) + 1
results["summary"] = summary

with open("live_test_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)

print("\n=== SUMMARY ===")
for k, v in summary.items():
    print(f"  {k:30s}  PASS={v.get('PASS',0)}  WARN={v.get('WARN',0)}  FAIL={v.get('FAIL',0)}")
print("\nSaved: live_test_results.json")
