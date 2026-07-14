import importlib.util
from pathlib import Path

PRODUCER_PATH = Path(__file__).parents[1] / "deploy" / "browser_activity_producer.py"
SPEC = importlib.util.spec_from_file_location("browser_activity_producer", PRODUCER_PATH)
producer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(producer)


def test_matching_chatgpt_conversation_counts_as_activity():
    assert producer.is_chatgpt_window(
        "chrome.exe",
        "Browser Presence Detection - Google Chrome",
        idle_seconds=3,
        max_idle_seconds=60,
        title_substring="Browser Presence Detection",
    )


def test_other_browser_tab_does_not_count_as_chatgpt_activity():
    assert not producer.is_chatgpt_window(
        "chrome.exe",
        "Discord - Google Chrome",
        idle_seconds=3,
        max_idle_seconds=60,
        title_substring="Browser Presence Detection",
    )


def test_non_browser_application_does_not_count_as_chatgpt_activity():
    assert not producer.is_chatgpt_window(
        "telegram.exe",
        "Telegram",
        idle_seconds=3,
        max_idle_seconds=60,
        title_substring="Browser Presence Detection",
    )


def test_idle_chatgpt_window_does_not_refresh_activity():
    assert not producer.is_chatgpt_window(
        "msedge.exe",
        "Browser Presence Detection - Microsoft Edge",
        idle_seconds=61,
        max_idle_seconds=60,
        title_substring="Browser Presence Detection",
    )
