# -*- coding: utf-8 -*-
import sys, os, time, sqlite3, ipaddress, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import get_config

cfg = get_config()
db = cfg.db_path

print("检查索引状态...")
conn = sqlite3.connect(db)

# 查看现有索引
indexes = conn.execute("SELECT name, tbl_name FROM sqlite_master WHERE type='index' ORDER BY tbl_name").fetchall()
print(f"现有索引数量: {len(indexes)}")
for idx in indexes:
    print(f"  {idx[1]:25} → {idx[0]}")

print()

# 检查geoip表的查询计划
conn.execute("PRAGMA optimize")
conn.execute("ANALYZE")

ip_int = int(ipaddress.IPv4Address("8.8.8.8"))
plan = conn.execute(
    "EXPLAIN QUERY PLAN SELECT country_code FROM geoip WHERE network_start_int<=? AND network_end_int>=? LIMIT 1",
    (ip_int, ip_int)
).fetchall()
print("geoip查询计划:")
for row in plan:
    print(f"  {row}")

print()

# 如果没走索引，重建
needs_rebuild = any("SCAN" in str(row) and "USING INDEX" not in str(row) for row in plan)
if needs_rebuild:
    print("⚠️  没走索引！重建中...")
    conn.execute("DROP INDEX IF EXISTS idx_geoip_range")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_geoip_range ON geoip(network_start_int, network_end_int)")
    conn.execute("DROP INDEX IF EXISTS idx_asn_range")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_asn_range ON asn_info(network_start_int, network_end_int)")
    conn.execute("DROP INDEX IF EXISTS idx_threat_range")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_threat_range ON threat_intel(network_start_int, network_end_int)")
    conn.execute("ANALYZE")
    conn.commit()
    print("✓ 索引重建完成")
else:
    print("✓ 索引正常")

conn.close()

# 重测速度
print()
print("重测速度（100个IP）...")
conn2 = sqlite3.connect(db)
conn2.row_factory = sqlite3.Row

def random_ipv4():
    while True:
        a = random.randint(1, 223)
        if a in (10, 127, 172, 192): continue
        return f"{a}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

ips = [random_ipv4() for _ in range(100)]
t0 = time.perf_counter()
for ip in ips:
    n = int(ipaddress.IPv4Address(ip))
    conn2.execute("SELECT country_code FROM geoip WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (n,n)).fetchone()
    conn2.execute("SELECT asn FROM asn_info WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (n,n)).fetchone()
    conn2.execute("SELECT threat_type FROM threat_intel WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (n,n)).fetchone()
t1 = time.perf_counter()
conn2.close()

qps = 100 / (t1 - t0)
print(f"速度: {qps:,.0f} IP/秒  ({(t1-t0)/100*1000:.2f} ms/IP)")

input("\nPress Enter to exit...")
