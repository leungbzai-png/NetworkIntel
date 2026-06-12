"""
v0.2.0 收口 - 空库运行期读表安全（打包 exe 冒烟回归）。
=============================================================
聚焦用户 exe 冒烟暴露的阻断问题：全新 / 空 portable 目录首次运行时，GUI 在构造
统计条 / 威胁库 / 查询页时直接读表，触发 `sqlite3.OperationalError: no such table:
threat_intel`。修复点 = 启动期 ensure_runtime_database 先建好全部基础表（只建表、
不下载、不改 needs_setup）。

本文件验证 READ 路径（非下载路径）：建表后 query_ip / 统计 COUNT(*) 不再 no such
table，且 needs_setup 仍为 True（不得抑制首次初始化向导）。
兼容 tests/run_tests.py 最小运行器（无 pytest fixture）；全程零网络、零真实 key。
"""
import os
import sqlite3
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates

from utils import paths
from utils import config_loader
from utils.schema import get_connection
from datasources import setup_profiles as sp


# 启动后必须存在的 IPv4 基础表（含触发崩溃的 threat_intel）。
BASE_TABLES = {
    "asn_info", "geoip", "cloud_ranges", "peeringdb",
    "rir_delegated", "rpki", "threat_intel", "source_meta",
}


def _table_names(db_path) -> set:
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def _portable_home(home: Path) -> None:
    """把临时目录布置成解压后的 portable home 并完成首次运行初始化。"""
    os.environ["NETWORKINTEL_HOME"] = str(home)
    os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
    paths.reset_env_cache()
    scaffold_templates(home)
    config_loader.ensure_initialized()


# ── 启动期建表：含 threat_intel 在内的全部基础表 ─────────────────

def test_ensure_runtime_database_creates_all_base_tables():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        db_path = sp.ensure_runtime_database()
        assert Path(db_path) == (home / "live" / "intel.db").resolve()
        assert Path(db_path).exists()
        tables = _table_names(db_path)
        assert BASE_TABLES <= tables
        # v6 扩展表也应建好（v6 查询同样安全）
        assert {"threat_intel_v6", "geoip_v6"} <= tables


def test_threat_intel_exists_and_empty_after_init():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        db_path = sp.ensure_runtime_database()
        conn = get_connection(db_path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM threat_intel").fetchone()[0]
        finally:
            conn.close()
        assert n == 0


# ── 关键不变量：建表不得抑制首次初始化向导 ────────────────────

def test_needs_setup_still_true_after_init():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        db_path = sp.ensure_runtime_database()
        assert Path(db_path).exists()
        # init_db 只建出空的 source_meta → 仍判定需要初始化
        assert sp.needs_setup(db_path) is True


# ── 空库读路径：query_ip / 统计 不再 no such table ──────────────

def test_empty_db_query_ip_no_such_table():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        sp.ensure_runtime_database()
        from query.engine import query_ip
        res = query_ip("1.1.1.1")
        # 空库：返回结构化结果而非抛 OperationalError
        assert res.get("ip") == "1.1.1.1"
        assert "error" not in res
        assert res.get("threats") == []
        assert res.get("risk_level") == "clean"


def test_empty_db_dashboard_counts_zero():
    """模拟 DashboardBar / 统计卡片读路径：空库各表 COUNT(*) 应为 0 而非崩溃。"""
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        db_path = sp.ensure_runtime_database()
        conn = get_connection(db_path)
        try:
            for t in ("asn_info", "geoip", "threat_intel", "cloud_ranges", "rpki"):
                assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
        finally:
            conn.close()


# ── custom data_dir：建表落在 data_dir/live 而非 home ─────────────

def test_custom_data_dir_init_targets_data_dir():
    with isolated_env(), temp_dir() as d:
        home = d / "home"; data = d / "data"
        home.mkdir(); data.mkdir()
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "custom"
        os.environ["NETWORKINTEL_DATA_DIR"] = str(data)
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        db_path = sp.ensure_runtime_database()
        assert Path(db_path) == (data / "live" / "intel.db").resolve()
        assert "threat_intel" in _table_names(db_path)


# ── 设置页 key / data_dir 布局可 headless 构造（不报错）─────────

def test_settings_page_headless_layout():
    """
    headless 构造 SettingsPage，验证：
      * 整页被 QScrollArea 包裹（小窗口可滚动，不挤压）；
      * 四个 key 各有一行密码输入框，且有稳定最小高度（不被压成一条线）；
      * data_dir / home 输入存在且有最小高度。
    无 GUI 依赖（PySide6/offscreen 不可用）时跳过，视为通过。绝不输出/断言真实 key。
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PySide6.QtWidgets import QApplication, QScrollArea, QLineEdit
    except Exception:
        return  # 环境无 GUI 依赖：跳过

    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        sp.ensure_runtime_database()
        app = QApplication.instance() or QApplication([])  # noqa: F841
        import importlib
        main_gui = importlib.import_module("main_gui")
        page = main_gui.SettingsPage()
        try:
            assert page.findChild(QScrollArea) is not None
            assert set(page.key_inputs.keys()) >= {
                "MAXMIND_LICENSE_KEY", "IPINFO_TOKEN",
                "IP2LOCATION_API_KEY", "ABUSEIPDB_API_KEY"}
            for inp in page.key_inputs.values():
                # 密码回显，且最小高度足以完整显示（修复前被压成一条线）
                assert inp.echoMode() == QLineEdit.Password
                assert inp.minimumHeight() >= 28
            assert page.data_dir_input.minimumHeight() >= 28
            assert page.home_input.minimumHeight() >= 28
        finally:
            page.deleteLater()
