"""
Drama Blueprint — replaces FastAPI APIRouter.
All routes under /api/v1/dramas (registered in main.py with url_prefix).
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from api.deps import db_session, get_settings
from schemas.drama import (
    DramaCreate, DramaResponse, DramaUpdate,
    OutlineSave, SaveCharactersRequest, SaveEpisodesRequest, SaveProgressRequest,
)
from services.drama_service import DramaService

dramas_bp = Blueprint("dramas", __name__)


@dramas_bp.get("")
async def list_dramas():
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 20))
    async with db_session() as db:
        svc = DramaService(db)
        dramas, total = await svc.list_dramas(page, page_size)
    return jsonify({
        "data": [DramaResponse.model_validate(d).model_dump() for d in dramas],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@dramas_bp.post("")
async def create_drama():
    body = DramaCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = DramaService(db)
        drama = await svc.create_drama(body.model_dump(exclude_none=True))
    return jsonify(DramaResponse.model_validate(drama).model_dump()), 201


@dramas_bp.get("/stats")
async def get_stats():
    async with db_session() as db:
        svc = DramaService(db)
        stats = await svc.get_drama_stats()
    return jsonify(stats)


@dramas_bp.get("/<int:drama_id>")
async def get_drama(drama_id: int):
    async with db_session() as db:
        svc = DramaService(db)
        drama = await svc.get_drama(drama_id)
    if not drama:
        return jsonify({"error": "Drama not found"}), 404
    return jsonify(DramaResponse.model_validate(drama).model_dump())


@dramas_bp.put("/<int:drama_id>")
async def update_drama(drama_id: int):
    body = DramaUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = DramaService(db)
        drama = await svc.update_drama(drama_id, body.model_dump(exclude_none=True))
    if not drama:
        return jsonify({"error": "Drama not found"}), 404
    return jsonify(DramaResponse.model_validate(drama).model_dump())


@dramas_bp.delete("/<int:drama_id>")
async def delete_drama(drama_id: int):
    async with db_session() as db:
        svc = DramaService(db)
        deleted = await svc.delete_drama(drama_id)
    if not deleted:
        return jsonify({"error": "Drama not found"}), 404
    return "", 204


@dramas_bp.put("/<int:drama_id>/outline")
async def save_outline(drama_id: int):
    body = OutlineSave.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = DramaService(db)
        drama = await svc.update_drama(drama_id, body.model_dump(exclude_none=True))
    if not drama:
        return jsonify({"error": "Drama not found"}), 404
    return jsonify({"message": "Outline saved"})


@dramas_bp.get("/<int:drama_id>/characters")
async def get_characters(drama_id: int):
    async with db_session() as db:
        svc = DramaService(db)
        chars = await svc.get_characters(drama_id)
    return jsonify({"data": [c.__dict__ for c in chars]})


@dramas_bp.put("/<int:drama_id>/characters")
async def save_characters(drama_id: int):
    body = SaveCharactersRequest.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = DramaService(db)
        await svc.save_characters(drama_id, [c.model_dump() for c in body.characters])
    return jsonify({"message": "Characters saved"})


@dramas_bp.put("/<int:drama_id>/episodes")
async def save_episodes(drama_id: int):
    body = SaveEpisodesRequest.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = DramaService(db)
        await svc.save_episodes(drama_id, [e.model_dump() for e in body.episodes])
    return jsonify({"message": "Episodes saved"})


@dramas_bp.put("/<int:drama_id>/progress")
async def save_progress(drama_id: int):
    body = SaveProgressRequest.model_validate(request.get_json() or {})
    async with db_session() as db:
        svc = DramaService(db)
        await svc.update_drama(drama_id, {"status": body.status})
    return jsonify({"message": "Progress saved"})
