"""
ipinfo provider 测试（默认不依赖网络）：
  - 导入不触发网络。
  - 缺 token / 占位符 token / 已配置 token 的 validate_config 行为。
  - normalize_result 处理模拟响应。
  - query 通过 monkeypatch http 层验证：成功 / 401 / 429 / 超时。
  - 任何输出都不包含真实/测试 token。
"""
import os

import _bootstrap  # noqa: F401

import providers.http as http_mod
from providers.http import HttpResult
from providers.online.ipinfo import IPInfoProvider


MOCK_IPINFO = {
    "ip": "8.8.8.8",
    "hostname": "dns.google",
    "city": "Mountain View",
    "region": "California",
    "country": "US",
    "loc": "37.4056,-122.0775",
    "org": "AS15169 Google LLC",
    "timezone": "America/Los_Angeles",
}

DUMMY_TOKEN = "dummy-token-not-real"


def _set_token(value):
    saved = os.environ.get("IPINFO_TOKEN")
    if value is None:
        os.environ.pop("IPINFO_TOKEN", None)
    else:
        os.environ["IPINFO_TOKEN"] = value
    return saved


def _restore_token(saved):
    if saved is None:
        os.environ.pop("IPINFO_TOKEN", None)
    else:
        os.environ["IPINFO_TOKEN"] = saved


def _patch_http(fake):
    orig = http_mod.http_get_json
    http_mod.http_get_json = fake
    return orig


def test_import_does_not_touch_network():
    # 仅构造对象，不应有网络副作用
    p = IPInfoProvider()
    assert p.name == "ipinfo"
    assert p.requires_api_key is True
    assert p.ENV_KEY == "IPINFO_TOKEN"


def test_validate_missing_token():
    saved = _set_token(None)
    try:
        v = IPInfoProvider().validate_config()
        assert v.ok is False and v.missing
    finally:
        _restore_token(saved)


def test_validate_placeholder_token():
    saved = _set_token("${IPINFO_TOKEN}")
    try:
        assert IPInfoProvider().validate_config().ok is False
    finally:
        _restore_token(saved)
    # 形如 your_..._here 的占位符也应判为未配置
    saved = _set_token("your_ipinfo_token_here")
    try:
        assert IPInfoProvider().validate_config().ok is False
    finally:
        _restore_token(saved)


def test_validate_with_token():
    saved = _set_token(DUMMY_TOKEN)
    try:
        assert IPInfoProvider().validate_config().ok is True
    finally:
        _restore_token(saved)


def test_normalize_result_on_mock():
    p = IPInfoProvider()
    res = p.normalize_result(MOCK_IPINFO, ip="8.8.8.8")
    assert res.error is None
    d = res.data
    assert d["ip"] == "8.8.8.8"
    assert d["country_code"] == "US"
    assert d["region"] == "California"
    assert d["city"] == "Mountain View"
    assert d["latitude"] == "37.4056"
    assert d["longitude"] == "-122.0775"
    assert d["asn"] == 15169
    assert d["asn_name"] == "Google LLC"
    assert d["org"] == "AS15169 Google LLC"
    assert d["timezone"] == "America/Los_Angeles"
    assert d["source"] == "ipinfo"
    assert "fetched_at" in d


def test_query_offline_success():
    saved = _set_token(DUMMY_TOKEN)
    orig = _patch_http(lambda url, **kw: HttpResult(
        ok=True, status=200, json=MOCK_IPINFO, text=None,
        error=None, url=url, attempts=1, elapsed=0.0))
    try:
        res = IPInfoProvider().query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
        _restore_token(saved)
    assert res.error is None
    assert res.data["asn"] == 15169
    # token 绝不应出现在结果/原始数据/URL 中
    assert DUMMY_TOKEN not in str(res.data.get("raw"))


def test_query_missing_key_no_network():
    saved = _set_token(None)
    # 即便 http 被打 patch，也不应被调用（缺 key 提前返回）
    called = {"n": 0}

    def _should_not_call(url, **kw):
        called["n"] += 1
        return HttpResult(True, 200, {}, None, None, url, 1, 0.0)

    orig = _patch_http(_should_not_call)
    try:
        res = IPInfoProvider().query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
        _restore_token(saved)
    assert called["n"] == 0
    assert res.error and "missing_api_key" in res.error


def test_query_http_failures_return_unified():
    saved = _set_token(DUMMY_TOKEN)
    cases = [
        (401, "auth_failed"),
        (403, "auth_failed"),
        (429, "rate_limited"),
        (None, None),  # 超时/网络异常
    ]
    try:
        for status, expect in cases:
            err = "Timeout: simulated" if status is None else f"HTTP {status}"
            orig = _patch_http(lambda url, _s=status, _e=err, **kw: HttpResult(
                ok=False, status=_s, json=None, text=None,
                error=_e, url=url, attempts=1, elapsed=0.0))
            try:
                res = IPInfoProvider().query("8.8.8.8")
            finally:
                http_mod.http_get_json = orig
            assert res.error is not None
            assert res.data == {}
            if expect:
                assert expect in res.error
            # token 不得泄露到错误信息
            assert DUMMY_TOKEN not in res.error
    finally:
        _restore_token(saved)
