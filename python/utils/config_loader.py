"""
NetworkIntel - 配置加载器
读取和保存 configs/sources.yaml，支持运行时修改
"""

import os
import re
import yaml
from typing import Any, Optional
from pathlib import Path


# 默认配置文件路径
DEFAULT_CONFIG_PATH = r"E:\NetworkIntel\configs\sources.yaml"

# ${VAR} 占位符匹配
_ENV_PLACEHOLDER = re.compile(r"\$\{(\w+)\}")


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


class Config:
    """配置管理器，支持热更新"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or os.environ.get(
            "NETWORKINTEL_CONFIG", DEFAULT_CONFIG_PATH
        )
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        """从文件加载配置"""
        path = Path(self.config_path)
        if not path.exists():
            raise FileNotFoundError(f"配置文件不存在: {self.config_path}")

        # 先加载 .env（项目根目录 = configs 的上一级），再解析 ${VAR} 占位符
        project_root = path.resolve().parent.parent
        _load_dotenv(project_root / ".env")
        # 兼容当前工作目录下的 .env
        _load_dotenv(Path.cwd() / ".env")

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

    def set_maxmind_key(self, key: str) -> None:
        """
        设置 MaxMind License Key。
        出于安全考虑，真实密钥写入项目根目录的 .env（已被 .gitignore 忽略），
        而不是写入 sources.yaml。yaml 中仅保留 ${MAXMIND_LICENSE_KEY} 占位符。
        """
        # 确保 yaml 中是占位符而非真实值
        self._data.setdefault("sources", {}).setdefault("geoip", {})
        self._data["sources"]["geoip"]["license_key"] = "${MAXMIND_LICENSE_KEY}"
        self.save()

        # 写入 / 更新 .env
        project_root = Path(self.config_path).resolve().parent.parent
        env_path = project_root / ".env"
        self._upsert_env(env_path, "MAXMIND_LICENSE_KEY", key)
        # 立即在当前进程生效
        os.environ["MAXMIND_LICENSE_KEY"] = key

    @staticmethod
    def _upsert_env(env_path: Path, key: str, value: str) -> None:
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
        with open(env_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    @property
    def db_path(self) -> str:
        return self.get_global("db_path", r"E:\NetworkIntel\live\intel.db")

    @property
    def base_dir(self) -> str:
        return self.get_global("base_dir", r"E:\NetworkIntel")

    @property
    def snapshots_dir(self) -> str:
        return self.get_global("snapshots_dir", r"E:\NetworkIntel\snapshots")

    @property
    def gdrive_sync_dir(self) -> str:
        return self.get_global("gdrive_sync_dir", r"E:\NetworkIntel\gdrive_sync")

    @property
    def cache_dir(self) -> str:
        return self.get_global("cache_dir", r"E:\NetworkIntel\cache")

    @property
    def logs_dir(self) -> str:
        return self.get_global("logs_dir", r"E:\NetworkIntel\logs")

    @property
    def theme(self) -> str:
        return self.get_global("theme", "system")

    @property
    def log_level(self) -> str:
        return self.get_global("log_level", "INFO")


# 全局单例
_config: Optional[Config] = None


def get_config(config_path: Optional[str] = None) -> Config:
    """获取全局配置单例"""
    global _config
    if _config is None:
        _config = Config(config_path)
    return _config


def reload_config() -> None:
    """重新加载配置文件"""
    global _config
    if _config:
        _config.load()
