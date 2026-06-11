"""
NetworkIntel - 威胁情报插件集合
Tor出口 / VPN(X4BNet) / Spamhaus / FireHOL / Abuse.ch / EmergingThreats
"""

import ipaddress
from typing import Generator

from datasources.base import DataSourceBase
from utils.ip_utils import network_to_range


# ── 威胁情报基类 ──────────────────────────────────────────────
class ThreatBaseSource(DataSourceBase):
    THREAT_TYPE = ""
    LIST_NAME = ""
    SEVERITY = "medium"

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "network", "network_start_int", "network_end_int",
            "threat_type", "list_name", "severity",
            "source", "valid_from", "snapshot_date",
        ]
        from utils.schema import get_connection
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM threat_intel WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()

        count = 0
        with self._bulk_insert("threat_intel", columns) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count

    def _make_threat(self, cidr: str, threat_type: str = None,
                     list_name: str = None, severity: str = None) -> dict:
        """单条IP或CIDR构建威胁记录"""
        # 单IP转为/32
        if "/" not in cidr:
            cidr = f"{cidr}/32"
        start_int, end_int = network_to_range(cidr)
        return {
            "network":           cidr,
            "network_start_int": start_int,
            "network_end_int":   end_int,
            "threat_type":       threat_type or self.THREAT_TYPE,
            "list_name":         list_name or self.LIST_NAME,
            "severity":          severity or self.SEVERITY,
            "source":            self.SOURCE_NAME,
            "valid_from":        self.today_str,
            "snapshot_date":     self.today_str,
        }

    def _parse_plaintext(self, file_path: str, threat_type: str = None,
                         list_name: str = None, severity: str = None) -> Generator[dict, None, None]:
        """解析纯文本IP列表（每行一个IP或CIDR，#注释）"""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith(";"):
                    continue
                # 去掉行内注释
                if ";" in line:
                    line = line.split(";")[0].strip()
                if " " in line:
                    line = line.split()[0]
                if not line:
                    continue
                try:
                    # 验证是否有效IP/CIDR
                    if "/" in line:
                        ipaddress.ip_network(line, strict=False)
                    else:
                        ipaddress.ip_address(line)
                    yield self._make_threat(line, threat_type, list_name, severity)
                except ValueError:
                    continue


# ── Tor 出口节点 ──────────────────────────────────────────────
class TorExitsSource(ThreatBaseSource):
    SOURCE_NAME = "tor_exits"
    SOURCE_DESCRIPTION = "Tor出口节点列表（Tor Project官方）"
    THREAT_TYPE = "tor"
    LIST_NAME = "tor_exits"
    SEVERITY = "medium"

    def download(self) -> str:
        url = self.source_config.get("url", "https://check.torproject.org/torbulkexitlist")
        return self._download_file(url, "tor-exits.txt")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        yield from self._parse_plaintext(file_path)


# ── VPN (X4BNet) ──────────────────────────────────────────────
class VPNx4bnetSource(ThreatBaseSource):
    SOURCE_NAME = "vpn_x4bnet"
    SOURCE_DESCRIPTION = "X4BNet VPN出口IP列表"
    THREAT_TYPE = "vpn"
    LIST_NAME = "x4bnet_vpn"
    SEVERITY = "low"

    def download(self) -> str:
        url = self.source_config.get(
            "url",
            "https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/vpn/ipv4.txt"
        )
        return self._download_file(url, "vpn-x4bnet.txt")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        yield from self._parse_plaintext(file_path)


# ── Spamhaus DROP + EDROP ─────────────────────────────────────
class SpamhausSource(ThreatBaseSource):
    SOURCE_NAME = "spamhaus_drop"
    SOURCE_DESCRIPTION = "Spamhaus DROP + EDROP 黑名单"
    THREAT_TYPE = "spam"
    SEVERITY = "high"

    def download(self) -> str:
        urls = self.source_config.get("urls", {})
        self._download_file(
            urls.get("drop", "https://www.spamhaus.org/drop/drop.txt"),
            "spamhaus-drop.txt"
        )
        self._download_file(
            urls.get("edrop", "https://www.spamhaus.org/drop/edrop.txt"),
            "spamhaus-edrop.txt"
        )
        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        import os
        for fname, list_name in [
            ("spamhaus-drop.txt",  "spamhaus_drop"),
            ("spamhaus-edrop.txt", "spamhaus_edrop"),
        ]:
            fpath = os.path.join(self.cache_dir, fname)
            if os.path.exists(fpath):
                yield from self._parse_plaintext(
                    fpath, threat_type="spam", list_name=list_name, severity="high"
                )


# ── FireHOL Level 1-3 ─────────────────────────────────────────
class FireHOLSource(ThreatBaseSource):
    SOURCE_NAME = "firehol"
    SOURCE_DESCRIPTION = "FireHOL Level 1-3 恶意IP集合"
    THREAT_TYPE = "malicious"

    SEVERITY_MAP = {
        "firehol_level1": "critical",
        "firehol_level2": "high",
        "firehol_level3": "medium",
    }

    def download(self) -> str:
        urls = self.source_config.get("urls", {})
        for level, url in urls.items():
            self._download_file(url, f"firehol-{level}.netset")
        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        import os
        for level in ["level1", "level2", "level3"]:
            fpath = os.path.join(self.cache_dir, f"firehol-firehol_{level}.netset")
            # 兼容不同文件名格式
            if not os.path.exists(fpath):
                fpath = os.path.join(self.cache_dir, f"firehol-{level}.netset")
            if not os.path.exists(fpath):
                continue
            list_name = f"firehol_{level}"
            severity = self.SEVERITY_MAP.get(list_name, "medium")
            yield from self._parse_plaintext(
                fpath, threat_type="malicious", list_name=list_name, severity=severity
            )


# ── Abuse.ch Feodo Tracker ────────────────────────────────────
class AbusechSource(ThreatBaseSource):
    SOURCE_NAME = "abusech"
    SOURCE_DESCRIPTION = "Abuse.ch Feodo Tracker C2服务器IP"
    THREAT_TYPE = "c2"
    LIST_NAME = "abusech_feodo"
    SEVERITY = "critical"

    def download(self) -> str:
        url = self.source_config.get(
            "url",
            "https://feodotracker.abuse.ch/downloads/ipblocklist.txt"
        )
        return self._download_file(url, "abusech-feodo.txt")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        yield from self._parse_plaintext(file_path)


# ── EmergingThreats ───────────────────────────────────────────
class EmergingThreatsSource(ThreatBaseSource):
    SOURCE_NAME = "emerging_threats"
    SOURCE_DESCRIPTION = "EmergingThreats 恶意IP封锁列表"
    THREAT_TYPE = "scanner"
    LIST_NAME = "emerging_threats"
    SEVERITY = "high"

    def download(self) -> str:
        url = self.source_config.get(
            "url",
            "https://rules.emergingthreats.net/fwrules/emerging-Block-IPs.txt"
        )
        return self._download_file(url, "emerging-threats.txt")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        yield from self._parse_plaintext(file_path)
