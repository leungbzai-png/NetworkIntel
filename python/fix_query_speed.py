# -*- coding: utf-8 -*-
"""
修复查询速度 - 优化query engine的SQL查询
"""
import sys, os, time, sqlite3, ipaddress, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils.config_loader import get_config

cfg = get_config()
db = cfg.db_path

def random_ipv4():
    while True:
        a = random.randint(1, 223)
        if a in (10, 127, 172, 192): continue
        return f"{a}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row

# 测试优化后的查询方式
# 关键：先用 network_start_int <= ip_int ORDER BY network_start_int DESC LIMIT 1
# 找到最近的起始段，再验证 end_int >= ip_int
# 这样只扫描1行而不是大量行

ip = "8.8.8.8"
ip_int = int(ipaddress.IPv4Address(ip))

print("测试优化查询...")

# 方法1：原始方式
plan1 = conn.execute("EXPLAIN QUERY PLAN SELECT country_code FROM geoip WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (ip_int, ip_int)).fetchall()
print(f"原始查询计划: {plan1}")

# 方法2：优化方式 - 先找最近的起始，再验证结束
optimized_sql = """
    SELECT country_code, country_name, region, city, latitude, longitude, accuracy_radius, network
    FROM geoip
    WHERE network_start_int <= ?
    ORDER BY network_start_int DESC
    LIMIT 1
"""
# 然后在Python里验证 end_int >= ip_int

plan2 = conn.execute(f"EXPLAIN QUERY PLAN {optimized_sql}", (ip_int,)).fetchall()
print(f"优化查询计划: {plan2}")

# 速度对比
ips = [random_ipv4() for _ in range(200)]

print("\n原始方式 (200 IP)...")
t0 = time.perf_counter()
for ip in ips:
    n = int(ipaddress.IPv4Address(ip))
    conn.execute("SELECT country_code FROM geoip WHERE network_start_int<=? AND network_end_int>=? LIMIT 1", (n,n)).fetchone()
t1 = time.perf_counter()
old_qps = 200/(t1-t0)
print(f"速度: {old_qps:.0f} IP/秒")

print("\n优化方式 (200 IP)...")
t0 = time.perf_counter()
for ip in ips:
    n = int(ipaddress.IPv4Address(ip))
    row = conn.execute(
        "SELECT country_code, network_end_int FROM geoip WHERE network_start_int<=? ORDER BY network_start_int DESC LIMIT 1",
        (n,)
    ).fetchone()
    # 验证在范围内
    if row and row[1] >= n:
        pass  # hit
t1 = time.perf_counter()
new_qps = 200/(t1-t0)
print(f"速度: {new_qps:.0f} IP/秒")
print(f"提升: {new_qps/old_qps:.1f}x")

conn.close()

# 如果优化方式更快，自动patch engine.py
if new_qps > old_qps * 1.5:
    print("\n✓ 优化有效，自动更新 query/engine.py ...")
    engine_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "query", "engine.py")
    with open(engine_path, "r", encoding="utf-8") as f:
        content = f.read()

    old_geoip = '''    row = conn.execute("""
        SELECT country_code, country_name, region, city,
               latitude, longitude, accuracy_radius, network
        FROM geoip
        WHERE network_start_int <= ? AND network_end_int >= ?
        ORDER BY (network_end_int - network_start_int) ASC
        LIMIT 1
    """, (ip_int, ip_int)).fetchone()'''

    new_geoip = '''    row = conn.execute("""
        SELECT country_code, country_name, region, city,
               latitude, longitude, accuracy_radius, network, network_end_int
        FROM geoip
        WHERE network_start_int <= ?
        ORDER BY network_start_int DESC
        LIMIT 1
    """, (ip_int,)).fetchone()
    if row and row["network_end_int"] < ip_int:
        row = None'''

    if old_geoip in content:
        content = content.replace(old_geoip, new_geoip)
        with open(engine_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("✓ engine.py 已更新")
    else:
        print("⚠ engine.py 格式不匹配，请手动更新")
else:
    print(f"\n优化效果不明显（{new_qps/old_qps:.1f}x），保持原有查询方式")

input("\nPress Enter to exit...")
