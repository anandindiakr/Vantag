"""
SEO router — serves host-aware robots.txt and sitemap.xml.

Each of our 3 regional domains (retail-vantag.com, retailnazar.com, jagajaga.my,
etc.) gets its own absolute-URL sitemap so Google indexes them cleanly as
separate sites, while hreflang tags in index.html cross-link the regions.
"""
from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse, Response

seo_router = APIRouter(tags=["seo"])

# Public pages the crawler should index. Private pages (dashboard, admin,
# onboarding) are deliberately excluded and also blocked in robots.txt.
PUBLIC_PATHS: list[tuple[str, str, float]] = [
    # (path, changefreq, priority)
    ("/",                    "weekly",  1.0),
    ("/how-it-works",        "monthly", 0.8),
    ("/pricing",             "weekly",  0.9),
    ("/support",             "monthly", 0.6),
    ("/faq",                 "monthly", 0.7),
    ("/login",               "yearly",  0.3),
    ("/register",            "yearly",  0.5),
    ("/forgot-password",     "yearly",  0.2),
]

# Alternate regional domains — all three advertised as hreflang siblings.
ALTERNATE_DOMAINS = {
    "en-SG": "https://retail-vantag.com",
    "en-IN": "https://retailnazar.com",
    "en-MY": "https://retailjagajaga.com",
    "ms-MY": "https://jagajaga.my",
}


def _scheme(request: Request) -> str:
    return request.headers.get("x-forwarded-proto") or request.url.scheme or "https"


def _host(request: Request) -> str:
    return request.headers.get("host", "retail-vantag.com").split(":")[0]


@seo_router.get("/robots.txt", response_class=PlainTextResponse, include_in_schema=False)
async def robots(request: Request) -> str:
    """Host-aware robots.txt — allows all search engines, blocks private pages."""
    base = f"{_scheme(request)}://{_host(request)}"
    return (
        "# Vantag Retail Intelligence — robots.txt\n"
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# Block authenticated / private areas (no value to search crawlers)\n"
        "Disallow: /dashboard\n"
        "Disallow: /admin\n"
        "Disallow: /onboarding\n"
        "Disallow: /cameras\n"
        "Disallow: /cameras-manage\n"
        "Disallow: /incidents\n"
        "Disallow: /watchlist\n"
        "Disallow: /zone-editor\n"
        "Disallow: /demo-center\n"
        "Disallow: /health-check\n"
        "Disallow: /reset-password\n"
        "Disallow: /api/\n"
        "Disallow: /ws\n"
        "\n"
        "# Allow explicit crawl of public marketing pages\n"
        "Allow: /how-it-works\n"
        "Allow: /pricing\n"
        "Allow: /support\n"
        "Allow: /faq\n"
        "\n"
        "# Modern AI-search crawlers (explicitly welcomed)\n"
        "User-agent: GPTBot\nAllow: /\n\n"
        "User-agent: ChatGPT-User\nAllow: /\n\n"
        "User-agent: Google-Extended\nAllow: /\n\n"
        "User-agent: PerplexityBot\nAllow: /\n\n"
        "User-agent: ClaudeBot\nAllow: /\n\n"
        "User-agent: anthropic-ai\nAllow: /\n\n"
        "User-agent: CCBot\nAllow: /\n"
        "\n"
        f"Sitemap: {base}/sitemap.xml\n"
    )


@seo_router.get("/sitemap.xml", include_in_schema=False)
async def sitemap(request: Request) -> Response:
    """Host-aware sitemap.xml with hreflang alternates for the 3 regions."""
    base = f"{_scheme(request)}://{_host(request)}"
    today = datetime.utcnow().strftime("%Y-%m-%d")

    urls_xml: list[str] = []
    for path, changefreq, priority in PUBLIC_PATHS:
        loc = f"{base}{path}"
        alternates = "\n".join(
            f'    <xhtml:link rel="alternate" hreflang="{lang}" href="{dom}{path}" />'
            for lang, dom in ALTERNATE_DOMAINS.items()
        )
        alternates += (
            f'\n    <xhtml:link rel="alternate" hreflang="x-default" '
            f'href="https://retail-vantag.com{path}" />'
        )
        urls_xml.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{today}</lastmod>\n"
            f"    <changefreq>{changefreq}</changefreq>\n"
            f"    <priority>{priority:.1f}</priority>\n"
            f"{alternates}\n"
            "  </url>"
        )

    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"\n'
        '        xmlns:xhtml="http://www.w3.org/1999/xhtml">\n'
        + "\n".join(urls_xml) +
        "\n</urlset>\n"
    )
    return Response(content=body, media_type="application/xml")
