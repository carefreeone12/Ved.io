"""
Iterative Feedback Generator — Critic Service.
Evaluates draft scene assets using an LLM and returns per-scene scores + fix suggestions.

This is a NEW module with no Go equivalent.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel

from services.ai_service import AIService

logger = logging.getLogger(__name__)


# ---------- Contracts ----------

class SceneMetadata(BaseModel):
    scene_id: int
    location: str
    time: str
    action: Optional[str] = None
    dialogue: Optional[str] = None


class DraftAsset(BaseModel):
    scene_id: int
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    prompt_used: Optional[str] = None


class SceneIssue(BaseModel):
    scene_id: int
    reason: str
    fix_suggestion: str
    alternative_prompt: Optional[str] = None


class CriticInput(BaseModel):
    script_json: dict
    scene_metadata: list[SceneMetadata]
    draft_assets: list[DraftAsset]
    timings: list[float] = []


class CriticOutput(BaseModel):
    scene_scores: list[float]       # 0–10 per scene
    total_score: float
    issues: list[SceneIssue]
    regenerate_list: list[int]      # scene IDs to regenerate
    iteration: int = 0


CRITIC_SYSTEM_PROMPT = """You are an expert AI film critic and quality assurance engineer.
Your task is to evaluate AI-generated drama scene assets for quality and coherence.

For each scene, score it 0-10 on these dimensions:
1. Semantic alignment: Does the visual match the script/action?
2. Consistency: Are characters/locations consistent with other scenes?
3. Pacing: Is the shot duration and framing appropriate?
4. Quality: Is the visual prompt likely to produce a good image/video?

IMPORTANT GUIDELINES:
- Do not be overly pedantic about minor textual differences between the scene description and the image prompt.
- As long as the core semantic meaning and visual subject are captured, the prompt is successful. Score it >= 8.
- Only flag a scene for regeneration (< 7) if there is a severe logical contradiction or missing critical subject.

Return a JSON object with this exact structure:
{
  "scene_scores": [<float per scene>],
  "total_score": <float average>,
  "issues": [
    {
      "scene_id": <int>,
      "reason": "<what is wrong>",
      "fix_suggestion": "<how to fix it>",
      "alternative_prompt": "<better image/video prompt>"
    }
  ],
  "regenerate_list": [<scene_ids with score < threshold>]
}

Be strict but fair. Scores below 7 should be flagged and included in regenerate_list.
Do NOT include any extra text, only return the raw JSON object."""


class CriticService:
    """
    LLM-based scene critic. Evaluates draft assets and flags scenes for regeneration.
    """

    def __init__(self, ai_service: AIService, score_threshold: float = 7.0) -> None:
        self.ai_service = ai_service
        self.score_threshold = score_threshold

    async def evaluate(self, critic_input: CriticInput) -> CriticOutput:
        """
        Evaluate all scenes and return scores + regeneration list.
        """
        prompt = self._build_prompt(critic_input)

        try:
            response = await self.ai_service.generate_text(
                prompt=prompt,
                system_prompt=CRITIC_SYSTEM_PROMPT,
                temperature=0.3,   # Low temperature for consistent scoring
                max_tokens=4096,
            )
            return self._parse_response(response, critic_input)
        except Exception as e:
            logger.error(f"Critic evaluation failed: {e}", exc_info=True)
            # Return a safe default — all scenes need regeneration
            n = len(critic_input.scene_metadata)
            return CriticOutput(
                scene_scores=[0.0] * n,
                total_score=0.0,
                issues=[
                    SceneIssue(
                        scene_id=sm.scene_id,
                        reason=f"Critic evaluation error: {e}",
                        fix_suggestion="Re-run critic after fixing the error",
                    )
                    for sm in critic_input.scene_metadata
                ],
                regenerate_list=[sm.scene_id for sm in critic_input.scene_metadata],
            )

    def _build_prompt(self, ci: CriticInput) -> str:
        """Build the evaluation prompt from critic input."""
        scene_details = []
        for i, sm in enumerate(ci.scene_metadata):
            asset = next((a for a in ci.draft_assets if a.scene_id == sm.scene_id), None)
            timing = ci.timings[i] if i < len(ci.timings) else 5.0

            scene_details.append(f"""
Scene {i + 1} (ID: {sm.scene_id}):
  Location: {sm.location}
  Time: {sm.time}
  Action: {sm.action or 'N/A'}
  Dialogue: {sm.dialogue or 'N/A'}
  Duration: {timing}s
  Image prompt used: {asset.prompt_used if asset else 'N/A'}
  Has image: {'Yes' if asset and asset.image_url else 'No'}
  Has video: {'Yes' if asset and asset.video_url else 'No'}""")

        return f"""Drama script summary:
{json.dumps(ci.script_json, ensure_ascii=False, indent=2)[:2000]}

Scene breakdown:
{''.join(scene_details)}

Score threshold for pass: {self.score_threshold}/10
Please evaluate all {len(ci.scene_metadata)} scenes and return the JSON result."""

    def _parse_response(self, response: str, ci: CriticInput) -> CriticOutput:
        """Parse LLM response into CriticOutput."""
        response = response.strip()
        if response.startswith("```"):
            response = response.split("```")[1]
            if response.startswith("json"):
                response = response[4:]

        import json_repair
        try:
            data = json_repair.loads(response)
        except Exception:
            data = {}
            
        scores = data.get("scene_scores", [5.0] * len(ci.scene_metadata)) if isinstance(data, dict) else [5.0] * len(ci.scene_metadata)
        total = data.get("total_score", sum(scores) / max(len(scores), 1)) if isinstance(data, dict) else sum(scores) / max(len(scores), 1)

        # Normalize scores: if the LLM returned 0-100 scale, convert to 0-10
        # Heuristic: if any score > 10, the LLM used a 0-100 scale
        if scores and max(scores) > 10:
            scores = [min(s / 10.0, 10.0) for s in scores]
            total = total / 10.0 if total > 10 else total
        # Recompute total from normalized scores for consistency
        total = sum(scores) / max(len(scores), 1)

        issues = [
            SceneIssue(
                scene_id=iss["scene_id"],
                reason=iss.get("reason", ""),
                fix_suggestion=iss.get("fix_suggestion", ""),
                alternative_prompt=iss.get("alternative_prompt"),
            )
            for iss in data.get("issues", [])
        ]

        # Ensure regenerate_list includes all scenes below threshold
        regenerate_list = list(data.get("regenerate_list", []))
        for i, (score, sm) in enumerate(zip(scores, ci.scene_metadata)):
            if score < self.score_threshold and sm.scene_id not in regenerate_list:
                regenerate_list.append(sm.scene_id)

        return CriticOutput(
            scene_scores=scores,
            total_score=total,
            issues=issues,
            regenerate_list=regenerate_list,
        )
