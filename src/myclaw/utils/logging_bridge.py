"""Logging bridge to redirect standard library logging to loguru."""

import logging
import sys
from typing import Any

from loguru import logger


class LoguruHandler(logging.Handler):
    """Custom logging handler that redirects logs to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to loguru."""
        # Get corresponding loguru level
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller to get proper file/line info
        frame, depth = sys._getframe(6), 6
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        # Log to loguru with proper context
        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging_bridge(
    logger_name: str | None = None,
    level: int = logging.WARNING,
) -> None:
    """Setup bridge from standard library logging to loguru.

    Args:
        logger_name: Name of the logger to bridge. If None, bridges the root logger.
        level: Minimum logging level to capture.
    """
    # Get or create logger
    std_logger = logging.getLogger(logger_name)

    # Remove existing handlers to avoid duplicate logs
    std_logger.handlers = []

    # Add our custom handler
    handler = LoguruHandler()
    handler.setLevel(level)
    std_logger.addHandler(handler)

    # Don't propagate to parent to avoid duplicates
    std_logger.propagate = False


def bridge_lark_logging() -> None:
    """Bridge lark-oapi SDK logging to loguru.

    This redirects the Lark SDK's internal logging to use loguru instead.
    """
    # Remove existing Lark handlers
    lark_logger = logging.getLogger("Lark")
    lark_logger.handlers = []

    # Add loguru bridge handler
    handler = LoguruHandler()
    handler.setLevel(logging.DEBUG)
    lark_logger.addHandler(handler)
    lark_logger.setLevel(logging.DEBUG)

    # Don't propagate to avoid duplicates
    lark_logger.propagate = False
