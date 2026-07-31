"""One-off diagnostic for ACCOUNT_SETUP.md section 8: calls ElevenLabs TTS
directly using the config from .env, writes the result to an mp3 file so you
can confirm audio actually came back.

Run from the backend/ directory (so .env is found):
    .venv\\Scripts\\python.exe scripts\\verify_elevenlabs.py   (Windows)
    ./.venv/bin/python scripts/verify_elevenlabs.py            (macOS/Linux)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.elevenlabs_client import synthesize_speech  # noqa: E402

OUTPUT_PATH = Path(__file__).resolve().parent.parent / "verify_elevenlabs_output.mp3"


async def main() -> None:
    audio_bytes = await synthesize_speech("Hello from VoxMind, this is a test.", "en")
    OUTPUT_PATH.write_bytes(audio_bytes)
    print(f"OK — wrote {len(audio_bytes)} bytes to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
