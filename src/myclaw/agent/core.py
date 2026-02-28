from collections.abc import AsyncGenerator
from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient
from loguru import logger

from myclaw.agent.skills import SkillManager
from myclaw.config import Config


def _get_skill_dirs() -> list[Path]:
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


def _get_workspace_dir() -> Path:
  """Get the workspace directory for the agent.

  Returns:
      Path to the workspace directory.
  """
  current_file = Path(__file__).resolve()
  project_root = current_file.parent.parent.parent.parent
  workspace = project_root / "myclaw-workspace"
  workspace.mkdir(parents=True, exist_ok=True)
  return workspace


class ClawAgent:
  def __init__(self, config: Config):
    self.config = config
    self.skill_manager = SkillManager(
      skill_dirs=_get_skill_dirs()
    )
    self.client: ClaudeSDKClient | None = None
    self.options: ClaudeAgentOptions | None = None

  def initialize(self):
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
    claudecode_cfg = self.config.claudecode
    self.options = ClaudeAgentOptions(
      env={
        "DISABLE_TELEMETRY": '1',
        "DISABLE_ERROR_REPORTING": '1',
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": '1',
        "MCP_TIMEOUT": '60000',
        "ANTHROPIC_AUTH_TOKEN": claudecode_cfg.auth_token,
        "ANTHROPIC_BASE_URL": claudecode_cfg.base_url,
        "API_TIMEOUT_MS": '3000000',
        "ANTHROPIC_MODEL": claudecode_cfg.model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": claudecode_cfg.haiku_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": claudecode_cfg.opus_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": claudecode_cfg.sonnet_model,
      },
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
    logger.debug("Sending message to agent: {}", message[:100] + "..." if len(message) > 100 else message)
    await self.client.query(message)

    # Receive response
    logger.debug("Waiting for response from agent...")
    async for msg in self.client.receive_response():
      logger.debug("Received message type: {}, has content attr: {}, is string: {}",
                   type(msg).__name__, hasattr(msg, "content"), isinstance(msg, str))

      # Extract text content from message
      # Note: Actual structure depends on SDK version, assuming standard format
      if hasattr(msg, "content"):
        logger.debug("Processing message with content, content length: {}", len(msg.content) if hasattr(msg.content, "__len__") else "N/A")
        for idx, block in enumerate(msg.content):
          logger.debug("Processing block {}: type={}, has text attr: {}",
                       idx, type(block).__name__, hasattr(block, "text"))
          if hasattr(block, "text"):
            logger.debug("Received text block: {}", block.text[:100] + "..." if len(block.text) > 100 else block.text)
            yield block.text
          else:
            logger.debug("Block {} has no text attribute, skipping", idx)
      elif isinstance(msg, str):
        logger.debug("Received string message: {}", msg[:100] + "..." if len(msg) > 100 else msg)
        yield msg
      else:
        logger.debug("Unknown message type, skipping: {}", msg)

  async def close(self):
    if self.client:
      await self.client.__aexit__(None, None, None)
