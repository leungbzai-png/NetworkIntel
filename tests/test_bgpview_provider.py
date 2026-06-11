"""
BGPView provider 测试（默认不依赖网络）：
  - 导入不触发网络。
  - validate_config 无需 key。
  - normalize_result 能处理模拟数据。
  - query 通过 monkeypatch http 层离线验证（成功 + 失败两条路径）。
真实网络查询见 scripts/provider_smoke_test.py（手动）。
"""
import _bootstrap  # noqa: F401

import providers.http as http_mod
from providers.online.bgpview import BGPViewProvider
from providers.http import HttpResult


# 一段精简的 BGPView /ip/8.8.8.8 模拟响应
MOCK_BGPVIEW = {
    "status": "ok",
    "data": {
        "ip": "8.8.8.8",
        "prefixes": [
            {
                "prefix": "8.8.8.0/24",
                "country_code": "US",
                "asn": {"asn": 15169, "name": "GOOGLE",
                        "description": "Google LLC", "country_code": "US"},
            }
        ],
        "rir_allocation": {"rir_name": "ARIN", "country_code": "US"},
    },
}


def test_validate_config_no_key_needed():
    p = BGPViewProvider()
    assert p.requires_api_key is False
    assert p.validate_config().ok is True


def test_normalize_result_on_mock():
    p = BGPViewProvider()
    res = p.normalize_result(MOCK_BGPVIEW, ip="8.8.8.8")
    assert res.error is None
    d = res.data
    assert d["ip"] == "8.8.8.8"
    assert d["asn"] == 15169
    assert d["asn_name"] in ("GOOGLE", "Google LLC")
    assert d["prefix"] == "8.8.8.0/24"
    assert d["country_code"] == "US"
    assert d["rir"] == "ARIN"
    assert d["source"] == "bgpview"
    assert "fetched_at" in d


def test_normalize_result_handles_garbage():
    p = BGPViewProvider()
    res = p.normalize_result("not-a-dict", ip="1.2.3.4")
    # 不应崩溃；字段优雅降级为 None
    assert res.error is None
    assert res.data.get("asn") is None
    assert res.data.get("ip") == "1.2.3.4"


def test_query_offline_success():
    """monkeypatch http_get_json 返回成功，验证 query 端到端不联网。"""
    p = BGPViewProvider()
    orig = http_mod.http_get_json
    http_mod.http_get_json = lambda url, **kw: HttpResult(
        ok=True, status=200, json=MOCK_BGPVIEW, text=None,
        error=None, url=url, attempts=1, elapsed=0.0)
    try:
        res = p.query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
    assert res.error is None
    assert res.data["asn"] == 15169


def test_query_offline_failure():
    """http 失败时，query 返回统一失败对象，不抛异常。"""
    p = BGPViewProvider()
    orig = http_mod.http_get_json
    http_mod.http_get_json = lambda url, **kw: HttpResult(
        ok=False, status=None, json=None, text=None,
        error="Timeout: simulated", url=url, attempts=3, elapsed=0.0)
    try:
        res = p.query("8.8.8.8")
    finally:
        http_mod.http_get_json = orig
    assert res.error is not None
    assert res.data == {}
