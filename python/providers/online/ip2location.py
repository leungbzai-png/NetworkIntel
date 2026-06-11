"""
NetworkIntel - IP2Location 在线 Provider（骨架，未实现真实请求）
=============================================================
仅接口骨架 + 配置校验。query() 暂返回 not_implemented。
真实 key 从 .env 的 IP2LOCATION_API_KEY 读取（sources.yaml ${IP2LOCATION_API_KEY}）。

后续实现要点（参考）：GET https://api.ip2location.io/?key=<key>&ip=<ip>
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers.online.base import OnlineApiProvider
from providers.types import ProviderCategory, NormalizedResult


class IP2LocationProvider(OnlineApiProvider):
    name = "ip2location"
    category = ProviderCategory.GEOIP
    requires_api_key = True
    config_keys = ["api_key"]
    ENV_KEY = "IP2LOCATION_API_KEY"
    timeout = 15.0

    def query(self, ip: str) -> NormalizedResult:
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None,
            error="not_implemented: ip2location provider 仍是骨架",
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        try:
            d = raw if isinstance(raw, dict) else {}
            unified = {
                "ip":           d.get("ip") or ip or "",
                "country_code": d.get("country_code"),
                "region":       d.get("region_name"),
                "city":         d.get("city_name"),
                "latitude":     d.get("latitude"),
                "longitude":    d.get("longitude"),
                "asn":          d.get("asn"),
                "asn_name":     d.get("as"),
                "source":       self.name,
                "fetched_at":   datetime.now(timezone.utc).isoformat(),
                "raw":          raw,
            }
            return NormalizedResult(
                ip=unified["ip"], source=self.name,
                category=self.category.value, data=unified, raw=raw,
            )
        except Exception as e:
            return NormalizedResult(
                ip=ip or "", source=self.name, category=self.category.value,
                data={}, raw=raw, error=f"normalize error: {type(e).__name__}",
            )
