"""One-shot watchdog for Evergrowth's persistent Windows workers."""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

HEARTBEAT_DIR = Path.home() / ".evergrowth" / "service-heartbeats"
STATE_PATH = Path.home() / ".evergrowth" / "runtime-supervisor.json"
REPO_ROOT = Path(__file__).resolve().parents[1]
PERSISTENT_MARKER = Path.home() / ".evergrowth" / "persistent-runtime.lock.json"
PERSISTENT_CONFIG = Path.home() / ".evergrowth" / "ethan-config.json"
PERSISTENT_ROLE = "evergrowth-runtime"
DISCORD_ROLE = "ethan-discord-bot"
DISCORD_SCRIPT = Path.home() / "Ethan" / "ethan_discord_runner.py"
DISCORD_CONFIG = Path.home() / "Ethan" / "watcher_config.json"
DISCORD_PYTHON = Path(r"C:\Python314\pythonw.exe")
STALE_AFTER_SECONDS = 120
RESTART_COOLDOWN_SECONDS = 300
MAX_RESTARTS_PER_HOUR = 3

TASKS = {
    "browser-activity-producer": "Evergrowth Browser Activity Producer",
    "activity-presence-detector": "Evergrowth Activity Presence Detector",
    "presence-daemon": "Evergrowth Presence Bridge",
}


@dataclass
class ServiceHealth:
    role: str
    state: str
    age_seconds: float | None
    reason: str


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2)
    temporary = path.with_name(
        f"{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    temporary.write_text(text, encoding="utf-8")
    try:
        for _ in range(100):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                try:
                    path.write_text(text, encoding="utf-8")
                    return
                except PermissionError:
                    time.sleep(0.05)
        raise PermissionError(f"state file remained locked: {path}")
    finally:
        temporary.unlink(missing_ok=True)


def load_json(path: Path, default: dict) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else dict(default)
    except (OSError, json.JSONDecodeError):
        return dict(default)


def assess(role: str, now: float | None = None) -> ServiceHealth:
    current = time.time() if now is None else now
    path = HEARTBEAT_DIR / f"{role}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        heartbeat_at = float(payload["heartbeat_at"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ServiceHealth(role, "missing", None, "no valid heartbeat")
    age = max(0.0, current - heartbeat_at)
    if age > STALE_AFTER_SECONDS:
        return ServiceHealth(role, "stale", age, "heartbeat too old")
    return ServiceHealth(role, "healthy", age, "heartbeat current")


def assess_discord(now: float | None = None) -> ServiceHealth:
    path = HEARTBEAT_DIR / f"{DISCORD_ROLE}.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ServiceHealth(DISCORD_ROLE, "missing", None, "no valid heartbeat")
    if payload.get("blocked"):
        blocked_mtime = float(payload.get("config_mtime", 0) or 0)
        try:
            current_mtime = DISCORD_CONFIG.stat().st_mtime
        except OSError:
            current_mtime = 0
        if current_mtime > blocked_mtime:
            return ServiceHealth(DISCORD_ROLE, "missing", None, "configuration changed")
        return ServiceHealth(
            DISCORD_ROLE, "blocked", None,
            str(payload.get("reason") or "authentication blocked"),
        )
    return assess(DISCORD_ROLE, now)


def process_alive(pid: int | None) -> bool:
    """Return whether a recorded process still exists without signaling it."""
    if not pid:
        return False
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False

    if os.name == "nt":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        kernel32.OpenProcess.restype = ctypes.c_void_p
        kernel32.GetExitCodeProcess.argtypes = [
            ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)
        ]
        kernel32.GetExitCodeProcess.restype = ctypes.c_bool
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel32.CloseHandle.restype = ctypes.c_bool
        handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        exit_code = ctypes.c_uint32()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return bool(ok and exit_code.value == 259)  # STILL_ACTIVE

    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def assess_persistent(now: float | None = None) -> ServiceHealth:
    """Assess the one persistent Evergrowth runtime from its singleton marker."""
    current = time.time() if now is None else now
    try:
        payload = json.loads(PERSISTENT_MARKER.read_text(encoding="utf-8"))
        pid = int(payload["pid"])
        acquired_at = float(payload.get("acquired_at", current))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return ServiceHealth(PERSISTENT_ROLE, "missing", None, "no valid singleton marker")
    age = max(0.0, current - acquired_at)
    if not process_alive(pid):
        return ServiceHealth(PERSISTENT_ROLE, "missing", age, "singleton owner is not running")
    return ServiceHealth(PERSISTENT_ROLE, "healthy", age, "singleton owner is running")


def recent_attempts(state: dict, role: str, now: float) -> list[float]:
    attempts = state.get("restart_attempts", {}).get(role, [])
    return [float(item) for item in attempts if now - float(item) < 3600]


def restart_allowed(state: dict, role: str, now: float) -> tuple[bool, str]:
    attempts = recent_attempts(state, role, now)
    if len(attempts) >= MAX_RESTARTS_PER_HOUR:
        return False, "hourly restart budget exhausted"
    if attempts and now - attempts[-1] < RESTART_COOLDOWN_SECONDS:
        return False, "restart cooldown active"
    return True, "restart allowed"


def start_task(task_name: str) -> None:
    result = subprocess.run(
        ["schtasks", "/run", "/tn", task_name],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())


