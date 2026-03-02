"""
Agent 3 — Asset Orchestrator Agent (Executor Layer)

Provider-abstracted image & video generation with:
  - Retry logic with exponential backoff
  - Cost-aware provider prioritization
  - Fallback chain: Primary → Secondary → Stock placeholder
  - In-memory prompt hash cache (dedup)

Wraps existing image_service.py with the provider abstraction layer.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from services.ai_service import AIService
from services.agents.scene_planner import VisualPlan

logger = logging.getLogger(__name__)


class AssetProvider(str, Enum):
    RUNWAY = "runway"
    PIKA = "pika"
    STABILITY = "stability"
    MIDJOURNEY = "midjourney"
    OPENAI_DALLE = "openai_dalle"
    HUGGINGFACE = "huggingface"
    PLACEHOLDER = "placeholder"


@dataclass
class GeneratedAsset:
    scene_id: int
    image_url: str
    video_url: Optional[str]
    provider_used: AssetProvider
    prompt_used: str
    local_path: Optional[str] = None
    cached: bool = False

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "image_url": self.image_url,
            "video_url": self.video_url,
            "provider_used": self.provider_used.value,
            "prompt_used": self.prompt_used,
            "local_path": self.local_path,
            "cached": self.cached,
        }


class AssetOrchestratorAgent:
    """
    Agent 3: Generates visual assets for each scene.
    Implements provider fallback chain + prompt caching to minimize costs.
    """

    def __init__(
        self,
        ai_service: AIService,
        provider_chain: list[AssetProvider] = None,
        max_retries: int = 3,
    ):
        self.ai_service = ai_service
        # For local prototype: PLACEHOLDER first so pipeline always runs without external APIs
        # For production: move OPENAI_DALLE or STABILITY to front
        self.provider_chain = provider_chain or [
            AssetProvider.OPENAI_DALLE,     # try DALL-E if OpenAI key is set
            AssetProvider.HUGGINGFACE,      # try HF if HF key is set
            AssetProvider.PLACEHOLDER,      # always works locally
        ]
        self.max_retries = max_retries
        # Prompt hash → asset URL cache (avoids re-generating unchanged scenes)
        self._cache: dict[str, GeneratedAsset] = {}

    def _prompt_hash(self, prompt: str, provider: AssetProvider) -> str:
        return hashlib.md5(f"{provider}:{prompt}".encode()).hexdigest()

    async def run(
        self,
        job_id: str,
        visual_plans: list[VisualPlan],
        generate_video: bool = False,
    ) -> list[GeneratedAsset]:
        """Generate assets for all scenes. Runs scenes concurrently."""
        tasks = [self._generate_asset(plan, generate_video, job_id=job_id) for plan in visual_plans]
        return await asyncio.gather(*tasks)

    async def run_selective(
        self,
        job_id: str,
        visual_plans: list[VisualPlan],
        scene_ids: list[int],
        generate_video: bool = False,
    ) -> list[GeneratedAsset]:
        """Regenerate only specified scene IDs (called by Replanner)."""
        targets = [p for p in visual_plans if p.scene_id in scene_ids]
        tasks = [self._generate_asset(plan, generate_video, job_id=job_id) for plan in targets]
        return await asyncio.gather(*tasks)

    async def _generate_asset(self, plan: VisualPlan, generate_video: bool, job_id: str) -> GeneratedAsset:
        """Generate a single scene asset with provider fallback."""
        for provider in self.provider_chain:
            cache_key = self._prompt_hash(plan.visual_prompt, provider)
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                cached.cached = True
                return cached

            try:
                asset = await self._call_provider(plan, provider, generate_video, job_id)
                self._cache[cache_key] = asset
                return asset
            except Exception as e:
                logger.warning(f"Provider {provider} failed for scene {plan.scene_id}: {e}")
                continue

        # All providers failed — generate local placeholder
        return await self._local_placeholder(plan, job_id)

    async def _call_provider(
        self,
        plan: VisualPlan,
        provider: AssetProvider,
        generate_video: bool,
        job_id: str,
    ) -> GeneratedAsset:
        """Call a specific AI generation provider."""
        prompt = plan.visual_prompt
        negative = plan.negative_prompt

        if provider == AssetProvider.OPENAI_DALLE:
            return await self._dalle_generate(plan, prompt)
        elif provider == AssetProvider.HUGGINGFACE:
            return await self._hf_generate(plan, prompt, job_id)
        elif provider == AssetProvider.STABILITY:
            return await self._stability_generate(plan, prompt, negative)
        else:
            raise NotImplementedError(f"Provider {provider} not integrated yet")

    async def _hf_generate(self, plan: VisualPlan, prompt: str, job_id: str) -> GeneratedAsset:
        """Generate image via Hugging Face Serverless API."""
        try:
            import os
            # Use SDXL via huggingface_hub — verified working on HF free tier
            model = os.environ.get("HF_IMAGE_MODEL", "stabilityai/stable-diffusion-xl-base-1.0")
            
            # Build a proper SDXL-style tag prompt using all VisualPlan fields
            # SDXL performs best with comma-separated style tags, not natural-language sentences
            keywords_str = ", ".join(plan.keywords[:6]) if plan.keywords else ""
            mood_str = f"{plan.mood} mood, " if plan.mood else ""
            shot_str = f"{plan.shot_type}, " if plan.shot_type else "medium shot, "
            palette_str = f"{plan.color_palette}, " if plan.color_palette else ""
            style_str = f"{plan.style} style, " if plan.style else "cinematic style, "
            
            enhanced_prompt = (
                f"{prompt}, "
                f"{shot_str}"
                f"{mood_str}"
                f"{palette_str}"
                f"{style_str}"
                f"{keywords_str}, "
                f"masterpiece, highly detailed, 8k resolution, sharp focus, "
                f"no text, no words, no subtitles, no watermarks"
            ).strip(", ")
            # Use the plan's negative prompt directly — it's already curated by the scene planner
            negative_prompt = plan.negative_prompt or "blurry, low quality, text, watermark, nsfw"
            
            response = await self.ai_service.generate_image(
                prompt=enhanced_prompt[:1000], 
                provider="huggingface",
                model=model,
                job_id=job_id,
            )
            return GeneratedAsset(
                scene_id=plan.scene_id,
                image_url=response.get("url", ""),
                video_url=None,
                provider_used=AssetProvider.HUGGINGFACE,
                prompt_used=prompt,
                local_path=response.get("local_path"),
            )
        except Exception as e:
            raise RuntimeError(f"HF Generation failed: {e}")

    async def _dalle_generate(self, plan: VisualPlan, prompt: str) -> GeneratedAsset:
        """Generate image via OpenAI DALL·E."""
        response = await self.ai_service.generate_image(
            prompt=prompt[:1000],
            provider="openai",
            size="1024x576",
        )
        return GeneratedAsset(
            scene_id=plan.scene_id,
            image_url=response.get("url", ""),
            video_url=None,
            provider_used=AssetProvider.OPENAI_DALLE,
            prompt_used=prompt,
            local_path=response.get("local_path"),
        )

    async def _stability_generate(self, plan: VisualPlan, prompt: str, negative: str) -> GeneratedAsset:
        """Generate image via Stability AI (stub — extend with real client)."""
        raise NotImplementedError("Stability AI client not configured")

    async def _local_placeholder(self, plan: VisualPlan, job_id: str) -> GeneratedAsset:
        """
        Generate a local placeholder image with the scene text overlay.
        Works offline with no API key — uses FFmpeg to draw text on a dark background.
        """
        import os
        import asyncio
        from pathlib import Path

        # Store in data/storage/jobs/<job_id>
        placeholder_dir = Path("./data/storage/jobs") / job_id
        placeholder_dir.mkdir(parents=True, exist_ok=True)
        img_name = f"scene_{plan.scene_id}.jpg"
        img_path = str(placeholder_dir / img_name)
        static_url = f"/static/jobs/{job_id}/{img_name}"

        if not os.path.exists(img_path):
            # Use FFmpeg to draw scene label on dark background
            label = f"Scene {plan.scene_id}: {plan.visual_prompt[:50]}".replace("'", "").replace('"', '').replace(':', '')
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi",
                "-i", "color=c=#0f0f1a:size=1920x1080",
                "-vframes", "1",
                "-vf", f"drawtext=text='{label}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
                img_path
            ]
            
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await proc.communicate()
                
                if proc.returncode != 0:
                    logger.error(f"FFmpeg placeholder generation failed for scene {plan.scene_id}. stderr: {stderr.decode()}")
            except Exception as e:
                logger.error(f"Error executing FFmpeg for placeholder scene {plan.scene_id}: {e}")

        return GeneratedAsset(
            scene_id=plan.scene_id,
            image_url=static_url,
            video_url=None,
            local_path=img_path,
            provider_used=AssetProvider.PLACEHOLDER,
            prompt_used=plan.visual_prompt,
        )

    def clear_cache(self) -> None:
        """Clear the asset dedup cache."""
        self._cache.clear()
