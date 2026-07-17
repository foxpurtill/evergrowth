"""Atomic heartbeat files for long-running deployed workers."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

DEFAULT_DIR = Path.home() / ".evergrowth" / "service-heartbeats"


def write_heartbeat(role: str, *, state_dir: Path = DEFAULT_DIR) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    target = state_dir / f"{role}.json"
    payload = {
        "role": role,
        "pid": os.getpid(),
        "heartbeat_at": time.time(),
    }
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(target)
    return target
