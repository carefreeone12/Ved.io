"""
Miscellaneous Blueprints — replaces FastAPI APIRouters for:
characters, character_library, scenes, storyboards, props, episodes,
generation, upload, audio, settings.
"""
from __future__ import annotations

import threading
from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy import select

from api.deps import db_session, get_storage
from models.asset import CharacterLibrary
from models.drama import Character, Episode, Prop, Scene, Storyboard
from models.video_merge import FramePrompt
from schemas.drama import (
    CharacterResponse, CharacterUpdate,
    PropCreate, PropResponse, PropUpdate,
    SceneCreate, SceneResponse, SceneUpdate,
    StoryboardCreate, StoryboardResponse, StoryboardUpdate,
)
from schemas.generation import (
    CharacterLibraryCreate, CharacterLibraryResponse,
    FramePromptResponse, LanguageSetting,
)
from services.ai_service import AIService
from services.script_service import ScriptGenerationService

# ============================================================
# Characters Blueprint
# ============================================================

characters_bp = Blueprint("characters", __name__)


@characters_bp.put("/<int:character_id>")
async def update_character(character_id: int):
    body = CharacterUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        result = await db.execute(select(Character).where(Character.id == character_id, Character.deleted_at == None))  # noqa: E711
        char = result.scalars().first()
        if not char:
            return jsonify({"error": "Character not found"}), 404
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(char, k, v)
        char.updated_at = datetime.utcnow()
        await db.flush()
        resp = CharacterResponse.model_validate(char).model_dump()
    return jsonify(resp)


@characters_bp.delete("/<int:character_id>")
async def delete_character(character_id: int):
    async with db_session() as db:
        result = await db.execute(select(Character).where(Character.id == character_id, Character.deleted_at == None))  # noqa: E711
        char = result.scalars().first()
        if not char:
            return jsonify({"error": "Character not found"}), 404
        char.deleted_at = datetime.utcnow()
    return "", 204


@characters_bp.post("/batch-generate-images")
async def batch_generate_character_images():
    drama_id = request.args.get("drama_id", type=int)
    return jsonify({"message": "Batch character image generation queued", "drama_id": drama_id})


@characters_bp.post("/<int:character_id>/generate-image")
async def generate_character_image(character_id: int):
    return jsonify({"message": "Character image generation queued", "character_id": character_id})


@characters_bp.post("/<int:character_id>/upload-image")
async def upload_character_image(character_id: int):
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    storage = get_storage()
    data = file.read()
    ext = (file.content_type or "image/png").split("/")[-1]
    url = await storage.save_bytes(data, "characters", ext)
    async with db_session() as db:
        result = await db.execute(select(Character).where(Character.id == character_id, Character.deleted_at == None))  # noqa: E711
        char = result.scalars().first()
        if char:
            char.image_url = url
    return jsonify({"url": url})


@characters_bp.put("/<int:character_id>/image")
async def update_character_image(character_id: int):
    image_url = request.args.get("image_url", "")
    async with db_session() as db:
        result = await db.execute(select(Character).where(Character.id == character_id, Character.deleted_at == None))  # noqa: E711
        char = result.scalars().first()
        if not char:
            return jsonify({"error": "Character not found"}), 404
        char.image_url = image_url
        await db.flush()
        resp = CharacterResponse.model_validate(char).model_dump()
    return jsonify(resp)


@characters_bp.put("/<int:character_id>/image-from-library")
async def apply_library_to_character(character_id: int):
    library_item_id = request.args.get("library_item_id", type=int)
    async with db_session() as db:
        char_result = await db.execute(select(Character).where(Character.id == character_id, Character.deleted_at == None))  # noqa: E711
        char = char_result.scalars().first()
        lib_result = await db.execute(select(CharacterLibrary).where(CharacterLibrary.id == library_item_id, CharacterLibrary.deleted_at == None))  # noqa: E711
        lib = lib_result.scalars().first()
        if not char or not lib:
            return jsonify({"error": "Character or library item not found"}), 404
        char.image_url = lib.image_url
        await db.flush()
        resp = CharacterResponse.model_validate(char).model_dump()
    return jsonify(resp)


