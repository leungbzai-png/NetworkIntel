"""
ip2location provider 测试（默认不依赖网络）：
  - 导入不触发网络。
  - 缺 key / 占位符 / 已配置的 validate_config 行为。
  - normalize_result 处理模拟响应。
  - query 通过 monkeypatch http 验证：成功 / 401 / 429 / 超时。
  - 经 online_runner 验证缓存命中不回源、force_refresh 绕过缓存。
  - 任何输出不含真实/测试 key。
"""
import os
import tempfile

import _bootstrap  # noqa: F401

import providers.http as http_mod
from providers.http import HttpResult
from providers.online.ip2location import IP2LocationProvider
from providers.cache import OnlineCache
from providers.ratelimit import RateLimiter
from providers.online_runner import OnlineRunner


MOCK_IP2L = {
    "ip": "8.8.8.8",
    "country_code": "US",
    "country_name": "United States of America",
    "region_name": "California",
    "city_name": "Mountain View",
    "latitude": 37.405992,
    "longitude": -122.078515,
    "asn": "15169",
    "as": "Google LLC",
    "isp": "Google LLC",
    "domain": "google.com",
    "usage_type": "DCH",
}

DUMMY_KEY = "dummy-ip2l-key-not-real"


def _set_key(value):
    saved = os.environ.get("IP2LOCATION_API_KEY")
    if value is None:
        os.environ.pop("IP2LOCATION_API_KEY", None)
    else:
        os.environ["IP2LOCATION_API_KEY"] = value
    return saved


def _restore_key(saved):
    if saved is None:
        os.environ.pop("IP2LOCATION_API_KEY", None)
    else:
        os.environ["IP2LOCATION_API_KEY"] = saved


def _patch_http(fake):
    orig = http_mod.http_get_json
    http_mod.http_get_json = fake
    return orig


def test_import_no_network():
    p = IP2LocationProvider()
    assert p.name == "ip2location"
    assert p.requires_api_key is True
    assert p.ENV_KEY == "IP2LOCATION_API_KEY"


def test_validate_missing_key():
    saved = _set_key(None)
    try:
        v = IP2LocationProvider().validate_config()
        assert v.ok is False and v.missing
    finally:
        _restore_key(saved)


def test_validate_placeholder_key():
    for ph in ("${IP2LOCATION_API_KEY}", "your_ip2location_api_key_here"):
        saved = _set_key(ph)
        try:
            assert IP2LocationProvider().validate_config().ok is False
        finally:
            _restore_key(saved)


def test_validate_with_key():
    saved = _set_key(DUMMY_KEY)
    try:
        assert IP2LocationProvider().validate_config().ok is True
    finally:
        _restore_key(saved)


def test_normalize_result_on_mock():
    res = IP2LocationProvider().normalize_result(MOCK_IP2L, ip="8.8.8.8")
    assert res.error is None
    d = res.data
    assert d["ip"] == "8.8.8.8"
    assert d["country_code"] == "US"
    assert d["country_name"] == "United States of America"
    assert d["region"] == "California"
    assert d["city"] == "Mountain View"
    assert d["latitude"] == 37.405992
    assert d["longitude"] == -122.078515
    assert d["isp"] == "Google LLC"
    assert d["domain"] == "google.com"
    assert d["usage_type"] == "DCH"
    assert d["asn"] == 15169
    assert d["asn_name"] == "Google LLC"
    assert d["source"] == "ip2location"
    assert "fetched_at" in d


def test_query_offline_success():
    saved = _set_key(DUMMY_KEY)
    orig = _patch_http(lambda url, **kw: HttpResult(
        ok=True, status=200, json=MOCK_IP2L, text=None,
        error=None, url=url, attempts=1, elapsed=0.0))
    try:
        res = IP2LocationProvider().query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
        _restore_key(saved)
    assert res.error is None
    assert res.data["asn"] == 15169
    assert DUMMY_KEY not in str(res.data.get("raw"))


def test_query_missing_key_no_network():
    saved = _set_key(None)
    called = {"n": 0}

    def _should_not_call(url, **kw):
        called["n"] += 1
        return HttpResult(True, 200, {}, None, None, url, 1, 0.0)

    orig = _patch_http(_should_not_call)
    try:
        res = IP2LocationProvider().query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
        _restore_key(saved)
    assert called["n"] == 0
    assert res.error and "missing_api_key" in res.error


def test_query_http_failures_return_unified():
    saved = _set_key(DUMMY_KEY)
    cases = [(401, "auth_failed"), (403, "auth_failed"),
             (429, "rate_limited"), (None, None)]
    try:
        for status, expect in cases:
            err = "Timeout: simulated" if status is None else f"HTTP {status}"
            orig = _patch_http(lambda url, _s=status, _e=err, **kw: HttpResult(
                ok=False, status=_s, json=None, text=None,
                error=_e, url=url, attempts=1, elapsed=0.0))
            try:
                res = IP2LocationProvider().query("8.8.8.8")
            finally:
                http_mod.http_get_json = orig
            assert res.error is not None
            assert res.data == {}
            if expect:
                assert expect in res.error
            assert DUMMY_KEY not in res.error
    finally:
        _restore_key(saved)


def test_runner_cache_hit_and_force_refresh():
    """经 online_runner：缓存命中不回源；force_refresh 绕过缓存。"""
    saved = _set_key(DUMMY_KEY)
    http_calls = {"n": 0}

    def _fake_http(url, **kw):
        http_calls["n"] += 1
        return HttpResult(ok=True, status=200, json=MOCK_IP2L, text=None,
                          error=None, url=url, attempts=1, elapsed=0.0)

    orig = _patch_http(_fake_http)
    clock = [1000.0]
    try:
        with tempfile.TemporaryDirectory() as d:
            runner = OnlineRunner(
                cache=OnlineCache(db_path=os.path.join(d, "oc.sqlite"), now=lambda: clock[0]),
                limiter=RateLimiter(store_path=os.path.join(d, "rl.json"), now=lambda: clock[0]),
                # 用真实 provider 实例
                provider_factory=lambda name: IP2LocationProvider(),
                allowed={"ip2location"},
            )
            r1 = runner.run("ip2location", "8.8.8.8")
            assert r1.ok and r1.from_cache is False
            assert http_calls["n"] == 1
            # 命中缓存：不再回源
            r2 = runner.run("ip2location", "8.8.8.8")
            assert r2.ok and r2.from_cache is True
            assert http_calls["n"] == 1
            assert r2.data["asn"] == 15169
            # 强制刷新：绕过缓存
            r3 = runner.run("ip2location", "8.8.8.8", force_refresh=True)
            assert r3.from_cache is False
            assert http_calls["n"] == 2
    finally:
        http_mod.http_get_json = orig
        _restore_key(saved)
