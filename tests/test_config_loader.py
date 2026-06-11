"""
配置加载测试：
  - 示例配置不含真实 key（不泄露）。
  - ${VAR} 占位符解析正确。
  - .env 加载器不覆盖已有环境变量。
"""
import os
import re
import sys
import tempfile

import _bootstrap  # noqa: F401  (把 python/ 加入 sys.path)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_example_yaml_has_no_real_key():
    """sources.example.yaml 只能含占位符，不得出现真实长 token。"""
    path = os.path.join(ROOT, "configs", "sources.example.yaml")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    # geoip license_key 必须是占位符
    assert "license_key: ${MAXMIND_LICENSE_KEY}" in text
    # 任何 key 字段后不得出现真实密钥（必须是 ${VAR} 占位符）
    # 用 ^\s* 锚定，避免误匹配 requires_api_key 等子串
    for m in re.finditer(r"(?m)^\s*(license_key|api_key|token):\s*([^\s#]+)", text):
        val = m.group(2)
        assert val.startswith("${"), f"plaintext secret suspected at {m.group(1)}"
        assert not re.fullmatch(r"[A-Za-z0-9_]{30,}", val)


def test_resolve_env_placeholder_substitutes():
    from utils.config_loader import _resolve_env_placeholders
    os.environ["NI_TEST_VAR"] = "hello-123"
    try:
        assert _resolve_env_placeholders("${NI_TEST_VAR}") == "hello-123"
        assert _resolve_env_placeholders({"k": "${NI_TEST_VAR}"}) == {"k": "hello-123"}
        assert _resolve_env_placeholders(["${NI_TEST_VAR}", 5]) == ["hello-123", 5]
    finally:
        os.environ.pop("NI_TEST_VAR", None)


def test_resolve_missing_var_returns_empty():
    from utils.config_loader import _resolve_env_placeholders
    os.environ.pop("NI_UNSET_XYZ_987", None)
    assert _resolve_env_placeholders("${NI_UNSET_XYZ_987}") == ""


def test_dotenv_loader_no_override():
    from utils.config_loader import _load_dotenv
    from pathlib import Path
    os.environ["NI_PREEXISTING"] = "keep"
    with tempfile.TemporaryDirectory() as d:
        env = Path(d) / ".env"
        env.write_text("NI_PREEXISTING=changed\nNI_FROM_DOTENV=fromfile\n", encoding="utf-8")
        _load_dotenv(env)
    try:
        assert os.environ["NI_PREEXISTING"] == "keep"      # 不覆盖已有
        assert os.environ["NI_FROM_DOTENV"] == "fromfile"  # 新增生效
    finally:
        os.environ.pop("NI_PREEXISTING", None)
        os.environ.pop("NI_FROM_DOTENV", None)


def test_is_placeholder_detection():
    from providers.types import is_placeholder
    assert is_placeholder("")
    assert is_placeholder("${MAXMIND_LICENSE_KEY}")
    assert is_placeholder("YOUR_MAXMIND_LICENSE_KEY_HERE")
    assert not is_placeholder("realkey1234567890")
