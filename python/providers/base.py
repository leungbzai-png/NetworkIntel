"""
NetworkIntel - 统一 Provider 抽象基类（base）
=============================================
定义统一接口的字段与方法签名，并按「双数据流」拆分子类：
  - DownloadProvider   （批量下载 → 落库）  ─ GeoIPProvider / ASNProvider / ThreatIntelProvider
  - OnlineQueryProvider（在线逐 IP 查询）

设计要点（详见 docs/API_PROVIDER_SPEC.md）：
  * 不强制旧 provider 立即实现全部方法：不适用者 no-op 或抛 ProviderNotSupported。
  * 导入惰性：本模块不读配置、不联网、不实例化插件。
    validate_config() / error_handler() 仅在「被调用时」才惰性导入 utils.config_loader。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from providers.types import (
    ProviderCategory,
    ProviderKind,
    RateLimit,
    ConfigValidation,
    UpdateResult,
    ProviderError,
    NormalizedResult,
    is_placeholder,
)


class ProviderNotSupported(Exception):
    """provider 不支持该操作（如 DownloadProvider 不支持在线 query）。"""


class Provider(ABC):
    """
    统一 Provider 接口。
    子类必须设置类属性：name / category / kind；按需覆盖方法。
    """

    name: str = ""
    category: ProviderCategory = ProviderCategory.REGISTRY
    kind: ProviderKind = ProviderKind.DOWNLOAD
    enabled: bool = True
    requires_api_key: bool = False
    config_keys: list[str] = []
    rate_limit: Optional[RateLimit] = None
    timeout: float = 30.0

    # ── 行为方法（默认实现，按子类/具体 provider 覆盖）──────────────

    def query(self, ip: str) -> NormalizedResult:
        """在线逐 IP 查询。下载型 provider 不支持。"""
        raise ProviderNotSupported(
            f"{self.name}: query() 不适用于 kind={self.kind.value}"
        )

    def update(self) -> UpdateResult:
        """批量下载并落库。在线查询型 provider 默认 no-op。"""
        return UpdateResult(success=True, skipped=True)

    def normalize_result(self, raw) -> NormalizedResult:
        """把原始 API 响应映射为统一结构（在线型必须实现）。"""
        raise ProviderNotSupported(
            f"{self.name}: normalize_result() 未实现"
        )

    def validate_config(self) -> ConfigValidation:
        """
        校验配置。仅当 requires_api_key=True 时检查 config_keys。
        基于「解析后」的配置值（.env + ${VAR} 已由 config_loader 解析），
        占位符视为未配置。惰性导入，避免模块级副作用。
        """
        if not self.requires_api_key:
            return ConfigValidation(ok=True)

        try:
            from utils.config_loader import get_config
            src = get_config().get_source(self.name) or {}
        except Exception as e:  # 配置缺失等不应在校验阶段崩溃
            return ConfigValidation(
                ok=False, missing=list(self.config_keys),
                messages=[f"读取配置失败: {e}"],
            )

        missing = [k for k in self.config_keys if is_placeholder(src.get(k))]
        if missing:
            return ConfigValidation(
                ok=False, missing=missing,
                messages=[f"缺少或未填写: {', '.join(missing)}（请在 .env 配置）"],
            )
        return ConfigValidation(ok=True)

    def error_handler(self, exc: Exception, ctx: Optional[dict] = None) -> ProviderError:
        """把异常归一化为 ProviderError，并标注是否可重试。"""
        name = type(exc).__name__.lower()
        msg = str(exc)
        # 通过异常类型名做轻量分类，避免硬依赖 requests
        if "timeout" in name or "connection" in name:
            return ProviderError("network", msg, retryable=True)
        if "toomanyrequests" in name or "429" in msg or "ratelimit" in name.replace("_", ""):
            return ProviderError("rate_limit", msg, retryable=True)
        if "auth" in name or "401" in msg or "403" in msg:
            return ProviderError("auth", msg, retryable=False)
        if "json" in name or "decode" in name or "parse" in name or "value" in name:
            return ProviderError("parse", msg, retryable=False)
        return ProviderError("unknown", msg, retryable=False)

    # ── 元数据导出（调试/注册用）────────────────────────────────

    def describe(self) -> dict:
        return {
            "name": self.name,
            "category": self.category.value,
            "kind": self.kind.value,
            "enabled": self.enabled,
            "requires_api_key": self.requires_api_key,
            "config_keys": list(self.config_keys),
            "rate_limit": (
                None if self.rate_limit is None
                else {
                    "max_calls": self.rate_limit.max_calls,
                    "period_seconds": self.rate_limit.period_seconds,
                    "max_concurrency": self.rate_limit.max_concurrency,
                }
            ),
            "timeout": self.timeout,
        }


# ── 下载型 ────────────────────────────────────────────────────

class DownloadProvider(Provider):
    """批量下载 → 落库。不支持在线 query()。"""
    kind = ProviderKind.DOWNLOAD

    def query(self, ip: str) -> NormalizedResult:
        raise ProviderNotSupported(f"{self.name}: 下载型 provider 不支持 query()")

    @abstractmethod
    def update(self) -> UpdateResult:
        ...


class GeoIPProvider(DownloadProvider):
    category = ProviderCategory.GEOIP


class ASNProvider(DownloadProvider):
    category = ProviderCategory.ASN


class ThreatIntelProvider(DownloadProvider):
    category = ProviderCategory.THREAT_INTEL


# ── 在线查询型 ────────────────────────────────────────────────

class OnlineQueryProvider(Provider):
    """
    在线逐 IP 查询。子类实现 query() + normalize_result()（+ 需要时 validate_config）。
    update() 默认 no-op（不落库）。
    """
    kind = ProviderKind.ONLINE_QUERY

    def update(self) -> UpdateResult:
        return UpdateResult(success=True, skipped=True)

    @abstractmethod
    def query(self, ip: str) -> NormalizedResult:
        ...
