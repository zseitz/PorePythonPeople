"""Runtime skill-loader for hybrid knowledge + deterministic execution stages."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


_DEFAULT_STAGE_SKILLS: Dict[str, List[str]] = {
    "triage_plan": ["request-triage"],
    "implement": ["implementation-strategy"],
    "verify": ["verification-strategy"],
    "verify_after_refactor": ["verification-strategy"],
    "doc_sync": ["doc-sync-rules"],
    "memory_sync": ["doc-sync-rules"],
}


@dataclass(frozen=True)
class StageSkillContext:
    skills: List[Dict[str, str]]
    truncated: bool


class SkillLoader:
    """Loads markdown SKILL artifacts and provides bounded stage context."""

    def __init__(
        self,
        repo_root: Path,
        stage_skill_map: Optional[Dict[str, List[str]]] = None,
        max_chars_per_stage: int = 6000,
        enabled: bool = True,
    ) -> None:
        self.repo_root = repo_root
        self.stage_skill_map = stage_skill_map or dict(_DEFAULT_STAGE_SKILLS)
        self.max_chars_per_stage = max(100, int(max_chars_per_stage))
        self.enabled = enabled
        self._cache: Dict[str, str] = {}

    @classmethod
    def from_policy(cls, repo_root: Path, policy: Dict[str, object]) -> "SkillLoader":
        skills_cfg = policy.get("skills", {}) if isinstance(policy, dict) else {}
        if not isinstance(skills_cfg, dict):
            return cls(repo_root=repo_root, enabled=False)

        enabled = bool(skills_cfg.get("enabled", False))
        max_chars = int(skills_cfg.get("max_chars_per_stage", 6000))

        stage_map = skills_cfg.get("stage_map", {})
        parsed_stage_map: Dict[str, List[str]] = {}
        if isinstance(stage_map, dict):
            for stage, skill_names in stage_map.items():
                if not isinstance(stage, str):
                    continue
                if not isinstance(skill_names, list):
                    continue
                parsed_stage_map[stage] = [str(name) for name in skill_names if isinstance(name, str) and name.strip()]

        return cls(
            repo_root=repo_root,
            stage_skill_map=parsed_stage_map or dict(_DEFAULT_STAGE_SKILLS),
            max_chars_per_stage=max_chars,
            enabled=enabled,
        )

    def load_stage_context(self, stage_id: str) -> Dict[str, object]:
        if not self.enabled:
            return {}

        requested = self.stage_skill_map.get(stage_id, [])
        if not requested:
            return {}

        remaining = self.max_chars_per_stage
        truncated = False
        selected: List[Dict[str, str]] = []

        for skill_name in requested:
            text = self._load_skill(skill_name)
            if not text:
                continue

            skill_text = text.strip()
            if not skill_text:
                continue

            if len(skill_text) > remaining:
                if remaining < 120:
                    truncated = True
                    break
                skill_text = skill_text[: remaining - 24].rstrip() + "\n\n[TRUNCATED]"
                truncated = True

            selected.append({"name": skill_name, "content": skill_text})
            remaining -= len(skill_text)
            if remaining <= 0:
                truncated = True
                break

        if not selected:
            return {}

        context = StageSkillContext(skills=selected, truncated=truncated)
        return {
            "skills": context.skills,
            "truncated": context.truncated,
        }

    def _load_skill(self, skill_name: str) -> str:
        if skill_name in self._cache:
            return self._cache[skill_name]

        path = self.repo_root / "runtime" / "skills" / f"{skill_name}.SKILL.md"
        if not path.exists() or not path.is_file():
            self._cache[skill_name] = ""
            return ""

        try:
            content = path.read_text(encoding="utf-8")
        except OSError:
            content = ""

        self._cache[skill_name] = content
        return content
