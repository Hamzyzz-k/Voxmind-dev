"""Pure OTP generation/hashing/verification logic — no I/O, easy to unit test."""

import hashlib
import hmac
import secrets


def generate_otp() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(code: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.sha256(f"{salt}{code}".encode()).hexdigest()
    return f"{salt}${digest}"


def verify_otp(code: str, stored_hash: str) -> bool:
    try:
        salt, digest = stored_hash.split("$", 1)
    except ValueError:
        return False
    expected = hashlib.sha256(f"{salt}{code}".encode()).hexdigest()
    return hmac.compare_digest(expected, digest)
