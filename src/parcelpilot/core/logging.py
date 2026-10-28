from __future__ import annotations

import json
import logging
from typing import Any

from parcelpilot.settings import settings


def configure_logging() -> logging.Logger:
    logger = logging.getLogger("parcelpilot")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(handler)

    return logger


def log_event(logger: logging.Logger, event: str, context: dict[str, Any]) -> None:
    logger.debug("%s %s", event, json.dumps(context, sort_keys=True, default=str))
