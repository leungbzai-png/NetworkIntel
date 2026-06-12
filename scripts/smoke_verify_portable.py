"""
exe 级冒烟验证（DB / 文件系统层面）。
====================================================
对「解压 + 启动后」的全新 portable 目录做断言，复现并验证用户 exe 冒烟暴露的
阻断问题是否已修复：

  * 自动生成 .env / configs/sources.yaml；
  * 运行时子目录齐全（live/cache/logs/reports/snapshots/backups/gdrive_sync）；
  * live/intel.db 存在且基础表已建好（尤其 threat_intel）；
  * 模拟「查询 1.1.1.1」「首页统计」的只读 SQL —— 必须返回结果/计数，
    而不是抛 sqlite3.OperationalError: no such table。

用法：  python smoke_verify_portable.py <portable_dir>
退出码 0 = 全部通过；非 0 = 有断言失败（发布必须停止）。
不读取 / 不打印任何 key。
"""
import os
import sqlite3
import sys
from pathlib import Path

# 启动后必须存在的基础表（含触发崩溃的 threat_intel）。
BASE_TABLES = {
    "asn_info", "geoip", "cloud_ranges", "peeringdb",
    "rir_delegated", "rpki", "threat_intel", "source_meta",
    "whois_cache", "query_history",
}
RUNTIME_DIRS = ("live", "cache", "logs", "reports", "snapshots", "backups", "gdrive_sync")
IP_1111_INT = 16843009  # 1.1.1.1


def main(base: Path) -> int:
    fails = []
    oks = []

    def check(cond, label):
        (oks if cond else fails).append(label)

    # 1) 首次运行生成的配置 / 目录
    check((base / ".env").exists(), ".env auto-generated")
    check((base / "configs" / "sources.yaml").exists(), "configs/sources.yaml auto-generated")
    for d in RUNTIME_DIRS:
        check((base / d).is_dir(), f"runtime dir {d}/")

    db_path = base / "live" / "intel.db"
    check(db_path.exists(), "live/intel.db exists")

    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        try:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            for t in sorted(BASE_TABLES):
                check(t in tables, f"table {t} exists")
            check("threat_intel" in tables, "threat_intel exists (key regression)")

            # 2) 首页统计读路径：空库各表 COUNT(*) 必须返回（多为 0），不得 no such table
            for t in ("asn_info", "geoip", "threat_intel", "cloud_ranges", "rpki"):
                try:
                    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    check(True, f"stats COUNT({t})={n} (no OperationalError)")
                except sqlite3.OperationalError as e:
                    check(False, f"stats COUNT({t}) raised: {e}")

            # 3) 查询 1.1.1.1 读路径：复现 query_ip 的 v4 子查询，必须不抛 no such table
            v4_reads = {
                "geoip":        "SELECT 1 FROM geoip WHERE network_start_int <= ? LIMIT 1",
                "asn_info":     "SELECT 1 FROM asn_info WHERE network_start_int <= ? AND network_end_int >= ? LIMIT 1",
                "rpki":         "SELECT 1 FROM rpki WHERE network_start_int <= ? AND network_end_int >= ? LIMIT 1",
                "rir_delegated":"SELECT 1 FROM rir_delegated WHERE network_start_int <= ? AND network_end_int >= ? LIMIT 1",
                "cloud_ranges": "SELECT 1 FROM cloud_ranges WHERE network_start_int <= ? AND network_end_int >= ? LIMIT 1",
                "threat_intel": "SELECT 1 FROM threat_intel WHERE network_start_int <= ? AND network_end_int >= ? LIMIT 1",
                "whois_cache":  "SELECT 1 FROM whois_cache WHERE query = ? LIMIT 1",
            }
            for t, sql in v4_reads.items():
                try:
                    nparams = sql.count("?")
                    params = (["1.1.1.1"] if t == "whois_cache"
                              else [IP_1111_INT] * nparams)
                    conn.execute(sql, params).fetchone()
                    check(True, f"query 1.1.1.1 read on {t} (no OperationalError)")
                except sqlite3.OperationalError as e:
                    check(False, f"query 1.1.1.1 read on {t} raised: {e}")
        finally:
            conn.close()

    print("PASS:")
    for o in oks:
        print(f"  [OK]   {o}")
    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  [FAIL] {f}")
    print(f"\n{len(oks)} passed, {len(fails)} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python smoke_verify_portable.py <portable_dir>")
        sys.exit(2)
    sys.exit(main(Path(sys.argv[1])))
