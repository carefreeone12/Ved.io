"""
Setup Blueprint — /setup routes for the non-technical user setup wizard.

GET  /setup         — Render setup wizard page
POST /setup/save    — Save API key (writes .env + seeds DB + tests connection)
GET  /setup/status  — JSON: current AI config status
"""
from __future__ import annotations

import os
from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from api.deps import db_session
from services.ai_service import AIService

setup_bp = Blueprint("setup", __name__)

_ENV_FILE = Path(__file__).parent.parent.parent / "backend-py" / ".env"
# Resolve relative to the backend-py folder
_ENV_FILE = Path(__file__).parent.parent / ".env"


@setup_bp.get("")
def setup_page():
    return render_template("setup.html")


@setup_bp.get("/status")
def setup_status():
    """Return current AI config status (env vars only — fast, no DB)."""
    return jsonify(AIService.get_env_config_summary())


@setup_bp.post("/save")
async def save_config():
    """
    1. Write API key to .env file
    2. Set env vars in the running process
    3. Seed an AIServiceConfig row in the DB
    4. Test the connection
    5. Return success/error
    """
    data = request.get_json() or {}
    provider = data.get("provider", "gemini").lower()
    api_key = (data.get("api_key") or "").strip()
    model = (data.get("model") or "").strip()
    base_url = (data.get("base_url") or "").strip()

    if not api_key and provider not in ('custom',):
        return jsonify({"error": "API key is required"}), 400

    # ── 1. Determine env var names ────────────────────────────────────────
    if provider == "hf":
        env_updates = {
            "HF_API_KEY": api_key,
            "HF_MODEL": model or "mistralai/Mistral-7B-Instruct-v0.3",
        }
        provider_name = "HuggingFace"
    elif provider == "gemini":
        env_updates = {
            "GEMINI_API_KEY": api_key,
            "GEMINI_MODEL": model or "gemini-1.5-flash",
        }
        provider_name = "Google Gemini"
    elif provider == "openai":
        env_updates = {
            "OPENAI_API_KEY": api_key,
            "OPENAI_MODEL": model or "gpt-4o-mini",
            "OPENAI_BASE_URL": base_url or "https://api.openai.com",
        }
        provider_name = "OpenAI"
    else:  # custom
        env_updates = {
            "OPENAI_API_KEY": api_key or "local",
            "OPENAI_MODEL": model or "llama3",
            "OPENAI_BASE_URL": base_url or "http://localhost:11434",
        }
        provider_name = "Custom API"

    # ── 2. Write to .env file ─────────────────────────────────────────────
    _write_env_file(env_updates)

    # ── 3. Apply to running process immediately ───────────────────────────
    for k, v in env_updates.items():
        os.environ[k] = v

    # ── 4. Seed DB with this config ───────────────────────────────────────
    try:
        await _seed_db_config(provider, api_key, model, base_url)
    except Exception as e:
        pass  # DB seed is best-effort — env vars are the real fallback

    # ── 5. Test the connection ────────────────────────────────────────────
    try:
        async with db_session() as db:
            svc = AIService(db)
            test_prompt = "Reply with exactly: OK"
            result = await svc.generate_text(test_prompt, max_tokens=10)
            if not result:
                raise ValueError("Empty response from AI")
    except Exception as e:
        err = str(e)
        # Provide actionable error guidance
        if "API_KEY_INVALID" in err or "invalid" in err.lower():
            return jsonify({"error": "Invalid API key. Please double-check and try again."}), 400
        if "quota" in err.lower() or "rate" in err.lower():
            return jsonify({"error": "API quota exceeded. Try a different model or wait a moment."}), 429
        if "connection" in err.lower() or "timeout" in err.lower():
            return jsonify({"error": f"Could not connect to {provider_name}. Check your internet connection."}), 503
        return jsonify({"error": f"Connection test failed: {err[:200]}"}), 400

    return jsonify({
        "success": True,
        "provider": provider_name,
        "model": model,
        "message": f"Connected successfully to {provider_name}!",
    })


def _write_env_file(updates: dict[str, str]) -> None:
    """Write/update .env file with new key=value pairs."""
    env_path = _ENV_FILE

    # Read existing .env lines
    existing: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                existing[k.strip()] = v.strip()

    # Merge updates
    existing.update(updates)

    # Write back
    lines = [f"{k}={v}" for k, v in existing.items()]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def _seed_db_config(provider: str, api_key: str, model: str, base_url: str) -> None:
    """Insert or update an AIServiceConfig row for this provider."""
    from sqlalchemy import select
    from models.ai_config import AIServiceConfig

    async with db_session() as db:
        # Check if one already exists for this provider
        result = await db.execute(
            select(AIServiceConfig).where(
                AIServiceConfig.provider == provider,
                AIServiceConfig.service_type == "text",
            )
        )
        config = result.scalars().first()

        if provider == "hf":
            endpoint = f"/models/{model}/v1/chat/completions"
            resolved_base = "https://api-inference.huggingface.co"
        elif provider == "gemini":
            endpoint = "/v1/models"
            resolved_base = "https://generativelanguage.googleapis.com"
        elif provider == "openai":
            endpoint = "/v1/chat/completions"
            resolved_base = base_url or "https://api.openai.com"
        else:
            endpoint = "/v1/chat/completions"
            resolved_base = base_url or "http://localhost:11434"

        if config:
            config.api_key = api_key
            config.model = [model] if model else config.model
            config.base_url = resolved_base
            config.is_active = True
        else:
            config = AIServiceConfig(
                provider=provider,
                service_type="text",
                api_key=api_key,
                model=[model] if model else [],
                base_url=resolved_base,
                endpoint=endpoint,
                is_active=True,
                is_default=True,
                priority=10,
            )
            db.add(config)
