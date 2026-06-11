"""
NetworkIntel - AbuseIPDB 在线 Provider（旁路能力，未接入离线主查询）
==================================================================
真实实现：GET https://api.abuseipdb.com/api/v2/check?ipAddress=<ip>
认证：请求头 Key: <api_key>（key 从 .env 的 ABUSEIPDB_API_KEY 读取，经
config_loader 解析）。key **绝不**写入 URL / 日志 / 异常 / 缓存 / 返回对象。

免费额度约 1000 次/天；本实现按 abuseipdb 维度受 ratelimit 保护
（默认 per_day=900，留余量）。威胁类结果 TTL 较短（默认 6 小时，
ABUSEIPDB_CACHE_TTL_HOURS 可调）。

详见 docs/ONLINE_PROVIDERS.md
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

    BASE_URL = "https://api.abuseipdb.com/api/v2/check"
    MAX_AGE_DAYS = 90

    def query(self, ip: str) -> NormalizedResult:
        """在线查询。任何失败返回统一失败对象，且绝不泄露 api key。"""
        key = self._resolve_key()
        if not key:
            return self._fail(ip, "missing_api_key: 未配置 ABUSEIPDB_API_KEY（请在 .env 设置）")

        from providers.http import http_get_json
        # api key 走请求头（Key），不进 URL；verbose 让响应包含 isTor 等字段
        res = http_get_json(
            self.BASE_URL,
            params={"ipAddress": ip, "maxAgeInDays": self.MAX_AGE_DAYS, "verbose": ""},
            headers={"Key": key},
            timeout=self.timeout,
        )

        if not res.ok:
            return self._fail(ip, self._classify(res))

        # AbuseIPDB 在错误时返回 {"errors": [{"detail": ...}]}
        if isinstance(res.json, dict) and res.json.get("errors"):
            errs = res.json.get("errors") or [{}]
            detail = (errs[0] or {}).get("detail", "abuseipdb error")
            return self._fail(ip, f"abuseipdb_error: {detail}")

        return self.normalize_result(res.json, ip=ip)

    @staticmethod
    def _classify(res) -> str:
        """把 HTTP 失败映射为清晰、无 key 的错误串。"""
        if res.status in (401, 403):
            return f"auth_failed (HTTP {res.status}): 检查 ABUSEIPDB_API_KEY"
        if res.status == 429:
            return "rate_limited (HTTP 429): 已达 abuseipdb 速率/额度限制，请稍后重试"
        if res.status and 500 <= res.status < 600:
            return f"server_error (HTTP {res.status})"
        return res.error or "request_failed"

    def _fail(self, ip: str, msg: str) -> NormalizedResult:
        return NormalizedResult(
            ip=ip, source=self.name, category=self.category.value,
            data={}, raw=None, error=msg,
        )

    def normalize_result(self, raw, ip: str = None) -> NormalizedResult:
        """AbuseIPDB /check 响应 → 统一字段。可处理离线模拟数据。"""
        try:
            d = (raw or {}).get("data", {}) if isinstance(raw, dict) else {}
            if not isinstance(d, dict):
                d = {}
            score = d.get("abuseConfidenceScore")
            sev = _severity(score)
            resolved_ip = d.get("ipAddress") or ip or ""
            threats = []
            if isinstance(score, (int, float)) and score > 0:
                threats = [{
                    "list_name":   "abuseipdb",
                    "threat_type": "abuse",
                    "severity":    sev,
                }]
            unified = {
                "ip":                     resolved_ip,
                "abuse_confidence_score": score,
                "total_reports":          d.get("totalReports"),
                "num_distinct_users":     d.get("numDistinctUsers"),
                "is_public":              d.get("isPublic"),
                "is_whitelisted":         d.get("isWhitelisted"),
                "is_tor":                 d.get("isTor"),
                "usage_type":             d.get("usageType"),
                "isp":                    d.get("isp"),
                "domain":                 d.get("domain"),
                "country_code":           d.get("countryCode"),
                "severity":               sev,
                "threats":                threats,
                "source":                 self.name,
                "fetched_at":             datetime.now(timezone.utc).isoformat(),
                "raw":                    raw,
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


def _severity(score) -> str:
    """AbuseIPDB confidence(0-100) → 语义等级。

    0：clean | 1-24：low | 25-74：medium | 75-100：high
    """
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "clean"
    if s <= 0:
        return "clean"
    if s < 25:
        return "low"
    if s < 75:
        return "medium"
    return "high"
