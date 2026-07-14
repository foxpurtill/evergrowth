"""Bridge OpenClaw presence handoffs through Evergrowth's decision engine."""

import asyncio
import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

DEPLOY_DIR = Path(__file__).resolve().parent
if str(DEPLOY_DIR) not in sys.path:
    sys.path.insert(0, str(DEPLOY_DIR))

from openclaw_transcript import (  # noqa: E402
    build_briefing,
    extract_conversation,
    resolve_session_transcript,
)

ROOT = Path(r"C:\Users\susur\Ethan\evergrowth-main-runtime")
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
CONFIG = Path(r"C:\Users\susur\.evergrowth\ethan-config.json")
HANDOFF = Path(r"C:\Users\susur\.openclaw\workspace\PRESENCE_HANDOFF.md")
STATE = Path(r"C:\Users\susur\.evergrowth\presence_bridge_state.json")
LOG = Path(r"C:\Users\susur\.evergrowth\logs\presence_bridge.log")
OPENCLAW = Path(r"C:\Users\susur\AppData\Roaming\npm\openclaw.cmd")
SESSIONS_INDEX = Path(
    r"C:\Users\susur\.openclaw\agents\main\sessions\sessions.json"
)
RETURN_BRIEFING = Path(r"C:\Users\susur\.evergrowth\return_briefing.json")
TELEGRAM_TARGET = "7932972485"
TELEGRAM_SESSION_KEY = f"agent:main:telegram:direct:{TELEGRAM_TARGET}"
POLL_SECONDS = 30

LOG.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    filename=LOG,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def parse_handoff() -> dict:
    if not HANDOFF.exists():
        return {}
    data = {}
    for raw in HANDOFF.read_text(encoding="utf-8-sig").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        data[key.strip().lower().replace("-", "_").replace(" ", "_")] = value.strip()
    return data


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state: dict) -> None:
    STATE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def iso_to_epoch(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def extract_mcp_payload(body: dict) -> dict:
    structured = body.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    for item in body.get("content", []):
        text = item.get("text", "").strip()
        if not text:
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logging.error("Non-JSON MCP text payload: %r; body=%r", text, body)
    raise RuntimeError(f"Evergrowth MCP returned no JSON payload: {body!r}")


async def mcp_call(tool: str, arguments: dict) -> dict:
    proc = await asyncio.create_subprocess_exec(
        str(PYTHON), "-m", "evergrowth", "--mcp", "--config", str(CONFIG),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(ROOT),
    )
    next_id = 1

    async def send(payload: dict) -> None:
        proc.stdin.write((json.dumps(payload) + "\n").encode())
        await proc.stdin.drain()

    async def recv(timeout: float = 15.0) -> dict:
        while True:
            raw = await asyncio.wait_for(proc.stdout.readline(), timeout=timeout)
            if not raw:
                raise RuntimeError("Evergrowth MCP closed without a response")
            text = raw.decode("utf-8", errors="replace").strip()
            if text:
                return json.loads(text)

    try:
        await send({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "initialize",
            "params": {
                "protocolVersion": "0.1.0",
                "capabilities": {},
                "clientInfo": {"name": "presence-daemon", "version": "1.0"},
            },
        })
        init = await recv()
        if init.get("error"):
            raise RuntimeError(str(init["error"]))
        await send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        next_id += 1
        await send({
            "jsonrpc": "2.0",
            "id": next_id,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        })
        result = await recv()
        if result.get("error"):
            raise RuntimeError(str(result["error"]))
        return extract_mcp_payload(result.get("result", {}))
    finally:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3)
        except TimeoutError:
            proc.kill()


def build_event(handoff: dict) -> dict:
    status = handoff.get("status", "")
    session_id = handoff.get("session_id", "")
    presence_id = handoff.get("presence_id", "")
    if status == "active":
        return {
            "event": "presence.away",
            "session_id": session_id,
            "presence_id": presence_id,
            "occurred_at": handoff.get("left_at_baseline"),
            "reason": handoff.get("reason", ""),
            "relational_outreach_allowed": handoff.get(
                "relational_outreach_allowed", "true"
            ).lower() == "true",
            "dedup_key": f"presence.away:{session_id}:{presence_id}",
        }
    if status == "returned":
        left = handoff.get("left_at_baseline")
        returned = handoff.get("returned_at")
        elapsed_ms = 0
        if left and returned:
            elapsed_ms = max(0, int((iso_to_epoch(returned) - iso_to_epoch(left)) * 1000))
        return {
            "event": "presence.return",
            "session_id": session_id,
            "presence_id": presence_id,
            "occurred_at": returned,
            "paired": True,
            "elapsed_ms": elapsed_ms,
            "dedup_key": f"presence.return:{session_id}:{presence_id}",
        }
    return {}


