"""
Image generation service — manages AI image generation jobs.
Maps to Go application/services/image_generation_service.go.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage import LocalStorage
from models.image_generation import ImageGeneration
from services.ai_service import AIService

logger = logging.getLogger(__name__)


class ImageGenerationService:

    def __init__(
        self,
        db: AsyncSession,
        ai_service: AIService,
        storage: LocalStorage,
    ) -> None:
        self.db = db
        self.ai_service = ai_service
        self.storage = storage

    async def create(self, data: dict) -> ImageGeneration:
        gen = ImageGeneration(**data)
        self.db.add(gen)
        await self.db.flush()
        return gen

    async def get(self, gen_id: int) -> Optional[ImageGeneration]:
        result = await self.db.execute(
            select(ImageGeneration).where(ImageGeneration.id == gen_id)
        )
        return result.scalars().first()

    async def list(self, drama_id: Optional[int] = None, page: int = 1, page_size: int = 20) -> tuple[list[ImageGeneration], int]:
        from sqlalchemy import func
        query = select(ImageGeneration)
        if drama_id:
            query = query.where(ImageGeneration.drama_id == drama_id)
        count_result = await self.db.execute(select(func.count()).select_from(query.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            query.order_by(ImageGeneration.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def delete(self, gen_id: int) -> bool:
        gen = await self.get(gen_id)
        if not gen:
            return False
        await self.db.delete(gen)
        await self.db.flush()
        return True

    async def generate_image(
        self,
        gen: ImageGeneration,
        provider: Optional[str] = None,
    ) -> ImageGeneration:
        """
        Execute image generation: call AI provider, download result, save locally.
        Maps to Go ImageGenerationService.GenerateImage.
        """
        gen.status = "processing"
        await self.db.flush()

        try:
            client = await self.ai_service.get_image_client(provider or gen.provider)
            urls = await client.generate_image(
                prompt=gen.prompt,
                size=gen.size or "1024x1024",
                n=1,
                quality=gen.quality or "standard",
            )
            if not urls:
                raise ValueError("No image URL returned from provider")

            image_url = urls[0]
            # Download and store locally
            local_url = await self._download_and_store(image_url)

            gen.image_url = image_url
            gen.local_path = local_url
            gen.status = "completed"
            gen.completed_at = datetime.utcnow()
        except Exception as e:
            logger.error(f"Image generation failed: {e}", exc_info=True)
            gen.status = "failed"
            gen.error_msg = str(e)

        await self.db.flush()
        return gen

    async def _download_and_store(self, url: str) -> str:
        """Download an image from URL and save to local storage."""
        import httpx
        if url.startswith("data:image"):
            import base64
            header, data = url.split(",", 1)
            ext = header.split(";")[0].split("/")[1]
            return await self.storage.save_bytes(base64.b64decode(data), "images", ext)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content_type = resp.headers.get("content-type", "image/png")
            ext = content_type.split("/")[-1].split(";")[0]
            return await self.storage.save_bytes(resp.content, "images", ext)
