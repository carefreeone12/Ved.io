"""
SQLAlchemy models for ImageGeneration.
Maps to Go domain/models/image_generation.go.
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base


class ImageGenerationStatus(str, enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ImageProvider(str, enum.Enum):
    openai = "openai"
    midjourney = "midjourney"
    stable_diffusion = "stable_diffusion"
    dalle = "dalle"


class ImageType(str, enum.Enum):
    character = "character"
    scene = "scene"
    prop = "prop"
    storyboard = "storyboard"


class ImageGeneration(Base):
    """Maps to Go ImageGeneration struct / image_generations table."""
    __tablename__ = "image_generations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    storyboard_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("storyboards.id"), nullable=True, index=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scenes.id"), nullable=True, index=True)
    character_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("characters.id"), nullable=True, index=True)
    prop_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("props.id"), nullable=True, index=True)
    image_type: Mapped[str] = mapped_column(String(20), default="storyboard", index=True)
    frame_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    size: Mapped[str] = mapped_column(String(20), nullable=False, default="1024x1024")
    quality: Mapped[str] = mapped_column(String(20), nullable=False, default="standard")
    style: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cfg_scale: Mapped[Optional[float]] = mapped_column(nullable=True)
    seed: Mapped[Optional[int]] = mapped_column(nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    minio_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    task_id: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    error_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reference_images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
