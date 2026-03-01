"""Path utility functions for myclaw."""

from pathlib import Path


def get_skill_dirs() -> list[Path]:
  """Get skill directories by walking up from current dir to home.

  Returns:
      List of skill directories from current dir up to home.
  """
  skill_dirs = []
  current = Path.cwd().resolve()
  home = Path.home().resolve()

  # Walk up from current dir to home, collecting skills dirs
  while True:
    skills_dir = current / "skills"
    if skills_dir.exists() and skills_dir.is_dir():
      skill_dirs.append(skills_dir)
    if current == home:
      break
    parent = current.parent
    if parent == current:  # Reached root
      break
    current = parent

  # Always add ~/.myclaw/skills as fallback
  user_skills = Path("~/.myclaw/skills").expanduser()
  if user_skills not in skill_dirs:
    skill_dirs.append(user_skills)

  return skill_dirs


def get_workspace_dir() -> Path:
  """Get the workspace directory for the agent.

  Returns:
      Path to the workspace directory.
  """
  current_file = Path(__file__).resolve()
  project_root = current_file.parent.parent.parent.parent
  workspace = project_root / "myclaw-workspace"
  workspace.mkdir(parents=True, exist_ok=True)
  return workspace
