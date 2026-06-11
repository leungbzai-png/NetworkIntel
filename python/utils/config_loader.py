"""
NetworkIntel - 配置加载器
读取和保存 configs/sources.yaml，支持运行时修改。

路径解析全部委托给 utils.paths（Portable 路径系统），不再依赖固定的
E:\\NetworkIntel。sources.yaml 中的 global.* 路径会按 portable 规则解析：
相对路径相对 data_dir，遗留绝对路径转换为 portable 友好路径。
"""

import os
import re
import shutil
import yaml
from typing import Any, Optional
from pathlib import Path

from utils import paths


# ${VAR} 占位符匹配
_ENV_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")

# 可由 GUI 设置页管理的在线/离线 Provider key（全部写入 .env，绝不写入 yaml）
PROVIDER_KEYS = (
    "MAXMIND_LICENSE_KEY",
    "IPINFO_TOKEN",
    "IP2LOCATION_API_KEY",
    "ABUSEIPDB_API_KEY",
)

# 默认 .env 模板（仅在缺少 .env.example 时使用，绝不含真实 key）
_FALLBACK_ENV_TEMPLATE = """# NetworkIntel - 环境变量（本文件被 .gitignore 忽略，绝不提交）
# Portable 运行时变量
# NETWORKINTEL_HOME=
# NETWORKINTEL_CONFIG=
NETWORKINTEL_DATA_MODE=portable
# NETWORKINTEL_DATA_DIR=

# Provider key（仅在需要时填写真实值）
MAXMIND_LICENSE_KEY=your_maxmind_license_key_here
IPINFO_TOKEN=your_ipinfo_token_here
IP2LOCATION_API_KEY=your_ip2location_api_key_here
ABUSEIPDB_API_KEY=your_abuseipdb_api_key_here
"""


def _load_dotenv(env_path: Path) -> None:
    """
    极简 .env 加载器（零依赖）。
    将 KEY=VALUE 写入 os.environ，不覆盖已存在的环境变量。
    支持 # 注释与空行；不做引号转义之外的复杂解析。
    """
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        # .env 读取失败不应阻断程序启动
        pass


