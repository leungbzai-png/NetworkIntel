"""
v0.2.0 收口 - 空库首次初始化端到端（建表 → 串行下载落库，无 no such table）。
聚焦 c3f3f66 修复点：prepare_database 必须在任何下载落库前建好全部表，
并且 portable / custom 两种数据目录都解析到正确的 db_path。
兼容 tests/run_tests.py 最小运行器（不使用 pytest fixture）；全程零网络、零真实 key。
"""
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates

from utils import paths
from utils import config_loader
from utils.schema import get_connection
from datasources import setup_profiles as sp


def _table_names(db_path: Path) -> set:
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _writing_updater(name, progress_cb):
    """
    模拟真实插件落库：向修复前会 `no such table` 的表写入一行。
    使用 get_config().db_path —— 即 prepare_database 刚建好的同一个库。
    """
    progress_cb("写入数据库...", 50)
    conn = get_connection(get_config_db_path())
    try:
        if name == "ip2asn":
            conn.execute(
                "INSERT INTO asn_info (asn, network_start_int, network_end_int, "
                "source, snapshot_date) VALUES (?,?,?,?,?)",
                (64500, 1, 2, "ip2asn", "2026-01-01"))
        else:
            conn.execute(
                "INSERT INTO threat_intel (network, network_start_int, "
                "network_end_int, threat_type, list_name, source, snapshot_date) "
                "VALUES (?,?,?,?,?,?,?)",
                ("1.2.3.0/24", 1, 2, "tor", name, name, "2026-01-01"))
        conn.commit()
    finally:
        conn.close()
    return {"success": True, "record_count": 1, "error": None}


def get_config_db_path() -> str:
    return config_loader.get_config().db_path


# ── prepare_database 解析到正确数据目录 ───────────────────────

def test_prepare_database_portable_uses_home_live():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        # 无参 prepare_database 应解析到 home/live/intel.db
        db_path = sp.prepare_database()
        assert Path(db_path) == (home / "live" / "intel.db").resolve()
        assert Path(db_path).exists()
        tables = _table_names(Path(db_path))
        assert {"source_meta", "asn_info", "threat_intel", "geoip",
                "cloud_ranges", "rpki", "rir_delegated"} <= tables


def test_prepare_database_custom_uses_data_dir():
    with isolated_env(), temp_dir() as d:
        home = d / "home"; data = d / "data"
        home.mkdir(); data.mkdir()
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "custom"
        os.environ["NETWORKINTEL_DATA_DIR"] = str(data)
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        db_path = sp.prepare_database()
        # custom 模式：建表必须发生在 data_dir 下，而非 home
        assert Path(db_path) == (data / "live" / "intel.db").resolve()
        assert Path(db_path).exists()
        assert "threat_intel" in _table_names(Path(db_path))


# ── 空库首次初始化端到端：不再 no such table ──────────────────

def test_empty_portable_first_run_download_no_such_table():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        db_path = get_config_db_path()
        # 初始：库文件不存在 → 必须判定需要初始化
        assert not Path(db_path).exists()
        assert sp.needs_setup(db_path) is True

        # 修复路径：先建表，再串行下载落库（写入会触发原 no such table 的表）
        sp.prepare_database()
        summary = sp.download_sources(
            ["ip2asn", "tor_exits", "spamhaus_drop"],
            updater=_writing_updater,
        )
        assert summary["total"] == 3 and summary["ok"] == 3 and summary["failed"] == 0
        # 确认数据确实落库（没有任何 OperationalError 被吞掉）
        conn = get_connection(db_path)
        try:
            asn = conn.execute("SELECT COUNT(*) FROM asn_info").fetchone()[0]
            thr = conn.execute("SELECT COUNT(*) FROM threat_intel").fetchone()[0]
        finally:
            conn.close()
        assert asn == 1 and thr == 2


def test_download_without_prepare_would_fail_then_prepare_fixes():
    """
    反证修复必要性：未建表直接写库会 OperationalError(no such table)，
    download_sources 会把它记为失败（不崩溃）；prepare_database 后重试全成功。
    """
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        # 未 prepare_database：只建空文件、无表 → 写入应失败并被汇总为 failed
        from utils.schema import get_connection as _gc
        db_path = get_config_db_path()
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        _gc(db_path).close()  # 仅创建空库文件，不建表
        bad = sp.download_sources(["tor_exits"], updater=_writing_updater)
        assert bad["failed"] == 1
        assert "no such table" in (bad["results"][0]["error"] or "").lower()

        # 现在按修复路径建表后重试 → 成功
        sp.prepare_database()
        good = sp.download_sources(["tor_exits"], updater=_writing_updater)
        assert good["ok"] == 1 and good["failed"] == 0


# ── 最小模式选择 + 串行执行（无真实下载、无 key 泄露）─────────

def test_minimal_profile_serial_execution_order():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        # 提供 MaxMind key（占位 env 名集合，绝不含真实值）→ minimal = geoip + ip2asn
        sel = sp.resolve_selection("minimal", available_keys={"MAXMIND_LICENSE_KEY"})
        assert sel["selected"] == ["geoip", "ip2asn"]

        calls = []

        def fake(name, cb):
            calls.append(name)
            cb("...", 0)
            return {"success": True, "record_count": 1}

        sp.prepare_database()
        summary = sp.download_sources(sel["selected"], updater=fake)
        # 串行、按规范顺序逐个执行
        assert calls == ["geoip", "ip2asn"]
        assert summary["ok"] == 2 and summary["cancelled"] is False
