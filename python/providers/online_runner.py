"""
NetworkIntel - 在线 Provider 旁路执行器（online_runner）
======================================================
**仅供显式旁路调用**：不接入 query_ip、不被 scheduler/do_update 引用。

调用顺序：
  1) provider 是否在允许列表
  2) validate_config()（缺 key 优雅失败，不联网）
  3) 查缓存（use_cache 且非 force_refresh）—— 命中直接返回，**不消耗限额**
  4) 限速 / 熔断 can_call()（仅在需要回源时检查）
  5) 通过后才 provider.query()
  6) 记录限速 + 写缓存
  7) 返回统一 RunResult

> 缓存先于限速检查：缓存命中即使在限速/熔断期间仍可服务，且不占用额度；
> 只有真正回源（缓存未命中或 force_refresh）才受限速/熔断约束。
> force_refresh 跳过缓存，因此仍会经过限速/熔断检查。

缓存/限速通过环境开关：ONLINE_CACHE_ENABLED / ONLINE_RATE_LIMIT_ENABLED（默认 true）。
详见 docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from providers.cache import OnlineCache
from providers.ratelimit import RateLimiter, build_default_limiter
from providers.types import ProviderCategory


# 默认允许的无副作用在线 provider。abuseipdb 为显式旁路（缺 key 时优雅失败）。
ALLOWED_PROVIDERS = {"bgpview", "ipinfo", "ip2location", "abuseipdb"}


def _env_true(name: str, default: bool = True) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class RunResult:
    provider: str
    ip: str
    ok: bool
    from_cache: bool = False
    data: dict = field(default_factory=dict)
    error: Optional[str] = None
    rate_limited: bool = False
    circuit_open: bool = False
    next_available_at: Optional[str] = None


def _ttl_seconds(provider) -> int:
    name = getattr(provider, "name", "")
    cat = getattr(provider, "category", None)
    if name == "bgpview":
        return _env_int("BGPVIEW_CACHE_TTL_DAYS", 30) * 86400
    if name == "ipinfo":
        return _env_int("IPINFO_CACHE_TTL_DAYS", 14) * 86400
    if name == "ip2location":
        return _env_int("IP2LOCATION_CACHE_TTL_DAYS", 14) * 86400
    if name == "abuseipdb":
        return _env_int("ABUSEIPDB_CACHE_TTL_HOURS", 6) * 3600
    if cat == ProviderCategory.THREAT_INTEL:
        return 6 * 3600          # 威胁类默认 6 小时
    return 14 * 86400


class OnlineRunner:
    def __init__(self,
                 cache: Optional[OnlineCache] = None,
                 limiter: Optional[RateLimiter] = None,
                 provider_factory: Optional[Callable[[str], Any]] = None,
                 allowed: Optional[set] = None):
        self._cache = cache
        self._limiter = limiter
        self._factory = provider_factory
        self.allowed = allowed if allowed is not None else set(ALLOWED_PROVIDERS)

    # 懒构造，避免导入期副作用
    def _get_cache(self) -> Optional[OnlineCache]:
        if not _env_true("ONLINE_CACHE_ENABLED", True):
            return None
        if self._cache is None:
            self._cache = OnlineCache()
        return self._cache

    def _get_limiter(self) -> Optional[RateLimiter]:
        if not _env_true("ONLINE_RATE_LIMIT_ENABLED", True):
            return None
        if self._limiter is None:
            # 注入 per-provider 默认额度 + 熔断配置（环境可覆盖）
            self._limiter = build_default_limiter()
        return self._limiter

    def _make_provider(self, name: str):
        if self._factory is not None:
            return self._factory(name)
        from providers.online import get_online_provider
        return get_online_provider(name)

    def _blocked_result(self, provider_name: str, ip: str,
                        limiter: RateLimiter) -> RunResult:
        """限速/熔断时的统一失败对象（不调用 provider.query()）。"""
        nxt = limiter.next_available_at(provider_name)
        if limiter.in_circuit(provider_name):
            return RunResult(provider_name, ip, ok=False, circuit_open=True,
                             rate_limited=True, next_available_at=nxt,
                             error=f"circuit_open: 连续 429 熔断中，下次可用 {nxt}")
        return RunResult(provider_name, ip, ok=False, rate_limited=True,
                         next_available_at=nxt,
                         error=f"rate_limited: 下次可用 {nxt}")

    def run(self, provider_name: str, ip: str,
            force_refresh: bool = False, use_cache: bool = True) -> RunResult:
        # 1) 允许列表
        if provider_name not in self.allowed:
            return RunResult(provider_name, ip, ok=False,
                             error=f"provider_not_allowed: {provider_name}")

        provider = self._make_provider(provider_name)
        if provider is None:
            return RunResult(provider_name, ip, ok=False,
                             error=f"unknown_provider: {provider_name}")

        # 2) 配置校验（缺 key 优雅失败，不联网）
        if getattr(provider, "requires_api_key", False):
            v = provider.validate_config()
            if not v.ok:
                return RunResult(provider_name, ip, ok=False,
                                 error=f"missing_api_key: {','.join(v.missing)}")

        # 3) 缓存命中（不消耗限额；即便处于限速/熔断也可服务）
        cache = self._get_cache() if use_cache else None
        if cache is not None and not force_refresh:
            entry = cache.get(provider_name, "ip", ip)
            if entry is not None and entry.status == "ok":
                return RunResult(provider_name, ip, ok=True, from_cache=True,
                                 data=entry.normalized or {})

        # 4) 限速 / 熔断（仅在需要回源时检查；force_refresh 也受约束）
        limiter = self._get_limiter()
        if limiter is not None and not limiter.can_call(provider_name):
            return self._blocked_result(provider_name, ip, limiter)

        # 5) 回源
        result = provider.query(ip)

        # 6) 记录限速（按结果分类）
        if limiter is not None:
            err = result.error or ""
            if "429" in err or "rate_limited" in err:
                limiter.record_429(provider_name)
            elif result.error:
                limiter.record_failure(provider_name)
            else:
                limiter.record_success(provider_name)

        # 7) 写缓存（成功写正常 TTL；失败写短 TTL 负缓存）
        if cache is not None:
            if result.error:
                cache.set(provider_name, "ip", ip, normalized={}, raw=None,
                          ttl_seconds=600, status="error", error=result.error)
            else:
                cache.set(provider_name, "ip", ip,
                          normalized=result.data, raw=result.raw,
                          ttl_seconds=_ttl_seconds(provider), status="ok")

        return RunResult(provider_name, ip, ok=not result.error,
                         from_cache=False, data=result.data or {},
                         error=result.error,
                         rate_limited=bool(result.error and "429" in (result.error or "")))


# 模块级便捷函数（使用默认 runner）
_default_runner: Optional[OnlineRunner] = None


def run_provider(provider_name: str, ip: str,
                 force_refresh: bool = False, use_cache: bool = True) -> RunResult:
    global _default_runner
    if _default_runner is None:
        _default_runner = OnlineRunner()
    return _default_runner.run(provider_name, ip,
                               force_refresh=force_refresh, use_cache=use_cache)
