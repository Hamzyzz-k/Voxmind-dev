"""One-off diagnostic for ACCOUNT_SETUP.md section 7: sends a test OTP-style
email using the SMTP config from .env, so you can check SMTP works without
going through the full backend + Firebase auth flow.

Run from the backend/ directory (so .env is found):
    .venv\\Scripts\\python.exe scripts\\verify_smtp.py you@example.com   (Windows)
    ./.venv/bin/python scripts/verify_smtp.py you@example.com            (macOS/Linux)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.email_client import send_otp_email  # noqa: E402


async def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/verify_smtp.py you@example.com")
        sys.exit(1)

    to_email = sys.argv[1]
    await send_otp_email(to_email, "123456", 5)
    print(f"Sent to {to_email} — check the inbox (and spam folder).")


if __name__ == "__main__":
    asyncio.run(main())
