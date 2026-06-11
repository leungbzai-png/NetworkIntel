"""
首次运行初始化测试（config_loader.ensure_initialized）。
验证目录创建、.env 与 sources.yaml 模板生成、缺模板报错。
兼容 tests/run_tests.py 最小运行器（不使用 pytest fixture）。
"""
import os
import shutil
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates, ROOT

from utils import paths
from utils import config_loader


def test_first_run_creates_dirs_and_configs():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        paths.reset_env_cache()
        scaffold_templates(home)

        config_loader.ensure_initialized()

        for sub in ("configs", "live", "cache", "logs", "reports",
                    "snapshots", "backups", "gdrive_sync"):
            assert (home / sub).is_dir(), f"缺少目录 {sub}"
        assert (home / ".env").exists()
        assert (home / "configs" / "sources.yaml").exists()


def test_missing_env_example_creates_fallback():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        paths.reset_env_cache()
        # 只放 sources.example.yaml，不放 .env.example
        scaffold_templates(home, env_example=False)

        config_loader.ensure_initialized()
        env_text = (home / ".env").read_text(encoding="utf-8")
        assert "NETWORKINTEL_DATA_MODE" in env_text
        # 回退模板不得包含真实 key
        assert "your_maxmind_license_key_here" in env_text


def test_missing_sources_example_raises():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        paths.reset_env_cache()
        # 不提供任何 sources.example.yaml
        raised = False
        try:
            config_loader.ensure_initialized()
        except FileNotFoundError:
            raised = True
        assert raised, "缺少 sources.example.yaml 时应抛出 FileNotFoundError"


def test_init_is_idempotent():
    with isolated_env(), temp_dir() as home:
        os.environ["NETWORKINTEL_HOME"] = str(home)
        paths.reset_env_cache()
        scaffold_templates(home)

        config_loader.ensure_initialized()
        sources = home / "configs" / "sources.yaml"
        sources.write_text(sources.read_text(encoding="utf-8") + "\n# marker\n",
                           encoding="utf-8")
        config_loader.ensure_initialized()
        assert "# marker" in sources.read_text(encoding="utf-8")
