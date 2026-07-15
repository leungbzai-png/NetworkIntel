"""
NetworkIntel - 云服务商 IP 段插件
AWS / Azure / GCP / Cloudflare / Hetzner / Vultr
"""

import json
import ipaddress
from typing import Generator

from datasources.base import DataSourceBase
from utils.ip_utils import network_to_range


# ── 基类 ──────────────────────────────────────────────────────
class CloudBaseSource(DataSourceBase):
    PROVIDER = ""

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "provider", "network", "network_start_int", "network_end_int",
            "region", "service", "source", "snapshot_date",
        ]
        count = 0
        # 删旧 + 插新在同一事务内原子完成（replace_source=True），失败整体回滚。
        with self._bulk_insert("cloud_ranges", columns, replace_source=True) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count

    def _make_record(self, cidr: str, region: str = "", service: str = "") -> dict:
        start_int, end_int = network_to_range(cidr)
        return {
            "provider":          self.PROVIDER,
            "network":           cidr,
            "network_start_int": start_int,
            "network_end_int":   end_int,
            "region":            region,
            "service":           service,
            "source":            self.SOURCE_NAME,
            "snapshot_date":     self.today_str,
        }


# ── AWS ──────────────────────────────────────────────────────
class CloudAWSSource(CloudBaseSource):
    SOURCE_NAME = "cloud_aws"
    SOURCE_DESCRIPTION = "AWS IP ranges"
    PROVIDER = "aws"

    def download(self) -> str:
        url = self.source_config.get("url", "https://ip-ranges.amazonaws.com/ip-ranges.json")
        return self._download_file(url, "aws-ip-ranges.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for prefix in data.get("prefixes", []):
            cidr = prefix.get("ip_prefix", "")
            if cidr:
                yield self._make_record(
                    cidr,
                    region=prefix.get("region", ""),
                    service=prefix.get("service", ""),
                )
        for prefix in data.get("ipv6_prefixes", []):
            cidr = prefix.get("ipv6_prefix", "")
            if cidr:
                yield self._make_record(
                    cidr,
                    region=prefix.get("region", ""),
                    service=prefix.get("service", ""),
                )


# ── Azure ────────────────────────────────────────────────────
class CloudAzureSource(CloudBaseSource):
    SOURCE_NAME = "cloud_azure"
    SOURCE_DESCRIPTION = "Azure Service Tags IP ranges"
    PROVIDER = "azure"

    def download(self) -> str:
        import requests, re
        # Azure的下载链接每周变化，需要先从官方页面获取最新链接
        page_url = "https://www.microsoft.com/en-us/download/confirmation.aspx?id=56519"
        headers = {"User-Agent": "NetworkIntel/1.0"}
        resp = requests.get(page_url, headers=headers, timeout=30)
        # 从页面提取真实下载链接
        match = re.search(
            r'https://download\.microsoft\.com/download/[^"\']+ServiceTags_Public[^"\']+\.json',
            resp.text
        )
        if match:
            url = match.group(0)
        else:
            # 备用：直接尝试构造URL
            url = self.source_config.get("url", "")
        return self._download_file(url, "azure-service-tags.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for value in data.get("values", []):
            name = value.get("name", "")
            props = value.get("properties", {})
            region = props.get("region", "")
            for cidr in props.get("addressPrefixes", []):
                yield self._make_record(cidr, region=region, service=name)


# ── GCP ──────────────────────────────────────────────────────
class CloudGCPSource(CloudBaseSource):
    SOURCE_NAME = "cloud_gcp"
    SOURCE_DESCRIPTION = "Google Cloud IP ranges"
    PROVIDER = "gcp"

    def download(self) -> str:
        url = self.source_config.get("url", "https://www.gstatic.com/ipranges/cloud.json")
        return self._download_file(url, "gcp-cloud.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for prefix in data.get("prefixes", []):
            cidr = prefix.get("ipv4Prefix") or prefix.get("ipv6Prefix", "")
            if cidr:
                yield self._make_record(
                    cidr,
                    region=prefix.get("scope", ""),
                    service=prefix.get("service", ""),
                )


# ── Cloudflare ───────────────────────────────────────────────
class CloudCloudflareSource(CloudBaseSource):
    SOURCE_NAME = "cloud_cloudflare"
    SOURCE_DESCRIPTION = "Cloudflare IP ranges"
    PROVIDER = "cloudflare"

    def download(self) -> str:
        urls = self.source_config.get("urls", {})
        self._download_file(urls.get("v4", "https://www.cloudflare.com/ips-v4"), "cf-ips-v4.txt")
        self._download_file(urls.get("v6", "https://www.cloudflare.com/ips-v6"), "cf-ips-v6.txt")
        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        import os
        for fname in ["cf-ips-v4.txt", "cf-ips-v6.txt"]:
            fpath = os.path.join(self.cache_dir, fname)
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8") as f:
                for line in f:
                    cidr = line.strip()
                    if cidr and not cidr.startswith("#"):
                        yield self._make_record(cidr, service="Cloudflare CDN")


# ── Hetzner ──────────────────────────────────────────────────
class CloudHetznerSource(CloudBaseSource):
    SOURCE_NAME = "cloud_hetzner"
    SOURCE_DESCRIPTION = "Hetzner IP ranges"
    PROVIDER = "hetzner"

    def download(self) -> str:
        # Hetzner 官方IP段文本文件
        urls_to_try = [
            ("https://hetzner.de/assets/hetzner_ips.json", "hetzner-ips.json"),
            ("https://www.hetzner.com/assets/ips.txt", "hetzner-ips.txt"),
            ("https://ipinfo.io/AS24940/cidrs", "hetzner-ips.txt"),
        ]
        last_err = None
        for url, fname in urls_to_try:
            try:
                return self._download_file(url, fname)
            except Exception as e:
                last_err = e
                continue
        # 最后备用：直接写入已知Hetzner主要网段
        import os
        fpath = os.path.join(self.cache_dir, "hetzner-ips.txt")
        known = "5.9.0.0/16\n5.161.0.0/16\n23.88.0.0/17\n65.108.0.0/16\n65.109.0.0/16\n88.198.0.0/16\n95.216.0.0/16\n116.202.0.0/15\n136.243.0.0/16\n144.76.0.0/16\n157.90.0.0/16\n159.69.0.0/16\n162.55.0.0/16\n168.119.0.0/16\n176.9.0.0/16\n178.63.0.0/16\n188.40.0.0/16\n213.133.96.0/19\n"
        with open(fpath, "w") as f:
            f.write(known)
        self.logger.warning(f"[cloud_hetzner] All URLs failed, using static fallback")
        return fpath

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        if file_path.endswith(".json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        cidr = item.get("cidr") or item.get("prefix", "")
                        if cidr:
                            yield self._make_record(cidr, service="Hetzner Cloud")
                    return
            except Exception:
                pass
        # 纯文本格式
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                cidr = line.strip()
                if cidr and not cidr.startswith("#"):
                    yield self._make_record(cidr, service="Hetzner")


# ── Vultr ────────────────────────────────────────────────────
class CloudVultrSource(CloudBaseSource):
    SOURCE_NAME = "cloud_vultr"
    SOURCE_DESCRIPTION = "Vultr IP ranges"
    PROVIDER = "vultr"

    def download(self) -> str:
        url = self.source_config.get("url", "https://geofeed.constant.com/?json")
        return self._download_file(url, "vultr-ips.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            subnets = data if isinstance(data, list) else data.get("subnets", [])
            for item in subnets:
                cidr = item.get("ip_prefix") or item.get("subnet", "")
                if cidr:
                    yield self._make_record(
                        cidr,
                        region=item.get("alpha2code", ""),
                        service="Vultr",
                    )
        except json.JSONDecodeError:
            # 尝试纯文本
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    cidr = line.strip().split(",")[0]
                    if cidr and not cidr.startswith("#"):
                        yield self._make_record(cidr, service="Vultr")
