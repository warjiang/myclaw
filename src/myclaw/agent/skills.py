import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel


logger = logging.getLogger(__name__)


class Skill(BaseModel):
  """Represents a skill with metadata and content."""

  name: str
  description: str
  content: str
  metadata: dict = {}


class SkillManager:
  """Manages loading and storage of skills."""

  def __init__(self, skill_dirs: list[Path]):
    """Initialize SkillManager.

    Args:
        skill_dirs: List of directories to search for skills.
    """
    self.skill_dirs = skill_dirs
    self.skills: dict[str, Skill] = {}

  def load_skills(self) -> None:
    """Load all skills from configured directories."""
    for directory in self.skill_dirs:
      if not directory.exists():
        continue

      for root, _, files in os.walk(directory):
        if "SKILL.md" in files:
          skill_path = Path(root) / "SKILL.md"
          self._load_skill(skill_path)

  def _load_skill(self, path: Path) -> None:
    """Load a single skill file.

    Args:
        path: Path to the SKILL.md file.
    """
    try:
      with path.open() as f:
        content = f.read()

      if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
          frontmatter = yaml.safe_load(parts[1])
          body = parts[2]

          skill = Skill(
            name=frontmatter.get("name", path.parent.name),
            description=frontmatter.get("description", ""),
            content=body.strip(),
            metadata=frontmatter,
          )
          self.skills[skill.name] = skill
    except Exception:
      logger.exception("Error loading skill from %s", path)

  def get_system_prompt_addition(self) -> str:
    """Generate a system prompt addition containing all skills."""
    if not self.skills:
      return ""

    prompt = "\n\n# Available Skills\n\n"
    for skill in self.skills.values():
      prompt += f"## {skill.name}\n"
      prompt += f"{skill.description}\n\n"
      prompt += f"{skill.content}\n\n"
    return prompt
