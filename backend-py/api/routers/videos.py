"""
Videos, Video Merges, Tasks, Assets Blueprints.
Replaces FastAPI APIRouters for /api/v1/videos, /video-merges, /tasks, /assets.
"""
from __future__ import annotations

import threading
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from api.deps import db_session, get_storage
from models.asset import Asset
from models.task import AsyncTask
from models.video_generation import VideoGeneration
from models.video_merge import VideoMerge
from schemas.generation import (
    AssetCreate, AssetResponse, AssetUpdate,
    TaskResponse, VideoGenerateRequest, VideoGenResponse,
    VideoMergeRequest, VideoMergeResponse,
)
from services.task_service import TaskService
from services.video_merge_service import VideoMergeService

# ============================================================
# Videos Blueprint
# ============================================================

videos_bp = Blueprint("videos", __name__)


@videos_bp.get("")
async def list_videos():
    drama_id = request.args.get("drama_id", type=int)
    async with db_session() as db:
        query = select(VideoGeneration)
        if drama_id:
            query = query.where(VideoGeneration.drama_id == drama_id)
        result = await db.execute(query.order_by(VideoGeneration.created_at.desc()))
        items = result.scalars().all()
    return jsonify({"data": [VideoGenResponse.model_validate(v).model_dump() for v in items]})


@videos_bp.post("")
async def generate_video():
    body = VideoGenerateRequest.model_validate(request.get_json() or {})
    async with db_session() as db:
        gen = VideoGeneration(**body.model_dump(exclude_none=True), status="pending")
        db.add(gen)
        await db.flush()
        await db.refresh(gen)
        resp = VideoGenResponse.model_validate(gen).model_dump()
    return jsonify(resp), 201


@videos_bp.get("/<int:video_id>")
async def get_video(video_id: int):
    async with db_session() as db:
        result = await db.execute(select(VideoGeneration).where(VideoGeneration.id == video_id))
        gen = result.scalars().first()
    if not gen:
        return jsonify({"error": "Video generation not found"}), 404
    return jsonify(VideoGenResponse.model_validate(gen).model_dump())


@videos_bp.delete("/<int:video_id>")
async def delete_video(video_id: int):
    async with db_session() as db:
        result = await db.execute(select(VideoGeneration).where(VideoGeneration.id == video_id))
        gen = result.scalars().first()
        if not gen:
            return jsonify({"error": "Video not found"}), 404
        await db.delete(gen)
    return "", 204


@videos_bp.post("/image/<int:image_gen_id>")
async def generate_from_image(image_gen_id: int):
    body = VideoGenerateRequest.model_validate(request.get_json() or {})
    data = body.model_dump(exclude_none=True)
    data["image_gen_id"] = image_gen_id
    async with db_session() as db:
        gen = VideoGeneration(**data, status="pending")
        db.add(gen)
        await db.flush()
        await db.refresh(gen)
        resp = VideoGenResponse.model_validate(gen).model_dump()
    return jsonify(resp), 201


@videos_bp.post("/episode/<int:episode_id>/batch")
async def batch_generate_videos(episode_id: int):
    return jsonify({"message": "Batch video generation queued", "episode_id": episode_id})


# ============================================================
# Video Merges Blueprint
# ============================================================

video_merges_bp = Blueprint("video_merges", __name__)


@video_merges_bp.get("")
async def list_merges():
    drama_id = request.args.get("drama_id", type=int)
    async with db_session() as db:
        query = select(VideoMerge)
        if drama_id:
            query = query.where(VideoMerge.drama_id == drama_id)
        result = await db.execute(query.order_by(VideoMerge.created_at.desc()))
        items = result.scalars().all()
    return jsonify({"data": [VideoMergeResponse.model_validate(m).model_dump() for m in items]})


@video_merges_bp.post("")
async def merge_videos():
    body = VideoMergeRequest.model_validate(request.get_json() or {})
    async with db_session() as db:
        storage = get_storage()
        merge = VideoMerge(
            drama_id=body.drama_id,
            episode_id=body.episode_id,
            video_ids=body.video_ids,
            status="pending",
        )
        db.add(merge)
        await db.flush()
        await db.refresh(merge)
        resp = VideoMergeResponse.model_validate(merge).model_dump()
        merge_id = merge.id
        video_ids = body.video_ids

    def _bg_merge():
        import asyncio
        async def _run():
            async with db_session() as db2:
                result = await db2.execute(select(VideoMerge).where(VideoMerge.id == merge_id))
                m = result.scalars().first()
                if m:
                    svc = VideoMergeService(db2, get_storage())
                    await svc.merge_videos(m, video_ids)
        asyncio.run(_run())

    threading.Thread(target=_bg_merge, daemon=True).start()
    return jsonify(resp), 201


