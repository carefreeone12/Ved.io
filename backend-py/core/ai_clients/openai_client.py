"""
Async OpenAI HTTP client.
Maps to Go pkg/ai/openai_client.go.
Supports OpenAI-compatible endpoints (Ollama, LMStudio, DeepSeek, etc.).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class OpenAIClient:
    """
    Async OpenAI-compatible LLM + Image client.
    Replaces the Go OpenAIClient with proper async I/O.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        endpoint: str = "/v1/chat/completions",
        timeout: float = 600.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send a chat completion request."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        url = self.base_url + self.endpoint
        logger.debug(f"OpenAI request → {url} model={self.model}")

        client = self._get_client()
        resp = await client.post(url, json=payload)

        if resp.status_code != 200:
            body = resp.text
            # Handle o1/o3 models that don't support max_tokens → retry with max_completion_tokens
            if max_tokens and "max_tokens" in body and "Unsupported parameter" in body:
                payload.pop("max_tokens", None)
                payload["max_completion_tokens"] = max_tokens
                resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                raise httpx.HTTPStatusError(
                    f"OpenAI API error {resp.status_code}: {resp.text}",
                    request=resp.request,
                    response=resp,
                )

        data = resp.json()
        return data

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int | None = None,
        temperature: float = 0.7,
    ) -> str:
        """Generate text from a prompt."""
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        data = await self.chat_completion(messages, temperature=temperature, max_tokens=max_tokens)

        choices = data.get("choices", [])
        if not choices:
            raise ValueError("No choices returned from OpenAI API")

        finish_reason = choices[0].get("finish_reason", "")
        if finish_reason == "content_filter":
            raise ValueError("Content blocked by AI safety filter. Adjust your prompt.")

        content = choices[0].get("message", {}).get("content", "")
        return content

    async def generate_image(
        self,
        prompt: str,
        size: str = "1024x1024",
        n: int = 1,
        quality: str = "standard",
    ) -> list[str]:
        """Generate images and return URLs."""
        url = self.base_url + "/v1/images/generations"
        payload = {
            "prompt": prompt,
            "n": n,
            "size": size,
            "model": self.model,
            "quality": quality,
        }

        client = self._get_client()
        resp = await client.post(url, json=payload)
        if resp.status_code != 200:
            raise httpx.HTTPStatusError(
                f"OpenAI image API error {resp.status_code}: {resp.text}",
                request=resp.request,
                response=resp,
            )
        data = resp.json()
        urls = []
        for item in data.get("data", []):
            if item.get("url"):
                urls.append(item["url"])
            elif item.get("b64_json"):
                urls.append("data:image/png;base64," + item["b64_json"])
        return urls

    async def test_connection(self) -> bool:
        """Test API connectivity."""
        try:
            await self.generate_text("Hello", max_tokens=10)
            return True
        except Exception as e:
            logger.warning(f"OpenAI connection test failed: {e}")
            return False
