"""
AI Config Blueprint — replaces FastAPI APIRouter for /api/v1/ai-configs.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from api.deps import db_session
from core.ai_clients.openai_client import OpenAIClient
from models.ai_config import AIServiceConfig
from schemas.generation import AIConfigCreate, AIConfigResponse, AIConfigUpdate, TestConnectionRequest

ai_configs_bp = Blueprint("ai_configs", __name__)


@ai_configs_bp.get("")
async def list_configs():
    async with db_session() as db:
        result = await db.execute(select(AIServiceConfig).order_by(AIServiceConfig.priority.desc()))
        configs = result.scalars().all()
    return jsonify([AIConfigResponse.model_validate(c).model_dump() for c in configs])


@ai_configs_bp.post("")
async def create_config():
    body = AIConfigCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        config = AIServiceConfig(**body.model_dump())
        db.add(config)
        await db.flush()
        await db.refresh(config)
        resp = AIConfigResponse.model_validate(config).model_dump()
    return jsonify(resp), 201


@ai_configs_bp.post("/test")
async def test_connection():
    body = TestConnectionRequest.model_validate(request.get_json() or {})
    models = body.model if body.model else [""]
    client = OpenAIClient(
        base_url=body.base_url,
        api_key=body.api_key,
        model=models[0],
        endpoint=body.endpoint or "/v1/chat/completions",
    )
    ok = await client.test_connection()
    if not ok:
        return jsonify({"error": "Connection test failed"}), 400
    return jsonify({"message": "Connection successful"})


@ai_configs_bp.get("/<int:config_id>")
async def get_config(config_id: int):
    async with db_session() as db:
        result = await db.execute(select(AIServiceConfig).where(AIServiceConfig.id == config_id))
        config = result.scalars().first()
    if not config:
        return jsonify({"error": "Config not found"}), 404
    return jsonify(AIConfigResponse.model_validate(config).model_dump())


@ai_configs_bp.put("/<int:config_id>")
async def update_config(config_id: int):
    body = AIConfigUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        result = await db.execute(select(AIServiceConfig).where(AIServiceConfig.id == config_id))
        config = result.scalars().first()
        if not config:
            return jsonify({"error": "Config not found"}), 404
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(config, k, v)
        await db.flush()
        resp = AIConfigResponse.model_validate(config).model_dump()
    return jsonify(resp)


@ai_configs_bp.delete("/<int:config_id>")
async def delete_config(config_id: int):
    async with db_session() as db:
        result = await db.execute(select(AIServiceConfig).where(AIServiceConfig.id == config_id))
        config = result.scalars().first()
        if not config:
            return jsonify({"error": "Config not found"}), 404
        await db.delete(config)
    return "", 204
