# Project Specification: myclaw

## Overview
Re-implementation of `nanobot` (MyClaw simplified) using `claude-agent-sdk-python`.
The goal is to create a personal AI assistant that supports MCP, Skills, and multiple channels, running in a containerized environment.

## Architecture

### Core Components
1.  **ClawAgent**: The core agent logic wrapping `ClaudeSDKClient` from `claude-agent-sdk`.
    - Manages the conversation loop.
    - Handles tool execution (via SDK).
    - Manages context and memory.
2.  **SkillManager**: Responsible for loading and managing skills.
    - Loads `SKILL.md` files from local directories.
    - Parses metadata (frontmatter) and requirements.
    - Injects skill content into the system prompt or registers them as tools.
3.  **ConfigManager**: Loads configuration compatible with `nanobot`.
    - Loads MCP server configurations.
    - Loads API keys and model settings.
4.  **Channel Interface**: Abstract base class for communication channels.
    - `InputChannel`: Receives messages (CLI, HTTP, WebSocket).
    - `OutputChannel`: Sends responses.
    - Implementation of a `CLIChannel` for testing.
5.  **Runtime**: Docker container setup.

### Integration with `claude-agent-sdk`
- **Agent Loop**: Use `ClaudeSDKClient` for the main interaction loop.
- **Tools (MCP)**: Use `ClaudeAgentOptions.mcp_servers` to configure MCP servers.
- **Skills**:
    - "Context Skills" (Markdown): Loaded and appended to `system_prompt`.
    - "Tool Skills" (Python/Executable): Registered as MCP servers (SDK-based or stdio).

### Directory Structure
```
myclaw/
├── src/
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── core.py         # ClawAgent implementation
│   │   ├── skills.py       # SkillManager
│   │   ├── config.py       # Configuration loading
│   │   └── tools.py        # Custom tool definitions
│   ├── channels/
│   │   ├── __init__.py
│   │   ├── base.py         # Channel abstractions
│   │   └── cli.py          # CLI channel implementation
│   ├── main.py             # Entry point
│   └── utils.py
├── tests/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── .github/
│   └── workflows/
│       └── build-publish.yml
└── README.md
```

## Functional Requirements
1.  **Agent Execution**: Must use `ClaudeSDKClient` to handle user queries.
2.  **MCP Support**: Support connecting to external MCP servers defined in config.
3.  **Skill System**:
    - Load skills from a `skills/` directory.
    - Support importing third-party skills (git clone or download).
4.  **Containerization**: Provide a `Dockerfile` for easy deployment.
5.  **CI/CD**: GitHub Actions workflow to build and push the Docker image.

## Technology Stack
- **Language**: Python 3.10+
- **Core SDK**: `claude-agent-sdk`
- **Container**: Docker
- **Config**: YAML/TOML (pydantic-settings)
- **CI**: GitHub Actions
