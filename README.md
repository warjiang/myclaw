# MyClaw Next

A re-implementation of OpenClaw/Nanobot using the [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk-python).

## Features

- **Claude Agent SDK Core**: Built on top of the official SDK for robust agent capabilities.
- **Skill System**: Load skills from Markdown files (`SKILL.md`) with frontmatter metadata.
- **MCP Support**: Connect to Model Context Protocol servers.
- **Dockerized**: Ready for deployment with Docker and Docker Compose.
- **Extensible Channels**: Modular channel architecture (CLI included, others easy to add).

## Installation

### Local Development

1.  Clone the repository.
2.  Install dependencies:
    ```bash
    uv pip install -e ".[dev]"
    ```
3.  Install pre-commit hooks:
    ```bash
    uv run pre-commit install
    ```
4.  Run the agent:
    ```bash
    myclaw start
    ```

### Docker

1.  Build and run:
    ```bash
    docker-compose up --build
    ```

## Configuration

You can configure MyClaw using either a `config.yaml` file or environment variables.

### Using config.yaml

Create a `config.yaml` file in the root directory or `~/.myclaw/config.yaml`:

```yaml
provider:
  api_key: "sk-..."
  model: "claude-3-opus-20240229"

tools:
  mcp_servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"]
```

### Using Environment Variables

Alternatively, you can use environment variables. Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
# Edit .env with your configuration
```

The environment variables follow this pattern:
- `MYCLAW_PROVIDER__API_KEY` - LLM API key
- `MYCLAW_PROVIDER__MODEL` - Model name (default: claude-3-opus-20240229)
- `MYCLAW_FEISHU__*` - Feishu configuration (see Feishu Channel section)

## Skills

Place your skills in the `skills/` directory. A skill is a Markdown file named `SKILL.md` (or any `.md` file if configured) with frontmatter:

```markdown
---
name: MySkill
description: Does something cool
---

# Instructions

You can do X by running Y.
```

To import third-party skills, simply clone them into the `skills/` directory:

```bash
cd skills
git clone https://github.com/some-user/some-skill.git
```

## Feishu Channel

MyClaw supports integration with Feishu bot. Two modes are available:

### Mode 1: WebSocket (Long Connection)

This mode establishes a persistent WebSocket connection with Feishu for real-time message receiving.

**Configuration in `config.yaml`**:

```yaml
feishu:
  app_id: "your_app_id"
  app_secret: "your_app_secret"
  mode: "websocket"
```

**Feishu Platform Setup**:

1. Create an enterprise self-built app at Feishu Open Platform.
2. Get credentials from "Credentials & Basic Info": App ID and App Secret.
3. Go to "Events & Callbacks", add event `im.message.receive_v1`.
4. Set subscription method to "Use long connection (WebSocket)".
5. Publish the app.

### Mode 2: HTTP (Webhooks)

This mode uses HTTP callbacks to receive messages from Feishu.

**Configuration in `config.yaml`**:

```yaml
feishu:
  app_id: "your_app_id"
  app_secret: "your_app_secret"
  verification_token: "your_verification_token"
  encrypt_key: "your_encrypt_key"
  mode: "http"
  http_host: "0.0.0.0"
  http_port: 8089
```

**Feishu Platform Setup**:

1. Create an enterprise self-built app at Feishu Open Platform.
2. Get credentials from "Credentials & Basic Info": App ID and App Secret.
3. Get tokens from "Events & Callbacks": Verification Token and Encrypt Key.
4. Add event `im.message.receive_v1`.
5. Set subscription method to "Send callbacks to developer server".
6. Set callback URL to your server (e.g., `https://your-domain.com/webhook/event`).
7. Publish the app.

**Environment Variables**:

You can also configure via environment variables:

```bash
export MYCLAW_FEISHU__APP_ID="your_app_id"
export MYCLAW_FEISHU__APP_SECRET="your_app_secret"
export MYCLAW_FEISHU__MODE="websocket"  # or "http"
```
