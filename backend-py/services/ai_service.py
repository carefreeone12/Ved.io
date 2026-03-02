"""
Core AI Service — builds LLM clients.

Priority order:
  1. DB table (ai_service_configs) — user-configured via /setup UI
  2. Environment variables (OPENAI_API_KEY, GEMINI_API_KEY, OPENAI_BASE_URL)
  3. Helpful error message telling the user to go to /setup
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.ai_clients.gemini_client import GeminiClient
from core.ai_clients.huggingface_client import HuggingFaceClient, DEFAULT_MODEL as HF_DEFAULT_MODEL
from core.ai_clients.openai_client import OpenAIClient
from models.ai_config import AIServiceConfig

logger = logging.getLogger(__name__)


# ── Singleton env-var clients (no DB needed) ──────────────────────────────────

def _build_env_text_client() -> OpenAIClient | GeminiClient | HuggingFaceClient | None:
    """Build an LLM client purely from environment variables, no DB required."""

    # 1. HuggingFace (free tier — best free option)
    hf_key = os.environ.get("HF_API_KEY", "").strip()
    if hf_key:
        model = os.environ.get("HF_MODEL", HF_DEFAULT_MODEL)
        logger.info(f"Using HF_API_KEY from environment (model={model})")
        return HuggingFaceClient(api_key=hf_key, model=model)

    # 2. Gemini (free tier available)
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_key:
        logger.info("Using GEMINI_API_KEY from environment for text generation")
        return GeminiClient(api_key=gemini_key, model=os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"))

    # 3. OpenAI or any OpenAI-compatible endpoint (Ollama, Groq, Together, etc.)
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        logger.info(f"Using OPENAI_API_KEY from environment for text generation (model={model})")
        return OpenAIClient(base_url=base_url, api_key=openai_key, model=model)

    return None


def _build_env_image_client() -> OpenAIClient | HuggingFaceClient | None:
    """Build an image generation client from environment variables."""
    # 1. HuggingFace Free Image Generation
    hf_key = os.environ.get("HF_API_KEY", "").strip()
    if hf_key:
        model = os.environ.get("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
        logger.info(f"Using HF_API_KEY from environment for image generation (model={model})")
        return HuggingFaceClient(api_key=hf_key, model=model)

    # 2. OpenAI DALL-E
    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com")
        return OpenAIClient(
            base_url=base_url,
            api_key=openai_key,
            model="dall-e-3",
            endpoint="/v1/images/generations",
        )
    return None


# ── Main AIService class ──────────────────────────────────────────────────────

class AIService:
    """
    Builds and caches LLM clients.

    Lookup order:
      1. DB table (ai_service_configs) — highest priority
      2. Environment variables         — automatic fallback
      3. Raise descriptive error       — guides user to /setup
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._client_cache: dict[int, OpenAIClient | GeminiClient] = {}

    async def get_text_client(self, provider: Optional[str] = None) -> OpenAIClient | GeminiClient:
        """Get an LLM client for text generation."""
        # 1. Try DB config
        config = await self._get_config_or_none("text", provider)
        if config:
            return self._build_client(config)

        # 2. Try env vars
        client = _build_env_text_client()
        if client:
            return client

        # 3. No config anywhere — clear instructions for the user
        raise ValueError(
            "No AI API key configured. "
            "Please visit http://localhost:5678/setup to add your API key. "
            "Best free option: HuggingFace (https://huggingface.co/settings/tokens) "
            "or Gemini (https://aistudio.google.com/app/apikey)"
        )

    async def get_image_client(self, provider: Optional[str] = None) -> OpenAIClient:
        """Get a client for image generation."""
        config = await self._get_config_or_none("image", provider)
        if config:
            return self._build_client(config)  # type: ignore[return-value]

        client = _build_env_image_client()
        if client:
            return client  # type: ignore[return-value]

        # Image generation is optional — don't hard-fail
        openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not openai_key:
            raise ValueError(
                "No image generation API key configured. "
                "Visit http://localhost:5678/setup to add your OpenAI API key."
            )
        raise ValueError("Image generation requires an OpenAI API key with DALL-E access.")

    async def _get_config_or_none(
        self, service_type: str, provider: Optional[str] = None
    ) -> AIServiceConfig | None:
        """Query DB for an active config. Returns None instead of raising."""
        try:
            query = select(AIServiceConfig).where(
                AIServiceConfig.service_type == service_type,
                AIServiceConfig.is_active == True,  # noqa: E712
            )
            if provider:
                query = query.where(AIServiceConfig.provider == provider)
            else:
                query = query.order_by(
                    AIServiceConfig.priority.desc(),
                    AIServiceConfig.is_default.desc()
                )
            result = await self.db.execute(query)
            return result.scalars().first()
        except Exception as e:
            logger.warning(f"DB config lookup failed (will try env vars): {e}")
            return None

    def _build_client(self, config: AIServiceConfig) -> OpenAIClient | GeminiClient | HuggingFaceClient:
        if config.id in self._client_cache:
            return self._client_cache[config.id]

        models = config.model or []
        model_name = models[0] if models else ""

        if config.provider == "gemini":
            client = GeminiClient(api_key=config.api_key, model=model_name)
        else:
            client = OpenAIClient(
                base_url=config.base_url,
                api_key=config.api_key,
                model=model_name,
                endpoint=config.endpoint or "/v1/chat/completions",
            )

        self._client_cache[config.id] = client
        return client

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        service_type: str = "text",
        provider: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate text using the configured LLM."""
        client = await self.get_text_client(provider)
        return await client.generate_text(
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def generate_image(self, prompt: str, provider: str = "openai", **kwargs) -> dict:
        """Generate an image using the configured provider."""
        client = await self.get_image_client(provider)
        return await client.generate_image(prompt=prompt, **kwargs)

    async def test_connection(self, config_id: int) -> bool:
        """Test connectivity for a specific DB config."""
        result = await self.db.execute(
            select(AIServiceConfig).where(AIServiceConfig.id == config_id)
        )
        config = result.scalars().first()
        if not config:
            return False
        client = self._build_client(config)
        return await client.test_connection()

    @staticmethod
    def is_configured() -> bool:
        """Quick check: is any AI provider available (env vars only)?"""
        return bool(
            os.environ.get("HF_API_KEY")
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )

    @staticmethod
    def get_env_config_summary() -> dict:
        """Return human-readable summary of configured env-var providers."""
        providers = []
        if os.environ.get("HF_API_KEY"):
            providers.append({
                "name": "HuggingFace",
                "model": os.environ.get("HF_MODEL", HF_DEFAULT_MODEL),
                "source": "HF_API_KEY env var",
            })
        if os.environ.get("GEMINI_API_KEY"):
            providers.append({
                "name": "Google Gemini",
                "model": os.environ.get("GEMINI_MODEL", "gemini-1.5-flash"),
                "source": "GEMINI_API_KEY env var",
            })
        if os.environ.get("OPENAI_API_KEY"):
            providers.append({
                "name": "OpenAI / Compatible",
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com"),
                "source": "OPENAI_API_KEY env var",
            })
        return {"configured": bool(providers), "providers": providers}
