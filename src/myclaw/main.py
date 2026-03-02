import asyncio
from pathlib import Path

import typer
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console

from myclaw.agent.client_connect import ClawAgentConnect
from myclaw.bus.events import OutboundMessage
from myclaw.bus.queue import MessageBus
from myclaw.channels.manager import ChannelManager
from myclaw.config import load_config
from myclaw.utils.paths import get_cwd_dir


load_dotenv()

app = typer.Typer()
console = Console()


@app.command()
def start():
  """Start the MyClaw gateway."""
  try:
    cwd_dir = get_cwd_dir()
    config = load_config(Path(cwd_dir) / Path("config.json"))

    console.print(
      f"[bold magenta]MyClaw[/bold magenta] Starting gateway on port {config.gateway.port}..."
    )

    bus = MessageBus()
    agent = ClawAgentConnect(config)
    agent.initialize()

    channel_manager = ChannelManager(config, bus)

    if channel_manager.enabled_channels:
      console.print(
        f"[green]✓[/green] Channels enabled: {', '.join(channel_manager.enabled_channels)}"
      )
    else:
      console.print("[yellow]Warning: No channels enabled[/yellow]")

    hb_cfg = config.gateway.heartbeat
    if hb_cfg.enabled:
      console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")

    # Agent processing loop
    async def process_inbound():
      async with agent:
        # Connect to Claude
        await agent.connect()
        console.print("[green]✓[/green] Connected to Claude")

        while True:
          try:
            msg = await bus.consume_inbound()
            logger.info(f"Agent received message from {msg.sender_id} via {msg.channel}")

            # Simple implementation without streaming for now
            full_response = ""
            async for chunk in agent.query(msg.content):
              full_response += chunk

            outbound = OutboundMessage(
              channel=msg.channel,
              chat_id=msg.chat_id,
              content=full_response or "done",
            )
            await bus.publish_outbound(outbound)
            logger.info("Task completed for message from {} via {}", msg.sender_id, msg.channel)
          except asyncio.CancelledError:  # noqa: PERF203
            logger.info("Agent task cancelled")
            break
          except Exception:
            logger.exception("Error processing inbound message")

    async def run():
      agent_task = asyncio.create_task(process_inbound())
      try:
        await asyncio.gather(
          agent_task,
          channel_manager.start_all(),
        )
      except KeyboardInterrupt:
        console.print("\nShutting down...")
      finally:
        agent_task.cancel()
        await channel_manager.stop_all()

    asyncio.run(run())
  except KeyboardInterrupt:
    console.print("\n[bold yellow]Agent stopped by user.[/bold yellow]")


if __name__ == "__main__":
  app()
