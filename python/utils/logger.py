"""
NetworkIntel - 日志工具
统一日志格式，输出到文件 + 可选控制台
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(
    name: str = "networkintel",
    logs_dir: str = None,
    level: str = "INFO",
    console: bool = False,
) -> logging.Logger:
    """
    设置并返回 Logger
    - 日志文件按日滚动，保留30天
    - 文件最大10MB，保留5个备份
    - logs_dir 为 None 时使用 Portable 路径系统解析的日志目录
    """
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    if logs_dir is None:
        from utils import paths
        logs_dir = str(paths.get_logs_dir())

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    log_file = os.path.join(logs_dir, f"{name}.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 文件处理器（滚动）
    fh = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 控制台处理器（可选）
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

    return logger


def get_logger(name: str = "networkintel") -> logging.Logger:
    """获取已配置的Logger"""
    return logging.getLogger(name)
