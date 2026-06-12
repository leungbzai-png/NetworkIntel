"""
v0.2.1 hotfix 回归 - 数据源页面列表不再空白。
=============================================================
根因：main_gui.SourcesPage 的「表」创建段历史上被误置于 _open_setup() 作用域，
self.table 从未在 _build() 中创建，refresh() 抛 AttributeError 被吞掉，数据源页面
中间列表整页空白（用户已下载全部 17 源仍看不到任何行）。

本文件双重防护：
  1. 纯函数 compute_source_status_rows 的数据合并 / 容错（无需 Qt）。
  2. headless 构造 SourcesPage，断言 table 存在且行数 == 配置源数量
     （修复前该断言会失败：异常被吞、table 未创建）。

兼容 tests/run_tests.py 最小运行器（无 pytest fixture）；全程零网络、零真实 key。
"""
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates

from utils import paths
from utils import config_loader
from datasources import setup_profiles as sp

import main_gui


def _portable_home(home: Path) -> None:
    os.environ["NETWORKINTEL_HOME"] = str(home)
    os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
    paths.reset_env_cache()
    scaffold_templates(home)
    config_loader.ensure_initialized()


# ── 纯函数：空库仍返回全部配置源（status=never, count=0）──────────

def test_compute_rows_empty_meta_returns_all_sources():
    sources = {
        "ip2asn": {"description": "IP→ASN", "enabled": True},
        "geoip": {"description": "GeoIP", "enabled": True},
        "tor_exits": {"description": "Tor exits", "enabled": False},
    }
    rows = main_gui.compute_source_status_rows(sources, meta={}, live={})
    assert [r["name"] for r in rows] == ["ip2asn", "geoip", "tor_exits"]
    for r in rows:
        assert r["status"] == "never"
        assert r["record_count"] == 0
        assert r["last_updated"] == ""
    assert rows[2]["enabled"] is False


# ── 纯函数：含数据的 meta 能回带记录数 / 状态 / 时间 ──────────────

def test_compute_rows_with_meta_record_counts():
    sources = {"ip2asn": {"description": "IP→ASN", "enabled": True}}
    meta = {"ip2asn": {
        "source": "ip2asn",
        "last_updated": "2026-06-12T03:14:15.999",
        "record_count": 123456,
        "status": "ok",
        "error_message": "",
    }}
    rows = main_gui.compute_source_status_rows(sources, meta=meta, live={})
    assert len(rows) == 1
    r = rows[0]
    assert r["record_count"] == 123456
    assert r["status"] == "ok"
    assert r["last_updated"] == "2026-06-12 03:14:15"


# ── 纯函数：live(调度器)状态覆盖 DB 元数据 ───────────────────────

def test_compute_rows_live_overrides_meta():
    sources = {"firehol": {"description": "FireHOL", "enabled": True}}
    meta = {"firehol": {"status": "ok", "record_count": 10}}
    live = {"firehol": {"status": "running", "message": "downloading"}}
    rows = main_gui.compute_source_status_rows(sources, meta=meta, live=live)
    assert rows[0]["status"] == "running"
    assert rows[0]["message"] == "downloading"


# ── 纯函数：单源合并异常降级为 error，不影响其它源（不丢行）──────

def test_compute_rows_single_source_failure_isolated():
    # 第二个源故意为非 dict（且为真值）→ scfg.get 抛 AttributeError → 该行降级 error，
    # 但前后两个正常源必须照常出现。
    sources = {
        "good_a": {"description": "A", "enabled": True},
        "bad_b": 12345,            # 触发单源异常
        "good_c": {"description": "C", "enabled": True},
    }
    rows = main_gui.compute_source_status_rows(sources, meta={}, live={})
    assert [r["name"] for r in rows] == ["good_a", "bad_b", "good_c"]
    assert rows[1]["status"] == "error"
    assert rows[0]["status"] == "never" and rows[2]["status"] == "never"


# ── 纯函数：None 参数不崩溃 ───────────────────────────────────────

def test_compute_rows_handles_none_args():
    assert main_gui.compute_source_status_rows(None, None, None) == []


# ── 集成：portable 空库下，配置源解析非空（回退 example 模板）────

def test_portable_empty_db_sources_non_empty():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        sp.ensure_runtime_database()
        cfg = config_loader.get_config()
        sources = cfg.get_all_sources()
        assert sources, "portable 初始化后配置源不应为空"
        rows = main_gui.compute_source_status_rows(sources, meta={}, live={})
        assert len(rows) == len(sources)
        assert all(r["status"] == "never" for r in rows)


# ── headless 构造 SourcesPage：table 存在且行数 == 配置源数量 ─────

def test_sources_page_headless_table_populated():
    """
    headless 构造 SourcesPage，验证修复后的核心不变量：
      * self.table 真实创建（修复前从未创建）；
      * 行数 == 配置源数量（修复前 refresh 抛 AttributeError 被吞，行数为 0）。
    无 GUI 依赖时跳过（视为通过）。绝不输出真实 key。
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication, QTableWidget
    except Exception:
        return  # 环境无 GUI 依赖：跳过

    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        sp.ensure_runtime_database()
        cfg = config_loader.get_config()
        n_sources = len(cfg.get_all_sources())

        app = QApplication.instance() or QApplication([])  # noqa: F841
        page = main_gui.SourcesPage()
        try:
            assert hasattr(page, "table"), "SourcesPage.table 未创建（回归）"
            assert isinstance(page.table, QTableWidget)
            assert page.table.rowCount() == n_sources, (
                f"行数 {page.table.rowCount()} != 配置源数 {n_sources}（列表空白回归）")
            assert n_sources > 0
        finally:
            # 停掉 3s 轮询定时器，避免影响后续测试
            try:
                page._timer.stop()
            except Exception:
                pass
            page.deleteLater()
