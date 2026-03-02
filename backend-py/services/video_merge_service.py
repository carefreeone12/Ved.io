"""
Video merge service — assembles video clips using FFmpeg.
Maps to Go application/services/video_merge_service.go.
"""
from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from core.storage import LocalStorage
from models.video_generation import VideoGeneration
from models.video_merge import VideoMerge

logger = logging.getLogger(__name__)


class VideoMergeService:

    def __init__(self, db: AsyncSession, storage: LocalStorage) -> None:
        self.db = db
        self.storage = storage

    async def merge_videos(
        self, merge: VideoMerge, video_ids: list[int]
    ) -> VideoMerge:
        """
        Merge video clips into a single output video using FFmpeg.
        Maps to Go VideoMergeService.MergeVideos.
        """
        from sqlalchemy import select

        merge.status = "processing"
        await self.db.flush()

        try:
            # Fetch video generation records
            from models.video_generation import VideoGeneration
            result = await self.db.execute(
                select(VideoGeneration).where(VideoGeneration.id.in_(video_ids))
            )
            videos = result.scalars().all()

            # Collect local video file paths
            video_paths = []
            for v in sorted(videos, key=lambda x: video_ids.index(x.id)):
                if v.local_path:
                    path = self.storage.url_to_local_path(v.local_path)
                    if path and path.exists():
                        video_paths.append(str(path))
                    elif v.video_url:
                        # Download from URL
                        local = await self._download_video(v.video_url)
                        video_paths.append(local)

            if not video_paths:
                raise ValueError("No local video files found for merging")

            # Run FFmpeg merge
            output_path = await self._run_ffmpeg_merge(video_paths)
            local_url = await self.storage.save_file(output_path, "merged")

            merge.status = "completed"
            merge.output_url = local_url
            merge.local_path = local_url
        except Exception as e:
            logger.error(f"Video merge failed: {e}", exc_info=True)
            merge.status = "failed"
            merge.error_msg = str(e)

        await self.db.flush()
        return merge

    async def _run_ffmpeg_merge(self, video_paths: list[str]) -> str:
        """Run FFmpeg to concatenate video files."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="w") as list_file:
            for path in video_paths:
                list_file.write(f"file '{path}'\n")
            list_path = list_file.name

        output = tempfile.mktemp(suffix=".mp4")

        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", list_path,
            "-c", "copy",
            "-y",
            output,
        ]

        # Run FFmpeg in a thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._run_subprocess, cmd)
        return output

    def _run_subprocess(self, cmd: list[str]) -> None:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=3600
        )
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg failed: {result.stderr}")

    async def _download_video(self, url: str) -> str:
        import httpx
        async with httpx.AsyncClient(timeout=300.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            out = tempfile.mktemp(suffix=".mp4")
            Path(out).write_bytes(resp.content)
            return out
