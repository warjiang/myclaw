"""MemSearch hook for semantic memory search integration.

This module provides a hook implementation that integrates memsearch with
the claude-code-sdk, enabling semantic search across indexed markdown memories.

Reference implementation: /Users/warjiang/workspace/opensource/warjiang/myclaw/plugins/memsearch/hooks/
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import anyio
from anyio import Path as AsyncPath
from claude_agent_sdk.types import (
  HookContext,
  HookEvent,
  HookJSONOutput,
  HookMatcher,
  StopHookInput,
  UserPromptSubmitHookInput,
  UserPromptSubmitHookSpecificOutput,
)
from loguru import logger


@dataclass
class MemSearchConfig:
  """Configuration for MemSearch hook.

  Attributes:
    paths: Directories / files to index for memory search.
    memory_dir: Directory to store memory markdown files.
    embedding_provider: Name of the embedding backend ("openai", "google", etc.).
    embedding_model: Override the default model for the chosen provider.
    milvus_uri: Milvus connection URI.
    milvus_token: Authentication token for Milvus server.
    collection: Milvus collection name.
    top_k: Number of search results to include in context.
    max_chunk_size: Maximum chunk size for indexing.
    overlap_lines: Number of overlapping lines between chunks.
    enable_auto_save: Whether to auto-save conversation summaries to memory.
    min_prompt_length: Minimum prompt length to trigger memory search.
  """

  paths: list[str | Path] = field(default_factory=list)
  memory_dir: str | Path = "~/.myclaw/memories"
  embedding_provider: str = "openai"
  embedding_model: str | None = None
  milvus_uri: str = "~/.myclaw/memories/milvus.db"
  milvus_token: str | None = None
  collection: str = "myclaw_memories"
  top_k: int = 5
  max_chunk_size: int = 1500
  overlap_lines: int = 2
  enable_auto_save: bool = True
  min_prompt_length: int = 10


class MemSearchHook:
  """Hook implementation for semantic memory search.

  This hook integrates memsearch with claude-code-sdk by:
  1. SessionStart: Initialize memsearch and inject recent context
  2. UserPromptSubmit: Search relevant memories and inject into prompt
  3. Stop: Summarize conversation and save to memory (auto-save)
  4. SessionEnd: Cleanup resources

  Reference: plugins/memsearch/hooks/hooks.json

  Example:
    ```python
    config = MemSearchConfig(
        paths=["~/notes", "~/memories"],
        memory_dir="~/.myclaw/memories",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
    )
    hook = MemSearchHook(config)

    # Get hook matchers for ClaudeAgentOptions
    options = ClaudeAgentOptions(
        hooks=hook.get_hook_matchers()
    )
    ```
  """

  def __init__(self, config: MemSearchConfig | None = None):
    """Initialize the MemSearch hook.

    Args:
      config: MemSearch configuration. Uses defaults if not provided.
    """
    self.config = config or MemSearchConfig()
    self._memsearch: Any | None = None
    self._initialized: bool = False
    self._init_lock: asyncio.Lock = asyncio.Lock()
    # Use standard pathlib.Path for sync initialization
    self._memory_dir: AsyncPath = AsyncPath(Path(self.config.memory_dir).expanduser())
    self._current_session_file: AsyncPath | None = None

  async def _ensure_memory_dir(self) -> None:
    """Ensure memory directory exists."""
    await self._memory_dir.mkdir(parents=True, exist_ok=True)

  def _get_today_memory_file(self) -> AsyncPath:
    """Get today's memory file path."""
    today = date.today().isoformat()
    return self._memory_dir / f"{today}.md"

  async def _ensure_initialized(self) -> None:
    """Lazy initialization of memsearch client."""
    if self._initialized:
      return

    async with self._init_lock:
      if self._initialized:
        return

      try:
        from memsearch import MemSearch

        # Use memory_dir as the primary path if no paths specified
        paths = self.config.paths if self.config.paths else [str(self._memory_dir)]

        self._memsearch = MemSearch(
          paths=paths,
          embedding_provider=self.config.embedding_provider,
          embedding_model=self.config.embedding_model,
          milvus_uri=self.config.milvus_uri,
          milvus_token=self.config.milvus_token,
          collection=self.config.collection,
          max_chunk_size=self.config.max_chunk_size,
          overlap_lines=self.config.overlap_lines,
        )

        logger.info("MemSearch: Starting initial indexing...")
        await self._memsearch.index()
        logger.info("MemSearch: Initial indexing completed")

        self._initialized = True
      except Exception:
        logger.exception("MemSearch: Failed to initialize")
        raise

  async def _on_session_start(
    self,
    hook_input: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
  ) -> HookJSONOutput:
    """Handle session start: initialize and inject recent memories.

    Reference: plugins/memsearch/hooks/session-start.sh

    Args:
      hook_input: Hook input containing session info.
      tool_use_id: Optional tool use identifier.
      context: Hook context.

    Returns:
      Hook output with status message and recent context.
    """
    try:
      await self._ensure_memory_dir()

      # Write session heading to today's memory file
      memory_file = self._get_today_memory_file()
      now = datetime.now().strftime("%H:%M")

      async with await anyio.open_file(memory_file, "a", encoding="utf-8") as f:
        await f.write(f"\n## Session {now}\n\n")

      self._current_session_file = memory_file

      # Initialize memsearch
      await self._ensure_initialized()

      logger.info(
        "MemSearch: Session started, embedding: {}, collection: {}",
        self.config.embedding_provider,
        self.config.collection,
      )

    except Exception:
      logger.exception("MemSearch: Error in session start")

    return {"continue_": True}

  async def _get_recent_context(self, days: int = 2) -> str | None:
    """Get recent memory context from last N days.

    Args:
      days: Number of days to look back.

    Returns:
      Formatted context string or None if no memories found.
    """
    if not self._memsearch:
      return None

    try:
      # Find recent memory files
      recent_files = []
      for i in range(days):
        day = (date.today() - timedelta(days=i)).isoformat()
        mem_file = self._memory_dir / f"{day}.md"
        if await mem_file.exists():
          recent_files.append(mem_file)

      if not recent_files:
        return None

      # Read recent memories
      context_parts = ["## Recent Memories\n"]
      for mem_file in sorted(recent_files, reverse=True)[:2]:
        content = await mem_file.read_text(encoding="utf-8")
        if content.strip():
          # Extract just the heading and a preview
          lines = content.strip().split("\n")
          preview_lines = [line for line in lines[-20:] if line.strip()]
          if preview_lines:
            context_parts.append(f"\n**{mem_file.stem}:**")
            context_parts.append("\n".join(preview_lines[:10]))

      if len(context_parts) > 1:
        return "\n".join(context_parts)

    except Exception:
      logger.exception("MemSearch: Error getting recent context")
    return None

  async def _on_user_prompt_submit(
    self,
    hook_input: UserPromptSubmitHookInput,
    tool_use_id: str | None,
    context: HookContext,
  ) -> HookJSONOutput:
    """Handle user prompt submission by injecting relevant memories.

    Reference: plugins/memsearch/hooks/user-prompt-submit.sh

    Args:
      hook_input: Hook input containing the user prompt.
      tool_use_id: Optional tool use identifier.
      context: Hook context.

    Returns:
      Hook output with additional context from memory search.
    """
    try:
      # Skip short prompts (greetings, single words, etc.)
      query = hook_input.get("prompt", "")
      if not query or len(query) < self.config.min_prompt_length:
        return {"continue_": True}

      await self._ensure_initialized()

      if not self._memsearch:
        logger.warning("MemSearch: Not initialized, skipping search")
        return {"continue_": True}

      logger.debug(
        "MemSearch: Searching for query: {}", query[:100] + "..." if len(query) > 100 else query
      )

      results = await self._memsearch.search(query, top_k=self.config.top_k)

      if not results:
        logger.debug("MemSearch: No relevant memories found")
        return {"continue_": True}

      context_parts = ["\n\n## Relevant Memories\n"]
      for i, result in enumerate(results, 1):
        content = result.get("content", "")
        source = result.get("source", "unknown")
        score = result.get("score", 0.0)
        heading = result.get("heading", "")

        context_parts.append(f"\n### Memory {i}")
        context_parts.append(f"**Source:** {source}")
        if heading:
          context_parts.append(f"**Heading:** {heading}")
        context_parts.append(f"**Relevance:** {score:.3f}")
        context_parts.append(f"\n{content}\n")

      additional_context = "\n".join(context_parts)

      hook_specific: UserPromptSubmitHookSpecificOutput = {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": additional_context,
      }

      logger.info("MemSearch: Injected {} relevant memories", len(results))

    except Exception:
      logger.exception("MemSearch: Error during search")
      return {"continue_": True}
    else:
      return {
        "continue_": True,
        "hookSpecificOutput": hook_specific,
      }

  async def _on_stop(
    self,
    hook_input: StopHookInput,
    tool_use_id: str | None,
    context: HookContext,
  ) -> HookJSONOutput:
    """Handle stop: summarize conversation and save to memory.

    Reference: plugins/memsearch/hooks/stop.sh

    Args:
      hook_input: Hook input containing stop info.
      tool_use_id: Optional tool use identifier.
      context: Hook context.

    Returns:
      Hook output.
    """
    # Check if auto-save is disabled
    if not self.config.enable_auto_save:
      return {"continue_": True}

    # Prevent infinite loop: if this Stop was triggered by a previous Stop hook
    stop_hook_active = hook_input.get("stop_hook_active", False)
    if stop_hook_active:
      return {"continue_": True}

    try:
      transcript_path = hook_input.get("transcript_path", "")
      if not transcript_path:
        return {"continue_": True}

      transcript_file = AsyncPath(transcript_path)
      if not await transcript_file.exists():
        return {"continue_": True}

      # Parse and summarize transcript
      summary = await self._summarize_transcript(transcript_file)

      if summary:
        # Append to today's memory file
        await self._ensure_memory_dir()
        memory_file = self._get_today_memory_file()
        now = datetime.now().strftime("%H:%M")

        async with await anyio.open_file(memory_file, "a", encoding="utf-8") as f:
          await f.write(f"\n### {now}\n")
          await f.write(f"<!-- transcript: {transcript_path} -->\n")
          await f.write(f"{summary}\n\n")

        logger.info("MemSearch: Saved conversation summary to {}", memory_file)

        # Re-index to include new memories
        if self._memsearch:
          await self._memsearch.index()

    except Exception:
      logger.exception("MemSearch: Error in stop hook")

    return {"continue_": True}

  async def _summarize_transcript(self, transcript_file: AsyncPath) -> str | None:
    """Summarize transcript content.

    Args:
      transcript_file: Path to transcript file.

    Returns:
      Summary string or None.
    """
    import json

    if not await transcript_file.exists():
      return None

    try:
      # Read transcript lines
      content = await transcript_file.read_text(encoding="utf-8")
      lines = content.strip().split("\n")
      if len(lines) < 3:
        return None

      # Parse last turn (user message + responses)
      turns = []
      current_turn = {"user": "", "responses": []}

      for line in lines:
        obj = json.loads(line)
        msg_type = obj.get("type", "")

        if msg_type == "user":
          # Save previous turn if exists
          if current_turn["user"]:
            turns.append(current_turn)
            current_turn = {"user": "", "responses": []}
          msg_content = obj.get("message", {}).get("content", "")
          if isinstance(msg_content, str):
            current_turn["user"] = msg_content

        elif msg_type == "assistant":
          content_blocks = obj.get("content", [])
          for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
              text = block.get("text", "")
              if text:
                current_turn["responses"].append(text)

      # Add last turn
      if current_turn["user"]:
        turns.append(current_turn)

      if not turns:
        return None

      # Get last turn
      last_turn = turns[-1]

      # Create simple summary
      user_msg = last_turn["user"]
      summary_parts = [
        f"- User asked: {user_msg[:100]}..." if len(user_msg) > 100 else f"- User asked: {user_msg}"
      ]

      if last_turn["responses"]:
        # Extract key actions from responses
        response_text = " ".join(last_turn["responses"])
        summary_parts.append(f"- Claude responded with {len(response_text)} characters")

      return "\n".join(summary_parts)

    except Exception:
      logger.exception("MemSearch: Error summarizing transcript")
      return None

  async def _on_session_end(
    self,
    hook_input: dict[str, Any],
    tool_use_id: str | None,
    context: HookContext,
  ) -> HookJSONOutput:
    """Handle session end: cleanup resources.

    Reference: plugins/memsearch/hooks/session-end.sh

    Args:
      hook_input: Hook input.
      tool_use_id: Optional tool use identifier.
      context: Hook context.

    Returns:
      Hook output.
    """
    logger.info("MemSearch: Session ended")
    # Cleanup if needed
    return {"continue_": True}

  def get_hook_matchers(self) -> dict[HookEvent, list[HookMatcher]]:
    """Get hook matchers for ClaudeAgentOptions.

    Implements all hooks from plugins/memsearch/hooks/hooks.json:
    - SessionStart: Initialize and inject recent context
    - UserPromptSubmit: Search and inject relevant memories
    - Stop: Summarize and save conversation
    - SessionEnd: Cleanup

    Returns:
      Dictionary mapping hook events to their matchers.

    Example:
      ```python
      hook = MemSearchHook(config)
      options = ClaudeAgentOptions(
          hooks=hook.get_hook_matchers()
      )
      ```
    """
    return {
      "SessionStart": [
        HookMatcher(
          matcher=None,
          hooks=[self._on_session_start],
          timeout=10.0,
        )
      ],
      "UserPromptSubmit": [
        HookMatcher(
          matcher=None,
          hooks=[self._on_user_prompt_submit],
          timeout=15.0,
        )
      ],
      "Stop": [
        HookMatcher(
          matcher=None,
          hooks=[self._on_stop],
          timeout=120.0,
        )
      ],
      "SessionEnd": [
        HookMatcher(
          matcher=None,
          hooks=[self._on_session_end],
          timeout=10.0,
        )
      ],
    }

  async def index(self, *, force: bool = False) -> int:
    """Manually trigger indexing of memory paths.

    Args:
      force: Force re-indexing even if files haven't changed.

    Returns:
      Number of chunks indexed.
    """
    await self._ensure_initialized()
    if self._memsearch:
      return await self._memsearch.index(force=force)
    return 0

  async def search(self, query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    """Manually search memories.

    Args:
      query: Search query.
      top_k: Number of results to return (uses config default if not specified).

    Returns:
      List of search results.
    """
    await self._ensure_initialized()
    if self._memsearch:
      return await self._memsearch.search(query, top_k=top_k or self.config.top_k)
    return []
