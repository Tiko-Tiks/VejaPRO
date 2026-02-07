from app.utils.rate_limit import SlidingWindowRateLimiter


def test_rate_limiter_prunes_stale_buckets_on_interval(monkeypatch):
    # Force prune on every call for deterministic behavior.
    rl = SlidingWindowRateLimiter(max_buckets=10_000, prune_interval_seconds=1)

    t = {"now": 1000.0}

    def fake_monotonic():
        return t["now"]

    monkeypatch.setattr("app.utils.rate_limit.time.monotonic", fake_monotonic)

    # Create a lot of unique keys at time=1000.0
    for i in range(200):
        ok, _ = rl.allow(f"k:{i}", limit=1, window_seconds=60)
        assert ok is True

    # Advance beyond window + prune interval and hit a new key to trigger prune.
    t["now"] = 1000.0 + 120.0
    ok, _ = rl.allow("k:new", limit=1, window_seconds=60)
    assert ok is True

    # Now the previously created buckets should be stale and pruned.
    # Re-adding an old key should behave like a fresh bucket.
    ok, _ = rl.allow("k:0", limit=1, window_seconds=60)
    assert ok is True
