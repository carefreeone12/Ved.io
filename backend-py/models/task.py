"""
SQLAlchemy model for AsyncTask.
Maps to Go domain/models/task.go.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AsyncTask(Base):
    """Maps to Go AsyncTask struct / async_tasks table."""
    __tablename__ = "async_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    message: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    error: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)     # JSON string
    resource_id: Mapped[str] = mapped_column(String(36), nullable=False, default="", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
