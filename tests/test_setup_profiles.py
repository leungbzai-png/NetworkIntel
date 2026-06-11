"""
v0.2.0 Phase 2 - 首次初始化 / 数据源选择下载 测试（零网络）。
覆盖：预设分组关系、geoip key 门控、选择解析顺序、串行下载编排与失败汇总、
数据库状态检测（缺库/空库/有数据）。
兼容 tests/run_tests.py 最小运行器（不使用 pytest fixture）。
"""
import sqlite3
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import temp_dir

from datasources import setup_profiles as sp
from datasources.plugin_registry import PLUGIN_REGISTRY


# ── 预设分组 ──────────────────────────────────────────────────

def test_profiles_are_nested_and_registered():
    minimal = sp.PROFILE_SOURCES["minimal"]
    recommended = sp.PROFILE_SOURCES["recommended"]
    full = sp.PROFILE_SOURCES["full"]
    assert minimal <= recommended <= full
    # full == 注册表全部 17 源
    assert full == set(PLUGIN_REGISTRY.keys())
    # 所有预设成员都已注册
    for name in recommended:
        assert name in PLUGIN_REGISTRY
    # peeringdb 只在 full，不在 recommended
    assert "peeringdb" in full and "peeringdb" not in recommended


# ── geoip key 门控 ────────────────────────────────────────────

def test_minimal_without_key_skips_geoip():
    res = sp.resolve_selection("minimal", available_keys=set())
    assert res["selected"] == ["ip2asn"]
    skipped = {s["name"] for s in res["skipped"]}
    assert skipped == {"geoip"}
    assert "MAXMIND_LICENSE_KEY" in res["skipped"][0]["reason"]


def test_minimal_with_key_includes_geoip():
    res = sp.resolve_selection("minimal", available_keys={"MAXMIND_LICENSE_KEY"})
    assert res["selected"] == ["geoip", "ip2asn"]
    assert res["skipped"] == []


def test_selected_follows_canonical_order():
    res = sp.resolve_selection("recommended", available_keys={"MAXMIND_LICENSE_KEY"})
    order_index = {n: i for i, n in enumerate(sp.CANONICAL_ORDER)}
    idxs = [order_index[n] for n in res["selected"]]
    assert idxs == sorted(idxs), "selected 必须按注册表规范顺序"
    assert "peeringdb" not in res["selected"]


def test_custom_drops_unregistered_names():
    res = sp.resolve_selection(
        "custom", custom={"ip2asn", "not_a_real_source", "rpki"},
        available_keys=set())
    assert set(res["selected"]) == {"ip2asn", "rpki"}


def test_full_with_key_is_everything():
    res = sp.resolve_selection("full", available_keys={"MAXMIND_LICENSE_KEY"})
    assert set(res["selected"]) == set(PLUGIN_REGISTRY.keys())
    assert res["skipped"] == []


# ── 串行下载编排 ──────────────────────────────────────────────

def test_download_runs_serially_in_order():
    calls = []

    def fake_updater(name, progress_cb):
        calls.append(name)
        progress_cb("下载中...", 0)
        return {"success": True, "record_count": 42, "error": None}

    summary = sp.download_sources(["ip2asn", "rpki", "tor_exits"], updater=fake_updater)
    assert calls == ["ip2asn", "rpki", "tor_exits"], "必须按给定顺序串行执行"
    assert summary["total"] == 3 and summary["ok"] == 3 and summary["failed"] == 0
    assert [r["name"] for r in summary["results"]] == ["ip2asn", "rpki", "tor_exits"]


def test_download_continues_on_failure_and_aggregates():
    def fake_updater(name, progress_cb):
        if name == "rpki":
            return {"success": False, "record_count": 0, "error": "boom"}
        return {"success": True, "record_count": 10, "error": None}

    summary = sp.download_sources(["ip2asn", "rpki", "tor_exits"], updater=fake_updater)
    assert summary["ok"] == 2 and summary["failed"] == 1
    failed = [r for r in summary["results"] if not r["success"]]
    assert len(failed) == 1 and failed[0]["name"] == "rpki" and failed[0]["error"] == "boom"


