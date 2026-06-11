"""
NetworkIntel - BGPView 在线 Provider（旁路能力，未接入主查询）
=============================================================
数据源：BGPView 公开 API  https://api.bgpview.io/ip/{ip}
无需 API Key。仅作为「在线 Provider 旁路验证」，**不接入 query_ip 离线主流程**。

详见 docs/BGPVIEW_PROVIDER.md
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers.base import OnlineQueryProvider
from providers.types import (
    ProviderCategory, ConfigValidation, NormalizedResult,
)


class BGPViewProvider(OnlineQueryProvider):
    name = "bgpview"
    category = ProviderCategory.ASN
    requires_api_key = False
    config_keys: list[str] = []
    timeout = 15.0

    BASE_URL = "https://api.bgpview.io/ip/{ip}"

    def validate_config(self) -> ConfigValidation:
        # 无需密钥，配置永远有效
        return ConfigValidation(ok=True, messages=["bgpview 无需 API key"])

    def query(self, ip: str) -> NormalizedResult:
        """在线查询单个 IP 的 ASN/BGP 信息。任何失败返回统一失败对象。"""
        from providers.http import http_get_json
        res = http_get_json(self.BASE_URL.format(ip=ip), timeout=self.timeout)
        if not res.ok:
            return NormalizedResult(
                ip=ip, source=self.name, category=self.category.value,
                data={}, raw=None,
                error=res.error or "request failed",
            )
        # BGPView 用 status 字段标识业务成功
        if isinstance(res.json, dict) and res.json.get("status") != "ok":
            return NormalizedResult(
                ip=ip, source=self.name, category=self.category.value,
                data={}, raw=res.json,
                error=f"bgpview status={res.json.get('status')}",
            )
        return self.normalize_result(res.json, ip=ip)

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        """把 BGPView 响应映射为统一字段。可处理离线模拟数据。"""
        try:
            data = raw.get("data", {}) if isinstance(raw, dict) else {}
            resolved_ip = data.get("ip") or ip or ""

            prefixes = data.get("prefixes") or []
            first = prefixes[0] if prefixes else {}
            asn = first.get("asn") or {}
            rir_alloc = data.get("rir_allocation") or {}

            unified = {
                "ip":           resolved_ip,
                "asn":          asn.get("asn"),
                "asn_name":     asn.get("name") or asn.get("description"),
                "prefix":       first.get("prefix"),
                "country_code": first.get("country_code") or asn.get("country_code"),
                "rir":          rir_alloc.get("rir_name"),
                "source":       self.name,
                "fetched_at":   datetime.now(timezone.utc).isoformat(),
                "raw":          raw,
            }
            return NormalizedResult(
                ip=resolved_ip, source=self.name,
                category=self.category.value, data=unified, raw=raw,
            )
        except Exception as e:
            return NormalizedResult(
                ip=ip or "", source=self.name, category=self.category.value,
                data={}, raw=raw, error=f"normalize error: {type(e).__name__}: {e}",
            )
