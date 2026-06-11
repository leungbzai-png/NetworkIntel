"""
NetworkIntel - ipinfo.io 在线 Provider（骨架，未实现真实请求）
============================================================
仅提供接口骨架与配置校验。query() 暂返回 not_implemented，不发网络请求。
真实 token 从 .env 的 IPINFO_TOKEN 读取（经 sources.yaml ${IPINFO_TOKEN} 解析）。

后续实现要点（参考）：GET https://ipinfo.io/{ip}/json?token=<token>
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers.online.base import OnlineApiProvider
from providers.types import ProviderCategory, NormalizedResult


class IPInfoProvider(OnlineApiProvider):
    name = "ipinfo"
    category = ProviderCategory.GEOIP
    requires_api_key = True
    config_keys = ["token"]
    ENV_KEY = "IPINFO_TOKEN"
    timeout = 15.0

    def query(self, ip: str) -> NormalizedResult:
        # 骨架：不发真实请求
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None,
            error="not_implemented: ipinfo provider 仍是骨架",
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        """ipinfo /json 响应 → 统一字段（供未来实现，当前不被 query 调用）。"""
        try:
            d = raw if isinstance(raw, dict) else {}
            loc = (d.get("loc") or ",").split(",")
            unified = {
                "ip":           d.get("ip") or ip or "",
                "country_code": d.get("country"),
                "region":       d.get("region"),
                "city":         d.get("city"),
                "latitude":     loc[0] if len(loc) == 2 else None,
                "longitude":    loc[1] if len(loc) == 2 else None,
                "asn":          (d.get("org") or "").split(" ")[0].replace("AS", "") or None,
                "asn_name":     d.get("org"),
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
