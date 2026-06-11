"""
AbuseIPDB provider 测试（默认不依赖网络）：
  - 导入不触发网络。
  - 缺 key / 占位符 key / 已配置 dummy key 的 validate_config 行为。
  - normalize_result 处理模拟响应（断言完整统一字段 + severity 分级）。
  - query 通过 monkeypatch http 层验证：成功 / 401 / 403 / 429 / 超时。
  - 429 返回 rate_limited（供 runner 触发熔断）。
  - 任何输出都不包含真实/测试 key。
"""
import os

import _bootstrap  # noqa: F401

import providers.http as http_mod
from providers.http import HttpResult
from providers.online.abuseipdb import AbuseIPDBProvider, _severity


# 模拟 AbuseIPDB /check?verbose 响应
MOCK_ABUSEIPDB = {
    "data": {
        "ipAddress": "118.25.6.39",
        "isPublic": True,
        "ipVersion": 4,
        "isWhitelisted": False,
        "abuseConfidenceScore": 90,
        "countryCode": "CN",
        "usageType": "Data Center/Web Hosting/Transit",
        "isp": "Tencent Cloud Computing",
        "domain": "tencent.com",
        "isTor": False,
        "totalReports": 42,
        "numDistinctUsers": 17,
    }
}

DUMMY_KEY = "dummy-abuseipdb-key-not-real"


def _set_key(value):
    saved = os.environ.get("ABUSEIPDB_API_KEY")
    if value is None:
        os.environ.pop("ABUSEIPDB_API_KEY", None)
    else:
        os.environ["ABUSEIPDB_API_KEY"] = value
    return saved


def _restore_key(saved):
    if saved is None:
        os.environ.pop("ABUSEIPDB_API_KEY", None)
    else:
        os.environ["ABUSEIPDB_API_KEY"] = saved


def _patch_http(fake):
    orig = http_mod.http_get_json
    http_mod.http_get_json = fake
    return orig


def test_import_does_not_touch_network():
    p = AbuseIPDBProvider()
    assert p.name == "abuseipdb"
    assert p.requires_api_key is True
    assert p.ENV_KEY == "ABUSEIPDB_API_KEY"
    assert p.category.value == "threat_intel"


def test_validate_missing_key():
    saved = _set_key(None)
    try:
        v = AbuseIPDBProvider().validate_config()
        assert v.ok is False and v.missing
    finally:
        _restore_key(saved)


def test_validate_placeholder_key():
    for placeholder in ("${ABUSEIPDB_API_KEY}", "your_abuseipdb_api_key_here"):
        saved = _set_key(placeholder)
        try:
            assert AbuseIPDBProvider().validate_config().ok is False
        finally:
            _restore_key(saved)


def test_validate_with_dummy_key():
    saved = _set_key(DUMMY_KEY)
    try:
        assert AbuseIPDBProvider().validate_config().ok is True
    finally:
        _restore_key(saved)


def test_severity_bands():
    assert _severity(0) == "clean"
    assert _severity(1) == "low"
    assert _severity(24) == "low"
    assert _severity(25) == "medium"
    assert _severity(74) == "medium"
    assert _severity(75) == "high"
    assert _severity(100) == "high"
    assert _severity(None) == "clean"      # 缺分数不崩溃


def test_normalize_result_full_fields():
    p = AbuseIPDBProvider()
    res = p.normalize_result(MOCK_ABUSEIPDB, ip="118.25.6.39")
    assert res.error is None
    d = res.data
    # 完整统一字段集
    expected_keys = {
        "ip", "abuse_confidence_score", "total_reports", "num_distinct_users",
        "is_public", "is_whitelisted", "is_tor", "usage_type", "isp", "domain",
        "country_code", "severity", "threats", "source", "fetched_at", "raw",
    }
    assert expected_keys.issubset(set(d.keys()))
    assert d["ip"] == "118.25.6.39"
    assert d["abuse_confidence_score"] == 90
    assert d["total_reports"] == 42
    assert d["num_distinct_users"] == 17
    assert d["is_public"] is True
    assert d["is_whitelisted"] is False
    assert d["is_tor"] is False
    assert d["isp"] == "Tencent Cloud Computing"
    assert d["domain"] == "tencent.com"
    assert d["country_code"] == "CN"
    assert d["severity"] == "high"
    assert d["threats"] and d["threats"][0]["severity"] == "high"
    assert d["source"] == "abuseipdb"


def test_normalize_clean_score_no_threats():
    sample = {"data": {"ipAddress": "8.8.8.8", "abuseConfidenceScore": 0, "countryCode": "US"}}
    res = AbuseIPDBProvider().normalize_result(sample, ip="8.8.8.8")
    assert res.error is None
    assert res.data["severity"] == "clean"
    assert res.data["threats"] == []


def test_query_offline_success():
    saved = _set_key(DUMMY_KEY)
    orig = _patch_http(lambda url, **kw: HttpResult(
        ok=True, status=200, json=MOCK_ABUSEIPDB, text=None,
        error=None, url=url, attempts=1, elapsed=0.0))
    try:
        res = AbuseIPDBProvider().query("118.25.6.39")
    finally:
        http_mod.http_get_json = orig
        _restore_key(saved)
    assert res.error is None
    assert res.data["abuse_confidence_score"] == 90
    # key 绝不应出现在结果/原始数据中
    assert DUMMY_KEY not in str(res.data.get("raw"))
    assert DUMMY_KEY not in str(res.data)


def test_query_missing_key_no_network():
    saved = _set_key(None)
    called = {"n": 0}

    def _should_not_call(url, **kw):
        called["n"] += 1
        return HttpResult(True, 200, {}, None, None, url, 1, 0.0)

    orig = _patch_http(_should_not_call)
    try:
        res = AbuseIPDBProvider().query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
        _restore_key(saved)
    assert called["n"] == 0
    assert res.error and "missing_api_key" in res.error


def test_query_http_failures_return_unified():
    saved = _set_key(DUMMY_KEY)
    cases = [
        (401, "auth_failed"),
        (403, "auth_failed"),
        (429, "rate_limited"),
        (500, "server_error"),
        (None, None),  # 超时/网络异常
    ]
    try:
        for status, expect in cases:
            err = "Timeout: simulated" if status is None else f"HTTP {status}"
            orig = _patch_http(lambda url, _s=status, _e=err, **kw: HttpResult(
                ok=False, status=_s, json=None, text=None,
                error=_e, url=url, attempts=1, elapsed=0.0))
            try:
                res = AbuseIPDBProvider().query("8.8.8.8")
            finally:
                http_mod.http_get_json = orig
            assert res.error is not None
            assert res.data == {}
            if expect:
                assert expect in res.error
            assert DUMMY_KEY not in res.error
    finally:
        _restore_key(saved)
