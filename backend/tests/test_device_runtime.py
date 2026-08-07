import pytest

from app.services import device_runtime as rt


@pytest.fixture(autouse=True)
def _clean_state():
    """Module-level dicts persist across tests otherwise — see
    device_runtime._reset_for_tests."""
    rt._reset_for_tests()
    yield
    rt._reset_for_tests()


# --- Token cache ---


def test_cache_miss_returns_none():
    assert rt.cache_get_device("nonexistent") is None


def test_cache_put_then_get():
    rt.cache_put_device("hash1", "uid-1", "dev-1", now=0.0)
    assert rt.cache_get_device("hash1", now=1.0) == ("uid-1", "dev-1")


def test_cache_expires_after_ttl():
    rt.cache_put_device("hash1", "uid-1", "dev-1", now=0.0)
    just_before = rt.TOKEN_CACHE_TTL_SECONDS - 0.001
    assert rt.cache_get_device("hash1", now=just_before) == ("uid-1", "dev-1")
    assert rt.cache_get_device("hash1", now=rt.TOKEN_CACHE_TTL_SECONDS) is None


def test_expired_entry_is_evicted_not_just_hidden():
    rt.cache_put_device("hash1", "uid-1", "dev-1", now=0.0)
    rt.cache_get_device("hash1", now=rt.TOKEN_CACHE_TTL_SECONDS)
    assert "hash1" not in rt._token_cache


def test_evict_removes_immediately():
    """This is what makes revocation take effect right away instead of
    waiting out the TTL."""
    rt.cache_put_device("hash1", "uid-1", "dev-1", now=0.0)
    rt.cache_evict_device("hash1")
    assert rt.cache_get_device("hash1", now=0.0) is None


def test_evict_nonexistent_does_not_raise():
    rt.cache_evict_device("never-existed")


def test_two_devices_do_not_collide():
    rt.cache_put_device("hash1", "uid-1", "dev-1", now=0.0)
    rt.cache_put_device("hash2", "uid-2", "dev-2", now=0.0)
    assert rt.cache_get_device("hash1", now=0.0) == ("uid-1", "dev-1")
    assert rt.cache_get_device("hash2", now=0.0) == ("uid-2", "dev-2")


# --- Liveness ---


def test_unknown_device_is_offline():
    assert rt.is_online("never-seen") is False


def test_first_heartbeat_is_a_transition():
    assert rt.mark_seen("dev-1", now=0.0) is True


def test_second_heartbeat_is_not_a_transition():
    rt.mark_seen("dev-1", now=0.0)
    assert rt.mark_seen("dev-1", now=1.0) is False


def test_online_within_timeout():
    rt.mark_seen("dev-1", now=0.0)
    assert rt.is_online("dev-1", now=rt.LIVENESS_TIMEOUT_SECONDS - 0.001) is True


def test_offline_after_timeout():
    rt.mark_seen("dev-1", now=0.0)
    assert rt.is_online("dev-1", now=rt.LIVENESS_TIMEOUT_SECONDS) is False


def test_going_offline_then_back_online_is_a_transition_again():
    rt.mark_seen("dev-1", now=0.0)
    rt.mark_seen("dev-1", now=1.0)  # not a transition
    # Goes quiet past the timeout...
    was_transition = rt.mark_seen("dev-1", now=100.0)
    assert was_transition is True


def test_forget_device_clears_liveness():
    rt.mark_seen("dev-1", now=0.0)
    rt.forget_device("dev-1")
    assert rt.is_online("dev-1", now=0.0) is False


# --- Frame store ---


def test_no_frame_returns_none():
    assert rt.get_frame("dev-1") is None


def test_store_then_get():
    rt.store_frame("dev-1", b"jpeg-bytes", now=0.0)
    assert rt.get_frame("dev-1", now=0.0) == b"jpeg-bytes"


def test_frame_goes_stale():
    rt.store_frame("dev-1", b"jpeg-bytes", now=0.0)
    just_before = rt.FRAME_STALE_SECONDS - 0.001
    assert rt.get_frame("dev-1", now=just_before) == b"jpeg-bytes"
    assert rt.get_frame("dev-1", now=rt.FRAME_STALE_SECONDS + 0.001) is None


def test_stale_frame_is_none_not_the_old_bytes():
    """A frozen last image served as live is worse than an honest offline —
    this is the property that guarantees that."""
    rt.store_frame("dev-1", b"old-frame", now=0.0)
    stale_read = rt.get_frame("dev-1", now=1000.0)
    assert stale_read is None
    assert stale_read != b"old-frame"


def test_newer_frame_replaces_older():
    rt.store_frame("dev-1", b"frame-1", now=0.0)
    rt.store_frame("dev-1", b"frame-2", now=1.0)
    assert rt.get_frame("dev-1", now=1.0) == b"frame-2"


def test_oversized_frame_is_rejected():
    huge = b"x" * (rt.MAX_FRAME_BYTES + 1)
    with pytest.raises(rt.FrameTooLarge):
        rt.store_frame("dev-1", huge)


def test_frame_at_exactly_the_limit_is_accepted():
    exactly = b"x" * rt.MAX_FRAME_BYTES
    rt.store_frame("dev-1", exactly, now=0.0)
    assert rt.get_frame("dev-1", now=0.0) == exactly


def test_oversized_frame_does_not_get_stored():
    huge = b"x" * (rt.MAX_FRAME_BYTES + 1)
    with pytest.raises(rt.FrameTooLarge):
        rt.store_frame("dev-1", huge)
    assert rt.get_frame("dev-1") is None


def test_too_many_devices_rejected():
    for i in range(rt.MAX_TRACKED_DEVICES):
        rt.store_frame(f"dev-{i}", b"x", now=0.0)
    with pytest.raises(rt.TooManyDevices):
        rt.store_frame("one-too-many", b"x", now=0.0)


def test_updating_an_existing_device_does_not_count_against_the_cap():
    for i in range(rt.MAX_TRACKED_DEVICES):
        rt.store_frame(f"dev-{i}", b"x", now=0.0)
    # Re-posting from an already-tracked device must not be blocked by the cap
    # meant to stop unbounded growth from new devices.
    rt.store_frame("dev-0", b"updated", now=1.0)
    assert rt.get_frame("dev-0", now=1.0) == b"updated"


def test_forget_device_clears_its_frame():
    rt.store_frame("dev-1", b"jpeg-bytes", now=0.0)
    rt.forget_device("dev-1")
    assert rt.get_frame("dev-1", now=0.0) is None


def test_forgetting_one_device_does_not_affect_another():
    rt.store_frame("dev-1", b"frame-1", now=0.0)
    rt.store_frame("dev-2", b"frame-2", now=0.0)
    rt.forget_device("dev-1")
    assert rt.get_frame("dev-2", now=0.0) == b"frame-2"
