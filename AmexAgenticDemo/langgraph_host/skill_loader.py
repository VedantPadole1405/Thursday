"""Result aggregation node for the agent workflow."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

SKILLS_DIR = PROJECT_ROOT / "skills"


def load_skill(skill_name: str) -> str:
    """Load a trusted, locally installed agent Skill."""

    skill_path = (
        SKILLS_DIR / skill_name / "SKILL.md"
    ).resolve()

    if not skill_path.is_relative_to(SKILLS_DIR.resolve()):
        raise ValueError("Invalid skill path")

    if not skill_path.is_file():
        raise FileNotFoundError(
            f"Skill not found: {skill_path}"
        )

    return skill_path.read_text(encoding="utf-8")
