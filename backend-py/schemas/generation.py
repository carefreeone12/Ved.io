"""
Pydantic v2 schemas for AI config, Image/Video generation, VideoMerge, Assets.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


# ---------- AI Config ----------

class AIConfigCreate(BaseModel):
    service_type: str
    provider: str = ""
    name: str
    base_url: str
    api_key: str
    model: list[str] = []
    endpoint: str = ""
    query_endpoint: str = ""
    priority: int = 0
    is_default: bool = False
    is_active: bool = True
    settings: Optional[str] = None

class AIConfigUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[list[str]] = None
    endpoint: Optional[str] = None
    query_endpoint: Optional[str] = None
    priority: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    settings: Optional[str] = None

class AIConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    service_type: str
    provider: str
    name: str
    base_url: str
    api_key: str
    model: Optional[list[str]]
    endpoint: str
    query_endpoint: str
    priority: int
    is_default: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime

class TestConnectionRequest(BaseModel):
    service_type: str
    provider: str
    base_url: str
    api_key: str
    model: list[str] = []
    endpoint: str = ""


# ---------- Image Generation ----------

class ImageGenerateRequest(BaseModel):
    drama_id: int
    storyboard_id: Optional[int] = None
    scene_id: Optional[int] = None
    character_id: Optional[int] = None
    prop_id: Optional[int] = None
    image_type: str = "storyboard"
    provider: str = "openai"
    prompt: str
    negative_prompt: Optional[str] = None
    model: str = ""
    size: str = "1024x1024"
    quality: str = "standard"
    style: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None

class ImageGenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    storyboard_id: Optional[int]
    scene_id: Optional[int]
    character_id: Optional[int]
    prop_id: Optional[int]
    image_type: str
    provider: str
    prompt: str
    model: str
    size: str
    quality: str
    status: str
    image_url: Optional[str]
    local_path: Optional[str]
    task_id: Optional[str]
    error_msg: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


# ---------- Video Generation ----------

class VideoGenerateRequest(BaseModel):
    drama_id: int
    storyboard_id: Optional[int] = None
    provider: str = "doubao"
    prompt: str
    model: str = ""
    image_gen_id: Optional[int] = None
    reference_mode: Optional[str] = None
    image_url: Optional[str] = None
    first_frame_url: Optional[str] = None
    last_frame_url: Optional[str] = None
    duration: Optional[int] = None
    fps: Optional[int] = None
    resolution: Optional[str] = None
    aspect_ratio: Optional[str] = None

class VideoGenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    storyboard_id: Optional[int]
    provider: str
    prompt: str
    model: str
    image_url: Optional[str]
    status: str
    video_url: Optional[str]
    task_id: Optional[str]
    error_msg: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


# ---------- Video Merge ----------

class VideoMergeRequest(BaseModel):
    drama_id: int
    episode_id: Optional[int] = None
    video_ids: list[int]

class VideoMergeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    episode_id: Optional[int]
    status: str
    output_url: Optional[str]
    error_msg: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------- Asset ----------

class AssetCreate(BaseModel):
    drama_id: int
    type: str
    name: str
    url: Optional[str] = None
    metadata: Optional[dict] = None

class AssetUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    url: Optional[str] = None
    metadata: Optional[dict] = None

class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    drama_id: int
    type: str
    name: str
    url: Optional[str]
    local_path: Optional[str]
    created_at: datetime
    updated_at: datetime


# ---------- Task ----------

class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    type: str
    status: str
    progress: int
    message: str
    error: str
    result: Optional[str]
    resource_id: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]


# ---------- Character Library ----------

class CharacterLibraryCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[list] = None

class CharacterLibraryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str]
    image_url: Optional[str]
    tags: Optional[Any]
    created_at: datetime
    updated_at: datetime


# ---------- Frame Prompt ----------

class FramePromptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    storyboard_id: int
    frame_type: Optional[str]
    content: str
    prompt: Optional[str]
    image_url: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime


# ---------- Settings ----------

class LanguageSetting(BaseModel):
    language: str  # zh or en
