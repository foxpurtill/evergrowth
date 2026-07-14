"""Tests for the Windows browser activity signal."""

import importlib.util
from pathlib import Path

PRODUCER_PATH = Path(__file__).parents[1] / "deploy" / "browser_activity_producer.py"
SPEC = importlib.util.spec_from_file_location("browser_activity_producer", PRODUCER_PATH)
producer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(producer)


def test_chatgpt_browser_window_counts_as_activity():
    assert producer.is_chatgpt_window(
        "chrome.exe", "Ethan - ChatGPT", idle_seconds=3, max_idle_seconds=60
    )


def test_other_browser_tab_does_not_count_as_chatgpt_activity():
    assert not producer.is_chatgpt_window(
        "chrome.exe", "Telegram Web", idle_seconds=3, max_idle_seconds=60
    )


def test_idle_chatgpt_window_does_not_refresh_activity():
    assert not producer.is_chatgpt_window(
        "msedge.exe", "ChatGPT", idle_seconds=61, max_idle_seconds=60
    )