def test_download_catches_updater_exception():
    def fake_updater(name, progress_cb):
        if name == "rpki":
            raise RuntimeError("kaboom")
        return {"success": True, "record_count": 5, "error": None}

    summary = sp.download_sources(["ip2asn", "rpki"], updater=fake_updater)
    assert summary["ok"] == 1 and summary["failed"] == 1
    bad = [r for r in summary["results"] if r["name"] == "rpki"][0]
    assert bad["success"] is False and "kaboom" in (bad["error"] or "")


def test_download_cancel_before_next_source():
    calls = []
    # 取消标志在执行完第一个源后置位 → 第二个源不应启动
    state = {"done_one": False}

    def fake_updater(name, progress_cb):
        calls.append(name)
        state["done_one"] = True
        return {"success": True, "record_count": 1}

    summary = sp.download_sources(
        ["ip2asn", "rpki", "tor_exits"],
        updater=fake_updater,
        should_cancel=lambda: state["done_one"],
    )
    assert calls == ["ip2asn"], "取消后不应启动后续源"
    assert summary["cancelled"] is True and summary["ok"] == 1


def test_download_emits_progress_events():
    phases = []
    sp.download_sources(
        ["ip2asn"],
        updater=lambda n, cb: (cb("写入数据库...", 60), {"success": True, "record_count": 1})[1],
        on_progress=lambda ev: phases.append(ev["phase"]),
    )
    assert phases[0] == "source_start"
    assert "source_progress" in phases
    assert phases[-1] == "all_done"


# ── 数据库状态检测 ────────────────────────────────────────────

def _make_db(path: Path, *, with_table=True, ok_rows=0):
    conn = sqlite3.connect(str(path))
    try:
        if with_table:
            conn.execute(
                "CREATE TABLE source_meta (source TEXT PRIMARY KEY, status TEXT, "
                "record_count INTEGER)"
            )
            for i in range(ok_rows):
                conn.execute(
                    "INSERT INTO source_meta (source, status, record_count) VALUES (?,?,?)",
                    (f"src{i}", "ok", 1000),
                )
        conn.commit()
    finally:
        conn.close()


def test_prepare_database_creates_writable_schema():
    """空库场景：prepare_database 必须建表，否则首次下载 load 会 no such table。"""
    with temp_dir() as d:
        p = d / "live" / "intel.db"
        # 建表前：直连应没有 source_meta 表
        sp.prepare_database(str(p))
        assert p.exists()
        conn = sqlite3.connect(str(p))
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            assert "source_meta" in tables
            assert "threat_intel" in tables and "geoip" in tables
            # 真实写入（即此前会 no such table 的语句）现在应成功
            conn.execute(
                "INSERT OR REPLACE INTO threat_intel "
                "(network, network_start_int, network_end_int, threat_type, "
                " list_name, source, snapshot_date) VALUES (?,?,?,?,?,?,?)",
                ("1.2.3.0/24", 1, 2, "tor", "x", "x", "2026-01-01"))
            conn.commit()
        finally:
            conn.close()


def test_db_status_missing_file():
    with temp_dir() as d:
        st = sp.db_status(str(d / "nope.db"))
        assert st["exists"] is False and st["needs_setup"] is True


def test_db_status_empty_db_needs_setup():
    with temp_dir() as d:
        p = d / "intel.db"
        _make_db(p, with_table=True, ok_rows=0)
        st = sp.db_status(str(p))
        assert st["exists"] is True and st["ok_sources"] == 0
        assert st["needs_setup"] is True


def test_db_status_no_meta_table_needs_setup():
    with temp_dir() as d:
        p = d / "intel.db"
        _make_db(p, with_table=False)
        st = sp.db_status(str(p))
        assert st["needs_setup"] is True


def test_db_status_populated_ok():
    with temp_dir() as d:
        p = d / "intel.db"
        _make_db(p, with_table=True, ok_rows=2)
        st = sp.db_status(str(p))
        assert st["ok_sources"] == 2 and st["total_records"] == 2000
        assert st["needs_setup"] is False
        assert sp.needs_setup(str(p)) is False
