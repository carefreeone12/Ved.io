"""
Unit tests for ScriptGenerationService.
Tests prompt building, JSON parsing, and character/storyboard generation with mocked LLM.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.script_service import ScriptGenerationService
from services.ai_service import AIService


def make_svc(mock_response: str) -> ScriptGenerationService:
    ai_svc = MagicMock(spec=AIService)
    ai_svc.generate_text = AsyncMock(return_value=mock_response)
    return ScriptGenerationService(db=MagicMock(), ai_service=ai_svc)


@pytest.mark.asyncio
async def test_generate_characters_valid_json():
    """Should parse LLM JSON response into list of character dicts."""
    characters = [
        {"name": "Hero", "role": "protagonist", "description": "Brave", "appearance": "Tall", "personality": "Bold", "voice_style": "Deep"},
        {"name": "Villain", "role": "antagonist", "description": "Evil", "appearance": "Dark", "personality": "Cunning", "voice_style": "Raspy"},
    ]
    svc = make_svc(json.dumps(characters))
    result = await svc.generate_characters("Test Drama", "A hero's journey")

    assert len(result) == 2
    assert result[0]["name"] == "Hero"
    assert result[1]["role"] == "antagonist"


@pytest.mark.asyncio
async def test_generate_characters_strips_markdown():
    """Should parse even when LLM wraps response in markdown code fences."""
    characters = [{"name": "Alice", "role": "protagonist", "description": "Kind", "appearance": "Fair", "personality": "Gentle", "voice_style": "Soft"}]
    svc = make_svc(f"```json\n{json.dumps(characters)}\n```")
    result = await svc.generate_characters("Test Drama", "A gentle story")

    assert len(result) == 1
    assert result[0]["name"] == "Alice"


@pytest.mark.asyncio
async def test_generate_characters_invalid_json_raises():
    """Should raise ValueError when LLM returns non-JSON."""
    svc = make_svc("Sorry, I cannot help with that.")
    with pytest.raises(ValueError, match="invalid JSON"):
        await svc.generate_characters("Test Drama", "Some outline")


@pytest.mark.asyncio
async def test_generate_storyboards_attaches_episode_id():
    """Generated storyboards must each have episode_id set."""
    boards = [
        {"storyboard_number": 1, "title": "Opening", "location": "Office", "time": "Day",
         "shot_type": "wide", "angle": "eye-level", "movement": "static",
         "action": "Character walks in", "dialogue": "", "atmosphere": "Tense",
         "image_prompt": "An office", "video_prompt": "A man walking", "duration": 5},
        {"storyboard_number": 2, "title": "Confrontation", "location": "Office", "time": "Day",
         "shot_type": "close-up", "angle": "low-angle", "movement": "pan",
         "action": "Two people argue", "dialogue": "Never!", "atmosphere": "Intense",
         "image_prompt": "Angry faces", "video_prompt": "Argument scene", "duration": 7},
    ]
    svc = make_svc(json.dumps(boards))
    result = await svc.generate_storyboards(episode_id=42, episode_title="Ep1", script_content="Script here")

    assert len(result) == 2
    assert all(b["episode_id"] == 42 for b in result)
    assert result[0]["storyboard_number"] == 1
    assert result[1]["storyboard_number"] == 2
