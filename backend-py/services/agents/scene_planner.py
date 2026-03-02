"""
Agent 2 — Scene Planner Agent

Converts scene text → visual instructions with full narrative context:
  { scene_id, visual_prompt, keywords, style, negative_prompt, mood, shot_type, color_palette }

Two-pass approach:
  Pass 1: Extract a "Visual Bible" (characters, locations, art style) from the full script
  Pass 2: Generate per-scene prompts that reference the Visual Bible for cross-scene consistency

Ensures visual consistency and cultural alignment across all scenes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from services.ai_service import AIService
from services.agents.script_engineer import ScriptScene


@dataclass
class VisualPlan:
    scene_id: int
    visual_prompt: str
    keywords: list[str] = field(default_factory=list)
    style: str = "cinematic"
    negative_prompt: str = "blurry, low quality, text overlay, watermark, western"
    aspect_ratio: str = "16:9"
    mood: str = ""
    shot_type: str = "medium shot"
    color_palette: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scene_id": self.scene_id,
            "visual_prompt": self.visual_prompt,
            "keywords": self.keywords,
            "style": self.style,
            "negative_prompt": self.negative_prompt,
            "aspect_ratio": self.aspect_ratio,
            "mood": self.mood,
            "shot_type": self.shot_type,
            "color_palette": self.color_palette,
        }


CULTURAL_CONTEXT = {
    "hi": "Indian setting, vibrant colors, traditional + modern fusion, relatable to urban and semi-urban India",
    "te": "Telugu cultural context, Andhra or Telangana setting, culturally authentic visuals",
    "ta": "Tamil cultural context, South Indian setting, authentic regional aesthetics",
    "mr": "Maharashtrian cultural context, Pune/Mumbai setting, authentic regional aesthetics",
    "bn": "Bengali cultural aesthetics, West Bengal setting, culturally authentic visuals",
    "en": "Modern, clean, globally relatable visuals",
}

STYLE_PRESETS = {
    "educational": "clean whiteboard animation, infographic style, bright lighting, professional",
    "motivational": "dynamic, high energy, bold colors, dramatic lighting, cinematic",
    "storytelling": "documentary style, natural lighting, authentic human emotion, photorealistic",
    "neutral": "cinematic, professional, 4K quality, studio lighting",
    "conversational": "casual setting, natural light, warm tones, approachable",
}

VISUAL_BIBLE_PROMPT = """You are a visual development artist. Analyze this script and extract a "Visual Bible" — a consistent visual reference guide for all image generation.

Script Hook: {hook}
Script Story: {story}
Script CTA: {cta}
Genre: {genre}
Language/Culture: {language}

Extract and return ONLY valid JSON (no markdown):
{{
  "characters": [
    {{
      "name": "character name",
      "description": "detailed physical appearance, age, clothing style, distinguishing features"
    }}
  ],
  "primary_location": "detailed description of the main setting: architecture, environment, time period, time of day, lighting",
  "art_style": "overall visual style: photorealistic/illustrated/cinematic, color grading, film stock, era",
  "color_palette": "dominant colors and mood: e.g. deep blues and gold tones, warm amber, cold desaturated",
  "recurring_elements": "props, symbols, or visual motifs that should appear consistently across scenes"
}}"""

SCENE_PROMPT = """You are a visual director creating AI image prompts for a video. Use the Visual Bible below to ensure ALL images are consistent in character appearance, location, and art style.

=== VISUAL BIBLE (maintain consistency with this) ===
{visual_bible}

=== FULL STORY CONTEXT ===
Hook: {hook}
CTA: {cta}
Genre: {genre}
Cultural context: {cultural_ctx}
Visual style: {style_hint}

=== SCENES TO VISUALIZE ===
{scenes_json}

For each scene, create an image prompt that:
1. Shows the characters from the Visual Bible (use EXACT appearance descriptions)
2. Uses the established location/setting from the Visual Bible
3. Captures the EMOTIONAL BEAT and DRAMATIC TENSION of the scene — not just the literal words
4. Specifies the right shot type: CLOSE-UP for intense emotion/dialogue, MEDIUM for action/interaction, WIDE for establishing location/scale
5. Stays true to the Visual Bible's color palette and art style

