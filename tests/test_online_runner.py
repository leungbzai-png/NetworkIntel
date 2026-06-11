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
        res = r.run("abuseipdb", "8.8.8.8")
        assert res.ok is False
        assert "not_allowed" in res.error
        assert stub.calls == 0
