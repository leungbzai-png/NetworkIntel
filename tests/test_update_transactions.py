# -*- coding: utf-8 -*-
"""
v0.3.0 - 事务原子性与锁重试。
用 isolated_env + 临时 portable home（temp live/intel.db），绝不触碰真实库。
覆盖：成功 commit / 中途异常 rollback 保留旧数据 / replace_source 原子替换 /
busy_timeout 等待后成功 / 锁重试耗尽后抛 locked（有限、不死锁）。
零网络、零真实 key。
"""
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Generator

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates

from utils import paths
from utils import config_loader
from utils import schema
from datasources.base import DataSourceBase


class _FakeSource(DataSourceBase):
    SOURCE_NAME = "test_src"
    SOURCE_DESCRIPTION = "fake source for transaction tests"

    def download(self) -> str:
        return ""

    def parse(self, file_path):
        return iter([])

    def snapshot(self, source_file):
        return None  # 事务测试不归档文件

    def load(self, records: Generator[dict, None, None]) -> int:
        cols = ["network", "network_start_int", "network_end_int",
                "threat_type", "list_name", "severity",
                "source", "snapshot_date"]
        n = 0
        with self._bulk_insert("threat_intel", cols, replace_source=True) as insert:
            for r in records:
                insert(r)
                n += 1
        return n


def _rec(ip):
    return {"network": f"{ip}/32", "network_start_int": 1, "network_end_int": 1,
            "threat_type": "tor", "list_name": "test_src", "severity": "medium",
            "source": "test_src", "snapshot_date": "2026-01-01"}


def _count(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT COUNT(*) FROM threat_intel WHERE source='test_src'"
        ).fetchone()[0]
    finally:
        conn.close()


def _setup_home(home):
    os.environ["NETWORKINTEL_HOME"] = str(home)
    os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
    paths.reset_env_cache()
    scaffold_templates(home)
    config_loader.ensure_initialized()
    from datasources import setup_profiles as sp
    return sp.prepare_database()


def test_atomic_commit_persists():
    with isolated_env(), temp_dir() as home:
        db = _setup_home(home)
        src = _FakeSource()
        assert src.load(iter([_rec("1.1.1.1"), _rec("2.2.2.2"), _rec("3.3.3.3")])) == 3
        assert _count(db) == 3


def test_rollback_on_midway_exception_keeps_old_data():
    with isolated_env(), temp_dir() as home:
        db = _setup_home(home)
        src = _FakeSource()
        src.load(iter([_rec("1.1.1.1"), _rec("2.2.2.2"), _rec("3.3.3.3")]))
        assert _count(db) == 3

        def bad():
            yield _rec("9.9.9.9")
            raise RuntimeError("boom mid-insert")

        try:
            src.load(bad())
            assert False, "应抛出异常"
        except RuntimeError:
            pass
        # 事务整体回滚：旧数据完好（非空、非半份）
        assert _count(db) == 3


def test_replace_source_is_atomic_swap():
    with isolated_env(), temp_dir() as home:
        db = _setup_home(home)
        src = _FakeSource()
        src.load(iter([_rec("1.1.1.1"), _rec("2.2.2.2"), _rec("3.3.3.3")]))
        assert _count(db) == 3
        # 再次 load：删旧插新在同一事务，最终只剩新数据
        assert src.load(iter([_rec("5.5.5.5")])) == 1
        assert _count(db) == 1


