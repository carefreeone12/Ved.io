"""
OrchestrAI Job Manager

Tracks the complete lifecycle of a video generation job:
  pending → script → visual → assembly → critique → refining → done / failed

Persists state using the existing AsyncTask SQLAlchemy model.
Provides in-process job registry for fast status polling.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class JobStage(str, Enum):
    PENDING = "pending"
    SCRIPT = "script"         # ScriptEngineerAgent running
    VISUAL = "visual"         # ScenePlanner + AssetOrchestrator running
    ASSEMBLY = "assembly"     # DraftAssemblerAgent running
    CRITIQUE = "critique"     # CriticAgent evaluating
    REFINING = "refining"     # Replanner + selective regen running
    SAFETY = "safety"         # SafetyPolicyAgent running
    DONE = "done"
    FAILED = "failed"


@dataclass
class SceneStatus:
    scene_id: int
    stage: str = "pending"
    score: float = 0.0
    image_url: str = ""
    issue: str = ""
    iteration: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "stage": self.stage,
            "score": self.score,
            "image_url": self.image_url,
            "issue": self.issue,
            "iteration": self.iteration,
        }


@dataclass
class JobState:
    job_id: str
    stage: JobStage = JobStage.PENDING
    current_iteration: int = 0
    max_iterations: int = 3
    score_threshold: float = 7.5
    critic_score: float = 0.0
    scenes: list[SceneStatus] = field(default_factory=list)
    script: dict = field(default_factory=dict)
    visual_plans: list[dict] = field(default_factory=list)
    draft_result: dict = field(default_factory=dict)
    safety_result: dict = field(default_factory=dict)
    error: str = ""
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    language: str = "en"
    tone: str = "neutral"
    title: str = ""
    download_url: str = ""
    thumbnail_url: str = ""
    ai_disclosure: str = ""

    def touch(self) -> None:
        self.updated_at = datetime.utcnow().isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "stage": self.stage.value,
            "current_iteration": self.current_iteration,
            "max_iterations": self.max_iterations,
            "critic_score": round(self.critic_score, 2),
            "score_threshold": self.score_threshold,
            "scenes": [s.to_dict() for s in self.scenes],
            "script": self.script,
            "draft_result": self.draft_result,
            "safety_result": self.safety_result,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "language": self.language,
            "tone": self.tone,
            "title": self.title,
            "download_url": self.download_url,
            "thumbnail_url": self.thumbnail_url,
            "ai_disclosure": self.ai_disclosure,
            "progress_pct": self._progress_pct(),
        }

    def _progress_pct(self) -> int:
        stage_progress = {
            JobStage.PENDING: 0,
            JobStage.SCRIPT: 10,
            JobStage.VISUAL: 35,
            JobStage.ASSEMBLY: 60,
            JobStage.CRITIQUE: 70,
            JobStage.REFINING: 80,
            JobStage.SAFETY: 90,
            JobStage.DONE: 100,
            JobStage.FAILED: 0,
        }
        return stage_progress.get(self.stage, 0)


class JobManager:
    """
    In-process job registry for active video generation jobs.
    Jobs are stored in memory for fast status polling.
    For production, persist to Redis or DynamoDB.
    """

    def __init__(self):
        self._jobs: dict[str, JobState] = {}

    def create_job(
        self,
        title: str = "",
        language: str = "en",
        tone: str = "neutral",
        max_iterations: int = 3,
        score_threshold: float = 7.5,
    ) -> JobState:
        job_id = str(uuid.uuid4())
        state = JobState(
            job_id=job_id,
            title=title,
            language=language,
            tone=tone,
            max_iterations=max_iterations,
            score_threshold=score_threshold,
        )
        self._jobs[job_id] = state
        return state

    def get(self, job_id: str) -> Optional[JobState]:
        return self._jobs.get(job_id)

    def update_stage(self, job_id: str, stage: JobStage) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.stage = stage
            job.touch()

    def set_error(self, job_id: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.stage = JobStage.FAILED
            job.error = error
            job.touch()

    def list_jobs(self) -> list[dict[str, Any]]:
        return [j.to_dict() for j in self._jobs.values()]


# Global singleton (one per process — use Redis for multi-worker)
job_manager = JobManager()
