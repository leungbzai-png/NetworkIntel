# -*- coding: utf-8 -*-
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

db = r"E:\NetworkIntel\live\intel.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print("=" * 60)
print("Database Statistics")
print("=" * 60)
print(f"File size: {os.path.getsize(db) / 1024 / 1024:.1f} MB")
print()

# Records per table
tables = [
    ("geoip", "geoip"),
    ("asn_info", "ip2asn"),
    ("rpki", "rpki"),
    ("rir_delegated", "rir_delegated"),
    ("cloud_ranges", "cloud_ranges"),
    ("threat_intel", "threat_intel"),
]

for table, name in tables:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{name:20} {cnt:>15,} records")
    except Exception as e:
        print(f"{name:20} error: {e}")

print()
print("=" * 60)
print("Total IPv4 addresses covered by each source")
print("=" * 60)

# Sum the IP ranges to see total unique IPs covered
for table, name in [("geoip","GeoIP"), ("asn_info","ASN"), ("rpki","RPKI")]:
    try:
        r = conn.execute(f"""
            SELECT SUM(network_end_int - network_start_int + 1) FROM {table}
            WHERE network_end_int <= 4294967295
        """).fetchone()[0]
        if r:
            print(f"{name:10} covers {r:>15,} IPs ({r/4294967295*100:.1f}% of all IPv4)")
    except Exception as e:
        print(f"{name}: error: {e}")

print()
print("=" * 60)
print("Sample queries (random IPs)")
print("=" * 60)

test_ips = ["8.8.8.8", "1.1.1.1", "114.114.114.114", "208.67.222.222"]
for ip in test_ips:
    import ipaddress
    ip_int = int(ipaddress.IPv4Address(ip))
    geo = conn.execute("SELECT country_name, city FROM geoip WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (ip_int, ip_int)).fetchone()
    asn = conn.execute("SELECT asn, as_name FROM asn_info WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (ip_int, ip_int)).fetchone()
    print(f"{ip:18} geo={dict(geo) if geo else 'NONE'}, asn={dict(asn) if asn else 'NONE'}")

conn.close()
input("\nPress Enter to exit...")
