"""
Portable 测试辅助（无需 pytest fixture，兼容 tests/run_tests.py 最小运行器）。
提供环境隔离上下文与模板脚手架。
"""
import os
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import _bootstrap  # noqa: F401  (把 python/ 加入 sys.path)

from utils import paths
from utils import config_loader

ROOT = Path(__file__).resolve().parent.parent

_VARS = (
    "NETWORKINTEL_HOME",
    "NETWORKINTEL_CONFIG",
    "NETWORKINTEL_DATA_MODE",
    "NETWORKINTEL_DATA_DIR",
    "MAXMIND_LICENSE_KEY",
    "IPINFO_TOKEN",
    "IP2LOCATION_API_KEY",
    "ABUSEIPDB_API_KEY",
)


@contextmanager
def isolated_env():
    """备份并清除 Portable 环境变量，重置 config 单例；退出时恢复。"""
    saved = {k: os.environ.get(k) for k in _VARS}
    for k in _VARS:
        os.environ.pop(k, None)
    config_loader.reset_config()
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config_loader.reset_config()


def scaffold_templates(home, env_example=True, sources_example=True):
    """把真实模板复制进临时 home，模拟解压后的安装目录。"""
    home = Path(home)
    (home / "configs").mkdir(parents=True, exist_ok=True)
    if env_example:
        shutil.copyfile(ROOT / ".env.example", home / ".env.example")
    if sources_example:
        shutil.copyfile(ROOT / "configs" / "sources.example.yaml",
                        home / "configs" / "sources.example.yaml")


@contextmanager
def temp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)
