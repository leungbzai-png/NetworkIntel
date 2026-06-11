"""
NetworkIntel - 在线 Provider 限速（ratelimit）
=============================================
按 provider 维度的简单限速 + 429 冷却。状态持久化到独立 JSON 文件
（默认 cache/online_ratelimit.json），不涉及主库、不影响旧下载 Provider。
时钟可注入（now=callable），便于确定性测试。

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


# 默认限额（保守；可按 provider 覆盖）
DEFAULT_LIMITS = {
    "per_minute": None,   # None = 不限
    "per_hour": None,
    "per_day": None,
    "cooldown_seconds": 60,   # 429 冷却
}


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
        return self._state.setdefault(provider, {"calls": [], "cooldown_until": 0})

    def _prune(self, entry: dict, now: float) -> None:
        # 仅保留最近 1 天的调用时间戳
        entry["calls"] = [t for t in entry.get("calls", []) if now - t < 86400]

    def _count_within(self, entry: dict, now: float, window: float) -> int:
        return sum(1 for t in entry.get("calls", []) if now - t < window)

    # ── 查询 ──────────────────────────────────────────────
    def can_call(self, provider: str) -> bool:
        now = self._now()
        entry = self._entry(provider)
        self._prune(entry, now)
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
        """返回下次可调用的 ISO 时间；当前即可调用返回 None。"""
        now = self._now()
        entry = self._entry(provider)
        self._prune(entry, now)
        candidates = []
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
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(max(now, min(candidates))))

    # ── 记录 ──────────────────────────────────────────────
    def _record_call(self, provider: str) -> None:
        now = self._now()
        entry = self._entry(provider)
        entry.setdefault("calls", []).append(now)
        self._prune(entry, now)
        self._save()

    def record_success(self, provider: str) -> None:
        self._record_call(provider)

    def record_failure(self, provider: str) -> None:
        # 普通失败也计入调用（占用额度）
        self._record_call(provider)

    def record_429(self, provider: str, retry_after: Optional[float] = None) -> None:
        now = self._now()
        entry = self._entry(provider)
        entry.setdefault("calls", []).append(now)
        cooldown = retry_after if retry_after is not None else self._limits(provider)["cooldown_seconds"]
        entry["cooldown_until"] = now + (cooldown or 0)
        self._prune(entry, now)
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
            }
        return {p: self.stats(p) for p in self._state}
