"""Structured application logging.

A single ``configure_logging`` call sets up a consistent format across the app
and Uvicorn. In production this can be swapped to JSON output without touching
call sites — every module just uses ``logging.getLogger(__name__)``.
"""
from __future__ import annotations

import logging
import sys

from app.core.config import settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def configure_logging() -> None:
    level = logging.DEBUG if settings.DEBUG else logging.INFO

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Align Uvicorn's loggers with ours so output is uniform.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True

    # SQLAlchemy is noisy at DEBUG; keep it at WARNING unless explicitly wanted.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
