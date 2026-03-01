from collections.abc import AsyncGenerator

from claude_agent_sdk import (
  AssistantMessage,
  ClaudeAgentOptions,
  ClaudeSDKClient,
  PermissionMode,
  TextBlock,
  ThinkingBlock,
  ToolResultBlock,
  ToolUseBlock,
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

    # Add screenshot path restriction to system prompt
    workspace_dir = get_workspace_dir()
    system_prompt += (
      "\n\n## Screenshot and File Output Rules\n"
      "When saving screenshots or any output files, you MUST save them to the "
      f"following directory: {workspace_dir}\n"
      "- Screenshots: Save to the workspace directory with descriptive names\n"
      "- When referencing files in your response, use the full path or relative path "
      f"from workspace: {workspace_dir}/filename.png\n"
      "- Do NOT save files to system temp directories like /tmp, /var/folders, etc.\n"
      "- Do NOT use sandbox: prefix in file paths when referencing them\n"
    )

    # Add task completion requirement to system prompt
    system_prompt += (
      "\n\n## Task Completion Protocol\n"
      "When you have completed the user's task, you MUST end your response with the "
      "special marker: [TASK_COMPLETE]\n"
      "This marker signals to the system that the task is finished and no further "
      "actions are needed.\n"
      "\nExample response format:\n"
      "```\n"
      "I have successfully completed the task. The file has been created at ...\n"
      "\n"
      "[TASK_COMPLETE]\n"
      "```\n"
    )

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
    task_completed = False
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
            # Check for task completion marker
            if "[TASK_COMPLETE]" in block.text:
              task_completed = True
              # Remove the marker from the text before yielding
              clean_text = block.text.replace("[TASK_COMPLETE]", "").strip()
              if clean_text:
                yield clean_text
              yield "\n\n✅ **任务已完成**"
            else:
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
        # Check for task completion marker in string messages too
        if "[TASK_COMPLETE]" in msg:
          task_completed = True
          clean_text = msg.replace("[TASK_COMPLETE]", "").strip()
          if clean_text:
            yield clean_text
          yield "\n\n✅ **任务已完成**"
        else:
          yield msg
      else:
        logger.debug("Unknown message type: {}, message: {}", type(msg).__name__, message)

    # If task was completed, add a final notification
    if task_completed:
      logger.info("Task completed successfully")

  async def close(self):
    if self.client:
      await self.client.__aexit__(None, None, None)