@characters_bp.post("/<int:character_id>/add-to-library")
async def add_to_library(character_id: int):
    async with db_session() as db:
        result = await db.execute(select(Character).where(Character.id == character_id, Character.deleted_at == None))  # noqa: E711
        char = result.scalars().first()
        if not char:
            return jsonify({"error": "Character not found"}), 404
        lib_item = CharacterLibrary(name=char.name, description=char.description, image_url=char.image_url, local_path=char.local_path)
        db.add(lib_item)
        await db.flush()
        await db.refresh(lib_item)
        resp = CharacterLibraryResponse.model_validate(lib_item).model_dump()
    return jsonify(resp), 201


# ============================================================
# Character Library Blueprint
# ============================================================

character_library_bp = Blueprint("character_library", __name__)


@character_library_bp.get("")
async def list_library():
    async with db_session() as db:
        result = await db.execute(select(CharacterLibrary).where(CharacterLibrary.deleted_at == None))  # noqa: E711
        items = result.scalars().all()
    return jsonify([CharacterLibraryResponse.model_validate(i).model_dump() for i in items])


@character_library_bp.post("")
async def create_library_item():
    body = CharacterLibraryCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        item = CharacterLibrary(**body.model_dump())
        db.add(item)
        await db.flush()
        await db.refresh(item)
        resp = CharacterLibraryResponse.model_validate(item).model_dump()
    return jsonify(resp), 201


@character_library_bp.get("/<int:item_id>")
async def get_library_item(item_id: int):
    async with db_session() as db:
        result = await db.execute(select(CharacterLibrary).where(CharacterLibrary.id == item_id, CharacterLibrary.deleted_at == None))  # noqa: E711
        item = result.scalars().first()
    if not item:
        return jsonify({"error": "Library item not found"}), 404
    return jsonify(CharacterLibraryResponse.model_validate(item).model_dump())


@character_library_bp.delete("/<int:item_id>")
async def delete_library_item(item_id: int):
    async with db_session() as db:
        result = await db.execute(select(CharacterLibrary).where(CharacterLibrary.id == item_id, CharacterLibrary.deleted_at == None))  # noqa: E711
        item = result.scalars().first()
        if not item:
            return jsonify({"error": "Library item not found"}), 404
        item.deleted_at = datetime.utcnow()
    return "", 204


# ============================================================
# Props Blueprint
# ============================================================

props_bp = Blueprint("props", __name__)


@props_bp.post("")
async def create_prop():
    body = PropCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        prop = Prop(**body.model_dump())
        db.add(prop)
        await db.flush()
        await db.refresh(prop)
        resp = PropResponse.model_validate(prop).model_dump()
    return jsonify(resp), 201


@props_bp.put("/<int:prop_id>")
async def update_prop(prop_id: int):
    body = PropUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        result = await db.execute(select(Prop).where(Prop.id == prop_id, Prop.deleted_at == None))  # noqa: E711
        prop = result.scalars().first()
        if not prop:
            return jsonify({"error": "Prop not found"}), 404
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(prop, k, v)
        await db.flush()
        resp = PropResponse.model_validate(prop).model_dump()
    return jsonify(resp)


@props_bp.delete("/<int:prop_id>")
async def delete_prop(prop_id: int):
    async with db_session() as db:
        result = await db.execute(select(Prop).where(Prop.id == prop_id, Prop.deleted_at == None))  # noqa: E711
        prop = result.scalars().first()
        if not prop:
            return jsonify({"error": "Prop not found"}), 404
        prop.deleted_at = datetime.utcnow()
    return "", 204


@props_bp.post("/<int:prop_id>/generate")
async def generate_prop_image(prop_id: int):
    return jsonify({"message": "Prop image generation queued", "prop_id": prop_id})


# ============================================================
# Scenes Blueprint
# ============================================================

scenes_bp = Blueprint("scenes", __name__)


@scenes_bp.post("")
async def create_scene():
    body = SceneCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        scene = Scene(**body.model_dump())
        db.add(scene)
        await db.flush()
        await db.refresh(scene)
        resp = SceneResponse.model_validate(scene).model_dump()
    return jsonify(resp), 201


@scenes_bp.put("/<int:scene_id>")
async def update_scene(scene_id: int):
    body = SceneUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        result = await db.execute(select(Scene).where(Scene.id == scene_id, Scene.deleted_at == None))  # noqa: E711
        scene = result.scalars().first()
        if not scene:
            return jsonify({"error": "Scene not found"}), 404
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(scene, k, v)
        await db.flush()
        resp = SceneResponse.model_validate(scene).model_dump()
    return jsonify(resp)


