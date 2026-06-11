"""
NetworkIntel - 在线 Provider 限速（ratelimit）
=============================================
按 provider 维度的滑动窗口限速 + 429 冷却 + 连续 429 熔断（circuit breaker）。
状态持久化到独立 JSON 文件（默认 cache/online_ratelimit.json），不涉及主库、
不影响旧下载 Provider。时钟可注入（now=callable），便于确定性测试。

支持的 per-provider 配置键：
  per_minute / per_hour / per_day  ── 滑动窗口额度（None=不限）
  cooldown_seconds                 ── 单次 429 后的冷却
  max_consecutive_429              ── 连续 429 达到该阈值进入熔断
  circuit_breaker_seconds          ── 熔断持续时长

注意：RateLimiter 本身不内置任何 provider 的具体额度，保持纯配置驱动；
默认 per-provider 额度见 DEFAULT_PROVIDER_LIMITS，由 build_default_limiter()
（runner / smoke 脚本）注入。这样裸 RateLimiter() 仍是「无额度」语义，
不会破坏既有测试。

详见 docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Optional


def default_store_path() -> str:
    root = Path(__file__).resolve().parents[2]
    raw = os.environ.get("ONLINE_RATELIMIT_PATH", "cache/online_ratelimit.json")
    p = Path(raw)
    return str(p if p.is_absolute() else (root / p))


# 默认限额（保守；可按 provider 覆盖）。
# per_* 默认不限；熔断阈值/时长全局生效（单次 429 不触发熔断，需连续达阈值）。
DEFAULT_LIMITS = {
    "per_minute": None,            # None = 不限
    "per_hour": None,
    "per_day": None,
    "cooldown_seconds": 60,        # 单次 429 冷却
    "max_consecutive_429": 3,      # 连续 429 达到该值进入熔断
    "circuit_breaker_seconds": 3600,  # 熔断持续时间
}


# 各在线 provider 的建议默认额度（保守，保护免费额度）。
# 仅由 build_default_limiter() 注入，不写入 RateLimiter 内置默认。
DEFAULT_PROVIDER_LIMITS = {
    "bgpview":     {"per_minute": 30, "per_hour": 1000, "per_day": None},
    "ipinfo":      {"per_minute": 30, "per_hour": 500,  "per_day": None},
    "ip2location": {"per_minute": 30, "per_hour": 500,  "per_day": None},
    "abuseipdb":   {"per_minute": 10, "per_hour": 100,  "per_day": 900},
    "threatfox":   {"per_minute": 30, "per_hour": 500,  "per_day": None},
}


def _env_int(name: str, default: Optional[int]) -> Optional[int]:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def build_default_limiter(store_path: Optional[str] = None,
                          now: Callable[[], float] = time.time) -> "RateLimiter":
    """构造带 per-provider 默认额度 + 环境覆盖的 RateLimiter（runner/smoke 共用）。"""
    default_limits = {
        "max_consecutive_429": _env_int("ONLINE_MAX_CONSECUTIVE_429",
                                        DEFAULT_LIMITS["max_consecutive_429"]),
        "circuit_breaker_seconds": _env_int("ONLINE_CIRCUIT_BREAKER_SECONDS",
                                            DEFAULT_LIMITS["circuit_breaker_seconds"]),
    }
    provider_limits = {k: dict(v) for k, v in DEFAULT_PROVIDER_LIMITS.items()}
    # AbuseIPDB 额度允许 .env 覆盖（保护免费每日额度）
    ab = provider_limits.get("abuseipdb", {})
    ab["per_minute"] = _env_int("ABUSEIPDB_RATE_PER_MINUTE", ab.get("per_minute"))
    ab["per_hour"] = _env_int("ABUSEIPDB_RATE_PER_HOUR", ab.get("per_hour"))
    ab["per_day"] = _env_int("ABUSEIPDB_RATE_PER_DAY", ab.get("per_day"))
    provider_limits["abuseipdb"] = ab
    return RateLimiter(store_path=store_path, now=now,
                       default_limits=default_limits,
                       limits_by_provider=provider_limits)


class RateLimiter:
    def __init__(self, store_path: Optional[str] = None,
                 now: Callable[[], float] = time.time,
                 default_limits: Optional[dict] = None,
                 limits_by_provider: Optional[dict] = None):
        self.store_path = store_path or default_store_path()
        self._now = now
        self.default_limits = {**DEFAULT_LIMITS, **(default_limits or {})}
        self.limits_by_provider = limits_by_provider or {}
        self.last_error: Optional[str] = None
        self._state = self._load()

    # ── 持久化 ────────────────────────────────────────────
    def _load(self) -> dict:
        try:
            with open(self.store_path, "r", encoding="utf-8") as f:
                return json.load(f) or {}
        except Exception:
            return {}

    def _save(self) -> None:
        try:
            Path(self.store_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self.store_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f)
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"

    def _limits(self, provider: str) -> dict:
        return {**self.default_limits, **self.limits_by_provider.get(provider, {})}

    def _entry(self, provider: str) -> dict:
        return self._state.setdefault(
            provider,
            {"calls": [], "cooldown_until": 0, "circuit_until": 0, "consecutive_429": 0},
        )

    def _prune(self, entry: dict, now: float) -> None:
        # 仅保留最近 1 天的调用时间戳
        entry["calls"] = [t for t in entry.get("calls", []) if now - t < 86400]

    def _count_within(self, entry: dict, now: float, window: float) -> int:
        return sum(1 for t in entry.get("calls", []) if now - t < window)

    # ── 查询 ──────────────────────────────────────────────
    def in_circuit(self, provider: str) -> bool:
        """是否处于熔断（连续 429 触发）期间。"""
        now = self._now()
        return now < self._entry(provider).get("circuit_until", 0)

    def can_call(self, provider: str) -> bool:
        now = self._now()
        entry = self._entry(provider)
        self._prune(entry, now)
        if now < entry.get("circuit_until", 0):
            return False
        if now < entry.get("cooldown_until", 0):
            return False
        lim = self._limits(provider)
        if lim["per_minute"] is not None and self._count_within(entry, now, 60) >= lim["per_minute"]:
            return False
        if lim["per_hour"] is not None and self._count_within(entry, now, 3600) >= lim["per_hour"]:
            return False
        if lim["per_day"] is not None and self._count_within(entry, now, 86400) >= lim["per_day"]:
            return False
        return True

    def next_available_at(self, provider: str) -> Optional[str]:
        """返回下次可调用的 ISO 时间；当前即可调用返回 None。

        取所有「当前被违反的约束」的恢复时刻的最大值 —— 因为 can_call 需要
        全部约束解除才会变 True（如熔断 + 冷却同时存在，应等到熔断结束）。
        """
        now = self._now()
        entry = self._entry(provider)
        self._prune(entry, now)
        candidates = []
        ci = entry.get("circuit_until", 0)
        if now < ci:
            candidates.append(ci)
        cd = entry.get("cooldown_until", 0)
        if now < cd:
            candidates.append(cd)
        lim = self._limits(provider)
        for window, key in ((60, "per_minute"), (3600, "per_hour"), (86400, "per_day")):
            if lim[key] is not None and self._count_within(entry, now, window) >= lim[key]:
                calls = sorted(t for t in entry["calls"] if now - t < window)
                if calls:
                    candidates.append(calls[0] + window)
        if not candidates:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(max(now, max(candidates))))

    # ── 记录 ──────────────────────────────────────────────
    def _record_call(self, provider: str) -> None:
        now = self._now()
        entry = self._entry(provider)
        entry.setdefault("calls", []).append(now)
        self._prune(entry, now)
        self._save()

    def record_success(self, provider: str) -> None:
        # 成功回源清零连续 429 计数（熔断/冷却到期后自然恢复）
        entry = self._entry(provider)
        entry["consecutive_429"] = 0
        self._record_call(provider)

    def record_failure(self, provider: str) -> None:
        # 普通失败也计入调用（占用额度），但不像 429 那样累计熔断
        self._record_call(provider)

    def record_429(self, provider: str, retry_after: Optional[float] = None) -> None:
        now = self._now()
        entry = self._entry(provider)
        entry.setdefault("calls", []).append(now)
        lim = self._limits(provider)
        cooldown = retry_after if retry_after is not None else lim["cooldown_seconds"]
        entry["cooldown_until"] = now + (cooldown or 0)
        # 累计连续 429；达阈值进入熔断
        entry["consecutive_429"] = int(entry.get("consecutive_429", 0)) + 1
        threshold = lim.get("max_consecutive_429")
        cb = lim.get("circuit_breaker_seconds") or 0
        if threshold and entry["consecutive_429"] >= threshold and cb:
            entry["circuit_until"] = now + cb
        self._prune(entry, now)
        self._save()

    def reset(self, provider: str) -> None:
        """清空某 provider 的限速/熔断状态（仅本地，不联网）。"""
        self._state.pop(provider, None)
        self._save()

    def stats(self, provider: Optional[str] = None) -> dict:
        now = self._now()
        if provider:
            e = self._entry(provider)
            self._prune(e, now)
            return {
                "provider": provider,
                "calls_last_minute": self._count_within(e, now, 60),
                "calls_last_hour": self._count_within(e, now, 3600),
                "calls_last_day": self._count_within(e, now, 86400),
                "cooldown_until": e.get("cooldown_until", 0),
                "in_cooldown": now < e.get("cooldown_until", 0),
                "circuit_until": e.get("circuit_until", 0),
                "in_circuit": now < e.get("circuit_until", 0),
                "consecutive_429": int(e.get("consecutive_429", 0)),
                "next_available_at": self.next_available_at(provider),
            }
        return {p: self.stats(p) for p in self._state}
