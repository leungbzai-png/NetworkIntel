"""
在线旁路执行器测试（注入临时 cache/limiter + 桩 provider；不联网）：
  - 缓存命中时不调用真实 provider
  - force_refresh 绕过缓存
  - 缺 key provider 优雅失败且不调用 query
  - 不允许的 provider 被拒
"""
import os
import tempfile

import _bootstrap  # noqa: F401

from providers.cache import OnlineCache
from providers.ratelimit import RateLimiter
from providers.online_runner import OnlineRunner
from providers.types import ProviderCategory, ConfigValidation, NormalizedResult


class StubProvider:
    def __init__(self, name="bgpview", requires_api_key=False, valid=True):
        self.name = name
        self.requires_api_key = requires_api_key
        self.category = ProviderCategory.ASN
        self._valid = valid
        self.calls = 0

    def validate_config(self):
        return ConfigValidation(ok=self._valid, missing=[] if self._valid else ["api_key"])

    def query(self, ip):
        self.calls += 1
        return NormalizedResult(ip=ip, source=self.name, category=self.category.value,
                                data={"ip": ip, "asn": 15169}, raw={"ok": 1})


def _runner(tmpdir, clock, stub):
    return OnlineRunner(
        cache=OnlineCache(db_path=os.path.join(tmpdir, "oc.sqlite"), now=lambda: clock[0]),
        limiter=RateLimiter(store_path=os.path.join(tmpdir, "rl.json"), now=lambda: clock[0]),
        provider_factory=lambda name: stub,
        allowed={"bgpview", "ipinfo"},
    )


def test_first_call_queries_then_cache_hit():
    clock = [1000.0]
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, clock, stub)
        r1 = r.run("bgpview", "8.8.8.8")
        assert r1.ok and r1.from_cache is False and stub.calls == 1
        # 第二次应命中缓存，不再 query
        r2 = r.run("bgpview", "8.8.8.8")
        assert r2.ok and r2.from_cache is True
        assert stub.calls == 1
        assert r2.data["asn"] == 15169


def test_force_refresh_bypasses_cache():
    clock = [1000.0]
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, clock, stub)
        r.run("bgpview", "8.8.8.8")
        assert stub.calls == 1
        r.run("bgpview", "8.8.8.8", force_refresh=True)
        assert stub.calls == 2


def test_use_cache_false_always_queries():
    clock = [1000.0]
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, clock, stub)
        r.run("bgpview", "1.1.1.1", use_cache=False)
        r.run("bgpview", "1.1.1.1", use_cache=False)
        assert stub.calls == 2


def test_missing_key_graceful_no_query():
    clock = [1000.0]
    stub = StubProvider(name="ipinfo", requires_api_key=True, valid=False)
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, clock, stub)
        res = r.run("ipinfo", "8.8.8.8")
        assert res.ok is False
        assert "missing_api_key" in res.error
        assert stub.calls == 0


def test_provider_not_allowed():
    clock = [1000.0]
    stub = StubProvider(name="abuseipdb")
    with tempfile.TemporaryDirectory() as d:
        r = _runner(d, clock, stub)
        # 该 runner allowed={bgpview,ipinfo}，abuseipdb 不在内
        res = r.run("abuseipdb", "8.8.8.8")
        assert res.ok is False
        assert "not_allowed" in res.error
        assert stub.calls == 0


class FailProvider(StubProvider):
    """query() 总是返回指定错误（用于模拟 429/失败而不联网）。"""
    def __init__(self, name="bgpview", error="rate_limited (HTTP 429)"):
        super().__init__(name=name)
        self._error = error

    def query(self, ip):
        self.calls += 1
        return NormalizedResult(ip=ip, source=self.name, category=self.category.value,
                                data={}, raw=None, error=self._error)


def _runner_with_limits(tmpdir, clock, stub, limits):
    return OnlineRunner(
        cache=OnlineCache(db_path=os.path.join(tmpdir, "oc.sqlite"), now=lambda: clock[0]),
        limiter=RateLimiter(store_path=os.path.join(tmpdir, "rl.json"), now=lambda: clock[0],
                            limits_by_provider=limits),
        provider_factory=lambda name: stub,
        allowed={stub.name},
    )


def test_rate_limited_returns_unified_failure_no_query():
    clock = [1000.0]
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as d:
        r = _runner_with_limits(d, clock, stub, {"bgpview": {"per_minute": 1}})
        r.run("bgpview", "1.1.1.1", use_cache=False)     # 消耗额度
        assert stub.calls == 1
        res = r.run("bgpview", "2.2.2.2", use_cache=False)  # 第二个 IP 触发限速
        assert res.ok is False and res.rate_limited is True
        assert res.next_available_at is not None
        assert stub.calls == 1                            # 未再调用 query


def test_circuit_open_blocks_query():
    clock = [1000.0]
    stub = FailProvider(name="bgpview", error="rate_limited (HTTP 429)")
    with tempfile.TemporaryDirectory() as d:
        r = _runner_with_limits(d, clock, stub,
                                {"bgpview": {"cooldown_seconds": 1,
                                             "max_consecutive_429": 2,
                                             "circuit_breaker_seconds": 3600}})
        # 两次回源都返回 429 → 触发熔断
        r.run("bgpview", "1.1.1.1", use_cache=False)
        clock[0] += 2                                     # 越过 cooldown 再打一次
        r.run("bgpview", "1.1.1.1", use_cache=False)
        calls_before = stub.calls
        # 熔断期间：不再调用 query，返回 circuit_open
        res = r.run("bgpview", "1.1.1.1", use_cache=False)
        assert res.circuit_open is True
        assert stub.calls == calls_before


def test_cache_hit_does_not_consume_quota():
    clock = [1000.0]
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as d:
        r = _runner_with_limits(d, clock, stub, {"bgpview": {"per_minute": 1}})
        r.run("bgpview", "8.8.8.8")                       # 回源 1 次，写缓存，额度用 1
        for _ in range(5):
            res = r.run("bgpview", "8.8.8.8")             # 全部命中缓存
            assert res.from_cache is True and res.ok is True
        assert stub.calls == 1                            # 缓存命中未再 query/消耗额度


def test_force_refresh_still_respects_rate_limit():
    clock = [1000.0]
    stub = StubProvider()
    with tempfile.TemporaryDirectory() as d:
        r = _runner_with_limits(d, clock, stub, {"bgpview": {"per_minute": 1}})
        r.run("bgpview", "8.8.8.8")                       # 消耗唯一额度
        assert stub.calls == 1
        res = r.run("bgpview", "8.8.8.8", force_refresh=True)  # 跳过缓存但仍受限速
        assert res.ok is False and res.rate_limited is True
        assert stub.calls == 1                            # 未回源


def test_abuseipdb_missing_key_no_query():
    clock = [1000.0]
    stub = StubProvider(name="abuseipdb", requires_api_key=True, valid=False)
    with tempfile.TemporaryDirectory() as d:
        r = OnlineRunner(
            cache=OnlineCache(db_path=os.path.join(d, "oc.sqlite"), now=lambda: clock[0]),
            limiter=RateLimiter(store_path=os.path.join(d, "rl.json"), now=lambda: clock[0]),
            provider_factory=lambda name: stub,
            allowed={"abuseipdb"},
        )
        res = r.run("abuseipdb", "8.8.8.8")
        assert res.ok is False
        assert "missing_api_key" in res.error
        assert stub.calls == 0


def test_abuseipdb_in_default_allowed():
    from providers.online_runner import ALLOWED_PROVIDERS
    assert "abuseipdb" in ALLOWED_PROVIDERS