@scenes_bp.put("/<int:scene_id>/prompt")
async def update_scene_prompt(scene_id: int):
    prompt = request.args.get("prompt", "")
    async with db_session() as db:
        result = await db.execute(select(Scene).where(Scene.id == scene_id, Scene.deleted_at == None))  # noqa: E711
        scene = result.scalars().first()
        if not scene:
            return jsonify({"error": "Scene not found"}), 404
        scene.prompt = prompt
        await db.flush()
        resp = SceneResponse.model_validate(scene).model_dump()
    return jsonify(resp)


@scenes_bp.delete("/<int:scene_id>")
async def delete_scene(scene_id: int):
    async with db_session() as db:
        result = await db.execute(select(Scene).where(Scene.id == scene_id, Scene.deleted_at == None))  # noqa: E711
        scene = result.scalars().first()
        if not scene:
            return jsonify({"error": "Scene not found"}), 404
        scene.deleted_at = datetime.utcnow()
    return "", 204


@scenes_bp.post("/generate-image")
async def generate_scene_image():
    scene_id = request.args.get("scene_id", type=int)
    return jsonify({"message": "Scene image generation queued", "scene_id": scene_id})


# ============================================================
# Storyboards Blueprint
# ============================================================

storyboards_bp = Blueprint("storyboards", __name__)


@storyboards_bp.get("/episode/<int:episode_id>/generate")
async def generate_storyboard(episode_id: int):
    return jsonify({"message": "Storyboard generation queued", "episode_id": episode_id})


@storyboards_bp.post("")
async def create_storyboard():
    body = StoryboardCreate.model_validate(request.get_json() or {})
    async with db_session() as db:
        sb = Storyboard(**body.model_dump())
        db.add(sb)
        await db.flush()
        await db.refresh(sb)
        resp = StoryboardResponse.model_validate(sb).model_dump()
    return jsonify(resp), 201


@storyboards_bp.put("/<int:storyboard_id>")
async def update_storyboard(storyboard_id: int):
    body = StoryboardUpdate.model_validate(request.get_json() or {})
    async with db_session() as db:
        result = await db.execute(select(Storyboard).where(Storyboard.id == storyboard_id, Storyboard.deleted_at == None))  # noqa: E711
        sb = result.scalars().first()
        if not sb:
            return jsonify({"error": "Storyboard not found"}), 404
        for k, v in body.model_dump(exclude_none=True).items():
            setattr(sb, k, v)
        await db.flush()
        resp = StoryboardResponse.model_validate(sb).model_dump()
    return jsonify(resp)


@storyboards_bp.delete("/<int:storyboard_id>")
async def delete_storyboard(storyboard_id: int):
    async with db_session() as db:
        result = await db.execute(select(Storyboard).where(Storyboard.id == storyboard_id, Storyboard.deleted_at == None))  # noqa: E711
        sb = result.scalars().first()
        if not sb:
            return jsonify({"error": "Storyboard not found"}), 404
        sb.deleted_at = datetime.utcnow()
    return "", 204


@storyboards_bp.get("/<int:storyboard_id>/frame-prompts")
async def get_frame_prompts(storyboard_id: int):
    async with db_session() as db:
        result = await db.execute(
            select(FramePrompt).where(FramePrompt.storyboard_id == storyboard_id, FramePrompt.deleted_at == None)  # noqa: E711
        )
        fps = result.scalars().all()
    return jsonify([FramePromptResponse.model_validate(fp).model_dump() for fp in fps])


@storyboards_bp.post("/<int:storyboard_id>/frame-prompt")
async def generate_frame_prompt(storyboard_id: int):
    return jsonify({"message": "Frame prompt generation queued", "storyboard_id": storyboard_id})


@storyboards_bp.post("/<int:storyboard_id>/props")
async def associate_props(storyboard_id: int):
    return jsonify({"message": "Props associated", "storyboard_id": storyboard_id})


# ============================================================
# Episodes Blueprint
# ============================================================

episodes_bp = Blueprint("episodes", __name__)