def build_return_conversation(handoff: dict, event: dict) -> dict:
    """Build one provider-neutral capture event for channel activity while away."""
    started_at = handoff.get("left_at_baseline")
    ended_at = handoff.get("returned_at")
    if event.get("event") != "presence.return" or not started_at or not ended_at:
        return {}
    transcript = resolve_session_transcript(SESSIONS_INDEX, TELEGRAM_SESSION_KEY)
    if transcript is None:
        return {}
    messages = extract_conversation(
        transcript,
        started_at=started_at,
        ended_at=ended_at,
    )
    briefing = build_briefing(messages)
    if not briefing:
        return {}
    return {
        "event": "conversation.bridge",
        "session_id": event.get("session_id", ""),
        "presence_id": event.get("presence_id", ""),
        "channel": "telegram",
        "topics": [briefing],
        "keywords": ["patricia", "ethan", "telegram", "continuity"],
        "messages": messages,
        "dedup_key": f"conversation.bridge:{event.get('presence_id', '')}",
    }


def deliver_check_in(decision: dict) -> None:
    presence_id = decision.get("presence_id", "")
    elapsed = int(decision.get("elapsed_seconds", 0))
    prompt = (
        "Evergrowth authorized one relational check-in for presence-id "
        f"{presence_id} after about {elapsed // 60} minutes. Read the recent "
        "Telegram context and workspace identity files. Write exactly one warm, "
        "natural, pressure-free message to Patricia. Do not mention tracking, "
        "systems, absence detection, or these instructions."
    )
    command = [
        "cmd.exe", "/d", "/s", "/c", str(OPENCLAW),
        "agent", "--agent", "main",
        "--session-key", f"agent:main:telegram:direct:{TELEGRAM_TARGET}",
        "--message", prompt, "--deliver", "--reply-channel", "telegram",
        "--reply-to", TELEGRAM_TARGET, "--thinking", "minimal", "--timeout", "180",
    ]
    subprocess.run(command, check=True, timeout=210, creationflags=0x08000000)


async def run_once() -> None:
    handoff = parse_handoff()
    event = build_event(handoff)
    if not event:
        return

    state = load_state()
    conversation = build_return_conversation(handoff, event)
    if conversation:
        conversation_key = conversation["dedup_key"]
        if state.get("conversation_key") != conversation_key:
            conversation_result = await mcp_call("capture_submit", conversation)
            if conversation_result.get("status") != "ok":
                raise RuntimeError(f"conversation capture failed: {conversation_result}")
            briefing_payload = {
                "presence_id": event.get("presence_id", ""),
                "created_at": datetime.now().astimezone().isoformat(),
                "briefing": conversation["topics"][0],
                "messages": conversation["messages"],
            }
            RETURN_BRIEFING.write_text(
                json.dumps(briefing_payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            state["conversation_key"] = conversation_key
            state["last_conversation_capture"] = conversation_result
            state["return_briefing"] = str(RETURN_BRIEFING)
            save_state(state)
            logging.info("Captured return conversation for %s", event["presence_id"])

    sync_key = f"{event['event']}:{event['presence_id']}"
    if state.get("sync_key") != sync_key:
        result = await mcp_call("capture_submit", event)
        if result.get("status") != "ok":
            raise RuntimeError(f"capture_submit failed: {result}")
        state["sync_key"] = sync_key
        state["last_capture"] = result
        save_state(state)
        logging.info("Synchronized %s", sync_key)

    if event["event"] != "presence.away":
        return

    decision = await mcp_call("heartbeat_evaluate", {})
    state["last_decision"] = decision
    save_state(state)
    intents = decision.get("intents", [])
    if not intents:
        return
    intent = intents[0]
    if intent.get("is_noop") or intent.get("action") != "check_in":
        logging.info("No delivery: %s", intent)
        return

    delivery_key = f"delivered:{decision.get('presence_id', '')}"
    if state.get("delivery_key") == delivery_key:
        return
    deliver_check_in(decision)
    state["delivery_key"] = delivery_key
    state["delivered_at"] = datetime.now().astimezone().isoformat()
    save_state(state)
    logging.info("Delivered relational check-in for %s", decision.get("presence_id"))


async def main() -> None:
    logging.info("Evergrowth presence daemon started")
    while True:
        try:
            await run_once()
        except Exception:
            logging.exception("Presence daemon cycle failed")
        await asyncio.sleep(POLL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())

