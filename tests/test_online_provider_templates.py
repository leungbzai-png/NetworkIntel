"""
在线 Provider 模板测试（骨架 provider）：
  - 正确标记 requires_api_key 与 config_keys / ENV_KEY。
  - validate_config 能判断缺 key / 已配置，且缺 key 不崩溃。
  - query 为骨架：返回 not_implemented，不联网、不崩溃。
  - normalize_result 能处理模拟数据。

注：bgpview / ipinfo / ip2location / abuseipdb 已实现真实 query()，
由各自专属测试覆盖；此处仅覆盖仍为骨架的 threatfox。
"""
import os

import _bootstrap  # noqa: F401

from providers.online import ONLINE_PROVIDERS
from providers.online.threatfox import ThreatFoxProvider

# 仍为骨架的模板
TEMPLATES = [ThreatFoxProvider]


def test_registry_contains_all_online():
    for name in ("bgpview", "ipinfo", "ip2location", "abuseipdb", "threatfox"):
        assert name in ONLINE_PROVIDERS


def test_templates_require_api_key():
    for cls in TEMPLATES:
        p = cls()
        assert p.requires_api_key is True
        assert p.config_keys, f"{p.name} 缺 config_keys"
        assert p.ENV_KEY, f"{p.name} 缺 ENV_KEY"


def test_validate_config_missing_key_is_graceful():
    for cls in TEMPLATES:
        p = cls()
        saved = os.environ.pop(p.ENV_KEY, None)
        try:
            v = p.validate_config()
            assert v.ok is False
            assert v.missing  # 列出缺失项，不崩溃
        finally:
            if saved is not None:
                os.environ[p.ENV_KEY] = saved


def test_validate_config_with_key_ok():
    for cls in TEMPLATES:
        p = cls()
        saved = os.environ.get(p.ENV_KEY)
        os.environ[p.ENV_KEY] = "dummy-key-for-test"
        try:
            assert p.validate_config().ok is True
        finally:
            if saved is None:
                os.environ.pop(p.ENV_KEY, None)
            else:
                os.environ[p.ENV_KEY] = saved


def test_query_skeleton_not_implemented_no_network():
    for cls in TEMPLATES:
        p = cls()
        res = p.query("8.8.8.8")
        assert res.error and "not_implemented" in res.error
        assert res.data == {}


def test_normalize_result_handles_mock():
    # 各模板的 normalize_result 用最简模拟数据，确保不崩溃
    samples = {
        "threatfox":   {"data": [{"threat_type": "botnet_cc", "malware_printable": "X"}]},
    }
    for cls in TEMPLATES:
        p = cls()
        res = p.normalize_result(samples[p.name], ip="8.8.8.8")
        assert res.source == p.name
        assert res.error is None
