"""
NetworkIntel - DataSource 插件基类
=====================================
所有数据源插件必须继承此类并实现以下方法：
  - download()  下载原始数据
  - parse()     解析原始数据
  - load()      写入SQLite数据库
  - snapshot()  归档快照

新增数据源只需：
  1. 在 plugins/ 目录新建 my_source.py
  2. 继承 DataSourceBase
  3. 在 sources.yaml 添加配置
  4. 在 plugin_registry.py 注册名称

无需修改任何核心文件。
"""

import os
import time
import shutil
import hashlib
import requests
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, date
from pathlib import Path
from typing import Optional, Generator, Any
from contextlib import contextmanager

from utils.logger import get_logger
from utils.config_loader import get_config
from utils.redaction import redact_secrets
from utils.schema import (
    connect_write, is_locked_error, lock_retries, lock_backoff_s,
)


class DataSourceBase(ABC):
    """
    数据源插件统一基类
    子类实现 download / parse / load / snapshot 四个方法
    """

    # 子类必须定义
    SOURCE_NAME: str = ""          # 唯一标识，与 sources.yaml 的 key 对应
    SOURCE_DESCRIPTION: str = ""   # 人类可读描述

    def __init__(self):
        self.config = get_config()
        self.source_config = self.config.get_source(self.SOURCE_NAME) or {}
        self.logger = get_logger("networkintel")
        self.cache_dir = os.path.join(self.config.cache_dir, self.SOURCE_NAME)
        self.snapshot_category = self.source_config.get("snapshot_category", "registry")
        Path(self.cache_dir).mkdir(parents=True, exist_ok=True)

    # ── 必须实现的方法 ────────────────────────────────────────

    @abstractmethod
    def download(self) -> str:
        """
        下载数据源文件到 cache_dir
        返回：下载文件的本地路径
        """
        ...

    @abstractmethod
    def parse(self, file_path: str) -> Generator[dict, None, None]:
        """
        解析下载的文件
        Yield：每条记录的 dict（字段名与数据库表列名对应）
        """
        ...

    @abstractmethod
    def load(self, records: Generator[dict, None, None]) -> int:
        """
        将解析后的记录写入SQLite
        返回：写入的记录数
        """
        ...

    # ── 快照（默认实现，子类可覆盖）────────────────────────────

    def snapshot(self, source_file: str) -> Optional[str]:
        """
        将数据文件归档到 snapshots/ 和 gdrive_sync/
        返回：快照文件路径
        """
        today = date.today()
        category = self.snapshot_category

        # 按类别选择子目录格式
        if category == "threats":
            sub = today.strftime("%Y-%m-%d")
        elif category == "bgp":
            sub = today.strftime("%Y-W%W")
        else:  # registry / geoip
            sub = today.strftime("%Y-%m")

        # 如果 download() 返回的是目录（多文件插件），跳过单文件快照
        if os.path.isdir(source_file):
            self.logger.info(f"[{self.SOURCE_NAME}] 目录路径，跳过快照")
            return None

        fname = os.path.basename(source_file)
        snap_name = f"{self.SOURCE_NAME}_{today.strftime('%Y%m%d')}{Path(fname).suffix}"

        for base_dir in [self.config.snapshots_dir, self.config.gdrive_sync_dir]:
            dest_dir = os.path.join(base_dir, category, sub)
            Path(dest_dir).mkdir(parents=True, exist_ok=True)
            dest = os.path.join(dest_dir, snap_name)
            shutil.copy2(source_file, dest)
            self.logger.info(f"[{self.SOURCE_NAME}] 快照已保存: {dest}")

        return os.path.join(
            self.config.snapshots_dir, category, sub, snap_name
        )

    # ── 完整更新流程（通常不需要覆盖）─────────────────────────

    def update(self, progress_callback=None) -> dict:
        """
        执行完整更新：download → parse → load → snapshot → update_meta
        progress_callback(step: str, pct: int) 可选进度回调
        返回：{ success, record_count, error, duration_seconds }
        """
        start = datetime.now()
        result = {"success": False, "record_count": 0, "error": None,
                  "error_type": None}

        def _cb(step, pct):
            if progress_callback:
                progress_callback(step, pct)

        try:
            _cb("下载中...", 0)
            file_path = self.download()
            self.logger.info(f"[{self.SOURCE_NAME}] 下载完成: {file_path}")

            _cb("解析中...", 30)
            records = self.parse(file_path)

            _cb("写入数据库...", 60)
            count = self.load(records)
            self.logger.info(f"[{self.SOURCE_NAME}] 写入 {count} 条记录")

            _cb("归档快照...", 90)
            self.snapshot(file_path)

            duration = (datetime.now() - start).total_seconds()
            result.update({"success": True, "record_count": count,
                           "duration_seconds": duration})

            self._update_meta(status="ok", record_count=count, error=None)
            _cb("完成", 100)

        except Exception as e:
            # 锁冲突单独识别（与网络/解析错误区分），便于排查 database is locked。
            error_type = "db_locked" if is_locked_error(e) else type(e).__name__
            # 脱敏：异常消息可能带含 key 的下载 URL（如 MaxMind license_key）。
            safe_msg = redact_secrets(str(e))
            result["error_type"] = error_type
            result["error"] = safe_msg
            result["duration_seconds"] = (datetime.now() - start).total_seconds()
            import traceback
            safe_tb = redact_secrets(traceback.format_exc())
            if error_type == "db_locked":
                self.logger.error(
                    f"[{self.SOURCE_NAME}] 写库锁冲突（database is locked），"
                    f"busy_timeout/重试耗尽: {safe_msg}\n{safe_tb}")
            else:
                self.logger.error(
                    f"[{self.SOURCE_NAME}] 更新失败: {safe_msg}\n{safe_tb}")
            # 写状态本身也可能撞锁：吞掉其异常，保证 update() 返回结果、不二次崩溃。
            try:
                self._update_meta(status="error", error=safe_msg)
            except Exception as meta_e:
                self.logger.error(
                    f"[{self.SOURCE_NAME}] 写 source_meta 失败: {redact_secrets(str(meta_e))}")

        return result

    # ── 辅助方法 ──────────────────────────────────────────────

    def _download_file(self, url: str, filename: str, chunk_size: int = 65536) -> str:
        """通用文件下载，支持断点续传标头"""
        dest = os.path.join(self.cache_dir, filename)
        self.logger.info(f"[{self.SOURCE_NAME}] 下载: {url}")
        headers = {"User-Agent": "NetworkIntel/1.0 (github.com/local/networkintel)"}
        resp = requests.get(url, headers=headers, stream=True, timeout=120)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
        return dest

    def _begin_immediate(self, db_path: str):
        """
        获取一个已进入 `BEGIN IMMEDIATE`（持有写锁）的 autocommit 写连接。
        锁冲突（database is locked/busy）时按有限次数退避重试；耗尽后抛出原异常。
        成功返回时连接已持有写锁——后续 executemany 不再与其它写者竞争，
        因此可以安全地在事务内消费一次性生成器，无需重放。
        """
        retries = lock_retries()
        backoff = lock_backoff_s()
        last_exc: Optional[BaseException] = None
        for attempt in range(retries + 1):
            conn = connect_write(db_path)
            try:
                conn.execute("BEGIN IMMEDIATE")
                return conn
            except sqlite3.OperationalError as e:
                try:
                    conn.close()
                except Exception:
                    pass
                last_exc = e
                if is_locked_error(e) and attempt < retries:
                    self.logger.warning(
                        f"[{self.SOURCE_NAME}] 写锁繁忙，退避重试 "
                        f"{attempt + 1}/{retries}: {e}")
                    time.sleep(backoff * (attempt + 1))
                    continue
                raise
        # 理论不可达（最后一次要么 return 要么 raise），保底：
        raise last_exc  # pragma: no cover

    def _update_meta(self, status: str, record_count: int = 0,
                     error: Optional[str] = None) -> None:
        """更新 source_meta 表中本数据源的状态（单条 upsert，带锁重试）。"""
        now = datetime.now().isoformat()
        conn = self._begin_immediate(self.config.db_path)
        try:
            conn.execute("""
                INSERT INTO source_meta
                    (source, description, last_updated, status, record_count,
                     error_message, schedule, enabled, snapshot_category, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    last_updated=excluded.last_updated,
                    status=excluded.status,
                    record_count=excluded.record_count,
                    error_message=excluded.error_message,
                    schedule=excluded.schedule,
                    enabled=excluded.enabled,
                    updated_at=excluded.updated_at
            """, (
                self.SOURCE_NAME,
                self.SOURCE_DESCRIPTION,
                now if status == "ok" else None,
                status,
                record_count,
                error,
                self.source_config.get("schedule", ""),
                1 if self.source_config.get("enabled", True) else 0,
                self.snapshot_category,
                now,
            ))
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    @contextmanager
    def _bulk_insert(self, table: str, columns: list,
                     replace_source: bool = False, batch_size: int = 5000):
        """
        原子批量插入上下文管理器（v0.3.0：单连接、单事务）。

        用法：
            with self._bulk_insert('threat_intel', cols, replace_source=True) as insert:
                for rec in records:
                    insert(rec)

        约定：
          * __enter__ 先取写锁（BEGIN IMMEDIATE，带锁重试），再（可选）
            `DELETE FROM <table> WHERE source=SELF`，使「删旧 + 插新」处于
            **同一事务**，中途失败整体 ROLLBACK，杜绝「删了旧的、只写一半」的空窗。
          * 批次内 executemany 累积进事务、**不逐批 commit**，退出时一次性 COMMIT，
            兼顾原子性与批量性能（避免逐行/逐批 commit）。
          * 下载与解析在事务外完成，写锁只在真正落库期间持有。
        """
        conn = self._begin_immediate(self.config.db_path)
        placeholders = ",".join("?" * len(columns))
        sql = f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
        batch: list = []

        def insert(record: dict):
            row = [record.get(c) for c in columns]
            batch.append(row)
            if len(batch) >= batch_size:
                conn.executemany(sql, batch)
                batch.clear()

        try:
            if replace_source:
                conn.execute(f"DELETE FROM {table} WHERE source = ?",
                             (self.SOURCE_NAME,))
            yield insert
            if batch:
                conn.executemany(sql, batch)
            conn.execute("COMMIT")
        except BaseException:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    @property
    def today_str(self) -> str:
        return date.today().isoformat()

    @property
    def is_enabled(self) -> bool:
        return bool(self.source_config.get("enabled", True))
