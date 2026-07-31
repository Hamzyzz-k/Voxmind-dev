"""Regression tests for emulator env handling.

An empty FIRESTORE_EMULATOR_HOST took the deployed backend down: the Google
client libraries check whether the variable is *present*, not whether it holds
anything, so `FIRESTORE_EMULATOR_HOST=""` means "emulator at address ''" and
every Firestore call dies with an opaque
`Unknown: the target uri is not valid: dns:///`.
"""

import os
from dataclasses import dataclass

from app.firebase_app import apply_emulator_env

FIRESTORE = "FIRESTORE_EMULATOR_HOST"
AUTH = "FIREBASE_AUTH_EMULATOR_HOST"


@dataclass
class FakeSettings:
    firestore_emulator_host: str = ""
    firebase_auth_emulator_host: str = ""


def _clear(monkeypatch):
    monkeypatch.delenv(FIRESTORE, raising=False)
    monkeypatch.delenv(AUTH, raising=False)


def test_empty_value_removes_the_var_entirely(monkeypatch):
    """The production bug: blank must mean absent, not present-and-empty."""
    monkeypatch.setenv(FIRESTORE, "")
    monkeypatch.setenv(AUTH, "")
    apply_emulator_env(FakeSettings())
    assert FIRESTORE not in os.environ
    assert AUTH not in os.environ


def test_whitespace_only_also_removes_the_var(monkeypatch):
    monkeypatch.setenv(FIRESTORE, "   ")
    apply_emulator_env(FakeSettings(firestore_emulator_host="   "))
    assert FIRESTORE not in os.environ


def test_stale_var_is_cleared_when_config_says_no_emulator(monkeypatch):
    """Leftover shell exports must not silently redirect production traffic."""
    monkeypatch.setenv(FIRESTORE, "localhost:8080")
    apply_emulator_env(FakeSettings())
    assert FIRESTORE not in os.environ


def test_real_value_is_set(monkeypatch):
    _clear(monkeypatch)
    apply_emulator_env(
        FakeSettings(firestore_emulator_host="localhost:8080", firebase_auth_emulator_host="localhost:9099")
    )
    assert os.environ[FIRESTORE] == "localhost:8080"
    assert os.environ[AUTH] == "localhost:9099"


def test_value_is_trimmed(monkeypatch):
    _clear(monkeypatch)
    apply_emulator_env(FakeSettings(firestore_emulator_host="  localhost:8080  "))
    assert os.environ[FIRESTORE] == "localhost:8080"


def test_the_two_vars_are_independent(monkeypatch):
    _clear(monkeypatch)
    apply_emulator_env(FakeSettings(firestore_emulator_host="localhost:8080"))
    assert os.environ[FIRESTORE] == "localhost:8080"
    assert AUTH not in os.environ
