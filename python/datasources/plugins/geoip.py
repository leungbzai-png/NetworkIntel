"""
NetworkIntel - GeoIP 插件
数据源：MaxMind GeoLite2 City + ASN
需要在 sources.yaml 配置 license_key
"""

import os
import gzip
import csv
from pathlib import Path
from typing import Generator

from datasources.base import DataSourceBase
from utils.ip_utils import network_to_range


class GeoIPSource(DataSourceBase):
    SOURCE_NAME = "geoip"
    SOURCE_DESCRIPTION = "MaxMind GeoLite2 城市+ASN地理信息库"

    def download(self) -> str:
        license_key = self.source_config.get("license_key", "")
        if not license_key or license_key == "YOUR_MAXMIND_LICENSE_KEY_HERE":
            raise ValueError(
                "MaxMind License Key not configured. "
                "Please visit https://www.maxmind.com/en/geolite2/signup"
            )

        base = "https://download.maxmind.com/app/geoip_download"
        city_url = f"{base}?edition_id=GeoLite2-City-CSV&license_key={license_key}&suffix=zip"
        asn_url  = f"{base}?edition_id=GeoLite2-ASN-CSV&license_key={license_key}&suffix=zip"

        city_zip = self._download_file(city_url, "GeoLite2-City-CSV.zip")
        asn_zip  = self._download_file(asn_url,  "GeoLite2-ASN-CSV.zip")

        # 解压到 cache 目录
        import zipfile
        for zf_path in [city_zip, asn_zip]:
            with zipfile.ZipFile(zf_path, "r") as zf:
                zf.extractall(self.cache_dir)

        return self.cache_dir

    def parse(self, dir_path: str) -> Generator[dict, None, None]:
        """解析 GeoLite2-City-Blocks-IPv4.csv + GeoLite2-City-Locations-en.csv"""
        import glob
        cache = Path(dir_path)

        # 用 glob 递归搜索，兼容 Windows 路径
        blocks_file = None
        locations_file = None

        # glob pattern search (more reliable on Windows than rglob)
        for pattern in ["**/GeoLite2-City-Blocks-IPv4.csv"]:
            results = list(cache.rglob("GeoLite2-City-Blocks-IPv4.csv"))
            if results:
                blocks_file = str(results[0])
                break

        for pattern in ["**/GeoLite2-City-Locations-en.csv"]:
            results = list(cache.rglob("GeoLite2-City-Locations-en.csv"))
            if results:
                locations_file = str(results[0])
                break

        # Log what we found for debugging
        self.logger.info(f"[geoip] cache_dir={dir_path}")
        self.logger.info(f"[geoip] blocks_file={blocks_file}")
        self.logger.info(f"[geoip] locations_file={locations_file}")

        # If rglob fails, try os.walk as fallback
        if not blocks_file or not locations_file:
            import os
            for root, dirs, files in os.walk(dir_path):
                for fname in files:
                    if fname == "GeoLite2-City-Blocks-IPv4.csv":
                        blocks_file = os.path.join(root, fname)
                    if fname == "GeoLite2-City-Locations-en.csv":
                        locations_file = os.path.join(root, fname)

        self.logger.info(f"[geoip] after walk: blocks={blocks_file}, locs={locations_file}")

        if not blocks_file or not locations_file:
            # List cache dir contents for diagnosis
            import os
            all_files = []
            for root, dirs, files in os.walk(dir_path):
                for fname in files:
                    all_files.append(os.path.join(root, fname))
            self.logger.error(f"[geoip] cache contents: {all_files[:20]}")
            raise FileNotFoundError(
                f"GeoLite2 CSV not found in {dir_path}. "
                f"Files found: {[os.path.basename(f) for f in all_files[:10]]}"
            )

        # 加载 geoname_id → 位置信息 映射
        locations = {}
        with open(locations_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gid = row.get("geoname_id", "")
                if gid:
                    locations[gid] = {
                        "country_code": row.get("country_iso_code", ""),
                        "country_name": row.get("country_name", ""),
                        "region":       row.get("subdivision_1_name", ""),
                        "city":         row.get("city_name", ""),
                    }

        # 解析 blocks
        with open(blocks_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                network = row.get("network", "")
                if not network:
                    continue
                start_int, end_int = network_to_range(network)
                gid = row.get("geoname_id") or row.get("registered_country_geoname_id", "")
                loc = locations.get(gid, {})

                yield {
                    "network": network,
                    "network_start": network.split("/")[0],
                    "network_end": "",
                    "network_start_int": start_int,
                    "network_end_int":   end_int,
                    "country_code":   loc.get("country_code", ""),
                    "country_name":   loc.get("country_name", ""),
                    "region":         loc.get("region", ""),
                    "city":           loc.get("city", ""),
                    "latitude":       _safe_float(row.get("latitude")),
                    "longitude":      _safe_float(row.get("longitude")),
                    "accuracy_radius": _safe_int(row.get("accuracy_radius")),
                    "source":         self.SOURCE_NAME,
                    "snapshot_date":  self.today_str,
                }

    def load(self, records: Generator[dict, None, None]) -> int:
        columns = [
            "network", "network_start", "network_end",
            "network_start_int", "network_end_int",
            "country_code", "country_name", "region", "city",
            "latitude", "longitude", "accuracy_radius",
            "source", "snapshot_date",
        ]
        count = 0
        # 先清空旧数据
        from utils.schema import get_connection
        conn = get_connection(self.config.db_path)
        conn.execute("DELETE FROM geoip WHERE source = ?", (self.SOURCE_NAME,))
        conn.commit()
        conn.close()

        with self._bulk_insert("geoip", columns) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count


def _safe_float(v) -> float:
    try:
        return float(v) if v else 0.0
    except (ValueError, TypeError):
        return 0.0


def _safe_int(v) -> int:
    try:
        return int(v) if v else 0
    except (ValueError, TypeError):
        return 0
