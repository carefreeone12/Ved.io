"""
Flask Application factory and entry point.
Replaces FastAPI + uvicorn with Flask + gunicorn.
Maps to original main.py (FastAPI version).
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from core.config import settings as get_settings
from core.database import close_db, init_db
from core.logger import configure_logging, get_logger

# --- Import all Blueprints ---
from api.routers.orchestrai import orchestrai_bp
from api.routers.dramas import dramas_bp
from api.routers.ai_configs import ai_configs_bp
from api.routers.images import images_bp
from api.routers.videos import videos_bp, video_merges_bp, tasks_bp, assets_bp
from api.routers.setup import setup_bp
from api.routers.misc import (
    characters_bp,
    character_library_bp,
    props_bp,
    scenes_bp,
    storyboards_bp,
    episodes_bp,
    generation_bp,
    upload_bp,
    audio_bp,
    settings_bp,
)

logger = get_logger(__name__)


def create_app() -> Flask:
    """Create and configure the Flask application."""
    cfg = get_settings()
    configure_logging(cfg.app.debug)

    template_dir = Path(__file__).parent / "templates"
    app = Flask(__name__, static_folder=None, template_folder=str(template_dir))
    app.config["DEBUG"] = cfg.app.debug
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB upload limit

    # ---- CORS (replaces FastAPI CORSMiddleware) ----
    CORS(app, origins=cfg.server.cors_origins, supports_credentials=True)

    # ---- Rate Limiter (replaces slowapi) ----
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        default_limits=["200 per minute"],
        storage_uri="memory://",
    )

    with app.app_context():
        try:
            asyncio.run(init_db(cfg.database))
            logger.info("Database connected and migrated")
        except Exception as e:
            logger.warning(f"DB init skipped (may already exist): {e}")

        storage_dir = Path(cfg.storage.local_path)
        storage_dir.mkdir(parents=True, exist_ok=True)
        (storage_dir / "jobs").mkdir(exist_ok=True)
        logger.info(f"Storage ready: {cfg.storage.local_path}")

        # ---- First-run AI config check ----
        from services.ai_service import AIService
        if AIService.is_configured():
            summary = AIService.get_env_config_summary()
            for p in summary.get("providers", []):
                logger.info(f"AI provider ready: {p['name']} ({p.get('model', '')})")
        else:
            logger.warning(
                "\n" + "="*60 +
                "\n  ⚠️  NO AI API KEY CONFIGURED" +
                "\n  Open http://localhost:5678/setup to add your API key." +
                "\n  You can use a FREE Gemini key from aistudio.google.com" +
                "\n" + "="*60
            )

    # ---- Health Check ----
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "app": cfg.app.name, "version": cfg.app.version})

    # ---- Flask UI routes (Jinja2) ----
    @app.get("/")
    def index_page():
        from services.ai_service import AIService
        configured = AIService.is_configured()
        return render_template("index.html", ai_configured=configured)

    @app.get("/setup")
    def setup_page_redirect():
        return render_template("setup.html")

    @app.get("/job/<job_id>")
    def job_status_page(job_id: str):
        return render_template("status.html", job_id=job_id)

    # ---- Register all Blueprints under /api/v1 ----
    api_prefix = "/api/v1"
    app.register_blueprint(orchestrai_bp,        url_prefix=f"{api_prefix}")
    app.register_blueprint(setup_bp,             url_prefix="/setup")
    app.register_blueprint(dramas_bp,            url_prefix=f"{api_prefix}/dramas")
    app.register_blueprint(ai_configs_bp,        url_prefix=f"{api_prefix}/ai-configs")
    app.register_blueprint(images_bp,            url_prefix=f"{api_prefix}/images")
    app.register_blueprint(videos_bp,            url_prefix=f"{api_prefix}/videos")
    app.register_blueprint(video_merges_bp,      url_prefix=f"{api_prefix}/video-merges")
    app.register_blueprint(tasks_bp,             url_prefix=f"{api_prefix}/tasks")
    app.register_blueprint(assets_bp,            url_prefix=f"{api_prefix}/assets")
    app.register_blueprint(characters_bp,        url_prefix=f"{api_prefix}/characters")
    app.register_blueprint(character_library_bp, url_prefix=f"{api_prefix}/character-library")
    app.register_blueprint(props_bp,             url_prefix=f"{api_prefix}/props")
    app.register_blueprint(scenes_bp,            url_prefix=f"{api_prefix}/scenes")
    app.register_blueprint(storyboards_bp,       url_prefix=f"{api_prefix}/storyboards")
    app.register_blueprint(episodes_bp,          url_prefix=f"{api_prefix}/episodes")
    app.register_blueprint(generation_bp,        url_prefix=f"{api_prefix}/generation")
    app.register_blueprint(upload_bp,            url_prefix=f"{api_prefix}/upload")
    app.register_blueprint(audio_bp,             url_prefix=f"{api_prefix}/audio")
    app.register_blueprint(settings_bp,          url_prefix=f"{api_prefix}/settings")

    # ---- Static file serving for uploads + generated output ----
    storage_abs = os.path.abspath(cfg.storage.local_path)
    os.makedirs(storage_abs, exist_ok=True)

    @app.route("/static/<path:filename>")
    def serve_static(filename: str):
        return send_from_directory(storage_abs, filename)

    # ---- Serve frontend SPA ----
    frontend_dist = Path("../web/dist")
    if frontend_dist.exists():
        @app.route("/assets/<path:filename>")
        def serve_assets(filename: str):
            return send_from_directory(str(frontend_dist / "assets"), filename)

        @app.route("/", defaults={"path": ""})
        @app.route("/<path:path>")
        def spa_fallback(path: str):
            if path.startswith("api/") or path in ("health", "static", "assets"):
                return jsonify({"error": "Not found"}), 404
            index = frontend_dist / "index.html"
            if index.exists():
                return send_from_directory(str(frontend_dist), "index.html")
            return jsonify({"error": "Frontend not built"}), 404

    # ---- Global error handlers ----
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": str(e)}), 404

    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": str(e)}), 400

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Server error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    logger.info(f"🚀 {cfg.app.name} started on port {cfg.server.port}")
    return app


# Application instance
app = create_app()

if __name__ == "__main__":
    cfg = get_settings()
    app.run(
        host=cfg.server.host,
        port=cfg.server.port,
        debug=cfg.app.debug,
    )
