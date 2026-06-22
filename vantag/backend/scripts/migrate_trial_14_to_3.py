"""Migrate existing trial tenants from the legacy 14-day trial to the new 3-day trial.

Background
----------
Trials used to run for 14 days (`trial_ends_at = created_at + 14d`). The new
policy is a 3-day trial (`trial_ends_at = created_at + 3d`). This script
re-bases every *active trial* tenant onto the 3-day schedule.

Safety
------
- Only touches rows where ``status == 'trial'`` and ``deleted_at IS NULL``.
- Only shortens trials that are still on the old (longer) schedule, i.e.
  current ``trial_ends_at`` is later than ``created_at + 3d``. Trials already
  at or under 3 days are left untouched (idempotent).
- New ``trial_ends_at = created_at + 3d``.
- A tenant whose recomputed trial end is already in the past keeps the new
  (past) date; the normal expiry job will flip it to ``suspended`` -- we do
  NOT change ``status`` here.
- Dry-run by default. Pass ``--commit`` to actually write changes.

Usage
-----
    # preview only (no writes)
    python -m backend.scripts.migrate_trial_14_to_3

    # apply the changes
    python -m backend.scripts.migrate_trial_14_to_3 --commit
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from ..db.database import AsyncSessionLocal
from ..db.models.tenant import Tenant

NEW_TRIAL_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalise naive datetimes coming back from the DB to UTC-aware."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def migrate(commit: bool) -> int:
    now = _now()
    new_window = timedelta(days=NEW_TRIAL_DAYS)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Tenant).where(
                Tenant.status == "trial",
                Tenant.deleted_at.is_(None),
            )
        )
        tenants = result.scalars().all()

        candidates: list[tuple[Tenant, datetime, datetime | None]] = []
        for t in tenants:
            created = _as_utc(t.created_at)
            current_end = _as_utc(t.trial_ends_at)
            new_end = created + new_window

            # Skip rows already on (or under) the new 3-day schedule.
            if current_end is not None and current_end <= new_end + timedelta(minutes=1):
                continue
            candidates.append((t, new_end, current_end))

        print("=" * 78)
        print(f"Trial migration  14d -> {NEW_TRIAL_DAYS}d    ({'COMMIT' if commit else 'DRY-RUN'})")
        print(f"Now (UTC): {now.isoformat()}")
        print(f"Active trial tenants scanned : {len(tenants)}")
        print(f"Tenants needing migration    : {len(candidates)}")
        print("-" * 78)
        print(f"{'slug':<24} {'created':<20} {'old end':<20} {'new end':<20} note")
        print("-" * 78)

        expired_now = 0
        for t, new_end, current_end in candidates:
            created = _as_utc(t.created_at)
            note = "EXPIRES IMMEDIATELY" if new_end <= now else ""
            if new_end <= now:
                expired_now += 1
            print(
                f"{(t.slug or t.id)[:24]:<24} "
                f"{created.strftime('%Y-%m-%d %H:%M'):<20} "
                f"{(current_end.strftime('%Y-%m-%d %H:%M') if current_end else 'None'):<20} "
                f"{new_end.strftime('%Y-%m-%d %H:%M'):<20} {note}"
            )
            if commit:
                t.trial_ends_at = new_end

        print("-" * 78)
        print(f"Would expire immediately after migration: {expired_now}")

        if commit and candidates:
            await session.commit()
            print(f"COMMITTED: updated {len(candidates)} tenant(s).")
        elif commit:
            print("COMMITTED: nothing to update.")
        else:
            print("DRY-RUN: no changes written. Re-run with --commit to apply.")
        print("=" * 78)

    return len(candidates)


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate trial tenants 14d -> 3d")
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Apply the changes. Without this flag the script is a dry-run.",
    )
    args = parser.parse_args()
    asyncio.run(migrate(commit=args.commit))


if __name__ == "__main__":
    main()
