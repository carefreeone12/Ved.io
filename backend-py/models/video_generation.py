"""
SQLAlchemy models for VideoGeneration.
Maps to Go domain/models/video_generation.go.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class VideoStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class VideoProvider(str, enum.Enum):
    runway = "runway"
    pika = "pika"
    doubao = "doubao"
    openai = "openai"


class VideoGeneration(Base):
    """Maps to Go VideoGeneration struct / video_generations table."""
    __tablename__ = "video_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    storyboard_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("storyboards.id"), nullable=True, index=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    image_gen_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("image_generations.id"), nullable=True, index=True)
    reference_mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    first_frame_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    last_frame_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    reference_image_urls: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    aspect_ratio: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    style: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    motion_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    camera_motion: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    seed: Mapped[Optional[int]] = mapped_column(nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    minio_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    task_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
