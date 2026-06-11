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
    ap.add_argument("--query", default="8.8.8.8", help="查询的 IP（默认 8.8.8.8）")
    ap.add_argument("--provider", default="bgpview",
                    help="实测的在线 provider（默认 bgpview，无需 key）。"
                         "指定 ipinfo 等需 key 的 provider 时，仅在已配置 key 时才发起请求。")
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

    # ── 实测查询（仅指定的在线 provider）──────────────────
    from providers.online import get_online_provider, IMPLEMENTED
    name = args.provider
    _hr(f"在线实测: provider={name}  query={args.query}")

    if args.no_network:
        print("  已跳过（--no-network）")
        return 0

    p = get_online_provider(name)
    if p is None:
        print(f"  [跳过] 未知 provider: {name}")
        return 0

    # 需要 key 的 provider：仅在已配置 key 时才请求；否则清晰提示，不崩溃
    if p.requires_api_key:
        v = p.validate_config()
        if not v.ok:
            print(f"  [跳过] {name} 需要 API key 但未配置（{','.join(v.missing)}）。")
            print(f"         请在 .env 设置后重试（key 不会被打印）。")
            return 0
    if name not in IMPLEMENTED:
        print(f"  [跳过] {name} 仍是骨架（query 未实现）。")
        return 0

    try:
        res = p.query(args.query)
    except Exception as e:
        print(f"  [异常] {type(e).__name__}: {e}")
        return 1

    if res.error:
        print(f"  查询失败: {res.error}")
        return 0

    d = res.data
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
    else:
        for k, val in d.items():
            if k != "raw":
                print(f"  {k:<12}: {val}")
    print(f"  fetched_at: {d.get('fetched_at')}")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
