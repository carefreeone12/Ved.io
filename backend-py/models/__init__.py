"""
Models package — imports all models so SQLAlchemy metadata is fully populated.
"""
from models.ai_config import AIServiceConfig, AIServiceProvider
from models.asset import Asset, CharacterLibrary
from models.drama import Character, Drama, Episode, Prop, Scene, Storyboard
from models.image_generation import ImageGeneration, ImageGenerationStatus, ImageProvider, ImageType
from models.task import AsyncTask
from models.video_generation import VideoGeneration, VideoProvider, VideoStatus
from models.video_merge import FramePrompt, VideoMerge

__all__ = [
    # Drama group
    "Drama", "Character", "Episode", "Storyboard", "Scene", "Prop",
    # Generation
    "ImageGeneration", "ImageGenerationStatus", "ImageProvider", "ImageType",
    "VideoGeneration", "VideoProvider", "VideoStatus",
    "VideoMerge", "FramePrompt",
    # AI & Config
    "AIServiceConfig", "AIServiceProvider",
    # Assets & Library
    "Asset", "CharacterLibrary",
    # Tasks
    "AsyncTask",
]