def _resolve_env_placeholders(obj: Any) -> Any:
    """递归地把配置中的 ${VAR} 替换为环境变量值（缺失则替换为空字符串）。"""
    if isinstance(obj, dict):
        return {k: _resolve_env_placeholders(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env_placeholders(v) for v in obj]
    if isinstance(obj, str):
        return _ENV_PLACEHOLDER.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    return obj


def ensure_initialized() -> None:
    """
    首次运行初始化（幂等）：
      1. 创建 configs/live/cache/logs/reports/snapshots/backups/gdrive_sync 目录。
      2. 若 .env 不存在：从 .env.example 复制；缺模板则写入内置模板。
      3. 若 configs/sources.yaml 不存在：从 sources.example.yaml 复制；缺模板则报错。
    初始化日志/输出绝不包含任何 key。
    """
    paths.ensure_runtime_dirs()

    env_path = paths.get_env_path()
    if not env_path.exists():
        example = paths.get_env_example_path()
        try:
            if example.exists():
                shutil.copyfile(example, env_path)
            else:
                env_path.write_text(_FALLBACK_ENV_TEMPLATE, encoding="utf-8")
        except Exception:
            # 创建 .env 失败不应阻断启动（可能是只读目录）
            pass

    sources_path = paths.get_sources_path()
    if not sources_path.exists():
        example = paths.get_sources_example_path()
        if not example.exists():
            raise FileNotFoundError(
                f"缺少配置模板：{example}。无法初始化 {sources_path}，"
                f"请确认安装包包含 configs/sources.example.yaml。"
            )
        sources_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(example, sources_path)


def upsert_env(env_path: Path, key: str, value: str) -> None:
    """在 .env 中新增或更新 KEY=VALUE，保留其它行。"""
    lines = []
    found = False
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    env_path.parent.mkdir(parents=True, exist_ok=True)
    with open(env_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


class Config:
    """配置管理器，支持热更新"""

    def __init__(self, config_path: Optional[str] = None):
        # 路径解析委托给 paths 模块（不在 import 时求值）
        self.config_path = config_path or str(paths.get_sources_path())
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        """从文件加载配置"""
        # 先加载 home/.env（含 Portable 变量与 key），再加载 cwd/.env 兼容旧习惯
        paths.reset_env_cache()
        paths._ensure_env_loaded()
        _load_dotenv(Path.cwd() / ".env")

        path = Path(self.config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        # self._data 保存「原始」配置（保留 ${VAR} 占位符），确保 save() 不会把
        # 解析后的真实密钥写回 yaml。${VAR} 仅在读取访问器中解析。
        with open(path, "r", encoding="utf-8") as f:
            self._data = yaml.safe_load(f) or {}

    def save(self) -> None:
        """保存配置到文件"""
        path = Path(self.config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(self._data, f, allow_unicode=True, default_flow_style=False,
                      sort_keys=False)

    def get_global(self, key: str, default: Any = None) -> Any:
        return _resolve_env_placeholders(
            self._data.get("global", {}).get(key, default)
        )

    def get_source(self, source_name: str) -> Optional[dict]:
        src = self._data.get("sources", {}).get(source_name)
        return _resolve_env_placeholders(src) if src is not None else None

    def get_all_sources(self) -> dict:
        return _resolve_env_placeholders(self._data.get("sources", {}))

    def set_source_schedule(self, source_name: str, schedule: str) -> None:
        """修改数据源调度频率并保存"""
        if "sources" not in self._data:
            self._data["sources"] = {}
        if source_name not in self._data["sources"]:
            raise KeyError(f"数据源不存在: {source_name}")
        self._data["sources"][source_name]["schedule"] = schedule
        self.save()

    def set_source_enabled(self, source_name: str, enabled: bool) -> None:
        """启用/禁用数据源"""
        if source_name not in self._data.get("sources", {}):
            raise KeyError(f"数据源不存在: {source_name}")
        self._data["sources"][source_name]["enabled"] = enabled
        self.save()

    def set_theme(self, theme: str) -> None:
        """修改主题设置"""
        if "global" not in self._data:
            self._data["global"] = {}
        self._data["global"]["theme"] = theme
        self.save()

    # ── Provider key 管理（写入 .env，不写入 yaml）────────────────

    def set_provider_key(self, env_var: str, key: str) -> None:
        """
        保存任意 Provider key 到 .env。
        真实密钥仅写入 home/.env（已被 .gitignore 忽略），yaml 中不存明文。
        """
        env_path = paths.get_env_path()
        upsert_env(env_path, env_var, key)
        # 立即在当前进程生效
        os.environ[env_var] = key

    def set_maxmind_key(self, key: str) -> None:
        """
        设置 MaxMind License Key。
        yaml 中仅保留 ${MAXMIND_LICENSE_KEY} 占位符，真实值写入 .env。
        """
        # 确保 yaml 中是占位符而非真实值
        self._data.setdefault("sources", {}).setdefault("geoip", {})
        self._data["sources"]["geoip"]["license_key"] = "${MAXMIND_LICENSE_KEY}"
        self.save()
        self.set_provider_key("MAXMIND_LICENSE_KEY", key)

    @staticmethod
    def get_key_status() -> dict:
        """
        返回各 Provider key 的配置状态（True=已配置）。
        占位符 / 空值 视为未配置。绝不返回 key 本身。
        """
        from providers.types import is_placeholder
        return {
            var: not is_placeholder(os.environ.get(var, ""))
            for var in PROVIDER_KEYS
        }

    # 兼容旧调用名
    @staticmethod
    def _upsert_env(env_path: Path, key: str, value: str) -> None:
        upsert_env(env_path, key, value)

    # ── Portable 路径属性（全部经 paths 模块解析）─────────────────

    @property
    def db_path(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("db_path"), paths.get_db_path(), paths.get_data_dir()))

    @property
    def base_dir(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("base_dir"), paths.get_data_dir(), paths.get_data_dir()))

    @property
    def snapshots_dir(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("snapshots_dir"), paths.get_snapshots_dir(),
            paths.get_data_dir()))

    @property
    def gdrive_sync_dir(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("gdrive_sync_dir"), paths.get_gdrive_sync_dir(),
            paths.get_data_dir()))

    @property
    def cache_dir(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("cache_dir"), paths.get_cache_dir(), paths.get_data_dir()))

    @property
    def logs_dir(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("logs_dir"), paths.get_logs_dir(), paths.get_data_dir()))

    @property
    def reports_dir(self) -> str:
        return str(paths.resolve_runtime_path(
            self.get_global("reports_dir"), paths.get_reports_dir(),
            paths.get_data_dir()))

    @property
    def theme(self) -> str:
        return self.get_global("theme", "system")

    @property
    def log_level(self) -> str:
        return self.get_global("log_level", "INFO")


# 全局单例
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """获取全局配置单例（首次调用时执行首次运行初始化）。"""
    global _config
    if _config is None:
        ensure_initialized()
        _config = Config(config_path)
    return _config


def reset_config() -> None:
    """测试辅助：清空单例，使下次 get_config 重新解析路径。"""
    global _config
    _config = None
    paths.reset_env_cache()


def reload_config() -> None:
    """重新加载配置文件"""
    global _config
    if _config:
        _config.load()
