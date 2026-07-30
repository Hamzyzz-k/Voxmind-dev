import re

from app.services.otp import generate_otp, hash_otp, verify_otp


def test_generate_otp_is_six_digits():
    for _ in range(50):
        code = generate_otp()
        assert re.fullmatch(r"\d{6}", code)


def test_hash_and_verify_roundtrip():
    code = "123456"
    hashed = hash_otp(code)
    assert verify_otp(code, hashed) is True


def test_verify_rejects_wrong_code():
    hashed = hash_otp("123456")
    assert verify_otp("654321", hashed) is False


def test_verify_rejects_malformed_hash():
    assert verify_otp("123456", "not-a-valid-hash") is False


def test_hash_is_salted_differently_each_time():
    hashed1 = hash_otp("123456")
    hashed2 = hash_otp("123456")
    assert hashed1 != hashed2
    assert verify_otp("123456", hashed1)
    assert verify_otp("123456", hashed2)
