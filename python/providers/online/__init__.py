"""
NetworkIntel - 在线查询 Provider 集合（旁路能力，未接入主查询）
==============================================================
当前仅 BGPView 为可用实现；其余为骨架。所有在线 provider 均**不接入** query_ip 离线主流程。

用法：
    from providers.online import ONLINE_PROVIDERS, get_online_providers
    providers = get_online_providers()          # 返回实例列表
"""
from __future__ import annotations

from providers.online.bgpview import BGPViewProvider
from providers.online.ipinfo import IPInfoProvider
from providers.online.ip2location import IP2LocationProvider
from providers.online.abuseipdb import AbuseIPDBProvider
from providers.online.threatfox import ThreatFoxProvider


# name -> class（实例化无副作用：不读配置、不联网）
ONLINE_PROVIDERS: dict[str, type] = {
    BGPViewProvider.name:     BGPViewProvider,
    IPInfoProvider.name:      IPInfoProvider,
    IP2LocationProvider.name: IP2LocationProvider,
    AbuseIPDBProvider.name:   AbuseIPDBProvider,
    ThreatFoxProvider.name:   ThreatFoxProvider,
}

# 当前已实现真实 query() 的在线 provider（其余为骨架）
IMPLEMENTED = {"bgpview", "ipinfo"}


def get_online_providers() -> list:
    """返回所有在线 provider 实例。"""
    return [cls() for cls in ONLINE_PROVIDERS.values()]


def get_online_provider(name: str):
    """按 name 获取在线 provider 实例（不存在返回 None）。"""
    cls = ONLINE_PROVIDERS.get(name)
    return cls() if cls else None
