import asyncio

import typer
from dotenv import load_dotenv
from rich.console import Console

from myclaw.agent.config import Config
from myclaw.agent.core import ClawAgent
from myclaw.channels.cli import CLIChannel
from myclaw.channels.feishu import FeishuChannel


load_dotenv()

app = typer.Typer()
console = Console()


async def async_main():
  try:
    config = Config.load()

    agent = ClawAgent(config)
    await agent.initialize()

    async def handle_message(text: str):
      console.print("[bold purple]Claw:[/bold purple] ", end="")
      async for chunk in agent.process_message(text):
        console.print(chunk, end="")
      console.print()

    feishu_config = config.feishu
    if feishu_config.app_id and feishu_config.app_secret:
      channel = FeishuChannel(
        on_message=handle_message,
        app_id=feishu_config.app_id,
        app_secret=feishu_config.app_secret,
        verification_token=feishu_config.verification_token,
        encrypt_key=feishu_config.encrypt_key,
        mode=feishu_config.mode,
        webhook_url=feishu_config.webhook_url,
        http_host=feishu_config.http_host,
        http_port=feishu_config.http_port,
      )
      console.print("[bold green]Starting Feishu channel...[/bold green]")
    else:
      channel = CLIChannel(on_message=handle_message)

    await channel.start()

  except Exception as e:
    console.print(f"[bold red]Fatal Error:[/bold red] {e}")
  finally:
    if "agent" in locals():
      await agent.close()


@app.command()
def start():
  """Start the MyClaw agent."""
  asyncio.run(async_main())


if __name__ == "__main__":
  app()
