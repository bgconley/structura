from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")


def log_event(event: str, **fields: Any) -> None:
    payload = {
        "ts": datetime.now(UTC).isoformat(),
        "event": event,
        **fields,
    }
    logging.getLogger("structura").info(json.dumps(payload, default=str, sort_keys=True))
