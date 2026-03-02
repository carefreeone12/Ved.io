"""
Drama service — CRUD and orchestration for Drama, Episode, Character, Scene, Prop.
Maps to Go application/services/drama_service.go.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.drama import Character, Drama, Episode, Prop, Scene

logger = logging.getLogger(__name__)


class DramaService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ---- Drama CRUD ----

    async def list_dramas(
        self, page: int = 1, page_size: int = 20
    ) -> tuple[list[Drama], int]:
        base = select(Drama).where(Drama.deleted_at == None)  # noqa: E711
        count_result = await self.db.execute(select(func.count()).select_from(base.subquery()))
        total = count_result.scalar_one()
        result = await self.db.execute(
            base.order_by(Drama.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(result.scalars().all()), total

    async def get_drama(self, drama_id: int) -> Optional[Drama]:
        result = await self.db.execute(
            select(Drama)
            .where(Drama.id == drama_id, Drama.deleted_at == None)  # noqa: E711
            .options(
                selectinload(Drama.episodes),
                selectinload(Drama.characters),
                selectinload(Drama.scenes),
                selectinload(Drama.props),
            )
        )
        return result.scalars().first()

    async def create_drama(self, data: dict) -> Drama:
        drama = Drama(**data)
        self.db.add(drama)
        await self.db.flush()
        await self.db.refresh(drama)
        return drama

    async def update_drama(self, drama_id: int, data: dict) -> Optional[Drama]:
        drama = await self.get_drama(drama_id)
        if not drama:
            return None
        for key, value in data.items():
            if value is not None:
                setattr(drama, key, value)
        drama.updated_at = datetime.utcnow()
        await self.db.flush()
        return drama

    async def delete_drama(self, drama_id: int) -> bool:
        drama = await self.get_drama(drama_id)
        if not drama:
            return False
        drama.deleted_at = datetime.utcnow()
        await self.db.flush()
        return True

    async def get_drama_stats(self) -> dict:
        result = await self.db.execute(
            select(Drama.status, func.count(Drama.id))
            .where(Drama.deleted_at == None)  # noqa: E711
            .group_by(Drama.status)
        )
        counts = {row[0]: row[1] for row in result.all()}
        total = sum(counts.values())
        return {
            "total": total,
            "draft": counts.get("draft", 0),
            "in_progress": counts.get("in_progress", 0),
            "completed": counts.get("completed", 0),
        }

    # ---- Episode CRUD ----

    async def save_episodes(self, drama_id: int, episodes_data: list[dict]) -> list[Episode]:
        result = await self.db.execute(
            select(Episode).where(Episode.drama_id == drama_id, Episode.deleted_at == None)  # noqa: E711
        )
        existing = {e.episode_number: e for e in result.scalars().all()}
        saved = []
        for ep_data in episodes_data:
            ep_num = ep_data.get("episode_number", 0)
            if ep_num in existing:
                ep = existing[ep_num]
                for k, v in ep_data.items():
                    setattr(ep, k, v)
            else:
                ep = Episode(**ep_data, drama_id=drama_id)
                self.db.add(ep)
            saved.append(ep)
        await self.db.flush()
        return saved

    # ---- Character CRUD ----

    async def get_characters(self, drama_id: int) -> list[Character]:
        result = await self.db.execute(
            select(Character)
            .where(Character.drama_id == drama_id, Character.deleted_at == None)  # noqa: E711
            .order_by(Character.sort_order)
        )
        return list(result.scalars().all())

    async def save_characters(self, drama_id: int, characters_data: list[dict]) -> list[Character]:
        # Delete existing and re-insert (matches Go behaviour of replace-all)
        old = await self.db.execute(
            select(Character).where(Character.drama_id == drama_id, Character.deleted_at == None)  # noqa: E711
        )
        for c in old.scalars().all():
            c.deleted_at = datetime.utcnow()

        saved = []
        for cd in characters_data:
            cd["drama_id"] = drama_id
            char = Character(**cd)
            self.db.add(char)
            saved.append(char)
        await self.db.flush()
        return saved

    # ---- Finalize Episode ----

    async def finalize_episode(self, episode_id: int) -> Optional[Episode]:
        result = await self.db.execute(
            select(Episode).where(Episode.id == episode_id, Episode.deleted_at == None)  # noqa: E711
        )
        episode = result.scalars().first()
        if episode:
            episode.status = "completed"
            await self.db.flush()
        return episode
