# -*- coding: utf-8 -*-
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.config_loader import get_config
from utils.schema import init_db
from datasources.plugin_registry import get_enabled_plugins
from datasources.setup_profiles import resolve_selection
from update_coordinator import get_coordinator, UpdateTrigger, UpdateState


def main() -> int:
    """
    离线 CLI 更新入口（v0.3.0：统一走 UpdateCoordinator 串行队列）。
    - 与 GUI/调度器共用同一套写库执行层（进程内单写者）。
    - 缺 API Key 的源（目前仅 geoip 需 MaxMind Key）标记 skipped，不影响其它源。
    - 仅在存在 failed 时返回非零退出码（skipped 不算失败）。
    """
    cfg = get_config()
    init_db(cfg.db_path)

    enabled = list(get_enabled_plugins().keys())
    # 缺 key 的源自动剔除并标记 skipped（resolve_selection 不读 key 明文）。
    sel = resolve_selection("custom", custom=enabled)
    selected = sel["selected"]
    skipped = sel["skipped"]

    print("NetworkIntel - Data Update")
    print("=" * 50)
    print(f"Found {len(enabled)} enabled sources "
          f"({len(selected)} to update, {len(skipped)} skipped)")
    print()

    for sk in skipped:
        print(f"[{sk['name']}] SKIPPED - {sk['reason']}")
    if skipped:
        print()

    coord = get_coordinator()
    jobs = coord.enqueue_many(selected, UpdateTrigger.CLI)

    failed = 0
    # 队列严格串行执行；按入队顺序等待并输出，天然有序。
    for job in jobs:
        print(f"[{job.source_name}] Updating...")
        job.wait()
        if job.status == UpdateState.SUCCESS:
            print(f"  OK - {job.records_loaded:,} records "
                  f"({job.duration_seconds:.1f}s)")
        elif job.status == UpdateState.SKIPPED:
            print(f"  SKIPPED - {job.message}")
        else:
            failed += 1
            tag = "DB LOCKED" if job.error_type == "db_locked" else "FAILED"
            print(f"  {tag}: {job.message}")
        print()

    ok = sum(1 for j in jobs if j.status == UpdateState.SUCCESS)
    print("-" * 50)
    print(f"Done. success={ok} failed={failed} "
          f"skipped={len(skipped) + sum(1 for j in jobs if j.status == UpdateState.SKIPPED)}")

    coord.shutdown(wait=True, timeout=10.0)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
