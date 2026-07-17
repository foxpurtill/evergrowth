"""Build one human-readable status surface for the live Evergrowth runtime."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from runtime_supervisor import run_once as supervise_once
except ModuleNotFoundError:
    # Tests load this module directly rather than as a script from deploy/.
    supervise_once = None

HOME = Path.home()
EVERGROWTH = HOME / ".evergrowth"
ETHAN = HOME / "Ethan"
DEFAULT_OUTPUT = EVERGROWTH / "runtime-status.md"

SOURCES = {
    "chat_activity": ETHAN / "state" / "chat_activity.json",
    "browser_activity": EVERGROWTH / "browser_activity.json",
    "presence": EVERGROWTH / "activity_presence_state.json",
    "bridge": EVERGROWTH / "presence_bridge_state.json",
    "selfprompt": EVERGROWTH / "selfprompt_state.json",
    "heartbeat_signal": EVERGROWTH / "heartbeat_signal.txt",
    "supervisor": EVERGROWTH / "runtime-supervisor.json",
}


def load_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def parse_time(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def age_text(timestamp: float | None, now: float) -> str:
    if timestamp is None:
        return "unknown"
    seconds = max(0, int(now - timestamp))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3600:
        return f"{seconds // 60}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    return f"{seconds // 86400}d ago"


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def service_reports(state_dir: Path, now: float) -> list[dict]:
    reports = []
    for path in sorted(state_dir.glob("*.json")):
        record = load_json(path)
        heartbeat = float(record.get("heartbeat_at", 0) or 0)
        pid = record.get("pid")
        age = max(0.0, now - heartbeat) if heartbeat else None
        if not record:
            state, reason = "unknown", "unreadable heartbeat"
        elif record.get("blocked"):
            state = "blocked"
            reason = str(record.get("reason") or "service is blocked")
        elif age is not None and age > 180:
            state, reason = "stale", "worker heartbeat is older than 180 seconds"
        else:
            state, reason = "healthy", "worker heartbeat is current"
        reports.append({
            "role": record.get("role", path.stem), "state": state,
            "pid": pid, "age_seconds": age, "reason": reason,
        })
    return reports


def build_snapshot(now: float | None = None, sources: dict[str, Path] | None = None,
                   service_dir: Path | None = None) -> dict:
    now = time.time() if now is None else now
    sources = SOURCES if sources is None else sources
    chat = load_json(sources["chat_activity"])
    browser = load_json(sources["browser_activity"])
    presence = load_json(sources["presence"])
    bridge = load_json(sources["bridge"])
    selfprompt = load_json(sources["selfprompt"])
    supervisor = load_json(sources.get("supervisor", EVERGROWTH / "runtime-supervisor.json"))

    observed = parse_time(browser.get("observed_at"))
    last_chat = max(filter(None, [
        parse_time(chat.get("last_begin")), parse_time(chat.get("last_end"))
    ]), default=None)
    mode = presence.get("mode", "unknown")
    presence_id = presence.get("presence_id") or bridge.get("last_decision", {}).get("presence_id")
    decision = bridge.get("last_decision", {})
    intents = decision.get("intents", [])
    intent = intents[0] if intents else {}

    pending = bridge.get("delivery_pending_key")
    delivered = bridge.get("delivery_key")
    if pending:
        outreach = "delivery outcome pending"
    elif delivered:
        outreach = "last outreach confirmed delivered"
    elif intent.get("is_noop"):
        outreach = f"no-op: {intent.get('noop_reason') or intent.get('reason', 'no reason recorded')}"
    elif intent:
        outreach = f"authorized: {intent.get('action', 'unknown action')}"
    else:
        outreach = "no outreach decision recorded"

    heartbeat_text = ""
    try:
        heartbeat_text = sources["heartbeat_signal"].read_text(encoding="utf-8").strip()
    except OSError:
        pass

    services = service_reports(service_dir or EVERGROWTH / "service-heartbeats", now)
    supervisor_report = supervisor.get("last_report", {})
    supervisor_actions = supervisor_report.get("actions", [])
    supervisor_checked = supervisor_report.get("checked_at")
    soak = supervisor_report.get("soak", supervisor.get("soak", {}))
    issues = []
    if last_chat is None:
        issues.append("Chat activity source is missing or unreadable.")
    if observed is None:
        issues.append("Presence activity source is missing or unreadable.")
    elif last_chat and abs(observed - last_chat) > 5:
        issues.append("Published presence activity does not match the latest ChatGPT turn.")
    issues.extend(
        f"Service {item['role']} is {item['state']}: {item['reason']}."
        for item in services if item["state"] not in ("healthy", "historical")
    )
    issues.extend(
        f"Supervisor action for {item.get('role', 'unknown')}: {item.get('action')} ({item.get('reason', 'no reason')})."
        for item in supervisor_actions
        if item.get("action") in ("start_failed", "guarded_restart_required", "suppressed", "blocked")
    )

    return {
        "generated_at": datetime.fromtimestamp(now, timezone.utc).isoformat(),
        "overall": "attention" if issues else "healthy",
        "presence": {"mode": mode, "presence_id": presence_id,
                     "last_chat_age": age_text(last_chat, now),
                     "published_activity_age": age_text(observed, now)},
        "outreach": {"summary": outreach, "decision": intent,
                     "pending": bool(pending), "confirmed": bool(delivered)},
        "autonomy": {"heartbeat_signal": heartbeat_text or "unknown"},
        "services": services,
        "supervisor": {
            "last_check_age": age_text(supervisor_checked, now),
            "actions": supervisor_actions,
            "healthy_checks": int(soak.get("healthy_checks", 0) or 0),
            "healthy_for": age_text(soak.get("healthy_since"), now)
            if soak.get("healthy_since") else "not currently continuous",
            "last_break_age": age_text(soak.get("last_break_at"), now)
            if soak.get("last_break_at") else "none recorded",
        },
        "issues": issues,
    }


def render_markdown(snapshot: dict) -> str:
    presence = snapshot["presence"]
    outreach = snapshot["outreach"]
    lines = [
        "# Evergrowth Runtime Status",
        "",
        f"**Overall:** {snapshot['overall']}",
        f"**Generated:** {snapshot['generated_at']}",
        "",
        "## Presence",
        f"- Mode: {presence['mode']}",
        f"- Presence ID: {presence['presence_id'] or 'none'}",
        f"- Last real ChatGPT activity: {presence['last_chat_age']}",
        f"- Published presence activity: {presence['published_activity_age']}",
        "",
        "## Outreach",
        f"- {outreach['summary']}",
        "",
        "## Autonomy",
        f"- Heartbeat signal: {snapshot['autonomy']['heartbeat_signal']}",
        "",
        "## Services",
    ]
    if snapshot["services"]:
        for service in snapshot["services"]:
            age = age_text(
                time.time() - service["age_seconds"]
                if service["age_seconds"] is not None else None,
                time.time(),
            )
            lines.append(
                f"- {service['role']}: {service['state']} "
                f"(PID {service['pid'] or 'none'}, heartbeat {age})"
            )
    else:
        lines.append("- No worker heartbeats found.")

    supervisor = snapshot.get("supervisor", {})
    lines.extend([
        "",
        "## Recovery supervisor",
        f"- Last check: {supervisor.get('last_check_age', 'unknown')}",
        f"- Continuous healthy checks: {supervisor.get('healthy_checks', 0)}",
        f"- Healthy streak began: {supervisor.get('healthy_for', 'unknown')}",
        f"- Last streak break: {supervisor.get('last_break_age', 'none recorded')}",
    ])
    actions = supervisor.get("actions", [])
    if actions:
        lines.extend(
            f"- {item.get('role', 'unknown')}: {item.get('action')} ({item.get('reason', 'no reason')})"
            for item in actions
        )
    else:
        lines.append("- No recovery action was required.")

    lines.extend(["", "## Needs attention"])
    if snapshot["issues"]:
        lines.extend(f"- {issue}" for issue in snapshot["issues"])
    else:
        lines.append("- Nothing currently requires attention.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    supervisor_error = None
    if supervise_once is not None:
        try:
            supervise_once()
        except Exception as exc:
            supervisor_error = str(exc)
    snapshot = build_snapshot()
    if supervisor_error:
        snapshot["overall"] = "attention"
        snapshot["issues"].append(
            f"Recovery supervisor state update was temporarily blocked: {supervisor_error}"
        )
    text = json.dumps(snapshot, indent=2) if args.json else render_markdown(snapshot)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_name(
        f"{args.output.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    temporary.write_text(text, encoding="utf-8")
    try:
        for _ in range(100):
            try:
                os.replace(temporary, args.output)
                break
            except PermissionError:
                try:
                    args.output.write_text(text, encoding="utf-8")
                    break
                except PermissionError:
                    time.sleep(0.05)
        else:
            raise PermissionError(f"status file remained locked: {args.output}")
    finally:
        temporary.unlink(missing_ok=True)
    print(text, end="")


if __name__ == "__main__":
    main()
