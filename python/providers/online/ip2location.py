"""
NetworkIntel - IP2Location.io 在线 Provider（旁路能力，未接入离线主查询）
=====================================================================
真实实现：GET https://api.ip2location.io/?key=<key>&ip=<ip>
key 经 requests params 传递（不写入 HttpResult.url / 日志 / 异常 / 返回对象）。
key 从 .env 的 IP2LOCATION_API_KEY 读取（config_loader 解析）。

详见 docs/ONLINE_PROVIDERS.md
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

    BASE_URL = "https://api.ip2location.io/"

    def query(self, ip: str) -> NormalizedResult:
        """在线查询。任何失败返回统一失败对象，且绝不泄露 key。"""
        key = self._resolve_key()
        if not key:
            return self._fail(ip, "missing_api_key: 未配置 IP2LOCATION_API_KEY（请在 .env 设置）")

        from providers.http import http_get_json
        # key 走 params（requests 内部拼接），不进入 HttpResult.url
        res = http_get_json(
            self.BASE_URL,
            params={"key": key, "ip": ip},
            timeout=self.timeout,
        )

        if not res.ok:
            return self._fail(ip, self._classify(res))

        # ip2location.io 在错误时可能返回 {"error": {...}}（如无效 key / 额度）
        if isinstance(res.json, dict) and res.json.get("error"):
            err = res.json.get("error") or {}
            msg = err.get("error_message") or "ip2location error"
            return self._fail(ip, f"ip2location_error: {msg}")

        return self.normalize_result(res.json, ip=ip)

    @staticmethod
    def _classify(res) -> str:
        """把 HTTP 失败映射为清晰、无 key 的错误串。"""
        if res.status in (401, 403):
            return f"auth_failed (HTTP {res.status}): 检查 IP2LOCATION_API_KEY"
        if res.status == 429:
            return "rate_limited (HTTP 429): 已达 ip2location 速率/额度限制，请稍后重试"
        if res.status and 500 <= res.status < 600:
            return f"server_error (HTTP {res.status})"
        return res.error or "request_failed"

    def _fail(self, ip: str, msg: str) -> NormalizedResult:
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None, error=msg,
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        """ip2location.io 响应 → 统一字段。可处理离线模拟数据。"""
        try:
            d = raw if isinstance(raw, dict) else {}

            asn_raw = d.get("asn")
            asn_num = None
            if asn_raw is not None:
                s = str(asn_raw).strip()
                asn_num = int(s) if s.isdigit() else None

            resolved_ip = d.get("ip") or ip or ""
            unified = {
                "ip":           resolved_ip,
                "country_code": d.get("country_code"),
                "country_name": d.get("country_name"),
                "region":       d.get("region_name"),
                "city":         d.get("city_name"),
                "latitude":     d.get("latitude"),
                "longitude":    d.get("longitude"),
                "isp":          d.get("isp"),
                "domain":       d.get("domain"),
                "usage_type":   d.get("usage_type"),
                "asn":          asn_num,
                "asn_name":     d.get("as"),
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
                data={}, raw=raw, error=f"normalize error: {type(e).__name__}",
            )
