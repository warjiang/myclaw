from collections.abc import AsyncGenerator

from claude_agent_sdk import (
  AssistantMessage,
  ClaudeAgentOptions,
  ClaudeSDKClient,
  TextBlock,
  ThinkingBlock,
  ToolResultBlock,
  ToolUseBlock, PermissionMode,
)
from loguru import logger

from myclaw.agent.skills import SkillManager
from myclaw.config import Config
from myclaw.config.schema import MCPServerConfig
from myclaw.utils.paths import get_skill_dirs, get_workspace_dir


class ClawAgent:
  def __init__(self, config: Config):
    self.config = config
    self.skill_manager = SkillManager(
      skill_dirs=get_skill_dirs()
    )
    self.client: ClaudeSDKClient | None = None
    self.options: ClaudeAgentOptions | None = None

  def _build_mcp_servers_config(self) -> dict[str, dict]:
    """Build MCP servers configuration from config.

    Returns:
      Dictionary of server name to server configuration.
      Supports both stdio and HTTP transport types.
    """
    mcp_servers: dict[str, dict] = {}

    for name, server_config in self.config.tools.mcp_servers.items():
      server_cfg = self._build_single_mcp_config(name, server_config)
      if server_cfg:
        mcp_servers[name] = server_cfg

    return mcp_servers

  def _build_single_mcp_config(
    self, name: str, config: MCPServerConfig
  ) -> dict | None:
    """Build configuration for a single MCP server.

    Args:
      name: Server name (for logging).
      config: MCP server configuration.

    Returns:
      Server configuration dictionary or None if invalid.
    """
    # Stdio transport: requires command
    if config.command:
      return {
        "type": "stdio",
        "command": config.command,
        "args": config.args,
        "env": config.env,
      }

    # HTTP transport: requires url
    if config.url:
      return {
        "type": "http",
        "url": config.url,
        "headers": config.headers,
      }

    # Invalid configuration
    logger.warning(
      "MCP server '{}' has no command or url configured, skipping", name
    )
    return None

  def initialize(self):
    """Initialize the agent, load skills, and configure options."""
    self.skill_manager.load_skills()

    system_prompt = "You are MyClaw, a personal AI assistant.\n"
    system_prompt += self.skill_manager.get_system_prompt_addition()

    # Configure MCP servers from config
    mcp_servers = self._build_mcp_servers_config()
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
      cwd=str(get_workspace_dir()),
      system_prompt=system_prompt,
      mcp_servers=mcp_servers,
      # Add other options as needed
      allowed_tools=["Read", "Write", "Edit", "Bash"],
      permission_mode="bypassPermissions",
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
      # logger.debug("Received message type: {}", type(msg).__name__)

      # Extract text content from message using SDK types
      if isinstance(msg, AssistantMessage):
        logger.debug("Processing AssistantMessage with {} content blocks", len(msg.content))
        for idx, block in enumerate(msg.content):
          logger.debug("Processing block {}: type={}", idx, type(block).__name__)
          if isinstance(block, TextBlock):
            text_preview = block.text[:100] + "..." if len(block.text) > 100 else block.text
            logger.debug("Received text block: {}", text_preview)
            yield block.text
          elif isinstance(block, ThinkingBlock):
            logger.debug("Received thinking block (skipped)")
          elif isinstance(block, ToolUseBlock):
            logger.debug("Received tool_use block: name={}", block.name)
          elif isinstance(block, ToolResultBlock):
            logger.debug("Received tool_result block: tool_use_id={}", block.tool_use_id)
          else:
            logger.debug("Unknown content block type: {}", type(block).__name__)
      elif isinstance(msg, str):
        text_preview = msg[:100] + "..." if len(msg) > 100 else msg
        logger.debug("Received string message: {}", text_preview)
        yield msg
      else:
        logger.debug("Unknown message type: {}", type(msg).__name__)

  async def close(self):
    if self.client:
      await self.client.__aexit__(None, None, None)
