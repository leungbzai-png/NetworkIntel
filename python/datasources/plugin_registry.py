"""
NetworkIntel - 插件注册表
新增数据源插件后，在此文件添加一行注册即可
"""

from datasources.plugins.geoip import GeoIPSource
from datasources.plugins.ip2asn import IP2ASNSource
from datasources.plugins.rir_delegated import RIRDelegatedSource
from datasources.plugins.rpki import RPKISource
from datasources.plugins.cloud_aws import CloudAWSSource
from datasources.plugins.cloud_azure import CloudAzureSource
from datasources.plugins.cloud_gcp import CloudGCPSource
from datasources.plugins.cloud_cloudflare import CloudCloudflareSource
from datasources.plugins.cloud_hetzner import CloudHetznerSource
from datasources.plugins.cloud_vultr import CloudVultrSource
from datasources.plugins.tor_exits import TorExitsSource
from datasources.plugins.vpn_x4bnet import VPNx4bnetSource
from datasources.plugins.spamhaus import SpamhausSource
from datasources.plugins.firehol import FireHOLSource
from datasources.plugins.abusech import AbusechSource
from datasources.plugins.emerging_threats import EmergingThreatsSource
from datasources.plugins.peeringdb import PeeringDBSource

# ── 插件注册表 ────────────────────────────────────────────────
# key：与 sources.yaml 中的 source name 一致
# value：插件类
PLUGIN_REGISTRY: dict = {
    "geoip":             GeoIPSource,
    "ip2asn":            IP2ASNSource,
    "rir_delegated":     RIRDelegatedSource,
    "rpki":              RPKISource,
    "cloud_aws":         CloudAWSSource,
    "cloud_azure":       CloudAzureSource,
    "cloud_gcp":         CloudGCPSource,
    "cloud_cloudflare":  CloudCloudflareSource,
    "cloud_hetzner":     CloudHetznerSource,
    "cloud_vultr":       CloudVultrSource,
    "tor_exits":         TorExitsSource,
    "vpn_x4bnet":        VPNx4bnetSource,
    "spamhaus_drop":     SpamhausSource,
    "firehol":           FireHOLSource,
    "abusech":           AbusechSource,
    "emerging_threats":  EmergingThreatsSource,
    "peeringdb":         PeeringDBSource,
}


def get_plugin(source_name: str):
    """根据名称获取插件实例"""
    cls = PLUGIN_REGISTRY.get(source_name)
    if not cls:
        raise KeyError(f"未注册的数据源插件: {source_name}")
    return cls()


def get_all_plugins() -> dict:
    """获取所有插件实例（key: name, value: instance）"""
    return {name: cls() for name, cls in PLUGIN_REGISTRY.items()}


def get_enabled_plugins() -> dict:
    """获取所有已启用的插件实例"""
    return {
        name: instance
        for name, instance in get_all_plugins().items()
        if instance.is_enabled
    }
