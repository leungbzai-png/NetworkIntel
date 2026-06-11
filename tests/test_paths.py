"""
Portable 路径系统测试（utils.paths）。
验证 home / data_dir 解析、portable / custom 模式、相对与遗留绝对路径解析。
兼容 tests/run_tests.py 最小运行器（不使用 pytest fixture）。
"""
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir

from utils import paths


def test_home_from_env():
    with isolated_env(), temp_dir() as d:
        os.environ["NETWORKINTEL_HOME"] = str(d)
        paths.reset_env_cache()
        assert paths.get_home_dir() == d.resolve()


def test_portable_data_dir_equals_home():
    with isolated_env(), temp_dir() as d:
        os.environ["NETWORKINTEL_HOME"] = str(d)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        paths.reset_env_cache()
        assert paths.get_data_mode() == "portable"
        assert paths.get_data_dir() == d.resolve()


def test_custom_data_dir():
    with isolated_env(), temp_dir() as d:
        home = d / "home"; data = d / "mydata"
        home.mkdir(); data.mkdir()
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "custom"
        os.environ["NETWORKINTEL_DATA_DIR"] = str(data)
        paths.reset_env_cache()
        assert paths.get_data_mode() == "custom"
        assert paths.get_data_dir() == data.resolve()
        assert paths.get_db_path() == (data / "live" / "intel.db").resolve()


def test_portable_ignores_data_dir():
    with isolated_env(), temp_dir() as d:
        home = d / "home"; data = d / "mydata"
        home.mkdir(); data.mkdir()
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        os.environ["NETWORKINTEL_DATA_DIR"] = str(data)
        paths.reset_env_cache()
        # portable 模式必须忽略 DATA_DIR
        assert paths.get_data_dir() == home.resolve()


def test_db_path_under_data_dir():
    with isolated_env(), temp_dir() as d:
        os.environ["NETWORKINTEL_HOME"] = str(d)
        paths.reset_env_cache()
        assert paths.get_db_path() == (d / "live" / "intel.db").resolve()


def test_resolve_relative_path():
    with temp_dir() as base:
        out = paths.resolve_runtime_path("live/intel.db", base / "default.db", base)
        assert out == (base / "live" / "intel.db").resolve()


def test_resolve_empty_uses_default():
    with temp_dir() as d:
        default = d / "live" / "intel.db"
        assert paths.resolve_runtime_path("", default, d) == default
        assert paths.resolve_runtime_path(None, default, d) == default


def test_resolve_legacy_absolute_nonexistent_falls_back():
    with temp_dir() as d:
        default = d / "live" / "intel.db"
        legacy = r"E:\NetworkIntel\live\intel.db"
        # 遗留绝对路径在本机不存在时，应转换为 portable 默认路径
        if not Path(legacy).exists():
            assert paths.resolve_runtime_path(legacy, default, d) == default


def test_ensure_runtime_dirs():
    with isolated_env(), temp_dir() as d:
        os.environ["NETWORKINTEL_HOME"] = str(d)
        paths.reset_env_cache()
        paths.ensure_runtime_dirs()
        for sub in ("configs", "live", "cache", "logs", "reports",
                    "snapshots", "backups", "gdrive_sync"):
            assert (d / sub).is_dir(), f"缺少目录 {sub}"
