"""
Pydantic v2 schemas for Drama, Character, Episode, Storyboard, Scene, Prop.
These are the API request/response shapes — must match Go handler JSON output exactly.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------- Drama ----------

class DramaCreate(BaseModel):
    title: str
    description: Optional[str] = None
    genre: Optional[str] = None
    style: str = "realistic"
    total_episodes: int = 1
    tags: Optional[list] = None
    metadata: Optional[dict] = None

class DramaUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    genre: Optional[str] = None
    style: Optional[str] = None
    total_episodes: Optional[int] = None
    status: Optional[str] = None
    thumbnail: Optional[str] = None
    tags: Optional[list] = None
    metadata: Optional[dict] = None

class DramaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str]
    genre: Optional[str]
    style: str
    total_episodes: int
    total_duration: int
    status: str
    thumbnail: Optional[str]
    tags: Optional[Any]
    created_at: datetime
    updated_at: datetime

class DramaStats(BaseModel):
    total: int
    draft: int
    in_progress: int
    completed: int


# ---------- Character ----------

class CharacterCreate(BaseModel):
    drama_id: int
    name: str
    role: Optional[str] = None
    description: Optional[str] = None
    appearance: Optional[str] = None
    personality: Optional[str] = None
    voice_style: Optional[str] = None
    seed_value: Optional[str] = None
    sort_order: int = 0

class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    description: Optional[str] = None
    appearance: Optional[str] = None
    personality: Optional[str] = None
    voice_style: Optional[str] = None
    image_url: Optional[str] = None
    seed_value: Optional[str] = None
    sort_order: Optional[int] = None

class CharacterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    name: str
    role: Optional[str]
    description: Optional[str]
    appearance: Optional[str]
    personality: Optional[str]
    voice_style: Optional[str]
    image_url: Optional[str]
    seed_value: Optional[str]
    sort_order: int
    created_at: datetime
    updated_at: datetime


# ---------- Episode ----------

class EpisodeCreate(BaseModel):
    drama_id: int
    episode_number: int
    title: str
    description: Optional[str] = None
    script_content: Optional[str] = None

class EpisodeUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    script_content: Optional[str] = None
    status: Optional[str] = None
    duration: Optional[int] = None

class EpisodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    episode_number: int
    title: str
    description: Optional[str]
    script_content: Optional[str]
    duration: int
    status: str
    video_url: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------- Storyboard ----------

class StoryboardCreate(BaseModel):
    episode_id: int
    storyboard_number: int
    title: Optional[str] = None
    location: Optional[str] = None
    time: Optional[str] = None
    shot_type: Optional[str] = None
    angle: Optional[str] = None
    movement: Optional[str] = None
    action: Optional[str] = None
    dialogue: Optional[str] = None
    description: Optional[str] = None
    image_prompt: Optional[str] = None
    video_prompt: Optional[str] = None
    duration: int = 5

class StoryboardUpdate(BaseModel):
    title: Optional[str] = None
    location: Optional[str] = None
    time: Optional[str] = None
    shot_type: Optional[str] = None
    angle: Optional[str] = None
    movement: Optional[str] = None
    action: Optional[str] = None
    dialogue: Optional[str] = None
    description: Optional[str] = None
    image_prompt: Optional[str] = None
    video_prompt: Optional[str] = None
    bgm_prompt: Optional[str] = None
    sound_effect: Optional[str] = None
    duration: Optional[int] = None
    status: Optional[str] = None

class StoryboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    episode_id: int
    scene_id: Optional[int]
    storyboard_number: int
    title: Optional[str]
    location: Optional[str]
    time: Optional[str]
    shot_type: Optional[str]
    angle: Optional[str]
    movement: Optional[str]
    action: Optional[str]
    dialogue: Optional[str]
    description: Optional[str]
    image_prompt: Optional[str]
    video_prompt: Optional[str]
    bgm_prompt: Optional[str]
    sound_effect: Optional[str]
    duration: int
    composed_image: Optional[str]
    video_url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


# ---------- Scene ----------

class SceneCreate(BaseModel):
    drama_id: int
    episode_id: Optional[int] = None
    location: str
    time: str
    prompt: str
    storyboard_count: int = 1

class SceneUpdate(BaseModel):
    location: Optional[str] = None
    time: Optional[str] = None
    prompt: Optional[str] = None
    storyboard_count: Optional[int] = None
    status: Optional[str] = None

class SceneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    episode_id: Optional[int]
    location: str
    time: str
    prompt: str
    storyboard_count: int
    image_url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


# ---------- Prop ----------

class PropCreate(BaseModel):
    drama_id: int
    name: str
    type: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None

class PropUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    description: Optional[str] = None
    prompt: Optional[str] = None
    image_url: Optional[str] = None

class PropResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    name: str
    type: Optional[str]
    description: Optional[str]
    prompt: Optional[str]
    image_url: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------- Outline / Characters / Episodes / Progress ----------

class OutlineSave(BaseModel):
    outline: Optional[str] = None
    metadata: Optional[dict] = None

class SaveCharactersRequest(BaseModel):
    characters: list[CharacterCreate]

class SaveEpisodesRequest(BaseModel):
    episodes: list[EpisodeCreate]

class SaveProgressRequest(BaseModel):
    status: str
    progress: Optional[int] = None