@video_merges_bp.get("/<int:merge_id>")
async def get_merge(merge_id: int):
    async with db_session() as db:
        result = await db.execute(select(VideoMerge).where(VideoMerge.id == merge_id))
        merge = result.scalars().first()
    if not merge:
        return jsonify({"error": "Video merge not found"}), 404
    return jsonify(VideoMergeResponse.model_validate(merge).model_dump())


@video_merges_bp.delete("/<int:merge_id>")
async def delete_merge(merge_id: int):
    async with db_session() as db:
        result = await db.execute(select(VideoMerge).where(VideoMerge.id == merge_id))
        merge = result.scalars().first()
        if not merge:
            return jsonify({"error": "Video merge not found"}), 404
        await db.delete(merge)
    return "", 204


# ============================================================
# Tasks Blueprint
# ============================================================

tasks_bp = Blueprint("tasks", __name__)


@tasks_bp.get("/<string:task_id>")
async def get_task(task_id: str):
    async with db_session() as db:
        svc = TaskService(db)
        task = await svc.get_task(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(TaskResponse.model_validate(task).model_dump())


@tasks_bp.get("")
async def get_resource_tasks():
    resource_id = request.args.get("resource_id", "")
    async with db_session() as db:
        svc = TaskService(db)
        tasks = await svc.get_resource_tasks(resource_id)
    return jsonify([TaskResponse.model_validate(t).model_dump() for t in tasks])


# ============================================================
# Assets Blueprint
# ============================================================

assets_bp = Blueprint("assets", __name__)


@assets_bp.get("")
async def list_assets():
    drama_id = request.args.get("drama_id", type=int)
    async with db_session() as db:
        query = select(Asset).where(Asset.deleted_at == None)  # noqa: E711
        if drama_id:
            query = query.where(Asset.drama_id == drama_id)
        result = await db.execute(query)
        items = result.scalars().all()
    return jsonify([AssetResponse.model_validate(a).model_dump() for a in items])


@assets_bp.post("")
async def create_asset():
    body = AssetCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        asset = Asset(**body.model_dump())
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        resp = AssetResponse.model_validate(asset).model_dump()
    return jsonify(resp), 201


@assets_bp.get("/<int:asset_id>")
async def get_asset(asset_id: int):
    async with db_session() as db:
        result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.deleted_at == None))  # noqa: E711
        asset = result.scalars().first()
    if not asset:
        return jsonify({"error": "Asset not found"}), 404
    return jsonify(AssetResponse.model_validate(asset).model_dump())


@assets_bp.put("/<int:asset_id>")
async def update_asset(asset_id: int):
    body = AssetUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.deleted_at == None))  # noqa: E711
        asset = result.scalars().first()
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(asset, k, v)
        await db.flush()
        resp = AssetResponse.model_validate(asset).model_dump()
    return jsonify(resp)


@assets_bp.delete("/<int:asset_id>")
async def delete_asset(asset_id: int):
    async with db_session() as db:
        result = await db.execute(select(Asset).where(Asset.id == asset_id, Asset.deleted_at == None))  # noqa: E711
        asset = result.scalars().first()
        if not asset:
            return jsonify({"error": "Asset not found"}), 404
        asset.deleted_at = datetime.utcnow()
    return "", 204


@assets_bp.post("/import/image/<int:image_gen_id>")
async def import_from_image(image_gen_id: int):
    drama_id = request.args.get("drama_id", type=int)
    from models.image_generation import ImageGeneration
    async with db_session() as db:
        result = await db.execute(select(ImageGeneration).where(ImageGeneration.id == image_gen_id))
        img = result.scalars().first()
        if not img:
            return jsonify({"error": "Image generation not found"}), 404
        asset = Asset(drama_id=drama_id, type="image", name=f"Image #{image_gen_id}", url=img.image_url, local_path=img.local_path)
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        resp = AssetResponse.model_validate(asset).model_dump()
    return jsonify(resp), 201


@assets_bp.post("/import/video/<int:video_gen_id>")
async def import_from_video(video_gen_id: int):
    drama_id = request.args.get("drama_id", type=int)
    async with db_session() as db:
        result = await db.execute(select(VideoGeneration).where(VideoGeneration.id == video_gen_id))
        vid = result.scalars().first()
        if not vid:
            return jsonify({"error": "Video generation not found"}), 404
        asset = Asset(drama_id=drama_id, type="video", name=f"Video #{video_gen_id}", url=vid.video_url, local_path=vid.local_path)
        db.add(asset)
        await db.flush()
        await db.refresh(asset)
        resp = AssetResponse.model_validate(asset).model_dump()
    return jsonify(resp), 201
