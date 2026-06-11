"""
NetworkIntel - 在线 Provider 结果缓存（cache）
=============================================
独立 SQLite 文件（默认 cache/online_cache.sqlite），**不触碰**主库 intel.db 与现有业务表。
仅缓存归一化结果与原始响应体；**绝不缓存 API token 或请求头**。
所有操作防御式处理：出错时降级（get→None, set→False），不影响主程序。

详见 docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS online_cache (
    provider        TEXT NOT NULL,
    query_type      TEXT NOT NULL,
    query_value     TEXT NOT NULL,
    normalized_json TEXT,
    raw_json        TEXT,
    fetched_at      TEXT NOT NULL,   -- ISO8601（展示用）
    expires_at      REAL,            -- epoch 秒（比较用；NULL=永不过期）
    status          TEXT,            -- ok / error
    error           TEXT,
    PRIMARY KEY (provider, query_type, query_value)
);
"""


def default_cache_path() -> str:
    """ONLINE_CACHE_DB_PATH（可相对项目根），默认 cache/online_cache.sqlite。"""
    root = Path(__file__).resolve().parents[2]   # python/providers/cache.py -> 项目根
    raw = os.environ.get("ONLINE_CACHE_DB_PATH", "cache/online_cache.sqlite")
    p = Path(raw)
    return str(p if p.is_absolute() else (root / p))


def _safe_dumps(obj: Any) -> Optional[str]:
    if obj is None:
        return None
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return None


def _safe_loads(s: Optional[str]) -> Any:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


@dataclass
class CacheEntry:
    provider: str
    query_type: str
    query_value: str
    normalized: Any
    raw: Any
    fetched_at: str
    expires_at: Optional[float]
    status: Optional[str]
    error: Optional[str]

    def is_expired(self, now: Optional[float] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now if now is not None else time.time()) >= self.expires_at


class OnlineCache:
    """在线结果缓存。线程安全性依赖每次操作独立连接。"""

    def __init__(self, db_path: Optional[str] = None, now: Callable[[], float] = time.time):
        self.db_path = db_path or default_cache_path()
        self._now = now
        self.last_error: Optional[str] = None
        self._ensure()

    # ── 内部 ──────────────────────────────────────────────
    def _connect(self) -> Optional[sqlite3.Connection]:
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return None

    def _ensure(self) -> None:
        conn = self._connect()
        if conn is None:
            return
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
        finally:
            conn.close()

    # ── 公开 API ──────────────────────────────────────────
    def get(self, provider: str, query_type: str, query_value: str,
            include_expired: bool = False) -> Optional[CacheEntry]:
        """命中返回 CacheEntry；未找到返回 None。默认过期视为未命中。"""
        conn = self._connect()
        if conn is None:
            return None
        try:
            row = conn.execute(
                "SELECT * FROM online_cache WHERE provider=? AND query_type=? AND query_value=?",
                (provider, query_type, query_value),
            ).fetchone()
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return None
        finally:
            conn.close()
        if not row:
            return None
        entry = CacheEntry(
            provider=row["provider"], query_type=row["query_type"],
            query_value=row["query_value"],
            normalized=_safe_loads(row["normalized_json"]),
            raw=_safe_loads(row["raw_json"]),
            fetched_at=row["fetched_at"], expires_at=row["expires_at"],
            status=row["status"], error=row["error"],
        )
        if entry.is_expired(self._now()) and not include_expired:
            return None
        return entry

    def set(self, provider: str, query_type: str, query_value: str,
            normalized: Any = None, raw: Any = None,
            ttl_seconds: Optional[float] = None,
            status: str = "ok", error: Optional[str] = None) -> bool:
        """写入/更新缓存。返回是否成功。"""
        now = self._now()
        expires_at = (now + ttl_seconds) if ttl_seconds is not None else None
        fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
        conn = self._connect()
        if conn is None:
            return False
        try:
            conn.execute(
                """INSERT INTO online_cache
                   (provider, query_type, query_value, normalized_json, raw_json,
                    fetched_at, expires_at, status, error)
                   VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(provider, query_type, query_value) DO UPDATE SET
                     normalized_json=excluded.normalized_json,
                     raw_json=excluded.raw_json,
                     fetched_at=excluded.fetched_at,
                     expires_at=excluded.expires_at,
                     status=excluded.status,
                     error=excluded.error""",
                (provider, query_type, query_value,
                 _safe_dumps(normalized), _safe_dumps(raw),
                 fetched_at, expires_at, status, error),
            )
            conn.commit()
            return True
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return False
        finally:
            conn.close()

    def purge_expired(self) -> int:
        """删除已过期条目，返回删除数量。"""
        conn = self._connect()
        if conn is None:
            return 0
        try:
            cur = conn.execute(
                "DELETE FROM online_cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (self._now(),),
            )
            conn.commit()
            return cur.rowcount or 0
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return 0
        finally:
            conn.close()

    def stats(self) -> dict:
        """返回 {total, expired, by_provider}。出错返回带 error 的字典。"""
        conn = self._connect()
        if conn is None:
            return {"total": 0, "expired": 0, "by_provider": {}, "error": self.last_error}
        try:
            now = self._now()
            total = conn.execute("SELECT COUNT(*) FROM online_cache").fetchone()[0]
            expired = conn.execute(
                "SELECT COUNT(*) FROM online_cache WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            ).fetchone()[0]
            rows = conn.execute(
                "SELECT provider, COUNT(*) c FROM online_cache GROUP BY provider"
            ).fetchall()
            by_provider = {r["provider"]: r["c"] for r in rows}
            return {"total": total, "expired": expired, "by_provider": by_provider,
                    "db_path": self.db_path}
        except Exception as e:
            self.last_error = f"{type(e).__name__}: {e}"
            return {"total": 0, "expired": 0, "by_provider": {}, "error": self.last_error}
        finally:
            conn.close()
