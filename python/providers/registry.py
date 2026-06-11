"""
NetworkIntel - 兼容型 Provider 注册表（registry）
=================================================
把现有 17 个 DataSourceBase 插件「视图化」为统一 Provider，**不迁移、不改动**旧实现。

惰性保证（重要）：
  * 本模块顶层只依赖 providers.base / providers.types（纯 stdlib），
    `import providers.registry` 不会触发 get_config()、网络、或实例化任何插件。
  * 现有插件类经由 `get_provider_registry()` 在「被调用时」才惰性导入并包装；
    适配器仅持有「类引用 + 静态元数据」，真正实例化推迟到 `update()`。

详见 docs/API_PROVIDER_SPEC.md / API_PROVIDER_MIGRATION_PLAN.md
"""
from __future__ import annotations

from typing import Optional

from providers.base import DownloadProvider, ProviderNotSupported
from providers.types import ProviderCategory, UpdateResult, NormalizedResult


# ── 现有源的静态元数据（来自 docs/API_PROVIDERS_AUDIT.md，无需实例化即可获知）──
# name -> (category, requires_api_key, config_keys)
_LEGACY_META: dict[str, tuple[ProviderCategory, bool, list[str]]] = {
    "geoip":            (ProviderCategory.GEOIP,        True,  ["license_key"]),
    "ip2asn":           (ProviderCategory.ASN,          False, []),
    "rpki":             (ProviderCategory.ROUTING,      False, []),
    "rir_delegated":    (ProviderCategory.REGISTRY,     False, []),
    "cloud_aws":        (ProviderCategory.CLOUD,        False, []),
    "cloud_azure":      (ProviderCategory.CLOUD,        False, []),
    "cloud_gcp":        (ProviderCategory.CLOUD,        False, []),
    "cloud_cloudflare": (ProviderCategory.CLOUD,        False, []),
    "cloud_hetzner":    (ProviderCategory.CLOUD,        False, []),
    "cloud_vultr":      (ProviderCategory.CLOUD,        False, []),
    "tor_exits":        (ProviderCategory.THREAT_INTEL, False, []),
    "vpn_x4bnet":       (ProviderCategory.THREAT_INTEL, False, []),
    "spamhaus_drop":    (ProviderCategory.THREAT_INTEL, False, []),
    "firehol":          (ProviderCategory.THREAT_INTEL, False, []),
    "abusech":          (ProviderCategory.THREAT_INTEL, False, []),
    "emerging_threats": (ProviderCategory.THREAT_INTEL, False, []),
    "peeringdb":        (ProviderCategory.REGISTRY,     False, []),
}


class LegacyDownloadAdapter(DownloadProvider):
    """
    把一个现有 DataSourceBase **类** 包装成统一 DownloadProvider。
    仅持有类引用与静态元数据；实例化推迟到 update() 调用时。
    """

    def __init__(self, name: str, plugin_cls: type,
                 category: ProviderCategory,
                 requires_api_key: bool = False,
                 config_keys: Optional[list[str]] = None):
        self.name = name
        self._plugin_cls = plugin_cls
        self.category = category
        self.requires_api_key = requires_api_key
        self.config_keys = config_keys or []

    # enabled 惰性读取配置（仅在访问时），保持导入惰性
    @property
    def enabled(self) -> bool:
        try:
            from utils.config_loader import get_config
            src = get_config().get_source(self.name) or {}
            return bool(src.get("enabled", True))
        except Exception:
            return True

    def _instantiate(self):
        """按需创建底层插件实例（此时才读配置 / 建 cache 目录）。"""
        return self._plugin_cls()

    def update(self) -> UpdateResult:
        try:
            plugin = self._instantiate()
            res = plugin.update() or {}
            return UpdateResult(
                success=bool(res.get("success")),
                record_count=int(res.get("record_count", 0) or 0),
                error=res.get("error"),
            )
        except Exception as e:  # 适配层不应让旧逻辑异常逃逸
            return UpdateResult(success=False, error=str(e))

    def query(self, ip: str) -> NormalizedResult:
        raise ProviderNotSupported(f"{self.name}: 下载型 provider 不支持 query()")


class ProviderRegistry:
    """统一 Provider 容器（兼容旧源 + 未来原生 provider）。"""

    def __init__(self):
        self._providers: dict[str, DownloadProvider] = {}

    def register(self, provider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str):
        return self._providers.get(name)

    def list(self) -> list:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers.keys())

    def describe_all(self) -> list[dict]:
        return [p.describe() for p in self._providers.values()]


def build_legacy_registry() -> ProviderRegistry:
    """
    惰性构建：枚举现有 PLUGIN_REGISTRY，包装为 LegacyDownloadAdapter。
    在此函数被调用时才导入 datasources.plugin_registry（会拉入 requests 等依赖）。
    不实例化任何插件。
    """
    from datasources.plugin_registry import PLUGIN_REGISTRY  # 惰性导入

    reg = ProviderRegistry()
    for name, plugin_cls in PLUGIN_REGISTRY.items():
        category, requires_key, config_keys = _LEGACY_META.get(
            name, (ProviderCategory.REGISTRY, False, [])
        )
        reg.register(LegacyDownloadAdapter(
            name=name,
            plugin_cls=plugin_cls,
            category=category,
            requires_api_key=requires_key,
            config_keys=config_keys,
        ))
    return reg


# 进程内单例（首次调用时构建）
_registry: Optional[ProviderRegistry] = None


def get_provider_registry() -> ProviderRegistry:
    """获取统一 Provider 注册表（首次调用惰性构建）。"""
    global _registry
    if _registry is None:
        _registry = build_legacy_registry()
    return _registry
