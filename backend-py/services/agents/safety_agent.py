"""
Agent 7 — Safety & Policy Agent

Ensures all generated content is safe, compliant, and properly tagged:
  - Rule-based keyword filter (hate speech, misinformation triggers)
  - LLM-based semantic safety evaluation
  - Tags final video metadata with AI-generation disclosure
  - Returns SafetyResult: { passed, violations, content_warnings, ai_disclosure_tag }

Combines rule-based + LLM evaluation as described in OrchestrAI spec.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.ai_service import AIService


# Rule-based blocklist (extend as needed)
_BLOCKLIST_PATTERNS = [
    r"\b(hate|kill|murder|terrorist|bomb|drug trafficking)\b",
    r"\b(fake news|misinformation|propaganda)\b",
    r"\b(explicit|pornographic|adult content)\b",
    r"\b(child abuse|CSAM)\b",
]

_COMPILED_BLOCKLIST = [re.compile(p, re.IGNORECASE) for p in _BLOCKLIST_PATTERNS]


@dataclass
class SafetyViolation:
    type: str
    description: str
    scene_id: int | None = None


@dataclass
class SafetyResult:
    passed: bool
    violations: list[SafetyViolation] = field(default_factory=list)
    content_warnings: list[str] = field(default_factory=list)
    ai_disclosure_tag: str = "Generated with AI assistance. OrchestrAI."
    safety_score: float = 100.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": [{"type": v.type, "description": v.description, "scene_id": v.scene_id} for v in self.violations],
            "content_warnings": self.content_warnings,
            "ai_disclosure_tag": self.ai_disclosure_tag,
            "safety_score": self.safety_score,
        }


class SafetyPolicyAgent:
    """
    Agent 7: Safety and policy compliance checker.
    Blocks harmful content before final delivery.
    """

    def __init__(self, ai_service: AIService, llm_safety_enabled: bool = True):
        self.ai_service = ai_service
        self.llm_safety_enabled = llm_safety_enabled

    async def run(
        self,
        script_text: str,
        visual_prompts: list[str],
        language: str = "en",
    ) -> SafetyResult:
        """Run all safety checks on the generated content."""
        violations: list[SafetyViolation] = []
        content_warnings: list[str] = []

        # 1. Rule-based check on script text
        rule_violations = self._rule_based_check(script_text, "script")
        violations.extend(rule_violations)

        # 2. Rule-based check on each visual prompt
        for i, prompt in enumerate(visual_prompts):
            pv = self._rule_based_check(prompt, f"visual_prompt_scene_{i+1}")
            violations.extend(pv)

        # 3. LLM semantic safety evaluation
        if self.llm_safety_enabled and not violations:
            llm_result = await self._llm_safety_check(script_text, language)
            if llm_result:
                violations.extend(llm_result)

        # 4. Build result
        passed = len(violations) == 0
        safety_score = max(0.0, 100.0 - len(violations) * 25.0)

        # 5. Add content warnings for borderline content (not block-worthy)
        if any("propaganda" in v.description.lower() for v in violations):
            content_warnings.append("Content may contain politically sensitive material.")

        return SafetyResult(
            passed=passed,
            violations=violations,
            content_warnings=content_warnings,
            ai_disclosure_tag="Generated with AI assistance | OrchestrAI | Powered by Generative AI",
            safety_score=safety_score,
        )

    def _rule_based_check(self, text: str, source: str) -> list[SafetyViolation]:
        """Apply compiled regex blocklist patterns."""
        violations = []
        for pattern in _COMPILED_BLOCKLIST:
            match = pattern.search(text)
            if match:
                violations.append(SafetyViolation(
                    type="rule_based_violation",
                    description=f"Blocked pattern '{match.group()}' found in {source}",
                    scene_id=None,
                ))
        return violations

    async def _llm_safety_check(self, text: str, language: str) -> list[SafetyViolation]:
        """LLM semantic safety evaluation for subtle violations."""
        prompt = f"""You are a content safety reviewer. Evaluate the following video script for:
1. Misinformation or false claims
2. Hate speech or discrimination (especially against Indian communities/religions)
3. Glorification of violence or illegal activities
4. Inappropriate content for general audiences

Script (language: {language}):
\"\"\"
{text[:3000]}
\"\"\"

Respond ONLY with JSON:
{{
  "safe": true/false,
  "violations": [
    {{"type": "misinformation", "description": "Specific issue description"}}
  ]
}}

If completely safe, return: {{"safe": true, "violations": []}}"""

        try:
            response = await self.ai_service.generate_text(prompt)
            cleaned = re.sub(r"```(?:json)?", "", response).strip().strip("`")
            import json_repair
            data = json_repair.loads(cleaned)
            if isinstance(data, dict) and data.get("safe", True):
                return []
            return [
                SafetyViolation(type=v.get("type", "unknown"), description=v.get("description", ""))
                for v in data.get("violations", [])
            ]
        except Exception:
            return []  # On LLM error, default to safe (fail open)
