# -*- coding: utf-8 -*-
"""
NetworkIntel - 统一 Portable 路径系统
=====================================
让 NetworkIntel 不再依赖固定的 E:\\NetworkIntel，可以从任意目录运行。

路径解析优先级（home 目录）：
  1. NETWORKINTEL_HOME 环境变量
  2. 打包 exe 所在目录（sys.frozen）
  3. 源码运行时的项目根目录（python/utils/paths.py 的上三级）
  4. 当前工作目录（fallback）

支持的环境变量：
  - NETWORKINTEL_HOME       程序运行根目录
  - NETWORKINTEL_CONFIG     sources.yaml 完整路径（覆盖默认 configs/sources.yaml）
  - NETWORKINTEL_DATA_MODE  portable | custom（默认 portable）
  - NETWORKINTEL_DATA_DIR   custom 模式下的数据目录

模式：
  - portable（默认）：data_dir = home，所有运行时目录都在 home 下。
  - custom：data_dir = NETWORKINTEL_DATA_DIR，运行时数据目录放在 data_dir 下；
            configs/ 与 .env 仍放在 home 下。

注意：本模块不在 import 时解析任何路径常量——所有解析都在函数内部完成，
以便测试可以在 import 之后再设置 NETWORKINTEL_HOME 等环境变量。
"""

import os
import sys
from pathlib import Path
from typing import Optional


# 旧版固定根目录，仅用于把历史 yaml 中的绝对路径识别为「遗留路径」。
LEGACY_HOME = r"E:\NetworkIntel"

# 运行时数据子目录（相对 data_dir）。configs 例外，始终相对 home。
_DATA_SUBDIRS = ("live", "cache", "logs", "reports", "snapshots", "backups", "gdrive_sync")

# 标记 .env 是否已加载，避免重复 I/O。
_env_loaded = False


def _is_frozen() -> bool:
    """是否运行在 PyInstaller 打包的 exe 中。"""
    return bool(getattr(sys, "frozen", False))


