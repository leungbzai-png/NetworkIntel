"""
Provider 注册表测试：
  - import 惰性（导入不构建注册表、不实例化插件）。
  - 构建后含 17 个现有源，元数据正确。
  - 适配器仅持有类引用，不实例化底层插件。
"""
import importlib

import _bootstrap  # noqa: F401


def test_import_is_lazy():
    import providers.registry as reg_mod
    fresh = importlib.reload(reg_mod)
    assert fresh._registry is None, "导入/重载不应触发注册表构建"


def test_registry_has_17_legacy_sources():
    from providers.registry import get_provider_registry
    reg = get_provider_registry()
    names = reg.names()
    assert len(names) == 17
    assert "geoip" in names
    assert "abusech" in names


def test_geoip_metadata():
    from providers.registry import get_provider_registry
    from providers.types import ProviderCategory
    reg = get_provider_registry()
    geo = reg.get("geoip")
    assert geo.category == ProviderCategory.GEOIP
    assert geo.requires_api_key is True
    assert geo.config_keys == ["license_key"]


def test_adapter_holds_class_not_instance():
    """证明兼容适配器未实例化底层插件（持有的是类）。"""
    from providers.registry import get_provider_registry
    reg = get_provider_registry()
    adapter = reg.get("ip2asn")
    assert isinstance(adapter._plugin_cls, type)
    assert adapter._plugin_cls.__name__ == "IP2ASNSource"


def test_describe_all_shape():
    from providers.registry import get_provider_registry
    reg = get_provider_registry()
    rows = reg.describe_all()
    assert len(rows) == 17
    sample = rows[0]
    for key in ("name", "category", "kind", "enabled",
                "requires_api_key", "config_keys", "timeout"):
        assert key in sample
