"""
Iterative Feedback Generator — Orchestration Pipeline.
Implements the draft → critic → re-plan → re-generate → re-assemble loop.

NEW module — no Go equivalent.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

from services.critic import (
    CriticInput,
    CriticOutput,
    CriticService,
    DraftAsset,
    SceneMetadata,
)
from services.image_service import ImageGenerationService

logger = logging.getLogger(__name__)


@dataclass
class IterationResult:
    iteration: int
    score: float
    passed: bool
    regenerated_scene_ids: list[int]
    critic_output: CriticOutput


@dataclass
class PipelineResult:
    final_score: float
    total_iterations: int
    passed: bool
    history: list[IterationResult] = field(default_factory=list)
    final_regenerate_list: list[int] = field(default_factory=list)


class IterativePipeline:
    """
    State-machine pipeline: draft → critic → re-plan → re-generate → re-assemble.
    
    States:
      DRAFT → EVALUATE → (PASS or REPLAN) → REGENERATE → EVALUATE → ...
    
    Stops when:
      - total_score >= score_threshold, OR
      - iteration_count >= max_iterations
    """

    def __init__(
        self,
        critic_service: CriticService,
        image_service: ImageGenerationService,
        score_threshold: float = 7.5,
        max_iterations: int = 3,
    ) -> None:
        self.critic = critic_service
        self.image_service = image_service
        self.score_threshold = score_threshold
        self.max_iterations = max_iterations

        # Simple in-memory deduplication cache: prompt_hash → asset_url
        self._prompt_cache: dict[str, str] = {}

    async def run(
        self,
        script_json: dict,
        scene_metadata: list[SceneMetadata],
        draft_assets: list[DraftAsset],
        timings: Optional[list[float]] = None,
    ) -> PipelineResult:
        """
        Run the iterative feedback loop.
        
        Returns a PipelineResult containing the final score, iteration count,
        pass/fail status, and full history.
        """
        if timings is None:
            timings = [5.0] * len(scene_metadata)

        result = PipelineResult(
            final_score=0.0,
            total_iterations=0,
            passed=False,
        )

        current_assets = list(draft_assets)

        for iteration in range(1, self.max_iterations + 1):
            logger.info(
                f"[Iterative Pipeline] Iteration {iteration}/{self.max_iterations}"
            )

            # EVALUATE: Run critic
            critic_input = CriticInput(
                script_json=script_json,
                scene_metadata=scene_metadata,
                draft_assets=current_assets,
                timings=timings,
            )
            critic_output = await self.critic.evaluate(critic_input)
            critic_output.iteration = iteration

            logger.info(
                f"[Iterative Pipeline] Score: {critic_output.total_score:.2f} "
                f"| Regenerate: {critic_output.regenerate_list}"
            )

            iter_result = IterationResult(
                iteration=iteration,
                score=critic_output.total_score,
                passed=critic_output.total_score >= self.score_threshold,
                regenerated_scene_ids=list(critic_output.regenerate_list),
                critic_output=critic_output,
            )
            result.history.append(iter_result)
            result.total_iterations = iteration
            result.final_score = critic_output.total_score

            # PASS: Exit early
            if critic_output.total_score >= self.score_threshold:
                result.passed = True
                logger.info(
                    f"[Iterative Pipeline] PASSED on iteration {iteration} "
                    f"(score {critic_output.total_score:.2f} >= {self.score_threshold})"
                )
                break

            # REPLAN: No scenes to regenerate, nothing more to do
            if not critic_output.regenerate_list:
                logger.info("[Iterative Pipeline] No scenes flagged for regeneration. Stopping.")
                break

            # REGENERATE: Re-generate flagged assets
            current_assets = await self._regenerate_flagged(
                current_assets=current_assets,
                critic_output=critic_output,
                scene_metadata=scene_metadata,
            )

        result.final_regenerate_list = result.history[-1].critic_output.regenerate_list if result.history else []
        return result

    async def _regenerate_flagged(
        self,
        current_assets: list[DraftAsset],
        critic_output: CriticOutput,
        scene_metadata: list[SceneMetadata],
    ) -> list[DraftAsset]:
        """
        For each flagged scene, use the critic's alternative_prompt suggestion
        to regenerate the image asset (with dedup cache).
        """
        # Build a map of scene_id → issue
        issue_map = {iss.scene_id: iss for iss in critic_output.issues}
        assets_by_scene = {a.scene_id: a for a in current_assets}
        new_assets = list(current_assets)

        regen_tasks = []
        for scene_id in critic_output.regenerate_list:
            issue = issue_map.get(scene_id)
            if not issue:
                continue
            new_prompt = issue.alternative_prompt or issue.fix_suggestion
            regen_tasks.append((scene_id, new_prompt))

        # Execute regenerations concurrently (respecting rate limits)
        regenerated = await asyncio.gather(
            *[self._regen_single(sid, prompt, assets_by_scene.get(sid)) for sid, prompt in regen_tasks],
            return_exceptions=True,
        )

        for i, (scene_id, _) in enumerate(regen_tasks):
            if isinstance(regenerated[i], Exception):
                logger.error(f"Regen failed for scene {scene_id}: {regenerated[i]}")
                continue
            # Update the asset for this scene_id
            new_asset: DraftAsset = regenerated[i]
            for j, asset in enumerate(new_assets):
                if asset.scene_id == scene_id:
                    new_assets[j] = new_asset
                    break

        return new_assets

    async def _regen_single(
        self,
        scene_id: int,
        prompt: str,
        existing_asset: Optional[DraftAsset],
    ) -> DraftAsset:
        """Regenerate a single scene asset, using cache if available."""
        import hashlib
        cache_key = hashlib.md5(prompt.encode()).hexdigest()

        if cache_key in self._prompt_cache:
            logger.info(f"[Cache HIT] Scene {scene_id} reusing cached asset")
            return DraftAsset(
                scene_id=scene_id,
                image_url=self._prompt_cache[cache_key],
                prompt_used=prompt,
            )

        # For MVP: return the asset with updated prompt (actual generation 
        # happens via the image_service in the full workflow integration)
        # In production: call image_service.generate_image(..., prompt=prompt)
        logger.info(f"[Regen] Scene {scene_id} would regenerate with: {prompt[:80]}...")

        new_asset = DraftAsset(
            scene_id=scene_id,
            image_url=existing_asset.image_url if existing_asset else None,
            prompt_used=prompt,
        )

        if new_asset.image_url:
            self._prompt_cache[cache_key] = new_asset.image_url

        return new_asset