def test_busy_timeout_waits_then_succeeds():
    """竞争写锁短暂持有后释放，写者应在 busy_timeout 内等待成功而非立即报错。"""
    with isolated_env(), temp_dir() as home:
        db = _setup_home(home)
        os.environ["NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS"] = "3000"
        os.environ["NETWORKINTEL_SQLITE_LOCK_RETRIES"] = "0"

        holder = schema.connect_write(db)
        holder.execute("BEGIN IMMEDIATE")
        holder.execute("INSERT INTO threat_intel (network, network_start_int, "
                       "network_end_int, threat_type, list_name, source, snapshot_date) "
                       "VALUES ('8.8.8.8/32',1,1,'tor','test_src','test_src','2026-01-01')")

        released = threading.Event()

        def release_soon():
            time.sleep(0.2)
            holder.execute("ROLLBACK")
            holder.close()
            released.set()

        threading.Thread(target=release_soon, daemon=True).start()

        src = _FakeSource()
        t0 = time.monotonic()
        n = src.load(iter([_rec("1.1.1.1")]))  # 应等待锁释放后成功
        elapsed = time.monotonic() - t0
        assert released.is_set()
        assert n == 1
        assert _count(db) == 1
        assert elapsed < 3.0  # 在 busy_timeout 内完成
        os.environ.pop("NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS", None)
        os.environ.pop("NETWORKINTEL_SQLITE_LOCK_RETRIES", None)


def test_lock_retry_exhausts_then_raises_locked_bounded():
    """竞争锁全程持有：写者有限次重试后抛 database is locked，绝不死锁。"""
    with isolated_env(), temp_dir() as home:
        db = _setup_home(home)
        os.environ["NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS"] = "100"
        os.environ["NETWORKINTEL_SQLITE_LOCK_RETRIES"] = "2"
        os.environ["NETWORKINTEL_SQLITE_LOCK_BACKOFF_S"] = "0.02"
        try:
            holder = schema.connect_write(db)
            holder.execute("BEGIN IMMEDIATE")
            holder.execute("INSERT INTO threat_intel (network, network_start_int, "
                           "network_end_int, threat_type, list_name, source, snapshot_date) "
                           "VALUES ('8.8.8.8/32',1,1,'tor','test_src','test_src','2026-01-01')")
            try:
                src = _FakeSource()
                t0 = time.monotonic()
                raised = None
                try:
                    src.load(iter([_rec("1.1.1.1")]))
                except sqlite3.OperationalError as e:
                    raised = e
                elapsed = time.monotonic() - t0
                assert raised is not None, "应抛出 OperationalError"
                assert schema.is_locked_error(raised)
                assert elapsed < 5.0  # 有限重试，不无限等待
            finally:
                holder.execute("ROLLBACK")
                holder.close()
        finally:
            os.environ.pop("NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS", None)
            os.environ.pop("NETWORKINTEL_SQLITE_LOCK_RETRIES", None)
            os.environ.pop("NETWORKINTEL_SQLITE_LOCK_BACKOFF_S", None)


def test_update_flow_classifies_db_locked_and_preserves_data():
    """完整 update() 遇锁：返回 error_type=db_locked，旧数据不被破坏。"""
    with isolated_env(), temp_dir() as home:
        db = _setup_home(home)
        src = _FakeSource()
        src.load(iter([_rec("1.1.1.1"), _rec("2.2.2.2")]))
        assert _count(db) == 2

        # 让 parse 产出新数据，但写库时被竞争锁挡住 → update() 捕获为 db_locked
        os.environ["NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS"] = "100"
        os.environ["NETWORKINTEL_SQLITE_LOCK_RETRIES"] = "1"
        os.environ["NETWORKINTEL_SQLITE_LOCK_BACKOFF_S"] = "0.02"
        try:
            holder = schema.connect_write(db)
            holder.execute("BEGIN IMMEDIATE")
            holder.execute("INSERT INTO threat_intel (network, network_start_int, "
                           "network_end_int, threat_type, list_name, source, snapshot_date) "
                           "VALUES ('7.7.7.7/32',1,1,'tor','test_src','test_src','2026-01-01')")

            class _Locked(_FakeSource):
                def parse(self, file_path):
                    return iter([_rec("9.9.9.9")])

            try:
                res = _Locked().update()
                assert res["success"] is False
                assert res["error_type"] == "db_locked"
            finally:
                holder.execute("ROLLBACK")
                holder.close()
            # 旧的 2 行仍在（写事务从未拿到锁，未删旧数据）
            assert _count(db) == 2
        finally:
            os.environ.pop("NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS", None)
            os.environ.pop("NETWORKINTEL_SQLITE_LOCK_RETRIES", None)
            os.environ.pop("NETWORKINTEL_SQLITE_LOCK_BACKOFF_S", None)
