"""
NetworkIntel - 在线查询 Provider 共享基类（online.base）
======================================================
OnlineApiProvider：为需要 API Key 的在线 provider 提供统一的密钥解析与 validate_config()。

密钥来源（与 P0 的 .env/${VAR} 规范一致）：
  1) configs/sources.yaml 中该 source 的 config_keys（${VAR} 已由 config_loader 解析）；
  2) 回退到环境变量 ENV_KEY（config_loader 在 get_config() 时已把 .env 载入 os.environ）。
本模块不打印/记录任何密钥。
"""
from __future__ import annotations

import os
from typing import Optional

from providers.base import OnlineQueryProvider
from providers.types import ConfigValidation, is_placeholder


class OnlineApiProvider(OnlineQueryProvider):
    """需要 API Key 的在线 provider 基类。"""

    requires_api_key = True
    ENV_KEY = ""          # 例如 "ABUSEIPDB_API_KEY"

    def _resolve_key(self) -> str:
        """解析 API Key（不抛异常，未配置返回空串）。"""
        # 1) 配置文件中的 source 条目（${VAR} 已解析）
        try:
            from utils.config_loader import get_config
            src = get_config().get_source(self.name) or {}
            for k in self.config_keys:
                val = src.get(k)
                if val and not is_placeholder(val):
                    return val
        except Exception:
            pass
        # 2) 回退环境变量
        val = os.environ.get(self.ENV_KEY, "") if self.ENV_KEY else ""
        return "" if is_placeholder(val) else val

    def validate_config(self) -> ConfigValidation:
        if not self.requires_api_key:
            return ConfigValidation(ok=True)
        key = self._resolve_key()
        if not key:
            hint = self.ENV_KEY or (self.config_keys[0] if self.config_keys else "API_KEY")
            return ConfigValidation(
                ok=False,
                missing=list(self.config_keys) or [hint],
                messages=[f"未配置 {hint}（请在 .env 设置；不要写入被 git 跟踪的文件）"],
            )
        return ConfigValidation(ok=True, messages=["api key 已配置"])

    def has_key(self) -> bool:
        return bool(self._resolve_key())
