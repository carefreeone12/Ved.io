"""
Integration smoke test: drama creation + storyboard generation + critic evaluation loop.
Uses mocked AI providers to avoid real API calls.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from main import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "app" in data
    assert "version" in data


@pytest.mark.asyncio
async def test_openapi_spec(client: AsyncClient):
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert "paths" in spec
    # Verify key routes are present
    assert "/api/v1/dramas" in spec["paths"]
    assert "/api/v1/ai-configs" in spec["paths"]
    assert "/api/v1/images" in spec["paths"]
    assert "/api/v1/videos" in spec["paths"]


@pytest.mark.asyncio
async def test_create_and_get_drama(client: AsyncClient):
    """Create a drama and fetch it back."""
    create_resp = await client.post("/api/v1/dramas", json={
        "title": "Test Drama",
        "description": "A test drama",
        "style": "realistic",
    })
    assert create_resp.status_code == 201
    drama = create_resp.json()
    assert drama["title"] == "Test Drama"
    assert "id" in drama

    drama_id = drama["id"]
    get_resp = await client.get(f"/api/v1/dramas/{drama_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == drama_id


@pytest.mark.asyncio
async def test_drama_stats(client: AsyncClient):
    resp = await client.get("/api/v1/dramas/stats")
    assert resp.status_code == 200
    data = resp.json()
    assert "total" in data
    assert "draft" in data


@pytest.mark.asyncio
async def test_critic_pipeline_integration():
    """Smoke test: critic evaluates scenes and flags low-score ones for regen."""
    from services.critic import CriticService, CriticInput, SceneMetadata, DraftAsset
    from orchestrator.pipeline import IterativePipeline
    from services.image_service import ImageGenerationService

    # Mock critic returning 1 low + 2 high scores
    critic_responses = [
        json.dumps({
            "scene_scores": [4.0, 9.0, 9.5],
            "total_score": 7.5,
            "issues": [{"scene_id": 1, "reason": "Misaligned", "fix_suggestion": "Better prompt", "alternative_prompt": "Cinematic wide shot"}],
            "regenerate_list": [1],
        }),
        # Second iteration: all pass
        json.dumps({
            "scene_scores": [8.5, 9.0, 9.5],
            "total_score": 9.0,
            "issues": [],
            "regenerate_list": [],
        }),
    ]
    call_count = 0

    async def mock_generate_text(*args, **kwargs) -> str:
        nonlocal call_count
        resp = critic_responses[min(call_count, len(critic_responses) - 1)]
        call_count += 1
        return resp

    ai_svc = MagicMock()
    ai_svc.generate_text = AsyncMock(side_effect=mock_generate_text)

    critic = CriticService(ai_service=ai_svc, score_threshold=8.0)
    img_svc = MagicMock(spec=ImageGenerationService)

    pipeline = IterativePipeline(
        critic_service=critic,
        image_service=img_svc,
        score_threshold=8.0,
        max_iterations=3,
    )

    result = await pipeline.run(
        script_json={"title": "Test"},
        scene_metadata=[
            SceneMetadata(scene_id=i, location=f"Loc {i}", time="Day")
            for i in range(1, 4)
        ],
        draft_assets=[
            DraftAsset(scene_id=i, image_url=f"http://img/{i}.jpg", prompt_used=f"Prompt {i}")
            for i in range(1, 4)
        ],
    )

    assert result.passed is True
    assert result.final_score >= 8.0
    assert result.total_iterations == 2   # Needed 2 iterations to pass
