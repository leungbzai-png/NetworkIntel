# -*- coding: utf-8 -*-
import sys, os, gzip, ipaddress
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import get_config
from utils.schema import init_db, get_connection

cfg = get_config()
init_db(cfg.db_path)

cache_file = r"E:\NetworkIntel\cache\ip2asn\ip2asn-v4.tsv.gz"
print(f"Parsing {cache_file} ...")

count = 0
errors = []

with gzip.open(cache_file, "rt", encoding="utf-8") as f:
    for i, line in enumerate(f):
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
            count += 1
        except Exception as e:
            if len(errors) < 3:
                errors.append(f"line {i}: {e}")

print(f"Parsed {count:,} records")
if errors:
    print("Errors:", errors)

if count == 0:
    print("ERROR: still 0 - check errors above")
    input("Press Enter...")
    sys.exit(1)

# Write to DB
print("Writing to DB...")
conn = get_connection(cfg.db_path)
conn.execute("DELETE FROM asn_info WHERE source='ip2asn'")
conn.commit()

batch = []
with gzip.open(cache_file, "rt", encoding="utf-8") as f:
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
            if asn == 0:
                continue
            country  = parts[3].strip()
            as_name  = parts[4].strip()
            start_int = int(ipaddress.IPv4Address(start_ip))
            end_int   = int(ipaddress.IPv4Address(end_ip))
            diff = end_int - start_int + 1
            prefix_len = 32 - (diff - 1).bit_length() if diff > 1 else 32
            network = f"{start_ip}/{prefix_len}"
            batch.append((asn, as_name, country, network, start_int, end_int, "ip2asn", "2026-06-05"))
            if len(batch) >= 5000:
                conn.executemany(
                    "INSERT INTO asn_info (asn,as_name,country_code,network,network_start_int,network_end_int,source,snapshot_date) VALUES (?,?,?,?,?,?,?,?)",
                    batch
                )
                conn.commit()
                batch.clear()
        except Exception:
            continue

if batch:
    conn.executemany(
        "INSERT INTO asn_info (asn,as_name,country_code,network,network_start_int,network_end_int,source,snapshot_date) VALUES (?,?,?,?,?,?,?,?)",
        batch
    )
    conn.commit()

final = conn.execute("SELECT COUNT(*) FROM asn_info WHERE source='ip2asn'").fetchone()[0]
conn.close()
print(f"Done! {final:,} records in DB")
input("Press Enter to exit...")
