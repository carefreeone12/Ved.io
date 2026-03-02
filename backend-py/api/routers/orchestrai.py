"""
OrchestrAI Flask Blueprint — Core orchestration API layer.

POST /api/v1/generate           — Start full 7-agent pipeline
GET  /api/v1/status/<job_id>    — Poll job status + critic scores
POST /api/v1/regenerate/<job_id>— Trigger selective scene regeneration
GET  /api/v1/download/<job_id>  — Download final video
GET  /api/v1/jobs               — List all jobs
"""
from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from api.deps import db_session, get_settings, get_storage
from orchestrator.full_pipeline import OrchestrAIPipeline
from orchestrator.job_manager import JobStage, SceneStatus, job_manager
from services.ai_service import AIService

orchestrai_bp = Blueprint("orchestrai", __name__)


def _get_pipeline(db) -> OrchestrAIPipeline:
    cfg = get_settings()
    storage = get_storage()
    ai_svc = AIService(db)
    return OrchestrAIPipeline(
        ai_service=ai_svc,
        storage=storage,
        score_threshold=cfg.app.critic_threshold if hasattr(cfg.app, "critic_threshold") else 7.5,
        max_iterations=cfg.app.max_iterations if hasattr(cfg.app, "max_iterations") else 3,
        use_polly=False,  # Set True when AWS is configured
    )


def _run_pipeline_bg(job_id: str, payload: dict) -> None:
    """Run the full pipeline in a background thread."""
    async def _async_run():
        async with db_session() as db:
            pipeline = _get_pipeline(db)
            await pipeline.run(
                job_id=job_id,
                raw_content=payload["content"],
                title=payload.get("title", ""),
                language=payload.get("language", "en"),
                tone=payload.get("tone", "neutral"),
                genre=payload.get("genre", "general"),
                character_descriptions=payload.get("characters", []),
            )

    asyncio.run(_async_run())


# ── POST /api/v1/generate ─────────────────────────────────────────────────────

@orchestrai_bp.post("/generate")
def generate():
    """
    Start the full OrchestrAI pipeline.

    Body (JSON or multipart):
      content    — raw text or transcript
      title      — optional video title
      language   — en, hi, te, ta, mr, bn
      tone       — neutral, educational, motivational, storytelling, conversational
      genre      — general, drama, news, education
    """
    # Support both JSON and form data (for file upload)
    if request.is_json:
        data = request.get_json() or {}
        content = data.get("content", "")
    else:
        content = request.form.get("content", "")
        # If file uploaded, read it as text
        file = request.files.get("file")
        if file:
            content = file.read().decode("utf-8", errors="ignore")

    if not content.strip():
        return jsonify({"error": "content is required"}), 400

    title = data.get("title", "") if request.is_json else request.form.get("title", "")
    language = (data.get("language", "en") if request.is_json else request.form.get("language", "en")).lower()
    tone = (data.get("tone", "neutral") if request.is_json else request.form.get("tone", "neutral")).lower()
    genre = (data.get("genre", "general") if request.is_json else request.form.get("genre", "general")).lower()

    # Create job state
    job = job_manager.create_job(
        title=title or "Untitled",
        language=language,
        tone=tone,
    )

    # Run pipeline in background thread
    payload = {"content": content, "title": title, "language": language, "tone": tone, "genre": genre}
    thread = threading.Thread(target=_run_pipeline_bg, args=(job.job_id, payload), daemon=True)
    thread.start()

    return jsonify({
        "job_id": job.job_id,
        "stage": job.stage.value,
        "message": "Pipeline started. Poll /api/v1/status/<job_id> for updates.",
    }), 202


# ── GET /api/v1/status/<job_id> ───────────────────────────────────────────────

@orchestrai_bp.get("/status/<job_id>")
def get_status(job_id: str):
    """Poll job status, stage, critic score, and per-scene details."""
    job = job_manager.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job.to_dict())


# ── POST /api/v1/regenerate/<job_id> ─────────────────────────────────────────

@orchestrai_bp.post("/regenerate/<job_id>")
def regenerate(job_id: str):
    """
    Manually trigger selective regeneration for specific scenes.

    Body:
      scene_ids — list of scene IDs to regenerate
    """
    job = job_manager.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404

    if job.stage not in (JobStage.DONE, JobStage.CRITIQUE, JobStage.FAILED):
        return jsonify({"error": f"Cannot regenerate while job is in stage: {job.stage.value}"}), 409

    data = request.get_json() or {}
    scene_ids = data.get("scene_ids", [])
    if not scene_ids:
        return jsonify({"error": "scene_ids list is required"}), 400

    # Reset affected scenes
    for sc in job.scenes:
        if sc.scene_id in scene_ids:
            sc.stage = "pending"
            sc.issue = ""

    # Run selective regeneration in background
    async def _async_regen():
        async with db_session() as db:
            from services.agents.asset_orchestrator import AssetOrchestratorAgent
            from services.agents.scene_planner import ScenePlannerAgent, VisualPlan
            ai_svc = AIService(db)
            storage = get_storage()
            orchestrator = AssetOrchestratorAgent(ai_svc)
            plans = [VisualPlan(**p) for p in job.visual_plans if p["scene_id"] in scene_ids]
            new_assets = await orchestrator.run_selective(plans, scene_ids)
            for a in new_assets:
                for sc in job.scenes:
                    if sc.scene_id == a.scene_id:
                        sc.image_url = a.image_url
                        sc.stage = "regenerated"
            job_manager.update_stage(job_id, JobStage.DONE)

    thread = threading.Thread(target=lambda: asyncio.run(_async_regen()), daemon=True)
    thread.start()

    return jsonify({"message": f"Regenerating {len(scene_ids)} scenes", "scene_ids": scene_ids}), 202


# ── GET /api/v1/download/<job_id> ─────────────────────────────────────────────

@orchestrai_bp.get("/download/<job_id>")
def download(job_id: str):
    """Download the final rendered video."""
    job = job_manager.get(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    if job.stage != JobStage.DONE:
        return jsonify({"error": "Video not ready yet", "stage": job.stage.value}), 425

    cfg = get_settings()
    video_path = Path(cfg.storage.local_path) / "jobs" / job_id / "draft.mp4"
    if not video_path.exists():
        return jsonify({"error": "Video file not found on disk"}), 404

    return send_file(
        str(video_path),
        as_attachment=True,
        download_name=f"{job.title or job_id}.mp4",
        mimetype="video/mp4",
    )


# ── GET /api/v1/jobs ──────────────────────────────────────────────────────────

@orchestrai_bp.get("/jobs")
def list_jobs():
    """List all jobs (for admin/debugging)."""
    jobs = job_manager.list_jobs()
    return jsonify({"jobs": jobs, "total": len(jobs)})
