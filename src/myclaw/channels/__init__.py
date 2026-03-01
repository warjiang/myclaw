"""Chat channels module with plugin architecture."""

from myclaw.channels.base import BaseChannel
from myclaw.channels.manager import ChannelManager


__all__ = ["BaseChannel", "ChannelManager"]
