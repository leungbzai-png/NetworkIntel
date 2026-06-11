"""
NetworkIntel - Provider 层数据类型（types）
===========================================
纯 dataclass / Enum，零第三方依赖。供统一 Provider 接口与未来代码/测试使用。
本模块不读取配置、不发起网络、不实例化任何插件 —— 导入完全惰性。

详见 docs/API_PROVIDER_SPEC.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ProviderCategory(str, Enum):
    """数据源语义类别。"""
    GEOIP = "geoip"
    ASN = "asn"
    ROUTING = "routing"          # RPKI / ROA 等
    CLOUD = "cloud"
    THREAT_INTEL = "threat_intel"
    REGISTRY = "registry"        # RIR / PeeringDB 等
    ONLINE_QUERY = "online_query"


class ProviderKind(str, Enum):
    """主数据流模型。"""
    DOWNLOAD = "download"          # 批量下载 → 落库（现有 17 个源）
    ONLINE_QUERY = "online_query"  # 在线逐 IP 查询（未来 ipinfo/AbuseIPDB/...）


@dataclass(frozen=True)
class RateLimit:
    """速率限制描述（仅声明，执行由具体 provider/HTTP 工具负责）。"""
    max_calls: int
    period_seconds: float
    max_concurrency: int = 1


@dataclass
class ConfigValidation:
    """validate_config() 的返回。"""
    ok: bool
    missing: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    """update() 的返回（下载型）。"""
    success: bool
    record_count: int = 0
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class ProviderError:
    """error_handler() 归一化后的错误。"""
    category: str            # 'network' | 'rate_limit' | 'auth' | 'parse' | 'unknown'
    message: str
    retryable: bool = False


@dataclass
class NormalizedResult:
    """
    query() / normalize_result() 的统一返回。
    `data` 的键应对齐 query/engine.py::query_ip() 的结果结构
    （geoip / asn / rpki / cloud / threats / is_tor / is_vpn / ...），
    以便未来与本地数据合并。
    """
    ip: str
    source: str
    category: str
    data: dict = field(default_factory=dict)
    raw: Any = None
    error: Optional[str] = None


# 已知的「未配置」占位符（与 P0 的 .env/${VAR} 规范一致）
PLACEHOLDER_VALUES = {
    "YOUR_MAXMIND_LICENSE_KEY_HERE",
    "your_maxmind_license_key_here",
}


def is_placeholder(value: Any) -> bool:
    """判断配置值是否为未填的占位符（空 / ${VAR} / YOUR_..._HERE）。"""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    v = value.strip()
    if not v:
        return True
    if v.startswith("${") and v.endswith("}"):
        return True
    if v in PLACEHOLDER_VALUES:
        return True
    if v.upper().startswith("YOUR_") and v.upper().endswith("_HERE"):
        return True
    return False
