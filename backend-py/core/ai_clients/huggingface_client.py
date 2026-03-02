"""
HuggingFace Inference API Client

Uses the HF Models API Router (OpenAI compatible)
Endpoint: https://router.huggingface.co/v1

Free models available:
  - meta-llama/Llama-3.2-3B-Instruct       (fast, great quality)
  - meta-llama/Llama-3.1-8B-Instruct       (better quality)
  - Qwen/Qwen2.5-7B-Instruct               (excellent multilingual)
  - microsoft/Phi-3.5-mini-instruct         (very fast, lightweight)
  - HuggingFaceH4/zephyr-7b-beta           (good instruction following)

Get your free API key at: https://huggingface.co/settings/tokens
"""
import logging
from typing import Optional

from openai import AsyncOpenAI
from openai import OpenAIError
import httpx

logger = logging.getLogger(__name__)

HF_BASE = "https://router.huggingface.co"
FREE_MODELS = [
    "meta-llama/Llama-3.2-3B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
    "microsoft/Phi-3.5-mini-instruct",
    "HuggingFaceH4/zephyr-7b-beta",
]

DEFAULT_MODEL = "meta-llama/Llama-3.2-3B-Instruct"


class HuggingFaceClient:
    """
    Async client for Hugging Face Serverless Inference API via the OpenAI SDK router.
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        self.api_key = api_key
        self.model = model
        self.client = AsyncOpenAI(
            base_url=f"{HF_BASE}/v1",
            api_key=api_key,
        )

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: Optional[int] = 1024,
        temperature: float = 0.7,
    ) -> str:
        """Generate text via HF Inference API using the OpenAI client."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens or 1024,
                temperature=temperature,
            )
            return response.choices[0].message.content or ""
        except OpenAIError as e:
            err_msg = str(e).lower()
            if "503" in err_msg or "loading" in err_msg:
                raise RuntimeError(
                    f"Model '{self.model}' is loading. Wait 20 seconds and try again. "
                    "Free HF models cold-start on first request."
                )
            if "429" in err_msg or "rate limit" in err_msg:
                raise RuntimeError(
                    "HuggingFace rate limit reached. Wait a minute or use a different model."
                )
            if "401" in err_msg or "unauthorized" in err_msg:
                raise RuntimeError(
                    "Invalid HuggingFace API key. Get yours at https://huggingface.co/settings/tokens"
                )
            if "404" in err_msg or "not found" in err_msg:
                raise RuntimeError(
                    f"Model '{self.model}' not found or not accessible on free tier. "
                    f"Try: {', '.join(FREE_MODELS[:2])}"
                )
            if "402" in err_msg or "depleted" in err_msg:
                raise RuntimeError(
                    "You have depleted your monthly included credits for Hugging Face Inference Providers. "
                    "Please purchase pre-paid credits or subscribe to continue usage."
                )
            raise RuntimeError(f"HuggingFace generation failed: {e}")

    async def test_connection(self) -> bool:
        """Test the HF connection with a minimal prompt."""
        try:
            result = await self.generate_text("Reply with exactly: OK", max_tokens=5)
            return bool(result)
        except Exception as e:
            logger.warning(f"HuggingFace connection test failed: {e}")
            return False

    async def generate_image(self, prompt: str, **kwargs) -> dict:
        """Generate an image using a Hugging Face text-to-image model via the Inference API."""
        # Qwen doesn't have a direct free text-to-image model on HF router, but FLUX or SDXL are great.
        # If the user specifically asked for Qwen, understand they mean a free HF image model.
        # We'll use FLUX.1-dev or black-forest-labs/FLUX.1-schnell as it's the current best visual free model
        image_model = kwargs.get("model", "stabilityai/stable-diffusion-xl-base-1.0")
        
        # Determine paths
        import uuid
        import os
        from pathlib import Path
        
        job_id = kwargs.get("job_id", "hf_images")
        output_dir = Path("./data/storage/jobs") / job_id
        output_dir.mkdir(parents=True, exist_ok=True)
        img_name = f"hf_{uuid.uuid4().hex[:8]}.jpg"
        local_path = str(output_dir / img_name)
        
        # For simplicity, returning a placeholder URL, but the local path is what matters for generation
        static_url = f"/static/jobs/{job_id}/{img_name}"

        try:
            import asyncio
            from huggingface_hub import InferenceClient
            
            # Run the synchronous inference client in a thread pool to avoid blocking the async event loop
            def _generate_sync():
                client = InferenceClient(model=image_model, token=self.api_key)
                # This will raise exceptions on 503, 401, etc.
                img = client.text_to_image(prompt[:1000])
                img.save(local_path)
                return True
                
            await asyncio.to_thread(_generate_sync)

            return {
                "url": static_url,
                "local_path": local_path,
            }
        except Exception as e:
            logger.error(f"HuggingFace InferenceClient failed: {e}")
            raise RuntimeError(f"HuggingFace image generation failed: {e}")