def start_persistent_runtime() -> int:
    """Launch the singleton-protected persistent autonomy runtime."""
    executable = REPO_ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not executable.exists():
        raise RuntimeError(f"runtime executable missing: {executable}")
    flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    process = subprocess.Popen(
        [
            str(executable), "-X", "utf8", "-m", "evergrowth",
            "--config", str(PERSISTENT_CONFIG),
        ],
        cwd=str(REPO_ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    return int(process.pid)


def start_discord_bot() -> int:
    """Launch the singleton-protected Ethan Discord bot."""
    if not DISCORD_PYTHON.exists():
        raise RuntimeError(f"Discord Python missing: {DISCORD_PYTHON}")
    if not DISCORD_SCRIPT.exists():
        raise RuntimeError(f"Discord bot script missing: {DISCORD_SCRIPT}")
    flags = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    process = subprocess.Popen(
        [str(DISCORD_PYTHON), str(DISCORD_SCRIPT)],
        cwd=str(DISCORD_SCRIPT.parent),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )
    return int(process.pid)


def run_once(now: float | None = None) -> dict:
    current = time.time() if now is None else now
    state = load_json(STATE_PATH, {"restart_attempts": {}, "events": []})
    state.setdefault("restart_attempts", {})
    state.setdefault("events", [])
    report = {"checked_at": current, "services": {}, "actions": []}

    persistent = assess_persistent(current)
    report["services"][PERSISTENT_ROLE] = persistent.__dict__
    if persistent.state != "healthy":
        allowed, reason = restart_allowed(state, PERSISTENT_ROLE, current)
        if not allowed:
            action = {
                "role": PERSISTENT_ROLE,
                "action": "suppressed",
                "reason": reason,
            }
        else:
            try:
                launcher_pid = start_persistent_runtime()
                action = {
                    "role": PERSISTENT_ROLE,
                    "action": "start_requested",
                    "reason": persistent.reason,
                    "launcher_pid": launcher_pid,
                }
            except Exception as exc:
                action = {
                    "role": PERSISTENT_ROLE,
                    "action": "start_failed",
                    "reason": str(exc),
                }
            attempts = recent_attempts(state, PERSISTENT_ROLE, current)
            attempts.append(current)
            state["restart_attempts"][PERSISTENT_ROLE] = attempts
        state["events"].append({"at": current, **action})
        report["actions"].append(action)

    discord_health = assess_discord(current)
    report["services"][DISCORD_ROLE] = discord_health.__dict__
    if discord_health.state == "blocked":
        action = {
            "role": DISCORD_ROLE,
            "action": "blocked",
            "reason": discord_health.reason,
        }
        report["actions"].append(action)
    elif discord_health.state == "stale":
        action = {
            "role": DISCORD_ROLE,
            "action": "guarded_restart_required",
            "reason": discord_health.reason,
        }
        state["events"].append({"at": current, **action})
        report["actions"].append(action)
    elif discord_health.state != "healthy":
        allowed, reason = restart_allowed(state, DISCORD_ROLE, current)
        if not allowed:
            action = {
                "role": DISCORD_ROLE,
                "action": "suppressed",
                "reason": reason,
            }
        else:
            try:
                launcher_pid = start_discord_bot()
                action = {
                    "role": DISCORD_ROLE,
                    "action": "start_requested",
                    "reason": discord_health.reason,
                    "launcher_pid": launcher_pid,
                }
            except Exception as exc:
                action = {
                    "role": DISCORD_ROLE,
                    "action": "start_failed",
                    "reason": str(exc),
                }
            attempts = recent_attempts(state, DISCORD_ROLE, current)
            attempts.append(current)
            state["restart_attempts"][DISCORD_ROLE] = attempts
        state["events"].append({"at": current, **action})
        report["actions"].append(action)

    for role, task_name in TASKS.items():
        health = assess(role, current)
        report["services"][role] = health.__dict__
        if health.state == "healthy":
            continue
        if health.state == "stale":
            action = {
                "role": role,
                "action": "guarded_restart_required",
                "reason": health.reason,
            }
            state["events"].append({"at": current, **action})
            report["actions"].append(action)
            continue
        allowed, reason = restart_allowed(state, role, current)
        if not allowed:
            report["actions"].append(
                {"role": role, "action": "suppressed", "reason": reason}
            )
            continue

        try:
            start_task(task_name)
            action = {
                "role": role,
                "action": "start_requested",
                "reason": health.reason,
            }
        except Exception as exc:
            action = {
                "role": role,
                "action": "start_failed",
                "reason": str(exc),
            }

        attempts = recent_attempts(state, role, current)
        attempts.append(current)
        state["restart_attempts"][role] = attempts
        state["events"].append({"at": current, **action})
        report["actions"].append(action)

    soak = state.setdefault("soak", {})
    all_healthy = all(
        item.get("state") == "healthy" for item in report["services"].values()
    )
    if all_healthy:
        soak.setdefault("healthy_since", current)
        soak["healthy_checks"] = int(soak.get("healthy_checks", 0)) + 1
        soak["last_healthy_at"] = current
    else:
        soak["last_break_at"] = current
        soak["healthy_since"] = None
        soak["healthy_checks"] = 0
    report["soak"] = dict(soak)

    state["events"] = state["events"][-100:]
    state["last_report"] = report
    atomic_json(STATE_PATH, state)
    return report


def main() -> None:
    print(json.dumps(run_once(), indent=2))


if __name__ == "__main__":
    main()
