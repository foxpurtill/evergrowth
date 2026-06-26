"""Local Orpheus TTS for DI voice — zero cost, no API keys.

Calls standalone orpheus_tts.py via the Orpheus venv Python.
Emotion tags are preprocessed for better vocal quality.
"""

import logging
import re
import subprocess
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("evergrowth.di.voice")

ORPHEUS_PYTHON = str(Path.home() / "LocalOrpheusTTS" / ".venv" / "Scripts" / "python.exe")
ORPHEUS_SCRIPT = str(Path.home() / "LocalOrpheusTTS" / "orpheus_tts.py")
DEFAULT_VOICE = "tara"
OUTPUT_DIR = Path.home() / "Desktop" / "lyra-voice"

# Emotion tags that sound better as text for Orpheus 3B
# Tested: "Hehe.." beats <laugh> tag, "*laughs*" is sarcastic
EMOTION_MAP = {
    "<laugh>": "Hehe..",
    "<chuckle>": "Hehe..",
}


def _preprocess(text: str) -> str:
    """Replace emotion tags that Orpheus 3B handles poorly with text alternatives."""
    for tag, replacement in EMOTION_MAP.items():
        text = text.replace(tag, replacement)
    return text


def speak(text: str, block: bool = False, voice: str = DEFAULT_VOICE) -> str | None:
    """Generate speech with local Orpheus TTS and save to Desktop/lyra-voice/.

    Returns the path to the saved audio file, or None on failure.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    text = _preprocess(text)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = OUTPUT_DIR / f"lyra-{stamp}.wav"

    cmd = [
        ORPHEUS_PYTHON, ORPHEUS_SCRIPT,
        "--voice", voice,
        "--text", text[:5000],
        "--output", str(out_file),
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            logger.error(f"Orpheus error: {result.stderr[:500]}")
            return None

        if not out_file.exists():
            logger.error("Orpheus ran but no output file")
            return None

        logger.info(f"TTS saved: {out_file} ({out_file.stat().st_size} bytes)")

        # Also write latest copy
        latest = OUTPUT_DIR / "latest_orpheus.wav"
        latest.write_bytes(out_file.read_bytes())

        if block:
            import os
            os.startfile(str(out_file))

        return str(out_file)
    except subprocess.TimeoutExpired:
        logger.error("Orpheus timed out (300s)")
        return None
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None
