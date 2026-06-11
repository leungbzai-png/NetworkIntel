"""
数据目录模式测试（portable / custom）。
验证 config_loader 的路径属性随模式正确解析到 data_dir。
兼容 tests/run_tests.py 最小运行器（不使用 pytest fixture）。
"""
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates

from utils import paths
from utils import config_loader


def test_portable_mode_db_under_home():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "portable"
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        cfg = config_loader.get_config()
        assert Path(cfg.db_path) == (home / "live" / "intel.db").resolve()
        assert Path(cfg.cache_dir) == (home / "cache").resolve()
        assert Path(cfg.logs_dir) == (home / "logs").resolve()
        assert Path(cfg.reports_dir) == (home / "reports").resolve()


def test_custom_mode_db_under_data_dir():
    with isolated_env(), temp_dir() as d:
        home = d / "home"; data = d / "data"
        home.mkdir(); data.mkdir()
        os.environ["NETWORKINTEL_HOME"] = str(home)
        os.environ["NETWORKINTEL_DATA_MODE"] = "custom"
        os.environ["NETWORKINTEL_DATA_DIR"] = str(data)
        paths.reset_env_cache()
        scaffold_templates(home)
        config_loader.ensure_initialized()

        cfg = config_loader.get_config()
        assert Path(cfg.db_path) == (data / "live" / "intel.db").resolve()
        assert Path(cfg.cache_dir) == (data / "cache").resolve()
        # configs 仍在 home 下
        assert (home / "configs" / "sources.yaml").exists()
        # 自定义数据目录的运行时子目录已创建
        assert (data / "live").is_dir()
