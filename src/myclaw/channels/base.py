from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class BaseChannel(ABC):
  def __init__(self, on_message: Callable[[str], Awaitable[None]]):
    self.on_message = on_message

  @abstractmethod
  async def start(self):
    """Start listening for messages."""

  @abstractmethod
  async def send(self, message: str, end: str = "\n"):
    """Send a message to the user."""
