"""
OrchestrAI Full Pipeline Orchestrator

Chains all 7 agents in sequence with the iterative feedback loop:

  ScriptEngineer → ScenePlanner → AssetOrchestrator → DraftAssembler
      → Critic → if score < threshold: Replanner → selective regen
      → SafetyAgent → store result

Replaces/extends the existing orchestrator/pipeline.py which only
handled the draft→critic→replan sub-loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from orchestrator.job_manager import JobManager, JobStage, SceneStatus, job_manager
from services.agents.asset_orchestrator import AssetOrchestratorAgent
from services.agents.draft_assembler import DraftAssemblerAgent
from services.agents.replanner import ReplannerAgent
from services.agents.safety_agent import SafetyPolicyAgent
from services.agents.scene_planner import ScenePlannerAgent
from services.agents.script_engineer import ScriptEngineerAgent
from services.ai_service import AIService
from services.critic import CriticInput, CriticService, DraftAsset, SceneMetadata
from core.storage import LocalStorage

logger = logging.getLogger(__name__)


class OrchestrAIPipeline:
    """
    Full 7-agent OrchestrAI pipeline with iterative refinement.
    """

    def __init__(
        self,
        ai_service: AIService,
        storage: LocalStorage,
        score_threshold: float = 7.5,
        max_iterations: int = 3,
        use_polly: bool = False,
    ):
        # Instantiate all agents
        self.script_engineer = ScriptEngineerAgent(ai_service)
        self.scene_planner = ScenePlannerAgent(ai_service)
        self.asset_orchestrator = AssetOrchestratorAgent(ai_service)
        self.draft_assembler = DraftAssemblerAgent(storage, use_polly=use_polly)
        self.critic = CriticService(ai_service=ai_service, score_threshold=score_threshold)
        self.replanner = ReplannerAgent(ai_service)
        self.safety_agent = SafetyPolicyAgent(ai_service)
        self.storage = storage
        self.score_threshold = score_threshold
        self.max_iterations = max_iterations

    async def run(
        self,
        job_id: str,
        raw_content: str,
        title: str = "",
        language: str = "en",
        tone: str = "neutral",
        genre: str = "general",
        character_descriptions: list[dict] = None,
    ) -> dict:
        """Execute the full OrchestrAI pipeline for a given job."""
        jm = job_manager
        job = jm.get(job_id)
        if not job:
            raise ValueError(f"Job {job_id} not found")

        try:
            # ── Stage 1: Script Engineer ──────────────────────────────────
            jm.update_stage(job_id, JobStage.SCRIPT)
            logger.info(f"[{job_id}] Stage 1: Script Engineer")
            script = await self.script_engineer.run(
                raw_content=raw_content,
                title=title,
                language=language,
                tone=tone,
            )
            job.script = script.to_dict()
            job.touch()

            # ── Stage 2: Scene Planner ────────────────────────────────────
            jm.update_stage(job_id, JobStage.VISUAL)
            logger.info(f"[{job_id}] Stage 2: Scene Planner ({len(script.scenes)} scenes)")
            visual_plans = await self.scene_planner.run(
                scenes=script.scenes,
                genre=genre,
                language=language,
                tone=tone,
                character_descriptions=character_descriptions,
                script_hook=script.hook,
                script_cta=script.cta,
            )
            job.visual_plans = [p.to_dict() for p in visual_plans]
            job.scenes = [SceneStatus(scene_id=p.scene_id, stage="pending") for p in visual_plans]
            job.touch()

            # ── Stage 3: Asset Orchestrator ───────────────────────────────
            logger.info(f"[{job_id}] Stage 3: Asset Orchestrator")
            assets = await self.asset_orchestrator.run(job_id=job_id, visual_plans=visual_plans)
            for a in assets:
                for sc in job.scenes:
                    if sc.scene_id == a.scene_id:
                        sc.image_url = a.image_url
                        sc.stage = "generated"
            job.touch()

            # ── Stage 4: Draft Assembler ──────────────────────────────────
            jm.update_stage(job_id, JobStage.ASSEMBLY)
            logger.info(f"[{job_id}] Stage 4: Draft Assembler")
            draft = await self.draft_assembler.run(script=script, assets=assets, job_id=job_id)
            job.draft_result = draft.to_dict()
            job.touch()

            # ── Iterative Critique Loop ───────────────────────────────────
            current_plans = visual_plans
            current_assets = assets

            for iteration in range(1, self.max_iterations + 1):
                jm.update_stage(job_id, JobStage.CRITIQUE)
                logger.info(f"[{job_id}] Iteration {iteration}: Critic evaluation")
                job.current_iteration = iteration

                critic_input = CriticInput(
                    script_json=job.script,
                    scene_metadata=[
                        SceneMetadata(
                            scene_id=p.scene_id,
                            location="",
                            time="",
                            action=p.visual_prompt,
                        ) for p in current_plans
                    ],
                    draft_assets=[
                        DraftAsset(
                            scene_id=a.scene_id,
                            image_url=a.image_url,
                            prompt_used=a.prompt_used,
                        ) for a in current_assets
                    ],
                    timings=[s.duration for s in script.scenes],
                )

                critic_output = await self.critic.evaluate(critic_input)
                job.critic_score = critic_output.total_score

                # Update per-scene scores
                for i, score in enumerate(critic_output.scene_scores):
                    if i < len(job.scenes):
                        job.scenes[i].score = score
                        job.scenes[i].iteration = iteration

                for issue in critic_output.issues:
                    for sc in job.scenes:
                        if sc.scene_id == issue.scene_id:
                            sc.issue = issue.reason

                logger.info(f"[{job_id}] Critic score: {critic_output.total_score:.1f}/10 | Threshold: {self.score_threshold}/10 | Regen: {critic_output.regenerate_list}")
                job.touch()

                # Pass → exit loop: BOTH conditions must be true
                # Score must be above threshold AND no scenes need regeneration
                score_ok = critic_output.total_score >= self.score_threshold
                nothing_to_regen = not critic_output.regenerate_list
                if score_ok and nothing_to_regen:
                    logger.info(f"[{job_id}] ✅ Quality threshold met at iteration {iteration} (score={critic_output.total_score:.1f})")
                    break

                if score_ok and not nothing_to_regen:
                    logger.info(f"[{job_id}] Score passed but {len(critic_output.regenerate_list)} scenes still flagged — continuing to replan")
                elif not score_ok:
                    logger.info(f"[{job_id}] Score {critic_output.total_score:.1f} below threshold {self.score_threshold} — replanning")

                # Fail → Replanner (run on every failing iteration, including the last)
                jm.update_stage(job_id, JobStage.REFINING)
                logger.info(f"[{job_id}] Iteration {iteration}: Replanning {len(critic_output.regenerate_list)} scenes")

                # Re-run planner for flagged scenes — method is run(), returns ReplanResult
                replan_result = await self.replanner.run(
                    original_plans=current_plans,
                    critic_output=critic_output,
                    language=language,
                )
                new_plans = replan_result.revised_plans

                # Merge revised plans back
                revised_map = {p.scene_id: p for p in new_plans}
                current_plans = [revised_map.get(p.scene_id, p) for p in current_plans]

                # Selective regeneration
                new_assets = await self.asset_orchestrator.run_selective(
                    job_id=job_id,
                    visual_plans=new_plans,
                    scene_ids=critic_output.regenerate_list,
                )
                asset_map = {a.scene_id: a for a in new_assets}
                current_assets = [asset_map.get(a.scene_id, a) for a in current_assets]

                for sc in job.scenes:
                    if sc.scene_id in critic_output.regenerate_list:
                        sc.stage = "regenerated"
                job.touch()

                # Re-assemble the draft video with the improved assets if not on last iteration
                if iteration < self.max_iterations:
                    jm.update_stage(job_id, JobStage.ASSEMBLY)
                    logger.info(f"[{job_id}] Re-assembling draft after iteration {iteration}")
                    draft = await self.draft_assembler.run(script=script, assets=current_assets, job_id=job_id)
                    job.draft_result = draft.to_dict()
                    job.touch()

            # ── Stage 5: Safety Agent ─────────────────────────────────────
            jm.update_stage(job_id, JobStage.SAFETY)
            logger.info(f"[{job_id}] Stage 5: Safety check")
            script_text = " ".join(s.text for s in script.scenes)
            visual_texts = [p.visual_prompt for p in current_plans]
            safety = await self.safety_agent.run(script_text, visual_texts, language)
            job.safety_result = safety.to_dict()
            job.ai_disclosure = safety.ai_disclosure_tag
            job.touch()

            if not safety.passed:
                logger.warning(f"[{job_id}] Safety check FAILED: {safety.violations}")
                jm.set_error(job_id, f"Safety violations: {[v.description for v in safety.violations]}")
                return job.to_dict()

            # ── Done ──────────────────────────────────────────────────────
            job.download_url = f"/static/jobs/{job_id}/draft.mp4"
            job.thumbnail_url = f"/static/jobs/{job_id}/thumbnail.jpg"
            jm.update_stage(job_id, JobStage.DONE)
            logger.info(f"[{job_id}] Pipeline complete! Score: {job.critic_score:.1f}")
            return job.to_dict()

        except Exception as e:
            logger.exception(f"[{job_id}] Pipeline failed: {e}")
            jm.set_error(job_id, str(e))
            return job.to_dict()
