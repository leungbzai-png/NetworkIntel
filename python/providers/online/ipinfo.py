"""
NetworkIntel - ipinfo.io 在线 Provider（旁路能力，未接入离线主查询）
==================================================================
真实实现：GET https://ipinfo.io/{ip}/json
认证：Authorization: Bearer <token>（token 从 .env 的 IPINFO_TOKEN 读取，
经 config_loader 解析；本模块不把 token 写入 URL / 日志 / 异常 / 返回对象）。

详见 docs/ONLINE_PROVIDERS.md
"""
from __future__ import annotations

from datetime import datetime, timezone

from providers.online.base import OnlineApiProvider
from providers.types import ProviderCategory, NormalizedResult


class IPInfoProvider(OnlineApiProvider):
    name = "ipinfo"
    category = ProviderCategory.GEOIP   # 同时含 ASN 信息
    requires_api_key = True
    config_keys = ["token"]
    ENV_KEY = "IPINFO_TOKEN"
    timeout = 15.0

    BASE_URL = "https://ipinfo.io/{ip}/json"

    def query(self, ip: str) -> NormalizedResult:
        """在线查询。任何失败返回统一失败对象，且绝不泄露 token。"""
        key = self._resolve_key()
        if not key:
            return self._fail(ip, "missing_api_key: 未配置 IPINFO_TOKEN（请在 .env 设置）")

        from providers.http import http_get_json
        # token 走请求头，不进 URL；http 层不记录 headers
        res = http_get_json(
            self.BASE_URL.format(ip=ip),
            headers={"Authorization": f"Bearer {key}"},
            timeout=self.timeout,
        )

        if not res.ok:
            return self._fail(ip, self._classify(res))

        # ipinfo 在错误时返回 {"error": {...}}（如无效 token / 速率）
        if isinstance(res.json, dict) and res.json.get("error"):
            title = (res.json.get("error") or {}).get("title", "ipinfo error")
            return self._fail(ip, f"ipinfo_error: {title}")

        return self.normalize_result(res.json, ip=ip)

    @staticmethod
    def _classify(res) -> str:
        """把 HTTP 失败映射为清晰、无 token 的错误串。"""
        if res.status in (401, 403):
            return f"auth_failed (HTTP {res.status}): 检查 IPINFO_TOKEN"
        if res.status == 429:
            return "rate_limited (HTTP 429): 已达 ipinfo 速率限制，请稍后重试"
        if res.status and 500 <= res.status < 600:
            return f"server_error (HTTP {res.status})"
        return res.error or "request_failed"

    def _fail(self, ip: str, msg: str) -> NormalizedResult:
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None, error=msg,
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        """ipinfo /json 响应 → 统一字段。可处理离线模拟数据。"""
        try:
            d = raw if isinstance(raw, dict) else {}
            loc = (d.get("loc") or "").split(",")
            lat = loc[0] if len(loc) == 2 else None
            lon = loc[1] if len(loc) == 2 else None

            org = d.get("org") or ""
            asn_num = None
            asn_name = None
            if org:
                head, _, tail = org.partition(" ")
                if head.upper().startswith("AS") and head[2:].isdigit():
                    asn_num = int(head[2:])
                    asn_name = tail or None
                else:
                    asn_name = org

            resolved_ip = d.get("ip") or ip or ""
            unified = {
                "ip":           resolved_ip,
                "country_code": d.get("country"),
                "region":       d.get("region"),
                "city":         d.get("city"),
                "latitude":     lat,
                "longitude":    lon,
                "org":          org or None,
                "asn":          asn_num,
                "asn_name":     asn_name,
                "timezone":     d.get("timezone"),
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
