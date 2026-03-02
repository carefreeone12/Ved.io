"""
Script generation service — LLM-driven character and storyboard script generation.
Maps to Go application/services/script_generation_service.go.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services.ai_service import AIService

logger = logging.getLogger(__name__)

GENERATE_CHARACTERS_SYSTEM_PROMPT = """You are a professional screenplay writer and character designer.
Generate detailed character profiles for a drama based on the provided story outline.
Return a JSON array of character objects with these required fields:
- name: character name (string)
- role: character role (protagonist/antagonist/supporting)
- description: character backstory (string)
- appearance: physical description (string)
- personality: personality traits (string)
- voice_style: speaking style description (string)
Do NOT include any extra text or markdown, only return the raw JSON array."""

GENERATE_STORYBOARD_SYSTEM_PROMPT = """You are a professional film director and storyboard artist.
Generate detailed storyboard shots for a drama episode based on the provided script.
Return a JSON array of storyboard objects with these required fields:
- storyboard_number: sequential number starting from 1 (integer)
- title: shot title (string)
- location: shooting location (string)
- time: time of day (string)
- shot_type: camera shot type (close-up/medium/wide/extreme-close-up)
- angle: camera angle (eye-level/low-angle/high-angle/dutch-angle)
- movement: camera movement (static/pan/tilt/zoom/tracking)
- action: what happens in this shot (string)
- dialogue: character dialogue if any (string)
- atmosphere: overall mood and atmosphere (string)
- image_prompt: detailed AI image generation prompt (string)
- video_prompt: AI video generation prompt (string)
- duration: shot duration in seconds (integer, default 5)
Do NOT include any extra text or markdown, only return the raw JSON array."""


class ScriptGenerationService:

    def __init__(self, db: AsyncSession, ai_service: AIService) -> None:
        self.db = db
        self.ai_service = ai_service

    async def generate_characters(
        self,
        drama_title: str,
        outline: str,
        genre: Optional[str] = None,
        count: int = 5,
        language: str = "en",
    ) -> list[dict]:
        """Generate character profiles using LLM."""
        prompt = f"""Drama title: {drama_title}
Genre: {genre or 'General'}
Story outline:
{outline}

Please generate {count} characters for this drama."""

        response = await self.ai_service.generate_text(
            prompt=prompt,
            system_prompt=GENERATE_CHARACTERS_SYSTEM_PROMPT,
            temperature=0.8,
        )
        import json_repair
        try:
            data = json_repair.loads(response)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.error(f"Failed to parse character JSON: {e}")
            raise ValueError(f"AI returned invalid JSON: {str(e)}")

    async def generate_storyboards(
        self,
        episode_id: int,
        episode_title: str,
        script_content: str,
        storyboard_count: int = 10,
        language: str = "en",
    ) -> list[dict]:
        """Generate storyboard shots from episode script using LLM."""
        prompt = f"""Episode title: {episode_title}
Target number of shots: {storyboard_count}

Episode script:
{script_content}

Generate exactly {storyboard_count} storyboard shots for this episode."""

        response = await self.ai_service.generate_text(
            prompt=prompt,
            system_prompt=GENERATE_STORYBOARD_SYSTEM_PROMPT,
            temperature=0.7,
            max_tokens=8000,
        )
        import json_repair
        try:
            response = response.strip()
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
            boards = json_repair.loads(response)
            if not isinstance(boards, list):
                boards = []
            for i, b in enumerate(boards):
                b["episode_id"] = episode_id
                b["storyboard_number"] = b.get("storyboard_number", i + 1)
            return boards
        except Exception as e:
            logger.error(f"Failed to parse storyboard JSON: {e}")
            raise ValueError(f"AI returned invalid JSON: {str(e)}")
