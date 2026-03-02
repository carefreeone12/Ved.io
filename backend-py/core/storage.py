"""
Local filesystem storage adapter.
Maps to Go infrastructure/storage/local_storage.go.
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Optional


class LocalStorage:
    """Handles file storage on local filesystem, serves via /static URL."""

    def __init__(self, base_path: str, base_url: str) -> None:
        self.base_path = Path(base_path)
        self.base_url = base_url.rstrip("/")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _generate_path(self, category: str, ext: str) -> tuple[Path, str]:
        """Return (absolute_path, relative_url_path)."""
        unique = str(uuid.uuid4())
        rel = Path(category) / f"{unique}.{ext.lstrip('.')}"
        abs_path = self.base_path / rel
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return abs_path, str(rel)

    async def save_bytes(self, data: bytes, category: str = "uploads", ext: str = "bin") -> str:
        """Save bytes and return the accessible URL."""
        abs_path, rel = self._generate_path(category, ext)
        abs_path.write_bytes(data)
        return f"{self.base_url}/{rel}"

    async def save_file(self, src_path: str, category: str = "uploads") -> str:
        """Copy a file to storage and return the accessible URL."""
        ext = Path(src_path).suffix.lstrip(".")
        abs_path, rel = self._generate_path(category, ext or "bin")
        shutil.copy2(src_path, abs_path)
        return f"{self.base_url}/{rel}"

    def url_to_local_path(self, url: str) -> Optional[Path]:
        """Convert a stored URL back to absolute local path."""
        prefix = f"{self.base_url}/"
        if url.startswith(prefix):
            rel = url[len(prefix):]
            return self.base_path / rel
        return None

    def delete(self, url: str) -> bool:
        """Delete a file by URL. Returns True if deleted."""
        path = self.url_to_local_path(url)
        if path and path.exists():
            path.unlink()
            return True
        return False

    def exists(self, url: str) -> bool:
        path = self.url_to_local_path(url)
        return path is not None and path.exists()
