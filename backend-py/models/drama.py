"""
SQLAlchemy models for Drama, Character, Episode, Storyboard, Scene, Prop.
Maps to Go domain/models/drama.go.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

# ---------- Join tables ----------

from sqlalchemy import Table, Column

episode_characters = Table(
    "episode_characters",
    Base.metadata,
    Column("episode_id", Integer, ForeignKey("episodes.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
)

storyboard_characters = Table(
    "storyboard_characters",
    Base.metadata,
    Column("storyboard_id", Integer, ForeignKey("storyboards.id", ondelete="CASCADE"), primary_key=True),
    Column("character_id", Integer, ForeignKey("characters.id", ondelete="CASCADE"), primary_key=True),
)

storyboard_props = Table(
    "storyboard_props",
    Base.metadata,
    Column("storyboard_id", Integer, ForeignKey("storyboards.id", ondelete="CASCADE"), primary_key=True),
    Column("prop_id", Integer, ForeignKey("props.id", ondelete="CASCADE"), primary_key=True),
)


# ---------- Main models ----------

class Drama(Base):
    """Maps to Go Drama struct / dramas table."""
    __tablename__ = "dramas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    genre: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    style: Mapped[str] = mapped_column(String(50), default="realistic")
    total_episodes: Mapped[int] = mapped_column(Integer, default=1)
    total_duration: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    tags: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column(JSON, name="metadata", nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    episodes: Mapped[list["Episode"]] = relationship("Episode", back_populates="drama", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship("Character", back_populates="drama", cascade="all, delete-orphan")
    scenes: Mapped[list["Scene"]] = relationship("Scene", back_populates="drama", cascade="all, delete-orphan")
    props: Mapped[list["Prop"]] = relationship("Prop", back_populates="drama", cascade="all, delete-orphan")


class Character(Base):
    """Maps to Go Character struct / characters table."""
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    appearance: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    personality: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    voice_style: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    seed_value: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    drama: Mapped["Drama"] = relationship("Drama", back_populates="characters")
    episodes: Mapped[list["Episode"]] = relationship("Episode", secondary=episode_characters, back_populates="characters")
    storyboards: Mapped[list["Storyboard"]] = relationship("Storyboard", secondary=storyboard_characters, back_populates="characters")


class Episode(Base):
    """Maps to Go Episode struct / episodes table."""
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    script_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    video_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    thumbnail: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    drama: Mapped["Drama"] = relationship("Drama", back_populates="episodes")
    storyboards: Mapped[list["Storyboard"]] = relationship("Storyboard", back_populates="episode", cascade="all, delete-orphan")
    characters: Mapped[list["Character"]] = relationship("Character", secondary=episode_characters, back_populates="episodes")
    scenes: Mapped[list["Scene"]] = relationship("Scene", back_populates="episode")


class Storyboard(Base):
    """Maps to Go Storyboard struct / storyboards table."""
    __tablename__ = "storyboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    episode_id: Mapped[int] = mapped_column(Integer, ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("scenes.id"), nullable=True, index=True)
    storyboard_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    time: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    shot_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    angle: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    movement: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    action: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    atmosphere: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bgm_prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sound_effect: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dialogue: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duration: Mapped[int] = mapped_column(Integer, default=5)
    composed_image: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    video_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now())
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    episode: Mapped["Episode"] = relationship("Episode", back_populates="storyboards")
    background: Mapped[Optional["Scene"]] = relationship("Scene", foreign_keys=[scene_id])
    characters: Mapped[list["Character"]] = relationship("Character", secondary=storyboard_characters, back_populates="storyboards")
    props: Mapped[list["Prop"]] = relationship("Prop", secondary=storyboard_props, back_populates="storyboards")


class Scene(Base):
    """Maps to Go Scene struct / scenes table."""
    __tablename__ = "scenes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    episode_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("episodes.id"), nullable=True, index=True)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    time: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    storyboard_count: Mapped[int] = mapped_column(Integer, default=1)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    drama: Mapped["Drama"] = relationship("Drama", back_populates="scenes")
    episode: Mapped[Optional["Episode"]] = relationship("Episode", back_populates="scenes")


class Prop(Base):
    """Maps to Go Prop struct / props table."""
    __tablename__ = "props"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    drama_id: Mapped[int] = mapped_column(Integer, ForeignKey("dramas.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    prompt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    image_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reference_images: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)

    drama: Mapped["Drama"] = relationship("Drama", back_populates="props")
    storyboards: Mapped[list["Storyboard"]] = relationship("Storyboard", secondary=storyboard_props, back_populates="props")
