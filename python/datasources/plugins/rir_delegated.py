"""
NetworkIntel - RIR Delegated 插件
数据源：五大RIR 的 delegated-extended 文件
ARIN / RIPE / APNIC / LACNIC / AFRINIC
"""

import os
import ipaddress
from typing import Generator

from datasources.base import DataSourceBase
from utils.ip_utils import network_to_range, _safe_int


class RIRDelegatedSource(DataSourceBase):
    SOURCE_NAME = "rir_delegated"
    SOURCE_DESCRIPTION = "五大RIR IP分配记录（ARIN/RIPE/APNIC/LACNIC/AFRINIC）"

    def download(self) -> str:
        urls = self.source_config.get("urls", {})
        for rir, url in urls.items():
            self._download_file(url, f"delegated-{rir}-extended-latest.txt")
        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        urls = self.source_config.get("urls", {})
        for rir in urls.keys():
            fname = os.path.join(self.cache_dir, f"delegated-{rir}-extended-latest.txt")
            if not os.path.exists(fname):
                continue
            yield from self._parse_rir_file(fname, rir)

    def _parse_rir_file(self, file_path: str, rir: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                # 跳过注释和头部
                if not line or line.startswith("#") or line.startswith("2"):
                    # 版本行和汇总行以数字开头（如 "2|apnic|..."）
                    pass
                parts = line.split("|")
                if len(parts) < 7:
                    continue

                registry    = parts[0].lower()
                country     = parts[1].upper() if parts[1] != "*" else ""
                ip_type     = parts[2].lower()    # ipv4 / ipv6 / asn
                start       = parts[3]
                value_str   = parts[4]
                date_str    = parts[5]
                status      = parts[6].split("[")[0].strip()  # allocated/assigned等

                if ip_type not in ("ipv4", "ipv6"):
                    continue

                try:
                    value = int(value_str)
                except ValueError:
                    continue

                # 计算前缀长度
                try:
                    if ip_type == "ipv4":
                        # value = 地址数量，转换为前缀长度
                        prefix_len = 32 - (value - 1).bit_length() if value > 0 else 32
                        network = f"{start}/{prefix_len}"
                        net = ipaddress.ip_network(network, strict=False)
                        start_int = int(net.network_address)
                        end_int   = int(net.broadcast_address)
                    else:
                        # ipv6：value是前缀长度
                        network = f"{start}/{value}"
                        net = ipaddress.ip_network(network, strict=False)
                        start_int = int(net.network_address)
                        end_int   = int(net.broadcast_address)
                        prefix_len = value
                except Exception:
                    continue

                yield {
                    "rir":               rir,
                    "country_code":      country,
                    "ip_type":           ip_type,
                    "network":           network,
                    "network_start_int": _safe_int(start_int),
                    "network_end_int":   _safe_int(end_int),
                    "prefix_length":     prefix_len,
                    "value":             value,
                    "date_allocated":    date_str if date_str != "00000000" else None,
                    "status":            status,
                    "source":            self.SOURCE_NAME,
                    "snapshot_date":     self.today_str,
                }

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "rir", "country_code", "ip_type", "network",
            "network_start_int", "network_end_int",
            "prefix_length", "value", "date_allocated", "status",
            "source", "snapshot_date",
        ]
        count = 0
        # 删旧 + 插新在同一事务内原子完成（replace_source=True），失败整体回滚。
        with self._bulk_insert("rir_delegated", columns, replace_source=True) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count
