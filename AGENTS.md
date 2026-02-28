# Agents

This project defines the following core Agents and related components.

## Code Style

This project follows the **Google Python Style Guide** with additional rules enforced by [ruff](https://docs.astral.sh/ruff/).

### Ruff Configuration

The project uses ruff for linting and formatting. See [pyproject.toml](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/pyproject.toml) for full configuration.

**Key Rules**:
- **Docstrings**: Google-style docstrings (see [pydocstyle](https://docs.astral.sh/ruff/settings/#tool.ruff.lint.pydocstyle))
- **Line Length**: 100 characters
- **Indent**: 2 spaces
- **Quotes**: Double quotes
- **Import Sorting**: isort with force-single-line disabled

**Enabled Linters**:
| Code | Category |
|------|----------|
| E, W | pycodestyle |
| F | pyflakes |
| I | isort |
| N | pep8-naming |
| UP | pyupgrade |
| C4 | flake8-comprehensions |
| PIE | flake8-pie |
| RET | flake8-return |
| SIM | flake8-simplify |
| PL | pylint |

### Pre-commit Hooks

The project uses pre-commit to run ruff automatically before each commit:

```bash
# Install pre-commit hooks
uv run pre-commit install

# Run manually
uv run pre-commit run --all-files
```

### Dependency Management

This project uses [uv](https://github.com/astral-sh/uv) for dependency management. All dependency operations should use `uv` instead of `pip`.

**Key Commands**:
```bash
# Install all dependencies (including dev)
uv pip install -e ".[dev]"

# Install development dependencies only
uv pip install -e ".[dev]"

# Run commands with dependencies
uv run <command>

# Sync dependencies from pyproject.toml
uv sync
```

**Important**:
- Never use `pip install` directly - always use `uv pip install`
- When adding new dependencies, update `pyproject.toml` and run `uv pip install -e ".[dev]"`
- Use `uv run` to execute any Python scripts or commands that need dependencies
- Run `uv run pre-commit install` to set up pre-commit hooks

### Writing Code

1. **Docstrings**: Use Google-style docstrings:
```python
def function_name(param1: str, param2: int) -> bool:
    """Short description.

    Args:
        param1: Description of param1.
        param2: Description of param2.

    Returns:
        Description of return value.

    Raises:
        ValueError: Description of when this is raised.
    """
```

2. **Type Hints**: Always use type hints for function signatures.

3. **Imports**: Group imports in order: stdlib, third-party, local.

4. **Minimize Import Impact**: Avoid importing heavy third-party libraries (especially those with many dependencies like `lark_oapi`) at the top of files. Instead:
   - Use lazy imports inside functions where the library is actually used
   - This significantly improves startup time for CLI applications

## Core Agent

### ClawAgent

The main Agent class for this project, built on top of the Claude Agent SDK.

**File Location**: [src/myclaw/agent/core.py](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/src/myclaw/agent/core.py)

**Main Features**:
- Initialize Claude Agent SDK client
- Load and manage Skills
- Configure MCP servers
- Process user messages and stream responses

**Initialization Flow**:
```python
agent = ClawAgent(config)
await agent.initialize()
async for response in agent.process_message(message):
    print(response)
```

## Agent Configuration

### Config

Root configuration class, managed using pydantic-settings.

**File Location**: [src/myclaw/agent/config.py](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/src/myclaw/agent/config.py)

**Configuration Structure**:
- `provider`: LLM provider configuration
  - `api_key`: API key
  - `api_base`: API endpoint (optional)
  - `model`: Model name (default: claude-3-opus-20240229)
- `tools`: Tools configuration
  - `mcp_servers`: Dictionary of MCP servers

**Configuration Loading**:
```python
config = Config.load()  # Loads from config.yaml or ~/.myclaw/config.yaml
```

## Skills System

### SkillManager

Component responsible for loading and managing Skills.

**File Location**: [src/myclaw/agent/skills.py](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/src/myclaw/agent/skills.py)

**Features**:
- Load SKILL.md files from configured directories
- Parse frontmatter metadata
- Generate system prompt additions

**Skill Directories**:
- `skills/` - Built-in project skills
- `~/.myclaw/skills/` - User-defined skills

**Skill Format**:
```markdown
---
name: SkillName
description: Description of the skill
---

# Skill instruction content
```

## Channel

### CLIChannel

Command-line interaction channel.

**File Location**: [src/myclaw/channels/cli.py](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/src/myclaw/channels/cli.py)

### BaseChannel

Base class for channels.

**File Location**: [src/myclaw/channels/base.py](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/src/myclaw/channels/base.py)

## Entry Point

### main.py

Project entry point, CLI app built with Typer.

**File Location**: [src/myclaw/main.py](file:///Users/warjiang/workspace/opensource/warjiang/myclaw/src/myclaw/main.py)

**Start Command**:
```bash
myclaw start
```

## Architecture Diagram

```
┌─────────────────────────────────────────┐
│              main.py                     │
│           (Typer CLI App)                │
└────────────────┬────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────┐
│             ClawAgent                    │
│         (Claude Agent SDK)               │
├─────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────────┐   │
│  │ SkillManager│  │ ClaudeAgentOpts │   │
│  └─────────────┘  └─────────────────┘   │
└────────────────┬────────────────────────┘
                 │
        ┌────────┴────────┐
        ▼                 ▼
┌──────────────┐   ┌──────────────┐
│   Skills     │   │  MCP Servers │
│  (SKILL.md)  │   │   (Config)   │
└──────────────┘   └──────────────┘
```