@episodes_bp.post("/<int:episode_id>/storyboards")
async def generate_episode_storyboards(episode_id: int):
    return jsonify({"message": "Storyboard generation queued", "episode_id": episode_id})


@episodes_bp.post("/<int:episode_id>/props/extract")
async def extract_props(episode_id: int):
    return jsonify({"message": "Prop extraction queued", "episode_id": episode_id})


@episodes_bp.post("/<int:episode_id>/characters/extract")
async def extract_characters(episode_id: int):
    return jsonify({"message": "Character extraction queued", "episode_id": episode_id})


@episodes_bp.get("/<int:episode_id>/storyboards")
async def get_storyboards_for_episode(episode_id: int):
    async with db_session() as db:
        result = await db.execute(
            select(Storyboard)
            .where(Storyboard.episode_id == episode_id, Storyboard.deleted_at == None)  # noqa: E711
            .order_by(Storyboard.storyboard_number)
        )
        sbs = result.scalars().all()
    return jsonify({"data": [StoryboardResponse.model_validate(sb).model_dump() for sb in sbs]})


@episodes_bp.post("/<int:episode_id>/finalize")
async def finalize_episode(episode_id: int):
    async with db_session() as db:
        result = await db.execute(select(Episode).where(Episode.id == episode_id, Episode.deleted_at == None))  # noqa: E711
        episode = result.scalars().first()
        if not episode:
            return jsonify({"error": "Episode not found"}), 404
        episode.status = "completed"
    return jsonify({"message": "Episode finalized", "episode_id": episode_id})


@episodes_bp.get("/<int:episode_id>/download")
async def download_episode_video(episode_id: int):
    async with db_session() as db:
        result = await db.execute(select(Episode).where(Episode.id == episode_id, Episode.deleted_at == None))  # noqa: E711
        episode = result.scalars().first()
    if not episode or not episode.video_url:
        return jsonify({"error": "Episode video not found"}), 404
    return jsonify({"video_url": episode.video_url})


# ============================================================
# Generation Blueprint (LLM-based character generation)
# ============================================================

generation_bp = Blueprint("generation", __name__)


@generation_bp.post("/characters")
async def generate_characters():
    drama_id = request.args.get("drama_id", type=int)
    count = request.args.get("count", 5, type=int)
    from models.drama import Drama
    async with db_session() as db:
        drama_result = await db.execute(select(Drama).where(Drama.id == drama_id, Drama.deleted_at == None))  # noqa: E711
        drama = drama_result.scalars().first()
        if not drama:
            return jsonify({"error": "Drama not found"}), 404
        ai_svc = AIService(db)
        svc = ScriptGenerationService(db, ai_svc)
        try:
            characters = await svc.generate_characters(
                drama_title=drama.title,
                outline=drama.description or "",
                genre=drama.genre,
                count=count,
            )
        except Exception as e:
            return jsonify({"error": f"Generation failed: {e}"}), 500
    return jsonify({"data": characters})


# ============================================================
# Upload Blueprint
# ============================================================

upload_bp = Blueprint("upload", __name__)


@upload_bp.post("/image")
async def upload_image():
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided"}), 400
    storage = get_storage()
    data = file.read()
    ext = (file.content_type or "image/png").split("/")[-1]
    url = await storage.save_bytes(data, "uploads", ext)
    return jsonify({"url": url, "filename": file.filename})


# ============================================================
# Audio Blueprint
# ============================================================

audio_bp = Blueprint("audio", __name__)


@audio_bp.post("/extract")
async def extract_audio():
    video_url = request.args.get("video_url", "")
    return jsonify({"message": "Audio extraction queued", "video_url": video_url})


@audio_bp.post("/extract/batch")
async def batch_extract_audio():
    episode_id = request.args.get("episode_id", type=int)
    return jsonify({"message": "Batch audio extraction queued", "episode_id": episode_id})


# ============================================================
# Settings Blueprint
# ============================================================

settings_bp = Blueprint("settings", __name__)

_language_store: dict[str, str] = {"language": "zh"}


@settings_bp.get("/language")
def get_language():
    return jsonify({"language": _language_store["language"]})


@settings_bp.put("/language")
def update_language():
    data = request.get_json() or {}
    lang = data.get("language", "zh")
    _language_store["language"] = lang
    return jsonify({"language": lang})
