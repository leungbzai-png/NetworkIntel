"""
NetworkIntel - Provider 手动自检脚本
====================================
用途：
  * 列出兼容注册表中的现有源（17 个）与在线 provider。
  * 校验各 provider 配置（不打印任何真实 key）。
  * 默认对 BGPView 做一次真实查询（无需 key），其余在线 provider 仅显示配置状态。

用法（在项目根目录）：
  python scripts/provider_smoke_test.py                 # 默认查询 8.8.8.8
  python scripts/provider_smoke_test.py --query 1.1.1.1
  python scripts/provider_smoke_test.py --no-network    # 不发任何网络请求

说明：
  * 不会调用需要 API key 的在线 provider（仅展示 validate_config 结果）。
  * 输出绝不包含真实 key。
"""
import argparse
import os
import sys

# 控制台可能是非 UTF-8（如 cp932/cp936）；安全输出，避免 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "python"))


def _hr(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> int:
    ap = argparse.ArgumentParser(description="NetworkIntel provider 自检")
    ap.add_argument("--query", default=None,
                    help="要查询的 IP。仅在显式提供时才发起在线请求（经缓存+限速旁路执行器）。")
    ap.add_argument("--provider", default="bgpview",
                    help="在线 provider（默认 bgpview，无需 key）。需 key 者仅在已配置时才请求。")
    ap.add_argument("--force-refresh", action="store_true", help="绕过缓存强制回源")
    ap.add_argument("--cache-stats", action="store_true", help="打印在线缓存统计")
    ap.add_argument("--purge-cache", action="store_true", help="清理已过期缓存条目")
    ap.add_argument("--no-network", action="store_true", help="不发任何网络请求")
    args = ap.parse_args()

    # ── 现有源（兼容适配器）────────────────────────────────
    _hr("兼容注册表：现有数据源（旧 plugin 经适配器视图化）")
    try:
        from providers.registry import get_provider_registry
        reg = get_provider_registry()
        for row in reg.describe_all():
            key_flag = "需要KEY" if row["requires_api_key"] else "无需KEY"
            print(f"  {row['name']:<18} {row['category']:<13} {row['kind']:<13} {key_flag}")
        print(f"  合计: {len(reg.names())} 个")
    except Exception as e:
        print(f"  [错误] 无法构建注册表: {type(e).__name__}: {e}")

    # ── 在线 provider ──────────────────────────────────────
    _hr("在线 Provider（旁路，未接入离线主查询）")
    try:
        from providers.online import get_online_providers, IMPLEMENTED
        online = get_online_providers()
    except Exception as e:
        print(f"  [错误] 无法加载在线 provider: {type(e).__name__}: {e}")
        return 1

    for p in online:
        v = p.validate_config()
        status = "已配置" if v.ok else f"未配置({','.join(v.missing)})"
        impl = "已实现" if p.name in IMPLEMENTED else "骨架"
        keyflag = "需要KEY" if p.requires_api_key else "无需KEY"
        print(f"  {p.name:<14} {p.category.value:<13} {keyflag:<8} {impl:<6} 配置:{status}")

    # ── 缓存维护 ───────────────────────────────────────────
    if args.cache_stats or args.purge_cache:
        _hr("在线缓存")
        try:
            from providers.cache import OnlineCache
            c = OnlineCache()
            if args.purge_cache:
                print(f"  已清理过期条目: {c.purge_expired()} 条")
            if args.cache_stats:
                s = c.stats()
                print(f"  db_path : {s.get('db_path')}")
                print(f"  total   : {s.get('total')}  expired: {s.get('expired')}")
                print(f"  by_provider: {s.get('by_provider')}")
        except Exception as e:
            print(f"  [错误] {type(e).__name__}: {e}")

    # ── 实测查询（仅在显式 --query 时；经缓存+限速旁路执行器）──
    if args.query is None:
        _hr("在线实测")
        print("  未指定 --query，跳过在线请求（默认不联网）。")
        print("  示例: python scripts/provider_smoke_test.py --provider bgpview --query 8.8.8.8")
        print("\n完成。")
        return 0

    name = args.provider
    _hr(f"在线实测: provider={name}  query={args.query}  force_refresh={args.force_refresh}")
    if args.no_network:
        print("  已跳过（--no-network）")
        return 0

    try:
        from providers.online_runner import run_provider
        res = run_provider(name, args.query, force_refresh=args.force_refresh)
    except Exception as e:
        print(f"  [异常] {type(e).__name__}: {e}")
        return 1

    if not res.ok:
        # 缺 key / 限速 / 网络失败均在此优雅呈现（不含 token）
        print(f"  未返回结果: {res.error}")
        print("\n完成。")
        return 0

    d = res.data
    print(f"  来源      : {'缓存' if res.from_cache else '实时回源'}")
    if name == "bgpview":
        print(f"  IP        : {d.get('ip')}")
        print(f"  ASN       : AS{d.get('asn')}  {d.get('asn_name')}")
        print(f"  Prefix    : {d.get('prefix')}")
        print(f"  Country   : {d.get('country_code')}")
        print(f"  RIR       : {d.get('rir')}")
    elif name == "ipinfo":
        print(f"  IP        : {d.get('ip')}")
        print(f"  Location  : {d.get('city')}, {d.get('region')}, {d.get('country_code')}")
        print(f"  Lat/Lon   : {d.get('latitude')}, {d.get('longitude')}")
        print(f"  ASN       : AS{d.get('asn')}  {d.get('asn_name')}")
        print(f"  Timezone  : {d.get('timezone')}")
    elif name == "ip2location":
        print(f"  IP        : {d.get('ip')}")
        print(f"  Location  : {d.get('city')}, {d.get('region')}, {d.get('country_name')} ({d.get('country_code')})")
        print(f"  Lat/Lon   : {d.get('latitude')}, {d.get('longitude')}")
        print(f"  ASN       : AS{d.get('asn')}  {d.get('asn_name')}")
        print(f"  ISP       : {d.get('isp')}")
        print(f"  Usage     : {d.get('usage_type')}")
    else:
        for k, val in d.items():
            if k != "raw":
                print(f"  {k:<12}: {val}")
    print(f"  fetched_at: {d.get('fetched_at')}")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
