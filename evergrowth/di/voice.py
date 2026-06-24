"""ElevenLabs TTS integration for DI voice."""

import json
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from urllib import request, error

logger = logging.getLogger("evergrowth.di.voice")

VOICE_ID = "CKfuQaJKfvUG2Wtrda3Y"
MODEL_ID = "eleven_flash_v2_5"
OUTPUT_DIR = Path.home() / "Desktop" / "lyra-voice"


def _get_api_key() -> str | None:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if key:
        return key
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as h:
            key, _ = winreg.QueryValueEx(h, "ELEVENLABS_API_KEY")
            return key
    except Exception:
        return None


def speak(text: str, block: bool = False) -> str | None:
    """Send text to ElevenLabs TTS and save to Desktop/lyra-voice/.
    
    Returns the path to the saved audio file, or None on failure.
    """
    api_key = _get_api_key()
    if not api_key:
        logger.warning("ELEVENLABS_API_KEY not found — TTS disabled")
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = OUTPUT_DIR / f"lyra-{stamp}.mp3"

    payload = json.dumps({
        "text": text[:5000],
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }).encode("utf-8")

    req = request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        data=payload,
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with request.urlopen(req) as resp:
            out_file.write_bytes(resp.read())
        logger.info(f"TTS saved: {out_file} ({out_file.stat().st_size} bytes)")

        if block:
            subprocess.Popen(["start", str(out_file)], shell=True)

        return str(out_file)
    except error.URLError as e:
        logger.error(f"TTS API error: {e}")
        return None
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None
