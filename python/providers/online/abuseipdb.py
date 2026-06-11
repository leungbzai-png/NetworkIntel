"""
NetworkIntel - AbuseIPDB 在线 Provider（骨架，未实现真实请求）
============================================================
仅接口骨架 + 配置校验。query() 暂返回 not_implemented。
真实 key 从 .env 的 ABUSEIPDB_API_KEY 读取（sources.yaml ${ABUSEIPDB_API_KEY}）。
免费额度约 1000 次/天 —— 已在 rate_limit 中声明（供未来限速）。

后续实现要点（参考）：
  GET https://api.abuseipdb.com/api/v2/check?ipAddress=<ip>
  Header: Key: <api_key>, Accept: application/json
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers.online.base import OnlineApiProvider
from providers.types import ProviderCategory, NormalizedResult, RateLimit


class AbuseIPDBProvider(OnlineApiProvider):
    name = "abuseipdb"
    category = ProviderCategory.THREAT_INTEL
    requires_api_key = True
    config_keys = ["api_key"]
    ENV_KEY = "ABUSEIPDB_API_KEY"
    timeout = 15.0
    rate_limit = RateLimit(max_calls=1000, period_seconds=86400)  # 免费额度

    def query(self, ip: str) -> NormalizedResult:
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None,
            error="not_implemented: abuseipdb provider 仍是骨架",
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        try:
            d = (raw or {}).get("data", {}) if isinstance(raw, dict) else {}
            score = d.get("abuseConfidenceScore")
            unified = {
                "ip":                   d.get("ipAddress") or ip or "",
                "abuse_confidence":     score,
                "total_reports":        d.get("totalReports"),
                "country_code":         d.get("countryCode"),
                "is_tor":               d.get("isTor"),
                "usage_type":           d.get("usageType"),
                "threats":              ([{"list_name": "abuseipdb",
                                           "threat_type": "abuse",
                                           "severity": _severity(score)}]
                                         if score else []),
                "source":               self.name,
                "fetched_at":           datetime.now(timezone.utc).isoformat(),
                "raw":                  raw,
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


def _severity(score) -> str:
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "low"
    if s >= 85:
        return "critical"
    if s >= 50:
        return "high"
    if s >= 25:
        return "medium"
    return "low"
