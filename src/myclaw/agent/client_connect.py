"""ClawAgent client implementation using connect method.

This module provides an alternative implementation of ClawAgent that uses
the Claude Agent SDK's `connect()` method for establishing a persistent
connection with Claude.
"""

import os
from collections.abc import AsyncGenerator
from typing import Any

from claude_agent_sdk import (
  AssistantMessage,
  ClaudeAgentOptions,
  ClaudeSDKClient,
  PermissionMode,
  ResultMessage,
  SdkPluginConfig,
  TextBlock,
  ThinkingBlock,
  ToolResultBlock,
  ToolUseBlock,
  UserMessage,
  create_sdk_mcp_server,
  tool,
)
from loguru import logger

from myclaw.agent.hooks.memsearch import MemSearchHook
from myclaw.agent.skills import SkillManager
from myclaw.config import Config
from myclaw.config.schema import MCPServerConfig
from myclaw.utils.paths import get_skill_dirs, get_workspace_dir


# Define task_complete tool with @tool decorator
@tool(
  name="task_complete",
  description="Call this tool when you have completed the user's task.",
  input_schema={
    "type": "object",
    "properties": {
      "summary": {
        "type": "string",
        "description": "A brief summary of what was accomplished",
      },
      "status": {
        "type": "string",
        "enum": ["success", "partial", "failed"],
        "description": "The completion status of the task",
      },
      "outputs": {
        "type": "array",
        "items": {"type": "string"},
        "description": "List of output files or results generated",
      },
    },
    "required": ["summary", "status"],
  },
)
async def task_complete_tool(args: dict[str, Any]) -> dict[str, Any]:
  """Execute the task completion notification.

  Args:
      args: Tool arguments containing summary, status, and optional outputs.

  Returns:
      Tool result with completion information.
  """
  summary = args.get("summary", "")
  status = args.get("status", "success")
  outputs = args.get("outputs", [])

  logger.info("Task completed - status: {}, summary: {}", status, summary)

  return {
    "content": [{"type": "text", "text": f"Task {status}: {summary}"}],
    "isError": status == "failed",
    "metadata": {
      "status": status,
      "summary": summary,
      "outputs": outputs,
    },
  }


# Create SDK MCP server with task_complete tool
task_complete_server = create_sdk_mcp_server(
  name="utilities",
  version="1.0.0",
  tools=[task_complete_tool],
)


class AgentNotInitializedError(RuntimeError):
  """Raised when agent operations are called before initialization."""

  def __init__(self) -> None:
    super().__init__("Agent not initialized. Call initialize() first.")


class NotConnectedError(RuntimeError):
  """Raised when Claude operations are called before connecting."""

  def __init__(self) -> None:
    super().__init__("Not connected to Claude. Call connect() first.")


