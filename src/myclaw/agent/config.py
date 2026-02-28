from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MCPServerConfig(BaseModel):
  """MCP server configuration."""

  command: str = ""
  args: list[str] = Field(default_factory=list)
  env: dict[str, str] = Field(default_factory=dict)
  disabled: bool = False


class ProviderConfig(BaseModel):
  """LLM provider configuration."""

  api_key: str = ""
  api_base: str | None = None
  model: str = "claude-3-opus-20240229"


class ToolsConfig(BaseModel):
  """Tools configuration."""

  mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)


class FeishuConfig(BaseModel):
  """Feishu channel configuration."""

  app_id: str = ""
  app_secret: str = ""
  verification_token: str = ""
  encrypt_key: str = ""
  mode: str = "websocket"
  webhook_url: str = ""
  http_host: str = "0.0.0.0"
  http_port: int = 8089


class Config(BaseSettings):
  """Root configuration."""

  provider: ProviderConfig = Field(default_factory=ProviderConfig)
  tools: ToolsConfig = Field(default_factory=ToolsConfig)
  feishu: FeishuConfig = Field(default_factory=FeishuConfig)

  model_config = SettingsConfigDict(env_prefix="MYCLAW_", env_nested_delimiter="__")

  @classmethod
  def load(cls, path: Path | None = None) -> "Config":
    """Load configuration from a file or environment variables.

    Args:
        path: Optional path to config file.

    Returns:
        Config instance loaded from file or environment.
    """
    config_data = {}
    if path and path.exists():
      with path.open() as f:
        config_data = yaml.safe_load(f) or {}

    if not path:
      default_paths = [
        Path("config.yaml"),
        Path("~/.myclaw/config.yaml").expanduser(),
      ]
      for p in default_paths:
        if p.exists():
          with p.open() as f:
            config_data = yaml.safe_load(f) or {}
          break

    return cls(**config_data)
