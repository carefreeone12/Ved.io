"""
SQLAlchemy models for VideoMerge and FramePrompt.
Maps to Go domain/models/video_merge.go and frame_prompt.go.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class VideoMerge(Base):
    """Maps to Go VideoMerge struct / video_merges table."""
    __tablename__ = "video_merges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    episode_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("episodes.id"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    output_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    video_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # JSON array of video IDs
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)


class FramePrompt(Base):
    """Maps to Go FramePrompt struct / frame_prompts table."""
    __tablename__ = "frame_prompts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    storyboard_id: Mapped[int] = mapped_column(Integer, ForeignKey("storyboards.id"), nullable=False, index=True)
    frame_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
