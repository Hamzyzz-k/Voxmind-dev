import pytest

from app.services.device_auth import (
    STREAM_TICKET_TTL_SECONDS,
    InvalidTicket,
    generate_device_token,
    hash_device_token,
    issue_stream_ticket,
    parse_device_authorization,
    parse_ticket_authorization,
    tokens_match,
    verify_stream_ticket,
)

SECRET = "test-secret-not-a-real-one"


# --- Device tokens ---


def test_generated_tokens_are_unique_and_long():
    tokens = {generate_device_token() for _ in range(200)}
    assert len(tokens) == 200
    # token_urlsafe(32) base64-encodes 32 bytes, so ~43 chars.
    assert all(len(t) >= 40 for t in tokens)


def test_hash_is_deterministic():
    """The whole point of dropping the salt: the same token must always hash to
    the same value, because the hash is the Firestore document key used to look
    up which user owns the device."""
    token = generate_device_token()
    assert hash_device_token(token) == hash_device_token(token)


def test_hash_differs_between_tokens():
    assert hash_device_token("aaa") != hash_device_token("bbb")


def test_hash_does_not_contain_the_token():
    token = generate_device_token()
    assert token not in hash_device_token(token)


def test_tokens_match_accepts_correct_and_rejects_wrong():
    token = generate_device_token()
    stored = hash_device_token(token)
    assert tokens_match(token, stored)
    assert not tokens_match(generate_device_token(), stored)
    assert not tokens_match("", stored)


# --- Authorization header parsing ---


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Device abc123", "abc123"),
        ("Device   abc123  ", "abc123"),
        (None, None),
        ("", None),
        ("Bearer abc123", None),  # a Firebase ID token must never be read as a device token
        ("Ticket abc123", None),
        ("Device", None),
        ("Device    ", None),
        ("device abc123", None),  # case-sensitive on purpose
    ],
)
def test_parse_device_authorization(header, expected):
    assert parse_device_authorization(header) == expected


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Ticket abc.def", "abc.def"),
        (None, None),
        ("Bearer abc", None),
        ("Device abc", None),  # a device token must never be accepted as a ticket
        ("Ticket ", None),
    ],
)
def test_parse_ticket_authorization(header, expected):
    assert parse_ticket_authorization(header) == expected


# --- Stream tickets ---


def test_ticket_roundtrip():
    ticket = issue_stream_ticket("uid-1", "dev-1", SECRET)
    assert verify_stream_ticket(ticket, SECRET) == ("uid-1", "dev-1")


def test_ticket_rejected_with_wrong_secret():
    ticket = issue_stream_ticket("uid-1", "dev-1", SECRET)
    with pytest.raises(InvalidTicket):
        verify_stream_ticket(ticket, "different-secret")


def test_ticket_rejected_when_payload_tampered():
    """Someone editing the uid to read another user's camera must fail the
    signature check before the payload is trusted for anything."""
    ticket = issue_stream_ticket("uid-1", "dev-1", SECRET)
    payload_b64, signature = ticket.split(".", 1)
    forged = issue_stream_ticket("uid-2", "dev-1", SECRET).split(".", 1)[0]
    with pytest.raises(InvalidTicket):
        verify_stream_ticket(f"{forged}.{signature}", SECRET)


def test_ticket_rejected_when_signature_tampered():
    ticket = issue_stream_ticket("uid-1", "dev-1", SECRET)
    payload_b64, _ = ticket.split(".", 1)
    with pytest.raises(InvalidTicket):
        verify_stream_ticket(f"{payload_b64}.notavalidsignature", SECRET)


def test_ticket_expires():
    issued_at = 1_000_000.0
    ticket = issue_stream_ticket("uid-1", "dev-1", SECRET, now=issued_at)

    # Still valid a second before expiry.
    assert verify_stream_ticket(ticket, SECRET, now=issued_at + STREAM_TICKET_TTL_SECONDS - 1) == (
        "uid-1",
        "dev-1",
    )

    with pytest.raises(InvalidTicket):
        verify_stream_ticket(ticket, SECRET, now=issued_at + STREAM_TICKET_TTL_SECONDS)


@pytest.mark.parametrize("bad", ["", "no-dot", "...", "a.b.c", "!!!.???"])
def test_malformed_tickets_raise_rather_than_crash(bad):
    with pytest.raises(InvalidTicket):
        verify_stream_ticket(bad, SECRET)


def test_two_devices_get_distinguishable_tickets():
    """A ticket for one device must not grant access to another, even for the
    same user — the frame endpoint checks the device id in the ticket against
    the one in the path."""
    a = verify_stream_ticket(issue_stream_ticket("uid-1", "dev-a", SECRET), SECRET)
    b = verify_stream_ticket(issue_stream_ticket("uid-1", "dev-b", SECRET), SECRET)
    assert a == ("uid-1", "dev-a")
    assert b == ("uid-1", "dev-b")
