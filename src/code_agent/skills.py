"""Application-owned local discovery and initial, model-owned selection."""

import json
from dataclasses import dataclass
from pathlib import Path

import yaml

from .openai_llm import call_openai_model


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    path: Path


def discover_skills(root: Path, allowed_names: set[str] | None = None) -> list[Skill]:
    """Read only frontmatter; optionally restrict the application's candidates."""
    skills = []
    for path in sorted(root.glob("*/SKILL.md")):
        with path.open(encoding="utf-8") as source:
            if source.readline().strip() != "---":
                raise ValueError(f"Missing skill frontmatter: {path}")
            lines = []
            for line in source:
                if line.strip() == "---":
                    break
                lines.append(line)
            else:
                raise ValueError(f"Unclosed skill frontmatter: {path}")
        metadata = yaml.safe_load("".join(lines))
        if not isinstance(metadata, dict) or any(
            not isinstance(metadata.get(key), str) or not metadata[key].strip()
            for key in ("name", "description")
        ):
            raise ValueError(f"Invalid skill metadata: {path}")
        name = metadata["name"]
        if allowed_names is not None and name not in allowed_names:
            continue
        if any(skill.name == name for skill in skills):
            raise ValueError(f"Duplicate skill name: {name}")
        skills.append(Skill(name, metadata["description"].strip(), path.resolve()))
    return skills


def select_skill(history: list, candidates: list[Skill]) -> Skill | None:
    """Select one initial procedure, without tools or full skill instructions."""
    if not candidates:
        return None
    metadata = [{"name": s.name, "description": s.description} for s in candidates]
    response = call_openai_model([
        *history,
        {"role": "developer", "content": (
            "Select a skill for the latest user request using the candidate metadata "
            "and conversation context. Select only when its described use conditions "
            "apply. Do not execute the task. Return only a JSON object with exactly "
            "one key, skill, whose value is a candidate name or null if none applies. "
            f"Candidates: {json.dumps(metadata, ensure_ascii=False)}"
        )},
    ], raw_response=True)
    selection = json.loads(response.output_text)
    if not isinstance(selection, dict) or set(selection) != {"skill"}:
        raise ValueError("Invalid skill selection response")
    if selection["skill"] is None:
        return None
    for skill in candidates:
        if selection["skill"] == skill.name:
            return skill
    raise ValueError("Selected skill is outside the application candidates")


def load_skill(skill: Skill) -> str:
    """Load the selected entry point; references remain ordinary tool reads."""
    return (
        f"Selected skill: {skill.name}\n"
        "Follow this procedure for the current task, subject to Application, System "
        "and Developer policies. Skill selection grants no tool permissions. "
        "If the procedure conflicts with policy or the environment, explain the "
        "conflict rather than inventing a replacement procedure. "
        f"Resolve relative supporting resource paths against: {skill.path.parent}\n"
        "Read supporting references only when the procedure calls for them, using "
        "available tools through the normal tool execution path.\n\n"
        + skill.path.read_text(encoding="utf-8")
    )
