from rich.console import Console
from rich.prompt import Prompt

from .base import BaseChannel
from .feishu import MessageInfo


console = Console()


class CLIChannel(BaseChannel):
  async def start(self):
    """Start CLI interaction loop."""
    console.print("[bold green]Welcome to MyClaw![/bold green]")

    while True:
      try:
        # Use standard input for blocking wait
        user_input = Prompt.ask("[bold blue]You[/bold blue]")
        if user_input.lower() in ("exit", "quit", "/bye"):
          break

        msg_info = MessageInfo(text=user_input, sender_id="")
        await self.on_message(msg_info)

      except KeyboardInterrupt:
        break
      except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

  async def send(self, message: str, end: str = "\n"):
    """Display message to user."""
    console.print(f"{message}", end=end)
