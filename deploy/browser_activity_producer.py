"""Record activity only while the target ChatGPT conversation is foreground."""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from ctypes import wintypes
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_OUTPUT = Path(r"C:\Users\susur\.evergrowth\browser_activity.json")
BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"}
DEFAULT_TITLE_SUBSTRING = "Browser Presence Detection"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


class LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def foreground_window() -> tuple[str, str]:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return "", ""
    length = user32.GetWindowTextLengthW(hwnd)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title, length + 1)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        return "", title.value
    try:
        size = wintypes.DWORD(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(process, 0, image, ctypes.byref(size)):
            return "", title.value
        return Path(image.value).name.lower(), title.value
    finally:
        kernel32.CloseHandle(process)


def input_idle_seconds() -> float:
    info = LastInputInfo(cbSize=ctypes.sizeof(LastInputInfo))
    if not user32.GetLastInputInfo(ctypes.byref(info)):
        return float("inf")
    return max(0.0, (kernel32.GetTickCount64() - info.dwTime) / 1000.0)


def is_chatgpt_window(
    process: str,
    title: str,
    idle_seconds: float,
    max_idle_seconds: float,
    title_substring: str,
) -> bool:
    return (
        process in BROWSER_PROCESSES
        and title_substring.lower() in title.lower()
        and idle_seconds <= max_idle_seconds
    )


def is_chatgpt_active(max_idle_seconds: float, title_substring: str) -> bool:
    process, title = foreground_window()
    return is_chatgpt_window(
        process,
        title,
        input_idle_seconds(),
        max_idle_seconds,
        title_substring,
    )


def write_activity(path: Path, session_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": session_id,
        "observed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload), encoding="utf-8")
    temporary.replace(path)


def run(
    output: Path,
    session_id: str,
    poll_seconds: float,
    max_idle_seconds: float,
    title_substring: str,
) -> None:
    while True:
        if is_chatgpt_active(max_idle_seconds, title_substring):
            write_activity(output, session_id)
        time.sleep(poll_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--session-id", default="browser:chatgpt")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--max-idle-seconds", type=float, default=60.0)
    parser.add_argument("--title-substring", default=DEFAULT_TITLE_SUBSTRING)
    args = parser.parse_args()
    run(
        args.output,
        args.session_id,
        args.poll_seconds,
        args.max_idle_seconds,
        args.title_substring,
    )


if __name__ == "__main__":
    main()
