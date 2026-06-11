"""
限速测试（临时 JSON 存储，可控时钟；不联网）：
  - 默认无限额 can_call True
  - per_minute 限额生效，窗口滑出后恢复
  - 429 进入 cooldown，冷却后恢复
  - next_available_at 在受限时返回时间
"""
import os
import tempfile

import _bootstrap  # noqa: F401

from providers.ratelimit import RateLimiter


def _limiter(tmpdir, clock, limits=None):
    return RateLimiter(
        store_path=os.path.join(tmpdir, "rl.json"),
        now=lambda: clock[0],
        limits_by_provider=limits or {},
    )


def test_default_unlimited():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock)
        for _ in range(100):
            rl.record_success("bgpview")
        assert rl.can_call("bgpview") is True


def test_per_minute_limit_and_recovery():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock, {"x": {"per_minute": 2}})
        assert rl.can_call("x") is True
        rl.record_success("x")
        rl.record_success("x")
        assert rl.can_call("x") is False        # 达上限
        assert rl.next_available_at("x") is not None
        clock[0] = 1000.0 + 61                   # 窗口滑出
        assert rl.can_call("x") is True


def test_429_sets_cooldown():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock, {"y": {"cooldown_seconds": 30}})
        assert rl.can_call("y") is True
        rl.record_429("y")
        assert rl.can_call("y") is False
        assert rl.next_available_at("y") is not None
        clock[0] = 1000.0 + 31
        assert rl.can_call("y") is True


def test_429_respects_retry_after():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock)
        rl.record_429("z", retry_after=120)
        assert rl.can_call("z") is False
        clock[0] = 1000.0 + 60
        assert rl.can_call("z") is False        # 仍在 120s 冷却内
        clock[0] = 1000.0 + 121
        assert rl.can_call("z") is True


def test_stats():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock)
        rl.record_success("p")
        rl.record_failure("p")
        s = rl.stats("p")
        assert s["calls_last_minute"] == 2
        assert s["in_cooldown"] is False
