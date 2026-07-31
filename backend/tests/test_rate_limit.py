"""The rate-limit key decides whose quota a request counts against, so getting
it wrong behind a proxy means either one shared bucket for everyone or a
trivially spoofable limit."""

import pytest

from app.middleware import rate_limit


class FakeClient:
    def __init__(self, host):
        self.host = host


class FakeRequest:
    def __init__(self, headers=None, host="10.0.0.1"):
        self.headers = headers or {}
        self.client = FakeClient(host)


@pytest.fixture
def proxy_mode(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "behind_proxy", True)


@pytest.fixture
def direct_mode(monkeypatch):
    monkeypatch.setattr(rate_limit.settings, "behind_proxy", False)


def test_uses_real_client_ip_from_forwarded_header(proxy_mode):
    req = FakeRequest(headers={"x-forwarded-for": "203.0.113.9"}, host="10.0.0.1")
    assert rate_limit.client_key(req) == "203.0.113.9"


def test_takes_first_hop_when_multiple_proxies(proxy_mode):
    # X-Forwarded-For is client, proxy1, proxy2 — the client is first.
    req = FakeRequest(headers={"x-forwarded-for": "203.0.113.9, 10.0.0.1, 10.0.0.2"})
    assert rate_limit.client_key(req) == "203.0.113.9"


def test_tolerates_whitespace_in_forwarded_header(proxy_mode):
    req = FakeRequest(headers={"x-forwarded-for": "  203.0.113.9 , 10.0.0.1"})
    assert rate_limit.client_key(req) == "203.0.113.9"


def test_falls_back_to_socket_ip_when_header_absent(proxy_mode):
    req = FakeRequest(headers={}, host="198.51.100.4")
    assert rate_limit.client_key(req) == "198.51.100.4"


def test_ignores_forwarded_header_when_not_behind_proxy(direct_mode):
    """Off-proxy the header is attacker-controlled — trusting it would let a
    caller rotate the value to bypass the limit entirely."""
    req = FakeRequest(headers={"x-forwarded-for": "1.2.3.4"}, host="198.51.100.4")
    assert rate_limit.client_key(req) == "198.51.100.4"


def test_distinct_clients_get_distinct_keys(proxy_mode):
    """The whole point: two users behind the same proxy must not share a bucket."""
    a = FakeRequest(headers={"x-forwarded-for": "203.0.113.9"}, host="10.0.0.1")
    b = FakeRequest(headers={"x-forwarded-for": "203.0.113.10"}, host="10.0.0.1")
    assert rate_limit.client_key(a) != rate_limit.client_key(b)
