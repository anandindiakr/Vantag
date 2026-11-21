from __future__ import annotations

from pathlib import Path

import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "frontend" / "web" / "public" / "handouts"


def main():
    with pdfplumber.open(DIRECTORY / "vantag-offline-demo-team-manual.pdf") as document:
        if len(document.pages) != 8:
            raise AssertionError(f"Expected 8 chapter pages, got {len(document.pages)}")
        for index, page in enumerate(document.pages):
            if f"{index + 1}. " not in page.extract_text():
                raise AssertionError(f"Chapter heading missing on page {index + 1}")
            for character in page.chars:
                if character["x0"] < 40 or character["x1"] > page.width - 40 or character["top"] < 30 or character["bottom"] > page.height - 20:
                    raise AssertionError(f"Text exceeds safe page bounds on page {index + 1}")
        text = "\n".join(page.extract_text() for page in document.pages)
    for phrase in ("UNDER VALIDATION", "Test decoded video", "Actual NVR password", "vantag-renewal-request.json", "vantag-demo-entitlement.json", "CPU fallback", "RTSP 401", "256 MB", "12 characters"):
        if phrase not in text:
            raise AssertionError(f"Missing manual instruction: {phrase}")
    page = (DIRECTORY / "vantag-offline-demo-team-manual.html").read_text(encoding="utf-8")
    if page.count('<section id="chapter-') != 8 or '<script' in page or '<img' in page or '<link' in page:
        raise AssertionError("Offline HTML has unexpected dependencies or chapter structure")
    print({"ok": True, "pdf_pages": 8, "bounds_checked": True, "key_procedures_checked": True, "self_contained_html": True})


if __name__ == "__main__":
    main()
