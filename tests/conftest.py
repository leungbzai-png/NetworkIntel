"""pytest 配置：把 python/ 加入 sys.path，并隔离 Portable 路径环境变量。"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYDIR = os.path.join(ROOT, "python")
if PYDIR not in sys.path:
    sys.path.insert(0, PYDIR)

# 受 Portable 路径系统影响的环境变量；测试间必须隔离，避免相互污染。
_PORTABLE_VARS = (
    "NETWORKINTEL_HOME",
    "NETWORKINTEL_CONFIG",
    "NETWORKINTEL_DATA_MODE",
    "NETWORKINTEL_DATA_DIR",
    "MAXMIND_LICENSE_KEY",
    "IPINFO_TOKEN",
    "IP2LOCATION_API_KEY",
    "ABUSEIPDB_API_KEY",
)


@pytest.fixture(autouse=True)
def _isolate_portable_env():
    """
    每个测试前后：
      - 备份/恢复 Portable 相关环境变量；
      - 重置 config 单例与 .env 加载缓存，避免跨测试状态泄漏。
    """
    saved = {k: os.environ.get(k) for k in _PORTABLE_VARS}

    def _reset():
        try:
            from utils.config_loader import reset_config
            reset_config()
        except Exception:
            try:
                from utils import paths
                paths.reset_env_cache()
            except Exception:
                pass

    _reset()
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    _reset()