def get_home_dir() -> Path:
    """
    解析程序运行根目录（home）。
    home 下存放 configs/ 与 .env，portable 模式下也存放全部运行时数据。
    """
    env_home = os.environ.get("NETWORKINTEL_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()

    if _is_frozen():
        return Path(sys.executable).resolve().parent

    # 源码运行：本文件位于 <root>/python/utils/paths.py → 上三级即项目根目录
    src_root = Path(__file__).resolve().parents[2]
    if src_root.exists():
        return src_root

    return Path.cwd().resolve()


def _ensure_env_loaded() -> None:
    """
    把 home/.env 加载进 os.environ（不覆盖已存在的变量）。
    必须在解析 data_dir 之前调用，因为 NETWORKINTEL_DATA_MODE /
    NETWORKINTEL_DATA_DIR 可能写在 .env 中。幂等。
    """
    global _env_loaded
    if _env_loaded:
        return
    # 标记在前：即使读取失败也不反复尝试，且避免与解析互相递归。
    _env_loaded = True
    env_path = get_home_dir() / ".env"
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


def reset_env_cache() -> None:
    """测试辅助：清除 .env 已加载标记，强制下次重新读取。"""
    global _env_loaded
    _env_loaded = False


def get_data_mode() -> str:
    """返回数据目录模式：portable（默认）或 custom。"""
    _ensure_env_loaded()
    mode = (os.environ.get("NETWORKINTEL_DATA_MODE") or "portable").strip().lower()
    return "custom" if mode == "custom" else "portable"


def get_data_dir() -> Path:
    """
    解析数据目录（data_dir）。
    portable：data_dir = home（忽略 NETWORKINTEL_DATA_DIR）。
    custom：  data_dir = NETWORKINTEL_DATA_DIR；未设置时回退 home。
    """
    home = get_home_dir()
    if get_data_mode() == "custom":
        custom = os.environ.get("NETWORKINTEL_DATA_DIR")
        if custom and custom.strip():
            return Path(custom).expanduser().resolve()
    return home


def get_config_dir() -> Path:
    """configs/ 目录（始终相对 home）。"""
    return get_home_dir() / "configs"


def get_env_path() -> Path:
    """.env 路径（始终相对 home）。"""
    return get_home_dir() / ".env"


def get_sources_path() -> Path:
    """sources.yaml 路径。NETWORKINTEL_CONFIG 可覆盖。"""
    env_cfg = os.environ.get("NETWORKINTEL_CONFIG")
    if env_cfg and env_cfg.strip():
        return Path(env_cfg).expanduser().resolve()
    return get_config_dir() / "sources.yaml"


def get_sources_example_path() -> Path:
    """sources.example.yaml 模板路径。"""
    return get_config_dir() / "sources.example.yaml"


def get_env_example_path() -> Path:
    """.env.example 模板路径。"""
    return get_home_dir() / ".env.example"


def get_live_dir() -> Path:
    return get_data_dir() / "live"


def get_db_path() -> Path:
    """主数据库路径：data_dir/live/intel.db。"""
    return get_live_dir() / "intel.db"


def get_cache_dir() -> Path:
    return get_data_dir() / "cache"


def get_logs_dir() -> Path:
    return get_data_dir() / "logs"


def get_reports_dir() -> Path:
    return get_data_dir() / "reports"


def get_snapshots_dir() -> Path:
    return get_data_dir() / "snapshots"


def get_backups_dir() -> Path:
    return get_data_dir() / "backups"


def get_gdrive_sync_dir() -> Path:
    return get_data_dir() / "gdrive_sync"


def is_legacy_absolute(value: str) -> bool:
    """判断字符串是否为指向旧版固定根目录 E:\\NetworkIntel 的绝对路径。"""
    if not value:
        return False
    try:
        p = Path(value)
    except Exception:
        return False
    if not p.is_absolute():
        return False
    return str(p).lower().startswith(LEGACY_HOME.lower())


def resolve_runtime_path(value: Optional[str], default: Path, base: Path) -> Path:
    """
    将 sources.yaml 中的路径值解析为 portable 友好的绝对路径。

    规则：
      - 空/None              → default（来自 paths 模块）
      - 相对路径             → base / value
      - 遗留 E:\\NetworkIntel → 若该路径真实存在则保留（兼容老用户），否则用 default
      - 其它绝对路径         → 原样保留（高级用户显式覆盖）
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        return default
    value = str(value)
    p = Path(value)
    if not p.is_absolute():
        return (base / value).resolve()
    if is_legacy_absolute(value):
        return p if p.exists() else default
    return p


def ensure_runtime_dirs() -> None:
    """首次运行时创建全部运行时目录（configs 在 home 下，数据目录在 data_dir 下）。"""
    get_config_dir().mkdir(parents=True, exist_ok=True)
    data_dir = get_data_dir()
    for sub in _DATA_SUBDIRS:
        (data_dir / sub).mkdir(parents=True, exist_ok=True)


def short_db_path(path: Optional[str], keep: int = 2) -> str:
    """
    把完整 DB 路径缩短为状态栏可读的尾段形式，例如 ``...\\live\\intel.db``。

    仅用于 UI 展示，**不改变任何真实 db_path / data_dir**：完整路径仍可通过状态栏
    tooltip 或设置页「当前路径」查看。``keep`` 控制保留的尾部层级数（默认 2）。
    路径层级数不超过 ``keep`` 时原样返回（不加省略号）。
    """
    if not path:
        return ""
    p = Path(str(path))
    parts = p.parts
    if len(parts) <= keep:
        return str(p)
    tail = os.sep.join(parts[-keep:])
    return "..." + os.sep + tail


def describe() -> dict:
    """返回当前路径解析结果，便于 GUI 展示与调试（不含任何 key）。"""
    return {
        "home": str(get_home_dir()),
        "data_mode": get_data_mode(),
        "data_dir": str(get_data_dir()),
        "config_dir": str(get_config_dir()),
        "db_path": str(get_db_path()),
    }
