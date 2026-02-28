from pathlib import Path

from myclaw.agent.config import Config
from myclaw.agent.skills import SkillManager


def test_config() -> None:
  """Test Config initialization."""
  config = Config()
  assert config.provider is not None
  assert config.tools is not None


def test_skills() -> None:
  """Test SkillManager loads skills correctly."""
  skills_dir = Path(__file__).resolve().parent.parent / "skills"
  manager = SkillManager([skills_dir])
  manager.load_skills()
  assert "TestSkill" in manager.skills
