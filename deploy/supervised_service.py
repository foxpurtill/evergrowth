"""Launch one registered long-running worker under a singleton service lease."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from evergrowth.supervision import ServiceLease

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path.home() / ".evergrowth" / "services"
SERVICES = {
    "presence-daemon": ROOT / "deploy" / "evergrowth_presence_daemon.py",
    "activity-presence-detector": ROOT / "deploy" / "activity_presence_detector.py",
    "browser-activity-producer": ROOT / "deploy" / "browser_activity_producer.py",
}


def run(role: str, extra_args: list[str] | None = None) -> int:
    script = SERVICES[role]
    lease = ServiceLease(role, STATE_DIR)
    if not lease.acquire():
        return 23
    command = [sys.executable, str(script), *(extra_args or [])]
    process = subprocess.Popen(command, cwd=str(ROOT))
    try:
        while process.poll() is None:
            lease.heartbeat()
            time.sleep(5)
        return int(process.returncode or 0)
    finally:
        if process.poll() is None:
            process.terminate()
        lease.release()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=sorted(SERVICES))
    args, extra = parser.parse_known_args()
    raise SystemExit(run(args.role, extra))


if __name__ == "__main__":
    main()
