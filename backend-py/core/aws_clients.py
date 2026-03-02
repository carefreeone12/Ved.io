"""
Local-only media utilities — AWS-free prototype mode.

Replaces aws_clients.py for local development:
  - LocalTTS: gTTS (Google Text-to-Speech, free internet API, no key needed)
  - LocalStorage: saves files to disk under ./data/storage/
  - No boto3, no AWS credentials needed

For production with AWS, swap these classes out for the real boto3 wrappers.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class LocalTTS:
    """
    Free Text-to-Speech using gTTS (Google Translate TTS endpoint).
    Supports all Indian languages: hi, te, ta, mr, bn, gu, kn, ml.
    No API key required. Requires internet connection.
    """

    LANG_MAP = {
        "en": "en",
        "hi": "hi",
        "te": "te",
        "ta": "ta",
        "mr": "mr",
        "bn": "bn",
        "gu": "gu",
        "kn": "kn",
        "ml": "ml",
        "pa": "pa",
    }

    async def synthesize(self, text: str, language: str, output_path: str) -> bool:
        """Synthesize speech and save to output_path. Returns True on success."""
        gtts_lang = self.LANG_MAP.get(language, "en")
        try:
            from gtts import gTTS
            loop = asyncio.get_event_loop()

            def _call():
                tts = gTTS(text=text[:3000], lang=gtts_lang, slow=False)
                tts.save(output_path)

            await loop.run_in_executor(None, _call)
            logger.info(f"TTS generated: {output_path} (lang={gtts_lang})")
            return True
        except ImportError:
            logger.warning("gTTS not installed — run: pip install gTTS")
            return False
        except Exception as e:
            logger.warning(f"gTTS failed for lang={gtts_lang}: {e}")
            return False


class LocalStorageClient:
    """
    Local filesystem storage — drop-in replacement for S3.
    Files are saved to ./data/storage/ and served via /static/.
    """

    def __init__(self, base_path: str = "./data/storage", base_url: str = "http://localhost:5678/static"):
        self.base_path = Path(base_path)
        self.base_url = base_url.rstrip("/")

    def upload_file(self, local_path: str, storage_key: str) -> str:
        """Copy a file to storage and return its public URL."""
        dest = self.base_path / storage_key
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(local_path, dest)
        return f"{self.base_url}/{storage_key}"

    def get_url(self, storage_key: str) -> str:
        """Get public URL for a stored file."""
        return f"{self.base_url}/{storage_key}"

    def exists(self, storage_key: str) -> bool:
        return (self.base_path / storage_key).exists()


def create_placeholder_image(output_path: str, text: str = "Scene", color: str = "0f0f1a") -> bool:
    """
    Create a dark placeholder image using FFmpeg (no Pillow/image library needed).
    Used when real image generation is unavailable locally.
    """
    try:
        import subprocess
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"color=c=#{color}:size=1920x1080:rate=1",
            "-vframes", "1",
            "-vf", f"drawtext=text='{text[:40]}':fontcolor=white:fontsize=48:x=(w-text_w)/2:y=(h-text_h)/2",
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=10)
        return result.returncode == 0
    except Exception as e:
        logger.warning(f"Placeholder image creation failed: {e}")
        # Last resort: create a minimal valid JPEG using raw bytes
        _create_minimal_jpeg(output_path)
        return True


def _create_minimal_jpeg(output_path: str) -> None:
    """Create the smallest valid JPEG (1x1 black pixel) as absolute fallback."""
    # Minimal valid JPEG bytes (1x1 black pixel)
    minimal_jpeg = bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD5,
        0xFF, 0xD9
    ])
    with open(output_path, "wb") as f:
        f.write(minimal_jpeg)
