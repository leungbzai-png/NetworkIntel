"""
NetworkIntel - ip2asn 插件
数据源：https://iptoasn.com/data/ip2asn-v4.tsv.gz
格式：start_ip\tend_ip\tasn\tcountry\tas_name (点分十进制)
"""

import os
import gzip
import ipaddress
from typing import Generator

from datasources.base import DataSourceBase


class IP2ASNSource(DataSourceBase):
    SOURCE_NAME = "ip2asn"
    SOURCE_DESCRIPTION = "ip2asn 全球ASN+BGP前缀映射 (iptoasn.com)"

    def download(self) -> str:
        url = "https://iptoasn.com/data/ip2asn-v4.tsv.gz"
        return self._download_file(url, "ip2asn-v4.tsv.gz")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with gzip.open(file_path, "rt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 5:
                    continue
                try:
                    start_ip = parts[0].strip()
                    end_ip   = parts[1].strip()
                    asn      = int(parts[2])
                    country  = parts[3].strip()
                    as_name  = parts[4].strip()

                    if asn == 0:
                        continue

                    start_int = int(ipaddress.IPv4Address(start_ip))
                    end_int   = int(ipaddress.IPv4Address(end_ip))
                    diff = end_int - start_int + 1
                    prefix_len = 32 - (diff - 1).bit_length() if diff > 1 else 32
                    network = f"{start_ip}/{prefix_len}"

                    yield {
                        "asn":               asn,
                        "as_name":           as_name,
                        "country_code":      country,
                        "network":           network,
                        "network_start_int": start_int,
                        "network_end_int":   end_int,
                        "source":            self.SOURCE_NAME,
                        "snapshot_date":     self.today_str,
                    }
                except (ValueError, IndexError):
                    continue

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "asn", "as_name", "country_code", "network",
            "network_start_int", "network_end_int",
            "source", "snapshot_date",
        ]
        count = 0
        # 删旧 + 插新在同一事务内原子完成（replace_source=True），失败整体回滚。
        with self._bulk_insert("asn_info", columns, replace_source=True) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count
