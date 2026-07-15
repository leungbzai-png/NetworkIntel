"""
NetworkIntel - RPKI 插件
数据源：Cloudflare RPKI JSON (https://rpki.cloudflare.com/rpki.json)
提供路由起源验证 (ROA) 数据
"""

import json
import os
from typing import Generator

from datasources.base import DataSourceBase
from utils.ip_utils import network_to_range


class RPKISource(DataSourceBase):
    SOURCE_NAME = "rpki"
    SOURCE_DESCRIPTION = "Cloudflare RPKI路由起源验证数据"

    def download(self) -> str:
        url = self.source_config.get("url", "https://rpki.cloudflare.com/rpki.json")
        return self._download_file(url, "rpki.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        roas = data.get("roas", [])
        self.logger.info(f"[{self.SOURCE_NAME}] 解析 {len(roas)} 条 ROA 记录")

        for roa in roas:
            prefix = roa.get("prefix", "")
            asn_raw = roa.get("asn", "")
            max_length = roa.get("maxLength")
            ta = roa.get("ta", "")

            if not prefix or not asn_raw:
                continue

            # asn 格式可能是 "AS12345" 或 12345
            try:
                asn = int(str(asn_raw).replace("AS", "").replace("as", ""))
            except ValueError:
                continue

            start_int, end_int = network_to_range(prefix)
            if start_int == 0 and end_int == 0:
                continue

            yield {
                "prefix":            prefix,
                "asn":               asn,
                "max_length":        max_length,
                "status":            "valid",  # Cloudflare JSON只含valid ROAs
                "ta":                ta,
                "network_start_int": start_int,
                "network_end_int":   end_int,
                "source":            self.SOURCE_NAME,
                "snapshot_date":     self.today_str,
            }

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "prefix", "asn", "max_length", "status", "ta",
            "network_start_int", "network_end_int",
            "source", "snapshot_date",
        ]
        count = 0
        # 删旧 + 插新在同一事务内原子完成（replace_source=True），失败整体回滚。
        with self._bulk_insert("rpki", columns, replace_source=True) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count
