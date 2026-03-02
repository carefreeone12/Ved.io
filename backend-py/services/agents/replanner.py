"""
Agent 6 — Replanner Agent

Receives Critic output and modifies only the failing scenes:
  - Adjusts visual prompts based on fix suggestions
  - Optionally extends duration for pacing issues
  - Triggers selective regeneration via AssetOrchestrator

This makes the system cost-efficient: only bad scenes are re-generated,
not the entire video.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from services.ai_service import AIService
from services.agents.scene_planner import VisualPlan
from services.critic import CriticOutput, SceneIssue


@dataclass
class ReplanResult:
    revised_plans: list[VisualPlan] = field(default_factory=list)
    scene_ids_to_regenerate: list[int] = field(default_factory=list)
    reasoning: dict[int, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "revised_plans": [p.to_dict() for p in self.revised_plans],
            "scene_ids_to_regenerate": self.scene_ids_to_regenerate,
            "reasoning": {str(k): v for k, v in self.reasoning.items()},
        }


class ReplannerAgent:
    """
    Agent 6: Revises failing scene plans based on Critic feedback.
    Only touches scenes flagged in critic_output.regenerate_list.
    """

    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service

    async def run(
        self,
        original_plans: list[VisualPlan],
        critic_output: CriticOutput,
        language: str = "en",
    ) -> ReplanResult:
        """Generate revised visual plans for scenes that failed critic evaluation."""
        if not critic_output.regenerate_list:
            return ReplanResult()

        # Map scene_id → original plan
        plan_map = {p.scene_id: p for p in original_plans}
        # Map scene_id → issue
        issue_map = {issue.scene_id: issue for issue in critic_output.issues}

        revised_plans: list[VisualPlan] = []
        reasoning: dict[int, str] = {}

        for scene_id in critic_output.regenerate_list:
            original = plan_map.get(scene_id)
            issue = issue_map.get(scene_id)

            if not original:
                continue

            # If the critic already provided an alternative_prompt, use it directly
            if issue and issue.alternative_prompt:
                revised = VisualPlan(
                    scene_id=scene_id,
                    visual_prompt=issue.alternative_prompt,
                    keywords=original.keywords,
                    style=original.style,
                    negative_prompt=original.negative_prompt,
                    aspect_ratio=original.aspect_ratio,
                )
                reasoning[scene_id] = f"Used critic's alternative prompt. Issue: {issue.reason}"
            else:
                # Ask LLM to rewrite the prompt based on the issue
                revised = await self._llm_revise(original, issue, language)
                reasoning[scene_id] = issue.fix_suggestion if issue else "Low score — prompt revised"

            revised_plans.append(revised)

        return ReplanResult(
            revised_plans=revised_plans,
            scene_ids_to_regenerate=critic_output.regenerate_list,
            reasoning=reasoning,
        )

    async def _llm_revise(
        self,
        original: VisualPlan,
        issue: SceneIssue | None,
        language: str,
    ) -> VisualPlan:
        """Use LLM to rewrite a failing visual prompt."""
        issue_text = f"Issue: {issue.reason}\nFix suggestion: {issue.fix_suggestion}" if issue else "The image was low quality or misaligned."

        prompt = f"""You are a visual prompt revision expert.

The following AI image generation prompt produced a poor result:
Original prompt: "{original.visual_prompt}"

{issue_text}

Rewrite the prompt to fix the issue. Be more specific about:
- Subject positioning and composition
- Lighting and color
- Camera angle
- Action and emotion

Return ONLY a JSON object:
{{
  "revised_prompt": "The improved prompt here",
  "reason": "What you changed and why"
}}"""

        response = await self.ai_service.generate_text(prompt)
        cleaned = re.sub(r"```(?:json)?", "", response).strip().strip("`")

        import json_repair
        try:
            data = json_repair.loads(cleaned)
            new_prompt = data.get("revised_prompt", original.visual_prompt) if isinstance(data, dict) else original.visual_prompt
        except Exception:
            # Fallback: prepend quality boost keywords
            new_prompt = f"ultra detailed, 8K, cinematic, {original.visual_prompt}"

        return VisualPlan(
            scene_id=original.scene_id,
            visual_prompt=new_prompt,
            keywords=original.keywords,
            style=original.style,
            negative_prompt=original.negative_prompt,
            aspect_ratio=original.aspect_ratio,
        )
