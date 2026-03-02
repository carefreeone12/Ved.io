"""
Flask dependency helpers.
Replaces FastAPI's Depends() system with simple helper functions.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, settings as get_settings_fn
from core.database import get_session_factory
from core.storage import LocalStorage


def get_settings() -> Settings:
    return get_settings_fn()


def get_storage() -> LocalStorage:
    cfg = get_settings()
    return LocalStorage(
        base_path=cfg.storage.local_path,
        base_url=cfg.storage.base_url,
    )


@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager that yields a database session.
    Use in Flask async route handlers:

        async with db_session() as db:
            result = await db.execute(...)
    """
    cfg = get_settings()
    factory = get_session_factory(cfg.database)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
