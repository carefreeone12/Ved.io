"""
Google Gemini async client.
Maps to Go pkg/ai/gemini_client.go.
"""
from __future__ import annotations

import logging
from typing import Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


class GeminiClient:
    """Async wrapper around Google Generative AI SDK."""

    def __init__(self, api_key: str, model: str = "gemini-pro") -> None:
        self.api_key = api_key
        self.model_name = model
        genai.configure(api_key=api_key)
        self._model: Optional[genai.GenerativeModel] = None

    def _get_model(self) -> genai.GenerativeModel:
        if self._model is None:
            self._model = genai.GenerativeModel(self.model_name)
        return self._model

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        model = self._get_model()
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        response = await model.generate_content_async(
            full_prompt,
            generation_config=generation_config,
        )
        return response.text

    async def test_connection(self) -> bool:
        try:
            await self.generate_text("Hello", max_tokens=10)
            return True
        except Exception as e:
            logger.warning(f"Gemini connection test failed: {e}")
            return False
