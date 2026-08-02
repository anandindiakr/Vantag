"""
manual_router.py — serves the downloadable Vantag User Manual (PDF) to
logged-in tenant users. Applies to all region sites (RetailNazar,
Retail-Vantag, RetailBantay, RetailJagaJaga, RetailPantau) since they all
share the same backend.

The manual is a static asset built offline (docs_output/build_user_manual.js
+ conversion to PDF) and checked into the repo under docs/manuals/. This
router just streams it back to any authenticated user — no tenant-specific
content is embedded in the PDF, so no further scoping is required beyond
"must be logged in."
"""
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from ..middleware.tenant_middleware import get_current_user_id

manual_router = APIRouter(prefix="/api/support", tags=["support"])

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
_MANUAL_PATH = _BASE_DIR / "docs" / "manuals" / "Vantag_User_Manual.pdf"


@manual_router.get("/manual")
async def download_user_manual(user: dict = Depends(get_current_user_id)):
    """Return the Vantag User Manual PDF for download."""
    if not _MANUAL_PATH.exists():
        raise HTTPException(status_code=404, detail="User manual is not currently available.")
    return FileResponse(
        path=str(_MANUAL_PATH),
        media_type="application/pdf",
        filename="Vantag_User_Manual.pdf",
    )