class ClawAgentConnect:
  """ClawAgent using ClaudeSDKClient.connect() method.

  This implementation establishes a persistent connection with Claude using
  the connect() method, which allows for:
  - Maintaining a long-lived session
  - Sending multiple queries without reconnecting
  - Better state management across interactions

  Example:
      agent = ClawAgentConnect(config)
      agent.initialize()

      # Use as async context manager (recommended)
      async with agent:
          # Connect with optional initial prompt
          await agent.connect("Hello, I'm ready to start.")

          # Send queries in the same session
          async for response in agent.query("What can you do?"):
              print(response)

          # Interrupt ongoing operations if needed
          await agent.interrupt()

      # Or manually manage connection
      await agent.connect()
      try:
          async for response in agent.query("Hello!"):
              print(response)
      finally:
          await agent.disconnect()
  """

  def __init__(self, config: Config):
    """Initialize the agent with configuration.

    Args:
        config: Application configuration containing provider settings,
            MCP servers, and other options.
    """
    self.config = config
    self.skill_manager = SkillManager(skill_dirs=get_skill_dirs())
    self.client: ClaudeSDKClient | None = None
    self.options: ClaudeAgentOptions | None = None
    self._session_id: str | None = None
    self._connected: bool = False
    self.memsearch_hook: MemSearchHook | None = None

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

  def _build_single_mcp_config(self, name: str, config: MCPServerConfig) -> dict | None:
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
    logger.warning("MCP server '{}' has no command or url configured, skipping", name)
    return None

  def initialize(self) -> None:
    """Initialize the agent, load skills, and configure options.

    This method prepares the agent configuration but does not establish
    a connection to Claude. Call connect() to establish the connection.
    """
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

    # Add task completion tool instruction to system prompt
    system_prompt += (
      "\n\n## Task Completion Protocol\n"
      "When you have completed the user's task, you MUST call the 'task_complete' tool "
      "as the final step. This tool notifies the system that the task is finished.\n"
      "The tool requires:\n"
      "- summary: A brief summary of what was accomplished\n"
      "- status: The completion status ('success', 'partial', or 'failed')\n"
      "- outputs (optional): List of output files or results generated\n"
    )

    # Configure MCP servers from config
    mcp_servers = self._build_mcp_servers_config()

    # Add utilities server to MCP servers
    mcp_servers["utilities"] = task_complete_server

    # Build hooks configuration
    claudecode_cfg = self.config.claudecode
    hooks = None
    if self.config.memsearch.enabled:
      from myclaw.agent.hooks.memsearch import MemSearchConfig

      memsearch_cfg = self.config.memsearch
      # fixme
      os.environ["OPENAI_BASE_URL"] = claudecode_cfg.base_url
      os.environ["OPENAI_API_KEY"] = claudecode_cfg.auth_token
      ms_config = MemSearchConfig(
        paths=memsearch_cfg.paths,
        memory_dir=memsearch_cfg.memory_dir,
        embedding_provider=memsearch_cfg.embedding_provider,
        embedding_model=memsearch_cfg.embedding_model,
        # milvus_uri=memsearch_cfg.milvus_uri,
        # milvus_token=memsearch_cfg.milvus_token,
        # collection=memsearch_cfg.collection,
        # top_k=memsearch_cfg.top_k,
        # max_chunk_size=memsearch_cfg.max_chunk_size,
        # overlap_lines=memsearch_cfg.overlap_lines,
        enable_auto_save=memsearch_cfg.enable_auto_save,
        min_prompt_length=memsearch_cfg.min_prompt_length,
      )
      self.memsearch_hook = MemSearchHook(ms_config)
      hooks = self.memsearch_hook.get_hook_matchers()
      logger.info("MemSearch hook enabled with paths: {}", memsearch_cfg.paths)
    logger.info("Workspace dir: {}", get_workspace_dir())

    self.options = ClaudeAgentOptions(
      env={
        "DISABLE_TELEMETRY": "1",
        "DISABLE_ERROR_REPORTING": "1",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "MCP_TIMEOUT": "60000",
        "ANTHROPIC_AUTH_TOKEN": claudecode_cfg.auth_token,
        "ANTHROPIC_BASE_URL": claudecode_cfg.base_url,
        "API_TIMEOUT_MS": "3000000",
        "ANTHROPIC_MODEL": claudecode_cfg.model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": claudecode_cfg.haiku_model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": claudecode_cfg.opus_model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": claudecode_cfg.sonnet_model,
      },
      cwd=str(get_workspace_dir()),
      system_prompt=system_prompt,
      mcp_servers=mcp_servers,
      hooks=hooks,
      allowed_tools=[
        "Read",
        "Write",
        "Edit",
        "Bash",
        "mcp__utilities__task_complete",
      ],
      permission_mode="bypassPermissions",
    )

    logger.info("Agent initialized with connect mode")

  async def connect(self, prompt: str | None = None) -> None:
    """Connect to Claude with an optional initial prompt.

    This method establishes a persistent connection to Claude. Once
    connected, you can send multiple queries using the same session.

    Args:
        prompt: Optional initial prompt or message stream to start
            the conversation.

    Raises:
        AgentNotInitializedError: If the agent has not been initialized.
    """
    if not self.options:
      raise AgentNotInitializedError

    if self.client:
      logger.warning("Already connected, disconnecting first")
      await self.disconnect()

    self.client = ClaudeSDKClient(options=self.options)

    # Connect with optional initial prompt
    logger.info("Connecting to Claude...")
    await self.client.connect(prompt)
    self._connected = True

    # Get server info including session ID
    server_info = await self.client.get_server_info()
    self._session_id = server_info.get("session_id")
    logger.info("Connected to Claude. Session ID: {}", self._session_id)

  async def query(self, prompt: str) -> AsyncGenerator[str, None]:
    """Send a new request in streaming mode.

    Sends a query to the connected Claude session and yields responses
    as they arrive.

    Args:
        prompt: The user message to send.

    Yields:
        Text response chunks from Claude.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    logger.debug(
      "Sending query to agent: {}", prompt[:100] + "..." if len(prompt) > 100 else prompt
    )

    # Send the query with session ID
    await self.client.query(prompt, session_id=self._session_id)

    # Receive and yield response
    logger.debug("Waiting for response from agent...")
    task_completed = False

    async for msg in self.client.receive_response():
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
            # Handle task_complete tool (format: mcp__utilities__task_complete)
            if block.name == "mcp__utilities__task_complete":
              task_completed = True
              logger.info("Task complete tool called with: {}", block.input)

          elif isinstance(block, ToolResultBlock):
            logger.debug("Received tool_result block: tool_use_id={}", block.tool_use_id)

          else:
            logger.debug("Unknown content block type: {}", type(block).__name__)

      elif isinstance(msg, str):
        text_preview = msg[:100] + "..." if len(msg) > 100 else msg
        logger.debug("Received string message: {}", text_preview)
        yield msg

      elif isinstance(msg, ResultMessage):
        # ResultMessage indicates the end of a response
        logger.debug(
          "Received ResultMessage: success={}, duration_ms={}, num_turns={}",
          msg.subtype,
          msg.duration_ms,
          msg.num_turns,
        )
        # Don't yield anything for ResultMessage, it's just metadata

      elif isinstance(msg, UserMessage):
        # UserMessage contains tool results, log but don't yield
        logger.debug("Received UserMessage with {} content blocks", len(msg.content))
        for block in msg.content:
          if isinstance(block, ToolResultBlock):
            logger.debug(
              "Tool result for {}: {}",
              block.tool_use_id,
              block.content[:100] + "..." if len(block.content) > 100 else block.content,
            )

      else:
        logger.debug("Unknown message type: {}, message: {}", type(msg).__name__, msg)

    if task_completed:
      logger.info("Task completed successfully")
      yield "\n\n✅ **任务已完成**"

  async def receive_messages(self) -> AsyncGenerator[str, None]:
    """Receive all messages from Claude as an async iterator.

    This is a lower-level method that yields all messages without
    filtering for complete responses.

    Yields:
        Raw message content from Claude.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    async for msg in self.client.receive_messages():
      if isinstance(msg, AssistantMessage):
        for block in msg.content:
          if isinstance(block, TextBlock):
            yield block.text
      elif isinstance(msg, str):
        yield msg

  async def interrupt(self) -> None:
    """Send interrupt signal to Claude.

    This only works in streaming mode and can be used to stop
    an ongoing response.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    logger.info("Sending interrupt signal")
    await self.client.interrupt()

  async def set_permission_mode(self, mode: PermissionMode) -> None:
    """Change the permission mode for the current session.

    Args:
        mode: The new permission mode to set.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    logger.info("Setting permission mode to: {}", mode)
    await self.client.set_permission_mode(mode)

  async def set_model(self, model: str | None) -> None:
    """Change the model for the current session.

    Args:
        model: The model name to use, or None to reset to default.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    logger.info("Setting model to: {}", model or "default")
    await self.client.set_model(model)

  async def get_mcp_status(self) -> dict:
    """Get the status of all configured MCP servers.

    Returns:
        Dictionary containing MCP server status information.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    status = await self.client.get_mcp_status()
    logger.debug("MCP status: {}", status)
    return status

  async def get_server_info(self) -> dict:
    """Get server information including session ID and capabilities.

    Returns:
        Dictionary containing server information.

    Raises:
        NotConnectedError: If not connected to Claude.
    """
    if not self.client or not self._connected:
      raise NotConnectedError

    info = await self.client.get_server_info()
    logger.debug("Server info: {}", info)
    return info

  async def disconnect(self) -> None:
    """Disconnect from Claude.

    Cleanly closes the connection and releases resources.
    """
    if self.client:
      logger.info("Disconnecting from Claude")
      await self.client.disconnect()
      self.client = None
      self._connected = False
      self._session_id = None

  async def __aenter__(self) -> "ClawAgentConnect":
    """Async context manager entry.

    Returns:
        The agent instance for use in async with statements.
    """
    return self

  async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
    """Async context manager exit.

    Ensures proper disconnection when exiting the context.
    """
    await self.disconnect()

  @property
  def is_connected(self) -> bool:
    """Check if the agent is currently connected to Claude."""
    return self._connected and self.client is not None

  @property
  def session_id(self) -> str | None:
    """Get the current session ID if connected."""
    return self._session_id
