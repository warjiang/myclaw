import asyncio
import logging

import typer
from dotenv import load_dotenv
from rich.console import Console

from myclaw.agent.config import Config
from myclaw.agent.core import ClawAgent
from myclaw.channels.cli import CLIChannel
from myclaw.channels.feishu import FeishuChannel, MessageInfo


load_dotenv()

app = typer.Typer()
console = Console()
logger = logging.getLogger(__name__)


async def async_main():
  try:
    config = Config.load()

    logging.basicConfig(
      level=config.log_level,
      format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    agent = ClawAgent(config)
    await agent.initialize()

    async def handle_message(msg_info: MessageInfo):
      await channel.send_stream(agent.process_message(msg_info.text))

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

  except asyncio.CancelledError:
    console.print("\n[bold yellow]Agent shutdown initiated...[/bold yellow]")
  except Exception as e:
    console.print(f"[bold red]Fatal Error:[/bold red] {e}")
  finally:
    if "agent" in locals():
      try:
        await agent.close()
      except Exception as e:
        logger.debug(f"Error closing agent: {e}")


@app.command()
def start():
  """Start the MyClaw agent."""
  try:
    asyncio.run(async_main())
  except KeyboardInterrupt:
    console.print("\n[bold yellow]Agent stopped by user.[/bold yellow]")


if __name__ == "__main__":
  app()
