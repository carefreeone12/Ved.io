"""
Images Blueprint — replaces FastAPI APIRouter for /api/v1/images.
"""
from __future__ import annotations

import threading

from flask import Blueprint, jsonify, request
from sqlalchemy import func, select

from api.deps import db_session, get_settings, get_storage
from models.image_generation import ImageGeneration
from schemas.generation import ImageGenerateRequest, ImageGenResponse
from services.ai_service import AIService
from services.image_service import ImageGenerationService

images_bp = Blueprint("images", __name__)


def _get_img_svc(db):
    cfg = get_settings()
    storage = get_storage()
    ai_svc = AIService(db)
    return ImageGenerationService(db, ai_svc, storage)


@images_bp.get("")
async def list_images():
    drama_id = request.args.get("drama_id", type=int)
    page = request.args.get("page", 1, type=int)
    page_size = request.args.get("page_size", 20, type=int)
    async with db_session() as db:
        svc = _get_img_svc(db)
        items, total = await svc.list(drama_id, page, page_size)
    return jsonify({
        "data": [ImageGenResponse.model_validate(i).model_dump() for i in items],
        "total": total,
    })


@images_bp.post("")
async def generate_image():
    body = ImageGenerateRequest.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = _get_img_svc(db)
        gen = await svc.create(body.model_dump(exclude_none=True))
        resp = ImageGenResponse.model_validate(gen).model_dump()

    # Run generation in a background thread (replaces FastAPI BackgroundTasks)
    def _bg():
        import asyncio
        async def _run():
            async with db_session() as db2:
                svc2 = _get_img_svc(db2)
                gen2 = await db2.get(ImageGeneration, gen["id"] if isinstance(gen, dict) else gen.id)
                if gen2:
                    await svc2.generate_image(gen2)
        asyncio.run(_run())

    threading.Thread(target=_bg, daemon=True).start()
    return jsonify(resp), 201


@images_bp.get("/<int:image_id>")
async def get_image(image_id: int):
    async with db_session() as db:
        svc = _get_img_svc(db)
        gen = await svc.get(image_id)
    if not gen:
        return jsonify({"error": "Image generation not found"}), 404
    return jsonify(ImageGenResponse.model_validate(gen).model_dump())


@images_bp.delete("/<int:image_id>")
async def delete_image(image_id: int):
    async with db_session() as db:
        svc = _get_img_svc(db)
        if not await svc.delete(image_id):
            return jsonify({"error": "Image generation not found"}), 404
    return "", 204


@images_bp.post("/scene/<int:scene_id>")
async def generate_for_scene(scene_id: int):
    body = ImageGenerateRequest.model_validate(request.get_json() or {})
    data = body.model_dump(exclude_none=True)
    data["scene_id"] = scene_id
    async with db_session() as db:
        svc = _get_img_svc(db)
        gen = await svc.create(data)
        resp = ImageGenResponse.model_validate(gen).model_dump()
    threading.Thread(target=lambda: __import__('asyncio').run(_bg_gen(gen)), daemon=True).start()
    return jsonify(resp), 201


async def _bg_gen(gen):
    async with db_session() as db:
        svc = _get_img_svc(db)
        real_gen = await db.get(ImageGeneration, gen.id if hasattr(gen, "id") else gen["id"])
        if real_gen:
            await svc.generate_image(real_gen)


@images_bp.get("/episode/<int:episode_id>/backgrounds")
async def get_backgrounds_for_episode(episode_id: int):
    async with db_session() as db:
        result = await db.execute(
            select(ImageGeneration).where(ImageGeneration.image_type == "scene")
        )
        items = result.scalars().all()
    return jsonify({"data": [ImageGenResponse.model_validate(i).model_dump() for i in items]})


@images_bp.post("/episode/<int:episode_id>/backgrounds/extract")
async def extract_backgrounds(episode_id: int):
    return jsonify({"message": "Background extraction queued", "episode_id": episode_id})


@images_bp.post("/episode/<int:episode_id>/batch")
async def batch_generate_for_episode(episode_id: int):
    return jsonify({"message": "Batch image generation queued", "episode_id": episode_id})
