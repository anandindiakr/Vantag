"""
backend/db/database.py
======================
SQLAlchemy async engine + session factory + base model.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# Load .env from project root or backend/ (whichever exists) before reading env vars
try:
    from dotenv import load_dotenv
    _here = Path(__file__).resolve()
    for _candidate in (_here.parent.parent.parent / ".env", _here.parent.parent / ".env"):
        if _candidate.exists():
            load_dotenv(_candidate, override=False)
            break
except ImportError:
    pass

# Build async URL: convert postgresql:// → postgresql+asyncpg://
# Accept either DATABASE_URL (preferred) or POSTGRES_URL (legacy)
_raw_url: str = (
    os.getenv("DATABASE_URL")
    or os.getenv("POSTGRES_URL")
    or "postgresql://vantag:vantag_dev_pass@127.0.0.1:5432/vantag_db"
)
# Normalise scheme to asyncpg
if _raw_url.startswith("postgresql+asyncpg://"):
    DATABASE_URL = _raw_url
elif _raw_url.startswith("postgresql://"):
    DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_url

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Create all tables (used in development; production uses Alembic)."""
    # Import models so they register with Base.metadata before create_all
    from .models import tenant as _tenant  # noqa: F401
    from .models import camera as _camera  # noqa: F401
    from .models import event as _event  # noqa: F401
    from .models import billing as _billing  # noqa: F401
    from .models import admin as _admin  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
