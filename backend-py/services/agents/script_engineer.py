"""
Agent 1 — Script Engineer Agent (Planner Agent)

Converts raw/long-form content into a structured video script:
  { hook, scenes: [{id, text, duration}], cta }

Supports multilingual output for Indian regional languages.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from services.ai_service import AIService


@dataclass
class ScriptScene:
    id: int
    text: str
    duration: int = 6  # seconds


@dataclass
class StructuredScript:
    hook: str
    scenes: list[ScriptScene] = field(default_factory=list)
    cta: str = ""
    language: str = "en"
    tone: str = "neutral"

    def to_dict(self) -> dict[str, Any]:
        return {
            "hook": self.hook,
            "scenes": [{"id": s.id, "text": s.text, "duration": s.duration} for s in self.scenes],
            "cta": self.cta,
            "language": self.language,
            "tone": self.tone,
        }


LANGUAGE_INSTRUCTIONS = {
    "hi": "Respond entirely in Hindi (Devanagari script). Make it culturally relevant for Indian audiences.",
    "te": "Respond entirely in Telugu. Make it culturally relevant for Telugu-speaking audiences.",
    "ta": "Respond entirely in Tamil. Make it culturally relevant for Tamil-speaking audiences.",
    "mr": "Respond entirely in Marathi. Make it culturally relevant for Marathi-speaking audiences.",
    "bn": "Respond entirely in Bengali. Make it culturally relevant for Bengali-speaking audiences.",
    "en": "Respond in clear, simple English. Make it engaging for a general audience.",
}

TONE_INSTRUCTIONS = {
    "educational": "Use a calm, informative, and authoritative tone. Focus on clarity.",
    "motivational": "Use an energetic, inspiring tone. Include power words and emotional hooks.",
    "storytelling": "Use a narrative tone. Build emotional connection through human stories.",
    "neutral": "Use a balanced, professional tone.",
    "conversational": "Use a friendly, casual tone as if speaking directly to the viewer.",
}


class ScriptEngineerAgent:
    """
    Agent 1: Converts raw content into a structured video script.
    Output JSON: { hook, scenes: [{id, text, duration}], cta }
    """

    def __init__(self, ai_service: AIService, max_scenes: int = 8):
        self.ai_service = ai_service
        self.max_scenes = max_scenes

    async def run(
        self,
        raw_content: str,
        title: str = "",
        language: str = "en",
        tone: str = "neutral",
        target_duration_sec: int = 60,
    ) -> StructuredScript:
        """Convert raw content to structured script."""
        lang_instruction = LANGUAGE_INSTRUCTIONS.get(language, LANGUAGE_INSTRUCTIONS["en"])
        tone_instruction = TONE_INSTRUCTIONS.get(tone, TONE_INSTRUCTIONS["neutral"])

        prompt = f"""You are an expert video script writer for short-form content (30-90 seconds).

{lang_instruction}
Tone: {tone_instruction}

Raw content to convert:
\"\"\"
{raw_content[:4000]}
\"\"\"

Create a structured video script. Target total duration: {target_duration_sec} seconds.
Maximum {self.max_scenes} scenes. Each scene should be 4-10 seconds.

Return ONLY valid JSON in this exact format:
{{
  "hook": "Attention-grabbing opening line (max 15 words)",
  "scenes": [
    {{"id": 1, "text": "Scene narration text", "duration": 6}},
    {{"id": 2, "text": "Scene narration text", "duration": 7}}
  ],
  "cta": "Clear call-to-action at the end"
}}

Rules:
- Hook must grab attention in first 3 seconds
- Each scene text should be speakable in exactly 'duration' seconds
- Total duration of all scenes should be approximately {target_duration_sec} seconds
- CTA must be direct and actionable
- No markdown, no explanation — just the JSON object"""

        response = await self.ai_service.generate_text(prompt)
        return self._parse_response(response, language, tone)

    def _parse_response(self, response: str, language: str, tone: str) -> StructuredScript:
        """Parse LLM JSON response into StructuredScript."""
        import json_repair
        # Strip markdown fences
        cleaned = re.sub(r"```(?:json)?", "", response).strip().strip("`").strip()

        try:
            data = json_repair.loads(cleaned)
            if not isinstance(data, dict):
                match = re.search(r"\{.*\}", cleaned, re.DOTALL)
                if match:
                    data = json_repair.loads(match.group())
                else:
                    data = {}
        except Exception:
            raise ValueError(f"ScriptEngineerAgent returned invalid JSON: {response[:200]}")

        scenes = []
        for i, s in enumerate(data.get("scenes", [])):
            scene_id = s.get("id") or s.get("scene_id") or (i + 1)
            text = s.get("text", "")
            duration = int(s.get("duration", 6))
            scenes.append(ScriptScene(id=scene_id, text=text, duration=duration))

        return StructuredScript(
            hook=data.get("hook", ""),
            scenes=scenes,
            cta=data.get("cta", ""),
            language=language,
            tone=tone,
        )
