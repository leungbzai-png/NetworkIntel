# -*- coding: utf-8 -*-
"""
v0.3.0 - SQLite 连接策略：busy_timeout / WAL / foreign_keys / 每线程独立连接。
全程使用临时 .db，绝不触碰真实 live/intel.db；零网络、零真实 key。
"""
import os
import sqlite3
import tempfile
import threading

import _bootstrap  # noqa: F401

from utils import schema


def _tmp_db():
    d = tempfile.mkdtemp()
    return os.path.join(d, "policy.db")


def test_busy_timeout_applied_on_read_and_write():
    p = _tmp_db()
    schema.init_db(p)
    for conn in (schema.connect_read(p), schema.connect_write(p)):
        try:
            got = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            assert got == schema.busy_timeout_ms()
            assert got > 0
        finally:
            conn.close()


def test_foreign_keys_on():
    p = _tmp_db()
    schema.init_db(p)
    conn = schema.connect_write(p)
    try:
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


def test_wal_enabled_or_graceful_fallback():
    p = _tmp_db()
    schema.init_db(p)
    conn = schema.connect_read(p)
    try:
        mode = str(conn.execute("PRAGMA journal_mode").fetchone()[0]).lower()
        # 正常应为 wal；若环境不支持则回退到其它模式但绝不抛异常。
        assert mode in {"wal", "delete", "truncate", "persist", "memory", "off"}
    finally:
        conn.close()


def test_write_connection_is_autocommit_for_explicit_transactions():
    p = _tmp_db()
    schema.init_db(p)
    conn = schema.connect_write(p)
    try:
        # isolation_level=None → 可显式 BEGIN IMMEDIATE，不会 "transaction within a transaction"
        assert conn.isolation_level is None
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
    finally:
        conn.close()


def test_busy_timeout_env_override_is_dynamic():
    saved = os.environ.get("NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS")
    os.environ["NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS"] = "1234"
    try:
        p = _tmp_db()
        schema.init_db(p)
        conn = schema.connect_write(p)
        try:
            assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 1234
        finally:
            conn.close()
    finally:
        if saved is None:
            os.environ.pop("NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS", None)
        else:
            os.environ["NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS"] = saved


def test_is_locked_error_classification():
    assert schema.is_locked_error(sqlite3.OperationalError("database is locked"))
    assert schema.is_locked_error(sqlite3.OperationalError("database is busy"))
    assert not schema.is_locked_error(sqlite3.OperationalError("no such table: x"))
    assert not schema.is_locked_error(ValueError("nope"))


def test_each_thread_uses_its_own_connection():
    """每线程各自 connect/close；并发只读不报错，验证连接不跨线程共享。"""
    p = _tmp_db()
    schema.init_db(p)
    errors = []

    def worker():
        try:
            conn = schema.connect_read(p)
            try:
                conn.execute("SELECT COUNT(*) FROM source_meta").fetchone()
            finally:
                conn.close()
        except Exception as e:  # pragma: no cover
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
