"""
NetworkIntel - IP 工具函数
提供IP地址转换、范围计算、特殊IP识别
"""

import ipaddress
import struct
import socket
from typing import Optional, Tuple


# ── 特殊IP范围（RFC定义）────────────────────────────────────
SPECIAL_RANGES = [
    (ipaddress.ip_network("0.0.0.0/8"),        "本地网络", "special"),
    (ipaddress.ip_network("10.0.0.0/8"),        "私有地址 (RFC1918)", "private"),
    (ipaddress.ip_network("100.64.0.0/10"),     "共享地址空间 (RFC6598)", "special"),
    (ipaddress.ip_network("127.0.0.0/8"),       "环回地址", "loopback"),
    (ipaddress.ip_network("169.254.0.0/16"),    "链路本地 (APIPA)", "link-local"),
    (ipaddress.ip_network("172.16.0.0/12"),     "私有地址 (RFC1918)", "private"),
    (ipaddress.ip_network("192.0.0.0/24"),      "IANA特殊地址", "special"),
    (ipaddress.ip_network("192.0.2.0/24"),      "文档地址 (TEST-NET-1)", "documentation"),
    (ipaddress.ip_network("192.168.0.0/16"),    "私有地址 (RFC1918)", "private"),
    (ipaddress.ip_network("198.18.0.0/15"),     "基准测试地址", "special"),
    (ipaddress.ip_network("198.51.100.0/24"),   "文档地址 (TEST-NET-2)", "documentation"),
    (ipaddress.ip_network("203.0.113.0/24"),    "文档地址 (TEST-NET-3)", "documentation"),
    (ipaddress.ip_network("224.0.0.0/4"),       "组播地址", "multicast"),
    (ipaddress.ip_network("240.0.0.0/4"),       "保留地址", "reserved"),
    (ipaddress.ip_network("255.255.255.255/32"),"广播地址", "special"),
    # IPv6
    (ipaddress.ip_network("::1/128"),           "IPv6环回地址", "loopback"),
    (ipaddress.ip_network("fe80::/10"),         "IPv6链路本地", "link-local"),
    (ipaddress.ip_network("fc00::/7"),          "IPv6唯一本地地址", "private"),
    (ipaddress.ip_network("::ffff:0:0/96"),     "IPv4映射地址", "special"),
]



# SQLite INTEGER 最大值（有符号64位）
_SQLITE_INT_MAX = (1 << 63) - 1

def ip_to_int(ip_str: str) -> int:
    """将IP地址字符串转为整数（IPv4和IPv6均支持）"""
    try:
        addr = ipaddress.ip_address(ip_str)
        return int(addr)
    except ValueError:
        return 0


def _safe_int(n: int) -> int:
    """截断超大整数到SQLite安全范围（IPv6用）"""
    if n > _SQLITE_INT_MAX:
        return _SQLITE_INT_MAX
    return n


def int_to_ip(ip_int: int, version: int = 4) -> str:
    """将整数转为IP地址字符串"""
    try:
        if version == 4:
            return str(ipaddress.IPv4Address(ip_int))
        else:
            return str(ipaddress.IPv6Address(ip_int))
    except Exception:
        return ""


def network_to_range(cidr: str) -> Tuple[int, int]:
    """将CIDR转为起止整数范围，返回 (start_int, end_int)
    IPv6超出SQLite有符号64位范围时截断，避免OverflowError"""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        return _safe_int(int(net.network_address)), _safe_int(int(net.broadcast_address))
    except ValueError:
        return 0, 0


def ip_in_network(ip_str: str, cidr: str) -> bool:
    """检查IP是否在CIDR范围内"""
    try:
        return ipaddress.ip_address(ip_str) in ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return False


def normalize_ip(ip_str: str) -> Optional[str]:
    """规范化IP地址，返回None如果无效"""
    try:
        return str(ipaddress.ip_address(ip_str.strip()))
    except ValueError:
        return None


def get_ip_version(ip_str: str) -> Optional[int]:
    """获取IP版本，返回4或6，无效返回None"""
    try:
        return ipaddress.ip_address(ip_str).version
    except ValueError:
        return None


def check_special_ip(ip_str: str) -> Optional[dict]:
    """
    检查是否为特殊IP（私有、环回、组播等）
    返回 dict 或 None（普通公网IP返回None）
    """
    try:
        addr = ipaddress.ip_address(ip_str)
        for network, description, category in SPECIAL_RANGES:
            if addr in network:
                return {
                    "is_special": True,
                    "category": category,
                    "description": description,
                    "network": str(network),
                }
        return None
    except ValueError:
        return None


def parse_ip_input(raw: str) -> Tuple[list, list]:
    """
    解析用户输入，支持：
    - 单个IP
    - CIDR
    - 多行IP（换行分隔）
    返回 (valid_ips: list, errors: list)
    """
    valid = []
    errors = []
    lines = [l.strip() for l in raw.strip().splitlines() if l.strip()]

    for line in lines:
        # 跳过注释
        if line.startswith('#'):
            continue
        # 去掉行尾注释
        if ' ' in line:
            line = line.split()[0]
        if '/' in line:
            # CIDR
            try:
                net = ipaddress.ip_network(line, strict=False)
                valid.append(str(net))
            except ValueError:
                errors.append(f"无效CIDR: {line}")
        else:
            ip = normalize_ip(line)
            if ip:
                valid.append(ip)
            else:
                errors.append(f"无效IP: {line}")

    return valid, errors


def expand_cidr_for_query(cidr: str, max_hosts: int = 256) -> list:
    """
    展开CIDR为IP列表（用于批量查询CIDR块内IP）
    超过max_hosts则只返回前max_hosts个
    """
    try:
        net = ipaddress.ip_network(cidr, strict=False)
        hosts = list(net.hosts())
        if not hosts:
            hosts = [net.network_address]
        return [str(h) for h in hosts[:max_hosts]]
    except ValueError:
        return []


def format_ip_display(ip_str: str) -> str:
    """格式化IP用于显示（IPv6压缩格式）"""
    try:
        addr = ipaddress.ip_address(ip_str)
        return str(addr)
    except ValueError:
        return ip_str
