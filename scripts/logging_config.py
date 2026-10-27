"""Shared logging configuration for PowerVote pipeline scripts."""
from __future__ import annotations

import logging
import sys


def configure_logging(level: int = logging.INFO, name: str = "powervote") -> logging.Logger:
    """Configure and return a logger with a consistent format.

    Call once at the entry point of each pipeline script:

        from scripts.logging_config import configure_logging
        logger = configure_logging()
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        # Already configured (e.g. called twice in tests); return as-is.
        return logger

    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger
