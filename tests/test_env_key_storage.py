"""
Provider key 存储测试。
验证 key 写入 .env 而非 sources.yaml，状态检测正确，且输出不含真实 key。
兼容 tests/run_tests.py 最小运行器（不使用 pytest fixture）。
"""
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from _portable_helpers import isolated_env, temp_dir, scaffold_templates

from utils import paths
from utils import config_loader

FAKE_KEY = "FAKEKEY_unit_test_value_0123456789"


def _portable_home(home: Path):
    os.environ["NETWORKINTEL_HOME"] = str(home)
    paths.reset_env_cache()
    scaffold_templates(home)
    config_loader.ensure_initialized()


def test_fresh_install_keys_unconfigured():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        cfg = config_loader.get_config()
        status = cfg.get_key_status()
        # 刚从 .env.example 复制，全部为占位符 → 未配置
        for var, ok in status.items():
            assert ok is False, f"{var} 误判为已配置"


def test_set_provider_key_writes_env_not_yaml():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        cfg = config_loader.get_config()
        cfg.set_provider_key("IPINFO_TOKEN", FAKE_KEY)

        env_text = (home / ".env").read_text(encoding="utf-8")
        assert f"IPINFO_TOKEN={FAKE_KEY}" in env_text

        sources_text = (home / "configs" / "sources.yaml").read_text(encoding="utf-8")
        assert FAKE_KEY not in sources_text  # 绝不写入 yaml 明文

        assert cfg.get_key_status()["IPINFO_TOKEN"] is True


def test_set_maxmind_key_keeps_placeholder_in_yaml():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        cfg = config_loader.get_config()
        cfg.set_maxmind_key(FAKE_KEY)

        sources_text = (home / "configs" / "sources.yaml").read_text(encoding="utf-8")
        assert "${MAXMIND_LICENSE_KEY}" in sources_text
        assert FAKE_KEY not in sources_text

        env_text = (home / ".env").read_text(encoding="utf-8")
        assert f"MAXMIND_LICENSE_KEY={FAKE_KEY}" in env_text


def test_key_status_does_not_leak_key():
    with isolated_env(), temp_dir() as home:
        _portable_home(home)
        cfg = config_loader.get_config()
        cfg.set_provider_key("ABUSEIPDB_API_KEY", FAKE_KEY)
        status = cfg.get_key_status()
        # 状态值只能是布尔，绝不返回 key 本身
        for v in status.values():
            assert isinstance(v, bool)
