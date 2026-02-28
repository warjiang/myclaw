import asyncio
from pathlib import Path

import typer
from dotenv import load_dotenv
from loguru import logger
from rich.console import Console

from myclaw.agent.core import ClawAgent
from myclaw.bus.events import OutboundMessage
from myclaw.bus.queue import MessageBus
from myclaw.channels.manager import ChannelManager
from myclaw.config import load_config

load_dotenv()

app = typer.Typer()
console = Console()


@app.command()
def start():
    """Start the MyClaw gateway."""
    try:
        # config = Config.load()
        config = load_config(Path('/Users/dingwenjiang/workspace/codereview/warjiang/myclaw/config.json'))

        console.print(f"[bold magenta]MyClaw[/bold magenta] Starting gateway on port {config.gateway.port}...")

        bus = MessageBus()
        agent = ClawAgent(config)
        agent.initialize()

        channel_manager = ChannelManager(config, bus)

        if channel_manager.enabled_channels:
            console.print(f"[green]✓[/green] Channels enabled: {', '.join(channel_manager.enabled_channels)}")
        else:
            console.print("[yellow]Warning: No channels enabled[/yellow]")

        hb_cfg = config.gateway.heartbeat
        if hb_cfg.enabled:
            console.print(f"[green]✓[/green] Heartbeat: every {hb_cfg.interval_s}s")

        # Agent processing loop
        async def process_inbound():
            while True:
                try:
                    msg = await bus.consume_inbound()
                    logger.info(f"Agent received message from {msg.sender_id} via {msg.channel}")

                    # Simple implementation without streaming for now
                    full_response = ""
                    async for chunk in agent.process_message(msg.content):
                        full_response += chunk

                    outbound = OutboundMessage(
                        channel=msg.channel,
                        chat_id=msg.chat_id,
                        content=full_response,
                    )
                    await bus.publish_outbound(outbound)
                except asyncio.CancelledError:
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
                try:
                    await agent.close()
                except Exception as e:
                    logger.debug(f"Error closing agent: {e}")

        asyncio.run(run())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Agent stopped by user.[/bold yellow]")


if __name__ == "__main__":
    app()
