"""
NetworkIntel - IPv6 数据源插件集合
所有IPv6数据写入 *_v6 表，使用hex字符串存储
"""

import os
import csv
import json
import gzip
import ipaddress
import zipfile
from pathlib import Path
from typing import Generator

from datasources.base import DataSourceBase
from utils.schema_v6 import ipv6_network_to_hex_range
from utils.schema import get_connection


# ============================================================
# 基类
# ============================================================
class V6Base(DataSourceBase):
    """IPv6插件基类"""

    def _bulk_insert_v6(self, table: str, columns: list):
        from contextlib import contextmanager

        @contextmanager
        def ctx():
            conn = get_connection(self.config.db_path)
            placeholders = ",".join("?" * len(columns))
            sql = f"INSERT OR REPLACE INTO {table} ({','.join(columns)}) VALUES ({placeholders})"
            batch = []

            def insert(rec):
                batch.append([rec.get(c) for c in columns])
                if len(batch) >= 5000:
                    conn.executemany(sql, batch)
                    conn.commit()
                    batch.clear()

            try:
                yield insert
                if batch:
                    conn.executemany(sql, batch)
                    conn.commit()
            finally:
                conn.close()

        return ctx()


# ============================================================
# GeoIP IPv6
# ============================================================
class GeoIPv6Source(V6Base):
    SOURCE_NAME = "geoip_v6"
    SOURCE_DESCRIPTION = "MaxMind GeoLite2 IPv6 城市数据"

    def download(self) -> str:
        # 复用已下载的City CSV zip（IPv4 plugin already downloaded it）
        # 如果没有，自己下载
        csv_zip = os.path.join(
            self.config.cache_dir, "geoip", "GeoLite2-City-CSV.zip"
        )
        if os.path.exists(csv_zip):
            self.logger.info("[geoip_v6] Reusing existing CSV zip")
            extract_dir = os.path.join(self.config.cache_dir, "geoip")
            with zipfile.ZipFile(csv_zip) as zf:
                zf.extractall(extract_dir)
            return extract_dir

        # Fallback: download fresh
        license_key = self.config.get_source("geoip").get("license_key", "")
        if not license_key or license_key == "YOUR_MAXMIND_LICENSE_KEY_HERE":
            raise ValueError("MaxMind License Key 未配置")
        url = f"https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City-CSV&license_key={license_key}&suffix=zip"
        zf_path = self._download_file(url, "GeoLite2-City-CSV.zip")
        with zipfile.ZipFile(zf_path) as zf:
            zf.extractall(self.cache_dir)
        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        cache = Path(dir_path)

        blocks_file = None
        locations_file = None
        for root, dirs, files in os.walk(dir_path):
            for fname in files:
                if fname == "GeoLite2-City-Blocks-IPv6.csv":
                    blocks_file = os.path.join(root, fname)
                if fname == "GeoLite2-City-Locations-en.csv":
                    locations_file = os.path.join(root, fname)

        if not blocks_file:
            raise FileNotFoundError("GeoLite2-City-Blocks-IPv6.csv not found")

        # Load locations
        locations = {}
        if locations_file:
            with open(locations_file, "r", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    gid = row.get("geoname_id", "")
                    if gid:
                        locations[gid] = {
                            "country_code": row.get("country_iso_code", ""),
                            "country_name": row.get("country_name", ""),
                            "region": row.get("subdivision_1_name", ""),
                            "city": row.get("city_name", ""),
                        }

        # Parse IPv6 blocks
        with open(blocks_file, "r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                network = row.get("network", "")
                if not network:
                    continue
                try:
                    start_hex, end_hex = ipv6_network_to_hex_range(network)
                except Exception:
                    continue
                gid = row.get("geoname_id") or row.get("registered_country_geoname_id", "")
                loc = locations.get(gid, {})

                yield {
                    "network":           network,
                    "network_start_hex": start_hex,
                    "network_end_hex":   end_hex,
                    "country_code":      loc.get("country_code", ""),
                    "country_name":      loc.get("country_name", ""),
                    "region":            loc.get("region", ""),
                    "city":              loc.get("city", ""),
                    "latitude":          _safe_float(row.get("latitude")),
                    "longitude":         _safe_float(row.get("longitude")),
                    "accuracy_radius":   _safe_int(row.get("accuracy_radius")),
                    "source":            self.SOURCE_NAME,
                    "snapshot_date":     self.today_str,
                }

    def load(self, records) -> int:
        cols = ["network","network_start_hex","network_end_hex","country_code",
                "country_name","region","city","latitude","longitude",
                "accuracy_radius","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM geoip_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("geoip_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# ip2asn IPv6
# ============================================================
class IP2ASNv6Source(V6Base):
    SOURCE_NAME = "ip2asn_v6"
    SOURCE_DESCRIPTION = "ip2asn IPv6 ASN+BGP前缀映射"

    def download(self) -> str:
        url = "https://iptoasn.com/data/ip2asn-v6.tsv.gz"
        return self._download_file(url, "ip2asn-v6.tsv.gz")

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

                    start_int = int(ipaddress.IPv6Address(start_ip))
                    end_int   = int(ipaddress.IPv6Address(end_ip))
                    start_hex = f"{start_int:032x}"
                    end_hex   = f"{end_int:032x}"

                    diff = end_int - start_int + 1
                    prefix_len = 128 - (diff - 1).bit_length() if diff > 1 else 128
                    network = f"{start_ip}/{prefix_len}"

                    yield {
                        "asn": asn, "as_name": as_name, "country_code": country,
                        "network": network,
                        "network_start_hex": start_hex, "network_end_hex": end_hex,
                        "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
                    }
                except (ValueError, IndexError, ipaddress.AddressValueError):
                    continue

    def load(self, records) -> int:
        cols = ["asn","as_name","country_code","network","network_start_hex",
                "network_end_hex","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM asn_info_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("asn_info_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# RPKI IPv6
# ============================================================
class RPKIv6Source(V6Base):
    SOURCE_NAME = "rpki_v6"
    SOURCE_DESCRIPTION = "Cloudflare RPKI IPv6 ROA"

    def download(self) -> str:
        # 复用IPv4插件已下载的JSON
        existing = os.path.join(self.config.cache_dir, "rpki", "rpki.json")
        if os.path.exists(existing):
            return existing
        url = "https://rpki.cloudflare.com/rpki.json"
        return self._download_file(url, "rpki.json")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for roa in data.get("roas", []):
            prefix = roa.get("prefix", "")
            if ":" not in prefix:
                continue  # IPv4 prefix, skip
            try:
                asn = int(str(roa.get("asn", "")).replace("AS", "").replace("as", ""))
            except (ValueError, AttributeError):
                continue
            try:
                start_hex, end_hex = ipv6_network_to_hex_range(prefix)
            except Exception:
                continue
            yield {
                "prefix": prefix, "asn": asn,
                "max_length": roa.get("maxLength"),
                "status": "valid", "ta": roa.get("ta", ""),
                "network_start_hex": start_hex, "network_end_hex": end_hex,
                "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
            }

    def load(self, records) -> int:
        cols = ["prefix","asn","max_length","status","ta",
                "network_start_hex","network_end_hex","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM rpki_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("rpki_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# Cloud Providers IPv6 (AWS, Cloudflare, GCP)
# ============================================================
class CloudV6Source(V6Base):
    SOURCE_NAME = "cloud_v6"
    SOURCE_DESCRIPTION = "云服务商IPv6段（AWS/CF/GCP/Azure）"

    def download(self) -> str:
        import requests
        sources = []

        # AWS
        try:
            r = requests.get("https://ip-ranges.amazonaws.com/ip-ranges.json", timeout=60)
            with open(os.path.join(self.cache_dir, "aws.json"), "w") as f:
                f.write(r.text)
            sources.append("aws")
        except Exception as e:
            self.logger.warning(f"aws v6: {e}")

        # GCP
        try:
            r = requests.get("https://www.gstatic.com/ipranges/cloud.json", timeout=60)
            with open(os.path.join(self.cache_dir, "gcp.json"), "w") as f:
                f.write(r.text)
            sources.append("gcp")
        except Exception as e:
            self.logger.warning(f"gcp v6: {e}")

        # Cloudflare
        try:
            r = requests.get("https://www.cloudflare.com/ips-v6", timeout=60)
            with open(os.path.join(self.cache_dir, "cf-v6.txt"), "w") as f:
                f.write(r.text)
            sources.append("cf")
        except Exception as e:
            self.logger.warning(f"cf v6: {e}")

        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        # AWS IPv6
        aws_file = os.path.join(self.cache_dir, "aws.json")
        if os.path.exists(aws_file):
            with open(aws_file) as f:
                data = json.load(f)
            for p in data.get("ipv6_prefixes", []):
                cidr = p.get("ipv6_prefix", "")
                if cidr:
                    try:
                        start_hex, end_hex = ipv6_network_to_hex_range(cidr)
                        yield {
                            "provider": "aws", "network": cidr,
                            "network_start_hex": start_hex, "network_end_hex": end_hex,
                            "region": p.get("region", ""), "service": p.get("service", ""),
                            "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
                        }
                    except Exception:
                        continue

        # GCP IPv6
        gcp_file = os.path.join(self.cache_dir, "gcp.json")
        if os.path.exists(gcp_file):
            with open(gcp_file) as f:
                data = json.load(f)
            for p in data.get("prefixes", []):
                cidr = p.get("ipv6Prefix", "")
                if cidr:
                    try:
                        start_hex, end_hex = ipv6_network_to_hex_range(cidr)
                        yield {
                            "provider": "gcp", "network": cidr,
                            "network_start_hex": start_hex, "network_end_hex": end_hex,
                            "region": p.get("scope", ""), "service": p.get("service", ""),
                            "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
                        }
                    except Exception:
                        continue

        # Cloudflare IPv6
        cf_file = os.path.join(self.cache_dir, "cf-v6.txt")
        if os.path.exists(cf_file):
            with open(cf_file) as f:
                for line in f:
                    cidr = line.strip()
                    if cidr and ":" in cidr:
                        try:
                            start_hex, end_hex = ipv6_network_to_hex_range(cidr)
                            yield {
                                "provider": "cloudflare", "network": cidr,
                                "network_start_hex": start_hex, "network_end_hex": end_hex,
                                "region": "", "service": "Cloudflare CDN",
                                "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
                            }
                        except Exception:
                            continue

    def load(self, records) -> int:
        cols = ["provider","network","network_start_hex","network_end_hex",
                "region","service","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM cloud_ranges_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("cloud_ranges_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# Tor Exits IPv6
# ============================================================
class TorV6Source(V6Base):
    SOURCE_NAME = "tor_v6"
    SOURCE_DESCRIPTION = "Tor出口节点IPv6"

    def download(self) -> str:
        # Tor list contains both v4 and v6 in same file
        url = "https://check.torproject.org/torbulkexitlist"
        return self._download_file(url, "tor-exits-all.txt")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                ip = line.strip()
                if not ip or ":" not in ip:
                    continue
                try:
                    addr = ipaddress.IPv6Address(ip)
                    int_val = int(addr)
                    hex_val = f"{int_val:032x}"
                    yield {
                        "network": f"{ip}/128",
                        "network_start_hex": hex_val,
                        "network_end_hex": hex_val,
                        "threat_type": "tor", "list_name": "tor_exits",
                        "severity": "medium",
                        "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
                    }
                except Exception:
                    continue

    def load(self, records) -> int:
        cols = ["network","network_start_hex","network_end_hex",
                "threat_type","list_name","severity","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM threat_intel_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("threat_intel_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# Spamhaus DROP IPv6
# ============================================================
class SpamhausV6Source(V6Base):
    SOURCE_NAME = "spamhaus_v6"
    SOURCE_DESCRIPTION = "Spamhaus DROP IPv6"

    def download(self) -> str:
        url = "https://www.spamhaus.org/drop/dropv6.txt"
        return self._download_file(url, "spamhaus-dropv6.txt")

    def parse(self, file_path: str) -> Generator[dict, None, None]:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("#"):
                    continue
                cidr = line.split(";")[0].strip().split()[0]
                if not cidr or ":" not in cidr:
                    continue
                try:
                    start_hex, end_hex = ipv6_network_to_hex_range(cidr)
                    yield {
                        "network": cidr,
                        "network_start_hex": start_hex, "network_end_hex": end_hex,
                        "threat_type": "spam", "list_name": "spamhaus_dropv6",
                        "severity": "high",
                        "source": self.SOURCE_NAME, "snapshot_date": self.today_str,
                    }
                except Exception:
                    continue

    def load(self, records) -> int:
        cols = ["network","network_start_hex","network_end_hex",
                "threat_type","list_name","severity","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM threat_intel_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("threat_intel_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# RIR IPv6
# ============================================================
class RIRv6Source(V6Base):
    SOURCE_NAME = "rir_v6"
    SOURCE_DESCRIPTION = "RIR IPv6 分配记录"

    def download(self) -> str:
        # Reuse files already downloaded by IPv4 plugin if present
        existing = os.path.join(self.config.cache_dir, "rir_delegated")
        if os.path.isdir(existing) and os.listdir(existing):
            return existing
        urls = {
            "arin": "https://ftp.arin.net/pub/stats/arin/delegated-arin-extended-latest",
            "ripe": "https://ftp.ripe.net/pub/stats/ripencc/delegated-ripencc-extended-latest",
            "apnic": "https://ftp.apnic.net/stats/apnic/delegated-apnic-extended-latest",
            "lacnic": "https://ftp.lacnic.net/pub/stats/lacnic/delegated-lacnic-extended-latest",
            "afrinic": "https://ftp.afrinic.net/pub/stats/afrinic/delegated-afrinic-extended-latest",
        }
        for rir, url in urls.items():
            self._download_file(url, f"delegated-{rir}-extended-latest.txt")
        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        for rir in ["arin","ripe","apnic","lacnic","afrinic"]:
            fpath = os.path.join(dir_path, f"delegated-{rir}-extended-latest.txt")
            if not os.path.exists(fpath):
                continue
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    parts = line.strip().split("|")
                    if len(parts) < 7 or parts[2] != "ipv6":
                        continue
                    try:
                        start = parts[3]
                        prefix_len = int(parts[4])
                        network = f"{start}/{prefix_len}"
                        start_hex, end_hex = ipv6_network_to_hex_range(network)
                        yield {
                            "rir": rir,
                            "country_code": parts[1].upper() if parts[1] != "*" else "",
                            "network": network,
                            "network_start_hex": start_hex,
                            "network_end_hex": end_hex,
                            "prefix_length": prefix_len,
                            "date_allocated": parts[5] if parts[5] != "00000000" else None,
                            "status": parts[6].split("[")[0].strip(),
                            "source": self.SOURCE_NAME,
                            "snapshot_date": self.today_str,
                        }
                    except Exception:
                        continue

    def load(self, records) -> int:
        cols = ["rir","country_code","network","network_start_hex","network_end_hex",
                "prefix_length","date_allocated","status","source","snapshot_date"]
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM rir_delegated_v6 WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()
        cnt = 0
        with self._bulk_insert_v6("rir_delegated_v6", cols) as insert:
            for r in records:
                insert(r); cnt += 1
        return cnt


# ============================================================
# Helpers
# ============================================================
def _safe_float(v):
    try:
        return float(v) if v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(v):
    try:
        return int(v) if v else 0
    except (ValueError, TypeError):
        return 0


# Plugin registry for v6
V6_PLUGINS = {
    "geoip_v6":    GeoIPv6Source,
    "ip2asn_v6":   IP2ASNv6Source,
    "rpki_v6":     RPKIv6Source,
    "cloud_v6":    CloudV6Source,
    "tor_v6":      TorV6Source,
    "spamhaus_v6": SpamhausV6Source,
    "rir_v6":      RIRv6Source,
}
