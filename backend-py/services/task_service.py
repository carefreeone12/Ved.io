"""
Async task service for tracking background operations.
Maps to Go application/services/task_service.go.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.task import AsyncTask

logger = logging.getLogger(__name__)


class TaskService:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task(
        self, task_type: str, resource_id: str = ""
    ) -> AsyncTask:
        task = AsyncTask(
            id=str(uuid.uuid4()),
            type=task_type,
            status="pending",
            progress=0,
            resource_id=resource_id,
        )
        self.db.add(task)
        await self.db.flush()
        logger.info("Task created", task_id=task.id, type=task_type)
        return task

    async def get_task(self, task_id: str) -> Optional[AsyncTask]:
        result = await self.db.execute(
            select(AsyncTask).where(AsyncTask.id == task_id, AsyncTask.deleted_at == None)  # noqa: E711
        )
        return result.scalars().first()

    async def get_resource_tasks(self, resource_id: str) -> list[AsyncTask]:
        result = await self.db.execute(
            select(AsyncTask)
            .where(AsyncTask.resource_id == resource_id, AsyncTask.deleted_at == None)  # noqa: E711
            .order_by(AsyncTask.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        error: Optional[str] = None,
        result: Optional[str] = None,
    ) -> Optional[AsyncTask]:
        task = await self.get_task(task_id)
        if not task:
            return None
        if status:
            task.status = status
        if progress is not None:
            task.progress = progress
        if message is not None:
            task.message = message
        if error is not None:
            task.error = error
        if result is not None:
            task.result = result
        if status in ("completed", "failed"):
            task.completed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()
        await self.db.flush()
        return task

    async def complete_task(self, task_id: str, result: Optional[str] = None) -> None:
        await self.update_task(task_id, status="completed", progress=100, result=result)

    async def fail_task(self, task_id: str, error: str) -> None:
        await self.update_task(task_id, status="failed", error=error)
