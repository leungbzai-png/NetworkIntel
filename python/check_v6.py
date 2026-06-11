# -*- coding: utf-8 -*-
import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

db = r"E:\NetworkIntel\live\intel.db"
conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

print("=" * 60)
print("IPv6 Database Statistics")
print("=" * 60)
print(f"Total DB size: {os.path.getsize(db) / 1024 / 1024:.1f} MB")
print()

tables = [
    ("geoip_v6", "GeoIP IPv6"),
    ("asn_info_v6", "ASN IPv6"),
    ("rpki_v6", "RPKI IPv6"),
    ("rir_delegated_v6", "RIR IPv6"),
    ("cloud_ranges_v6", "Cloud IPv6"),
    ("threat_intel_v6", "Threats IPv6"),
]

total = 0
for table, name in tables:
    try:
        cnt = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"  {name:20} {cnt:>12,} records")
        total += cnt
    except Exception as e:
        print(f"  {name:20} ERROR: {e}")

print(f"  {'TOTAL':20} {total:>12,} records")
print()

# Test queries
print("=" * 60)
print("Sample IPv6 Queries")
print("=" * 60)
test_ips = [
    ("2606:4700:4700::1111", "Cloudflare DNS"),
    ("2001:4860:4860::8888", "Google DNS"),
    ("2a00:1450:4001::1",    "Google Europe"),
    ("2620:fe::fe",          "Quad9 DNS"),
    ("2001:db8::1",          "Documentation"),
]
import ipaddress
for ip, desc in test_ips:
    try:
        ip_hex = f"{int(ipaddress.IPv6Address(ip)):032x}"
        geo = conn.execute("SELECT country_name FROM geoip_v6 WHERE network_start_hex<=? AND network_end_hex>=? LIMIT 1", (ip_hex, ip_hex)).fetchone()
        asn = conn.execute("SELECT asn, as_name FROM asn_info_v6 WHERE network_start_hex<=? AND network_end_hex>=? LIMIT 1", (ip_hex, ip_hex)).fetchone()
        cloud = conn.execute("SELECT provider FROM cloud_ranges_v6 WHERE network_start_hex<=? AND network_end_hex>=? LIMIT 1", (ip_hex, ip_hex)).fetchone()
        g = geo['country_name'] if geo else "—"
        a = f"AS{asn['asn']} {asn['as_name']}" if asn else "—"
        c = cloud['provider'] if cloud else "—"
        print(f"  {ip:30} [{desc}]")
        print(f"    geo={g}, asn={a}, cloud={c}")
    except Exception as e:
        print(f"  {ip}: ERROR {e}")

conn.close()
input("\nPress Enter to exit...")
