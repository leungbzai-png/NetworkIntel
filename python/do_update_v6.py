# -*- coding: utf-8 -*-
"""
NetworkIntel - IPv6 数据初始化/更新
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import get_config
from utils.schema import init_db
from utils.schema_v6 import init_v6_tables
from datasources.plugins_v6 import V6_PLUGINS


def main():
    cfg = get_config()
    init_db(cfg.db_path)
    init_v6_tables(cfg.db_path)

    print("NetworkIntel - IPv6 Data Update")
    print("=" * 60)
    print(f"Found {len(V6_PLUGINS)} IPv6 sources")
    print()

    for name, cls in V6_PLUGINS.items():
        print(f"[{name}] Updating...")
        plugin = cls()
        # Force snapshot category for v6 plugins
        plugin.snapshot_category = "registry"
        def cb(step, pct):
            print(f"  {step} ({pct}%)")
        try:
            result = plugin.update(progress_callback=cb)
            if result["success"]:
                print(f"  OK - {result['record_count']:,} records")
            else:
                print(f"  FAILED: {result['error']}")
        except Exception as e:
            print(f"  EXCEPTION: {e}")
        print()

    print("Done.")


if __name__ == "__main__":
    main()
