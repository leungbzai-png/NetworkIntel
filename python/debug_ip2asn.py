# -*- coding: utf-8 -*-
import sys, os, gzip
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

cache_file = r"E:\NetworkIntel\cache\ip2asn\ip2asn-v4.tsv.gz"

print(f"File exists: {os.path.exists(cache_file)}")
print(f"File size: {os.path.getsize(cache_file):,} bytes")
print()
print("First 10 lines:")
print("-" * 60)

count = 0
ok = 0
errors = []

with gzip.open(cache_file, "rt", encoding="utf-8") as f:
    for i, line in enumerate(f):
        line = line.strip()
        if i < 10:
            print(repr(line))
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        count += 1
        try:
            start_int = int(parts[0])
            end_int   = int(parts[1])
            asn       = int(parts[2])
            if asn == 0:
                continue
            import ipaddress
            start_ip = str(ipaddress.IPv4Address(start_int))
            ok += 1
        except Exception as e:
            if len(errors) < 5:
                errors.append(f"line {i}: {repr(line[:80])} -> {e}")

print()
print(f"Total lines: {count}")
print(f"Parseable: {ok}")
print(f"Sample errors:")
for e in errors:
    print(f"  {e}")

input("\nPress Enter to exit...")
