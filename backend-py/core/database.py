"""
SQLAlchemy 2.0 async database engine and session factory.
Maps to Go infrastructure/database/database.go.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from core.config import DatabaseConfig


class Base(DeclarativeBase):
    """SQLAlchemy declarative base shared by all models."""
    pass


_engine = None
_session_factory = None


def _ensure_sqlite_dir(db_path: str) -> None:
    """Create parent directory for SQLite database file if it doesn't exist."""
    parent = Path(db_path).parent
    parent.mkdir(parents=True, exist_ok=True)


def get_engine(cfg: DatabaseConfig):
    """Create and return the async SQLAlchemy engine."""
    global _engine
    if _engine is not None:
        return _engine

    if cfg.type == "sqlite":
        _ensure_sqlite_dir(cfg.path)

    connect_args: dict = {}
    if cfg.type == "sqlite":
        # WAL mode + busy timeout for better concurrency (matches Go config)
        connect_args = {
            "check_same_thread": False,
            "timeout": 20,
        }
        _engine = create_async_engine(
            cfg.async_url(),
            connect_args=connect_args,
            # SQLite: 1 concurrent writer to match Go behaviour
            pool_size=1,
            max_overflow=0,
            echo=False,
        )
    else:
        _engine = create_async_engine(
            cfg.async_url(),
            pool_size=cfg.max_idle,
            max_overflow=cfg.max_open - cfg.max_idle,
            pool_pre_ping=True,
            echo=False,
        )

    return _engine


def get_session_factory(cfg: DatabaseConfig) -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is not None:
        return _session_factory

    engine = get_engine(cfg)
    _session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
    return _session_factory


async def init_db(cfg: DatabaseConfig) -> None:
    """
    Run SQLAlchemy create_all (dev only).
    In production use Alembic migrations instead.
    """
    engine = get_engine(cfg)
    # Import all models so Base.metadata is populated
    import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_db(cfg=None) -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency: yields an async DB session.
    Usage: db: AsyncSession = Depends(get_db)
    """
    from core.config import settings as get_settings

    if cfg is None:
        cfg = get_settings().database

    factory = get_session_factory(cfg)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
