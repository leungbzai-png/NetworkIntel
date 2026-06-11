# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import get_config
from utils.schema import init_db
from datasources.plugin_registry import get_enabled_plugins

def main():
    cfg = get_config()
    init_db(cfg.db_path)
    plugins = get_enabled_plugins()
    print("NetworkIntel - Data Update")
    print("=" * 50)
    print(f"Found {len(plugins)} enabled sources")
    print()

    for name, plugin in plugins.items():
        print(f"[{name}] Updating...")
        def cb(step, pct, _name=name):
            print(f"  {step} ({pct}%)")
        result = plugin.update(progress_callback=cb)
        if result["success"]:
            print(f"  OK - {result['record_count']:,} records")
        else:
            print(f"  FAILED: {result['error']}")
        print()

    print("Done.")

if __name__ == "__main__":
    main()