Return ONLY valid JSON array (no markdown):
[
  {{
    "scene_id": 1,
    "visual_prompt": "A precise 50-80 word description referencing the exact characters, location and emotional tone of the scene",
    "keywords": ["keyword1", "keyword2", "keyword3"],
    "style": "cinematic",
    "negative_prompt": "blurry, low quality, text overlay, watermark, inconsistent style",
    "mood": "tense/joyful/melancholic/epic/intimate/etc",
    "shot_type": "close-up/medium shot/wide shot/over-the-shoulder",
    "color_palette": "specific color description matching the Visual Bible"
  }}
]"""


class ScenePlannerAgent:
    """
    Agent 2: Converts scene text into visual prompt instructions.
    
    Uses a two-pass approach:
      Pass 1: Build a Visual Bible (characters, locations, style guide)
      Pass 2: Generate per-scene prompts that are anchored to the Visual Bible
               for cross-scene consistency in characters and environments.
    """

    def __init__(self, ai_service: AIService):
        self.ai_service = ai_service

    async def run(
        self,
        scenes: list[ScriptScene],
        genre: str = "general",
        language: str = "en",
        tone: str = "neutral",
        character_descriptions: list[dict] = None,
        script_hook: str = "",
        script_cta: str = "",
    ) -> list[VisualPlan]:
        """Generate visual plans for all scenes with cross-scene consistency."""
        cultural_ctx = CULTURAL_CONTEXT.get(language, CULTURAL_CONTEXT["en"])
        style_hint = STYLE_PRESETS.get(tone, STYLE_PRESETS["neutral"])
        story_text = " ".join(s.text for s in scenes)

        # ── Pass 1: Extract Visual Bible ────────────────────────────────────
        visual_bible = await self._extract_visual_bible(
            hook=script_hook,
            story=story_text,
            cta=script_cta,
            genre=genre,
            language=language,
            character_descriptions=character_descriptions,
        )

        # ── Pass 2: Generate per-scene prompts using the Visual Bible ────────
        scenes_json = json.dumps(
            [{"id": s.id, "text": s.text} for s in scenes],
            ensure_ascii=False
        )

        prompt = SCENE_PROMPT.format(
            visual_bible=json.dumps(visual_bible, ensure_ascii=False, indent=2),
            hook=script_hook or "(none)",
            cta=script_cta or "(none)",
            genre=genre,
            cultural_ctx=cultural_ctx,
            style_hint=style_hint,
            scenes_json=scenes_json,
        )

        response = await self.ai_service.generate_text(prompt, max_tokens=2048)
        return self._parse_response(response)

    async def _extract_visual_bible(
        self,
        hook: str,
        story: str,
        cta: str,
        genre: str,
        language: str,
        character_descriptions: list[dict] = None,
    ) -> dict:
        """Pass 1: Extract Visual Bible from the script for cross-scene consistency."""
        # If characters were explicitly provided, use them directly
        if character_descriptions:
            chars = [
                {"name": c.get("name", "Unknown"), "description": c.get("appearance", "")}
                for c in character_descriptions
            ]
            return {
                "characters": chars,
                "primary_location": "as described in the script",
                "art_style": "cinematic, photorealistic",
                "color_palette": "natural, cinematic",
                "recurring_elements": "",
            }

        prompt = VISUAL_BIBLE_PROMPT.format(
            hook=hook or "(none)",
            story=story[:1500],
            cta=cta or "(none)",
            genre=genre,
            language=language,
        )

        try:
            response = await self.ai_service.generate_text(prompt, max_tokens=512)
            import json_repair
            cleaned = re.sub(r"```(?:json)?", "", response).strip().strip("`").strip()
            return json_repair.loads(cleaned)
        except Exception:
            # Graceful fallback — empty bible won't break the pipeline
            return {
                "characters": [],
                "primary_location": "contemporary setting",
                "art_style": "cinematic, photorealistic",
                "color_palette": "natural, cinematic tones",
                "recurring_elements": "",
            }

    def _parse_response(self, response: str) -> list[VisualPlan]:
        """Parse LLM JSON array response into list of VisualPlan."""
        import json_repair
        cleaned = re.sub(r"```(?:json)?", "", response).strip().strip("`").strip()

        try:
            data = json_repair.loads(cleaned)
            if not isinstance(data, list):
                match = re.search(r"\[.*\]", cleaned, re.DOTALL)
                if match:
                    data = json_repair.loads(match.group())
                else:
                    data = [data] if data else []
        except Exception:
            raise ValueError(f"ScenePlannerAgent returned invalid JSON: {response[:200]}")

        return [
            VisualPlan(
                scene_id=item["scene_id"],
                visual_prompt=item.get("visual_prompt", ""),
                keywords=item.get("keywords", []),
                style=item.get("style", "cinematic"),
                negative_prompt=item.get("negative_prompt", "blurry, low quality, text, watermark"),
                aspect_ratio=item.get("aspect_ratio", "16:9"),
                mood=item.get("mood", ""),
                shot_type=item.get("shot_type", "medium shot"),
                color_palette=item.get("color_palette", ""),
            )
            for item in data
        ]
