"""Structured logging, opt-in via CONDUCTOR_LOG_LEVEL."""

from __future__ import annotations

import logging
import os


def setup(level: str | None = None) -> None:
    lvl = (level or os.environ.get("CONDUCTOR_LOG_LEVEL", "WARNING")).upper()
    logging.basicConfig(
        level=getattr(logging, lvl, logging.WARNING),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S")
