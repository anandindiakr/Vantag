"""Small transactional migration runner used during backend startup.

The project does not ship Alembic. This runner gives production deployments a
versioned, auditable migration path without replacing SQLAlchemy's model
bootstrap for fresh databases. Each numbered SQL file is applied once and
recorded in ``schema_migrations``.
"""
from __future__ import annotations

from pathlib import Path

_MIGRATIONS_DIR = Path(__file__).resolve().parent


async def run_pending_migrations(conn) -> list[str]:  # noqa: ANN001
    """Apply numbered SQL migrations in lexical order on one DB connection."""
    await conn.exec_driver_sql(
        """CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(255) PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    rows = await conn.exec_driver_sql("SELECT version FROM schema_migrations")
    applied = {row[0] for row in rows.fetchall()}
    applied_now: list[str] = []

    for path in sorted(_MIGRATIONS_DIR.glob("[0-9]*.sql")):
        version = path.name
        if version in applied:
            continue
        sql = path.read_text(encoding="utf-8").strip()
        if not sql:
            continue
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                await conn.exec_driver_sql(statement)
        # ``version`` is derived from a repository filename, never user input.
        await conn.exec_driver_sql(
            "INSERT INTO schema_migrations(version) VALUES ("
            + repr(version)
            + ")"
        )
        applied_now.append(version)
    return applied_now
