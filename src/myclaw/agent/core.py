from collections.abc import AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from .config import Config
from .skills import SkillManager


def _get_workspace_dir() -> Path:
  """Get the workspace directory for the agent.

  Returns:
      Path to the workspace directory.
  """
  # Get the directory where this file is located
  current_file = Path(__file__).resolve()
  # Go up to project root (src/myclaw/agent/ -> project root)
  project_root = current_file.parent.parent.parent.parent
  # Use myclaw-workspace subdirectory
  workspace = project_root / "myclaw-workspace"
  # Create if it doesn't exist
  workspace.mkdir(parents=True, exist_ok=True)
  return workspace


class ClawAgent:
  def __init__(self, config: Config):
    self.config = config
    self.skill_manager = SkillManager(
      skill_dirs=[Path("skills"), Path("~/.myclaw/skills").expanduser()]
    )
    self.client: ClaudeSDKClient | None = None
    self.options: ClaudeAgentOptions | None = None

  async def initialize(self):
    """Initialize the agent, load skills, and configure options."""
    self.skill_manager.load_skills()

    system_prompt = "You are MyClaw, a personal AI assistant.\n"
    system_prompt += self.skill_manager.get_system_prompt_addition()

    # Configure MCP servers from config
    mcp_servers = {}
    for name, server_config in self.config.tools.mcp_servers.items():
      if server_config.disabled:
        continue

      if server_config.command:
        mcp_servers[name] = {
          "type": "stdio",
          "command": server_config.command,
          "args": server_config.args,
          "env": server_config.env,
        }
      elif server_config.url:
        # TODO: Support HTTP MCP
        pass

    self.options = ClaudeAgentOptions(
      cwd=str(_get_workspace_dir()),
      system_prompt=system_prompt,
      mcp_servers=mcp_servers,
      # Add other options as needed
      allowed_tools=["Read", "Write", "Edit", "Bash"],
    )

  async def process_message(self, message: str) -> AsyncGenerator[str, None]:
    """Process a user message and yield responses."""
    if not self.client:
      self.client = ClaudeSDKClient(options=self.options)
      await self.client.__aenter__()  # Manually enter context if keeping client alive

    # Send message
    await self.client.query(message)

    # Receive response
    async for msg in self.client.receive_response():
      # Extract text content from message
      # Note: Actual structure depends on SDK version, assuming standard format
      if hasattr(msg, "content"):
        for block in msg.content:
          if hasattr(block, "text"):
            yield block.text
      elif isinstance(msg, str):
        yield msg

  async def close(self):
    if self.client:
      await self.client.__aexit__(None, None, None)
