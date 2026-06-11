"""
NetworkIntel - PeeringDB 插件（可选，默认禁用）
数据源：PeeringDB API
提供 ASN → IXP/Peering 信息
"""

import json
from typing import Generator

from datasources.base import DataSourceBase


class PeeringDBSource(DataSourceBase):
    SOURCE_NAME = "peeringdb"
    SOURCE_DESCRIPTION = "PeeringDB ASN Peering信息（可选插件）"

    def download(self) -> str:
        url = self.source_config.get(
            "url",
            "https://peeringdb.com/api/net?depth=2&limit=10000"
        )
        return self._download_file(url, "peeringdb.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        nets = data.get("data", [])
        for net in nets:
            asn = net.get("asn")
            if not asn:
                continue

            # 提取 IXP 列表（netixlan关联）
            ix_names = []
            for ixlan in net.get("netixlan_set", []):
                ix_name = ixlan.get("name", "")
                if ix_name:
                    ix_names.append(ix_name)

            yield {
                "asn":            asn,
                "name":           net.get("name", ""),
                "aka":            net.get("aka", ""),
                "website":        net.get("website", ""),
                "info_type":      net.get("info_type", ""),
                "info_prefixes4": net.get("info_prefixes4", 0),
                "info_prefixes6": net.get("info_prefixes6", 0),
                "policy_general": net.get("policy_general", ""),
                "ix_list":        json.dumps(ix_names, ensure_ascii=False),
                "source":         self.SOURCE_NAME,
                "snapshot_date":  self.today_str,
            }

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "asn", "name", "aka", "website", "info_type",
            "info_prefixes4", "info_prefixes6", "policy_general",
            "ix_list", "source", "snapshot_date",
        ]
        from utils.schema import get_connection
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM peeringdb WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()

        count = 0
        with self._bulk_insert("peeringdb", columns) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count
