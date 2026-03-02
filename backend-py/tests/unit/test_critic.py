"""
Unit tests for the Critic Service (Iterative Feedback Generator).
Tests LLM-based scene scoring with mocked AI responses.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from services.critic import (
    CriticInput,
    CriticOutput,
    CriticService,
    DraftAsset,
    SceneIssue,
    SceneMetadata,
)
from services.ai_service import AIService


def make_critic_service(mock_response: str) -> CriticService:
    """Helper: create a CriticService with a mocked AI service."""
    ai_svc = MagicMock(spec=AIService)
    ai_svc.generate_text = AsyncMock(return_value=mock_response)
    return CriticService(ai_service=ai_svc, score_threshold=7.0)


def make_critic_input(n_scenes: int = 3) -> CriticInput:
    return CriticInput(
        script_json={"title": "Test Drama", "episode": 1},
        scene_metadata=[
            SceneMetadata(
                scene_id=i,
                location=f"Location {i}",
                time="Day",
                action=f"Action {i}",
                dialogue=None,
            )
            for i in range(1, n_scenes + 1)
        ],
        draft_assets=[
            DraftAsset(
                scene_id=i,
                image_url=f"http://example.com/image_{i}.jpg",
                prompt_used=f"Prompt for scene {i}",
            )
            for i in range(1, n_scenes + 1)
        ],
        timings=[5.0] * n_scenes,
    )


@pytest.mark.asyncio
async def test_critic_all_pass():
    """All scenes score above threshold — regenerate_list should be empty."""
    mock_response = json.dumps({
        "scene_scores": [8.5, 9.0, 8.0],
        "total_score": 8.5,
        "issues": [],
        "regenerate_list": [],
    })
    critic = make_critic_service(mock_response)
    result = await critic.evaluate(make_critic_input(3))

    assert result.total_score == 8.5
    assert len(result.regenerate_list) == 0
    assert result.scene_scores == [8.5, 9.0, 8.0]


@pytest.mark.asyncio
async def test_critic_some_fail():
    """Scenes below threshold should be in regenerate_list."""
    mock_response = json.dumps({
        "scene_scores": [9.0, 4.5, 8.0],
        "total_score": 7.17,
        "issues": [
            {
                "scene_id": 2,
                "reason": "Poor semantic alignment",
                "fix_suggestion": "Add more character detail",
                "alternative_prompt": "Cinematic close-up of character in distress",
            }
        ],
        "regenerate_list": [2],
    })
    critic = make_critic_service(mock_response)
    result = await critic.evaluate(make_critic_input(3))

    assert 2 in result.regenerate_list
    assert len(result.issues) == 1
    assert result.issues[0].scene_id == 2
    assert result.issues[0].alternative_prompt == "Cinematic close-up of character in distress"


@pytest.mark.asyncio
async def test_critic_below_threshold_not_in_list_gets_added():
    """Ensure critic service adds scenes below threshold even if LLM forgot them."""
    mock_response = json.dumps({
        "scene_scores": [9.0, 3.0, 8.5],  # scene 2 is 3.0, below 7.0 threshold
        "total_score": 6.83,
        "issues": [],
        "regenerate_list": [],  # LLM forgot to add it — we should auto-add
    })
    critic = make_critic_service(mock_response)
    result = await critic.evaluate(make_critic_input(3))

    # Scene index 1 (scene_id=2) has score 3.0 - should be auto-added
    assert 2 in result.regenerate_list


@pytest.mark.asyncio
async def test_critic_handles_ai_error():
    """When AI call fails, critic should return safe default (all fail)."""
    ai_svc = MagicMock(spec=AIService)
    ai_svc.generate_text = AsyncMock(side_effect=ValueError("AI service unavailable"))
    critic = CriticService(ai_service=ai_svc, score_threshold=7.0)

    result = await critic.evaluate(make_critic_input(2))

    assert result.total_score == 0.0
    assert len(result.regenerate_list) == 2  # All scenes flagged
    assert all(s == 0.0 for s in result.scene_scores)


@pytest.mark.asyncio
async def test_critic_strips_markdown_from_response():
    """Critic should handle responses wrapped in markdown code fences."""
    data = {
        "scene_scores": [8.0, 8.5],
        "total_score": 8.25,
        "issues": [],
        "regenerate_list": [],
    }
    # Simulate markdown-wrapped response
    mock_response = f"```json\n{json.dumps(data)}\n```"
    critic = make_critic_service(mock_response)
    result = await critic.evaluate(make_critic_input(2))

    assert result.total_score == 8.25
    assert len(result.regenerate_list) == 0
