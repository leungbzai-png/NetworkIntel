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


def test_providers_have_independent_quota():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock, {"a": {"per_minute": 2}, "b": {"per_minute": 2}})
        rl.record_success("a")
        rl.record_success("a")
        assert rl.can_call("a") is False        # a 已达上限
        assert rl.can_call("b") is True         # b 不受 a 影响


def test_per_day_limit_boundary():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock, {"ab": {"per_day": 900}})
        for _ in range(899):
            rl.record_success("ab")
        assert rl.can_call("ab") is True        # 899 < 900
        rl.record_success("ab")
        assert rl.can_call("ab") is False        # 达 900 上限


def test_consecutive_429_trips_circuit_breaker():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock,
                      {"c": {"cooldown_seconds": 30, "max_consecutive_429": 3,
                             "circuit_breaker_seconds": 3600}})
        rl.record_429("c")
        rl.record_429("c")
        assert rl.in_circuit("c") is False
        rl.record_429("c")                       # 第 3 次 → 熔断
        assert rl.in_circuit("c") is True
        assert rl.can_call("c") is False
        # 熔断时 next_available_at 应等于熔断结束（取最大约束，而非冷却 30s）
        clock[0] = 1000.0 + 31                    # 冷却已过，但熔断未过
        assert rl.can_call("c") is False
        clock[0] = 1000.0 + 3601                   # 熔断结束
        assert rl.can_call("c") is True


def test_record_success_resets_consecutive_429():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock,
                      {"e": {"cooldown_seconds": 1, "max_consecutive_429": 3,
                             "circuit_breaker_seconds": 3600}})
        rl.record_429("e")
        rl.record_429("e")
        assert rl.stats("e")["consecutive_429"] == 2
        clock[0] = 1000.0 + 2                       # 冷却过
        rl.record_success("e")
        assert rl.stats("e")["consecutive_429"] == 0
        # 清零后再来 2 次 429 不应熔断
        rl.record_429("e")
        rl.record_429("e")
        assert rl.in_circuit("e") is False


def test_record_failure_does_not_trip_circuit():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock, {"f": {"max_consecutive_429": 3,
                                       "circuit_breaker_seconds": 3600}})
        for _ in range(10):
            rl.record_failure("f")
        assert rl.in_circuit("f") is False         # 普通失败不强熔断


def test_reset_clears_state():
    clock = [1000.0]
    with tempfile.TemporaryDirectory() as d:
        rl = _limiter(d, clock,
                      {"g": {"max_consecutive_429": 1, "circuit_breaker_seconds": 3600}})
        rl.record_429("g")
        assert rl.in_circuit("g") is True
        rl.reset("g")
        assert rl.in_circuit("g") is False
        assert rl.can_call("g") is True


def test_default_provider_limits_abuseipdb_per_day():
    from providers.ratelimit import build_default_limiter
    # 清除可能的 env 覆盖，确保断言的是内置默认 per_day=900
    saved = {k: os.environ.pop(k, None) for k in
             ("ABUSEIPDB_RATE_PER_DAY", "ABUSEIPDB_RATE_PER_HOUR", "ABUSEIPDB_RATE_PER_MINUTE")}
    clock = [1000.0]
    try:
        with tempfile.TemporaryDirectory() as d:
            rl = build_default_limiter(store_path=os.path.join(d, "rl.json"),
                                       now=lambda: clock[0])
            # abuseipdb 默认 per_day=900；将调用按 ~95s 间隔铺开整天，
            # 使 per_minute(10)/per_hour(100) 窗口都不绑定，只检验 per_day。
            step = 95.0
            for _ in range(899):
                rl.record_success("abuseipdb")
                clock[0] += step
            assert rl.can_call("abuseipdb") is True       # 899 < 900
            rl.record_success("abuseipdb")
            assert rl.can_call("abuseipdb") is False        # 第 900 次达每日上限
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
