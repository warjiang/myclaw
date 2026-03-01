"""Built-in tools for the agent."""

from typing import Any

from loguru import logger


class TaskCompleteTool:
    """Tool to notify task completion."""

    name = "task_complete"
    description = """Call this tool when you have completed the user's task.

This tool should be called as the final step after you have:
1. Completed all necessary actions for the task
2. Provided the final result or output to the user
3. Saved any files or outputs to the workspace directory

The summary should briefly describe what was accomplished."""

    @staticmethod
    def get_schema() -> dict[str, Any]:
        """Get the tool schema for MCP."""
        return {
            "name": TaskCompleteTool.name,
            "description": TaskCompleteTool.description,
            "inputSchema": {
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
        }

    @staticmethod
    def execute(summary: str, status: str = "success", outputs: list[str] | None = None) -> dict[str, Any]:
        """Execute the task completion notification.

        Args:
            summary: Brief summary of what was accomplished.
            status: Completion status (success, partial, failed).
            outputs: List of output files or results.

        Returns:
            Tool result with completion information.
        """
        outputs = outputs or []
        logger.info("Task completed - status: {}, summary: {}", status, summary)

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Task {status}: {summary}",
                }
            ],
            "isError": status == "failed",
            "metadata": {
                "status": status,
                "summary": summary,
                "outputs": outputs,
            },
        }


def get_builtin_tools() -> list[dict[str, Any]]:
    """Get all built-in tool schemas."""
    return [TaskCompleteTool.get_schema()]


def execute_builtin_tool(name: str, **kwargs: Any) -> dict[str, Any] | None:
    """Execute a built-in tool by name.

    Args:
        name: Tool name.
        **kwargs: Tool arguments.

    Returns:
        Tool result or None if tool not found.
    """
    if name == TaskCompleteTool.name:
        return TaskCompleteTool.execute(**kwargs)
    return None
