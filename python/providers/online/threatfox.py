"""
NetworkIntel - ThreatFox (abuse.ch) 在线 Provider（骨架，未实现真实请求）
=====================================================================
仅接口骨架 + 配置校验。query() 暂返回 not_implemented。
abuse.ch 现要求 Auth-Key：真实 key 从 .env 的 THREATFOX_API_KEY 读取
（sources.yaml ${THREATFOX_API_KEY}）。

后续实现要点（参考）：
  POST https://threatfox-api.abuse.ch/api/v1/  body={"query":"search_ioc","search_term":"<ip>"}
  Header: Auth-Key: <api_key>
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers.online.base import OnlineApiProvider
from providers.types import ProviderCategory, NormalizedResult


class ThreatFoxProvider(OnlineApiProvider):
    name = "threatfox"
    category = ProviderCategory.THREAT_INTEL
    requires_api_key = True
    config_keys = ["api_key"]
    ENV_KEY = "THREATFOX_API_KEY"
    timeout = 15.0

    def query(self, ip: str) -> NormalizedResult:
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None,
            error="not_implemented: threatfox provider 仍是骨架",
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        try:
            rows = (raw or {}).get("data", []) if isinstance(raw, dict) else []
            threats = [
                {
                    "list_name":   "threatfox",
                    "threat_type": r.get("threat_type") or "ioc",
                    "malware":     r.get("malware_printable"),
                    "severity":    "high",
                }
                for r in (rows or []) if isinstance(r, dict)
            ]
            unified = {
                "ip":         ip or "",
                "threats":    threats,
                "ioc_count":  len(threats),
                "source":     self.name,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "raw":        raw,
            }
            return NormalizedResult(
                ip=ip or "", source=self.name,
                category=self.category.value, data=unified, raw=raw,
            )
        except Exception as e:
            return NormalizedResult(
                ip=ip or "", source=self.name, category=self.category.value,
                data={}, raw=raw, error=f"normalize error: {type(e).__name__}",
            )
