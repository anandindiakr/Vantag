"""
backend/utils/csv_export.py
============================
Shared helper that streams rows as a CSV download using FastAPI's
StreamingResponse.  Handles proper quoting and BOM for Excel compatibility.

Usage:
    from ..utils.csv_export import stream_csv

    return stream_csv(
        filename="payments_export.csv",
        headers=["id", "tenant_id", "amount", "currency", "status", "created_at"],
        rows=[[row.id, row.tenant_id, row.amount, row.currency, row.status, row.created_at]
              for row in results],
    )
"""
from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence

from fastapi.responses import StreamingResponse


def stream_csv(
    filename: str,
    headers: Sequence[str],
    rows: Iterable[Sequence],
) -> StreamingResponse:
    """
    Return a StreamingResponse that streams a CSV file.

    Args:
        filename:  The filename to use in the Content-Disposition header.
        headers:   Column names for the CSV header row.
        rows:      Iterable of row sequences (each item is a column value).

    Returns:
        A FastAPI StreamingResponse with Content-Type: text/csv.
    """

    def _generate():
        buf = io.StringIO()
        # UTF-8 BOM so Excel opens it correctly without import wizard
        buf.write("\ufeff")
        writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(headers)
        yield buf.getvalue()

        for row in rows:
            buf = io.StringIO()
            writer = csv.writer(buf, quoting=csv.QUOTE_MINIMAL)
            # Stringify every cell to avoid type errors
            writer.writerow([str(cell) if cell is not None else "" for cell in row])
            yield buf.getvalue()

    return StreamingResponse(
        _generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )
