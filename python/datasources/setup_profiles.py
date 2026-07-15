# -*- coding: utf-8 -*-
"""
NetworkIntel - 首次初始化 / 数据源选择下载（v0.2.0 Phase 2）
=============================================================
本模块只负责「选哪些源 + 串行下载它们」，不新增任何 Provider、不改 query_ip、
不接入在线 Provider。设计要点：

  1. 预设分组（minimal / recommended / full）+ custom 逐源勾选。
  2. geoip 依赖 MaxMind Key —— 无 key 时自动从选择中剔除并给出原因，绝不读 key 明文。
  3. 串行下载（**不是** scheduler.trigger_all 的并发模型）。首次初始化往往面对空库，
     并发写 intel.db 会触发已审计的 `database is locked`（见 docs/SQLITE_CONCURRENCY_AUDIT.md），
     因此这里逐个执行 plugin.update()，与 do_update.py 的「串行 CLI」安全路径一致。
  4. 下载执行器可注入（updater 参数），使编排逻辑可在零网络下测试。

数据库状态检测同样放在此处，供 GUI 横幅与首次初始化入口复用：
缺库 **或** 空库（无任何成功落库的源）都视为「需要初始化」。
"""

import os
import sqlite3
from typing import Callable, Iterable, Optional

from datasources.plugin_registry import PLUGIN_REGISTRY
from utils.config_loader import get_config


# ── 预设分组 ──────────────────────────────────────────────────
# 以插件注册表的顺序为规范顺序，保证下载与展示顺序确定。
CANONICAL_ORDER = list(PLUGIN_REGISTRY.keys())

# 需要 API Key 才能下载的源（env 变量名）。目前仅 geoip 需要 MaxMind Key。
KEY_REQUIRED = {
    "geoip": "MAXMIND_LICENSE_KEY",
}

# 最小：本地查询的核心（ASN/BGP 前缀映射 + 地理库）。
_MINIMAL = {"geoip", "ip2asn"}

# 推荐：最小 + 注册分配 + RPKI + 全部云段 + 主流威胁列表（除可选的 peeringdb）。
_RECOMMENDED = _MINIMAL | {
    "rir_delegated", "rpki",
    "cloud_aws", "cloud_azure", "cloud_gcp",
    "cloud_cloudflare", "cloud_hetzner", "cloud_vultr",
    "tor_exits", "vpn_x4bnet", "spamhaus_drop",
    "firehol", "abusech", "emerging_threats",
}

# 完整：注册表中全部 17 个源（含默认关闭的 peeringdb）。
_FULL = set(CANONICAL_ORDER)

PROFILE_SOURCES: dict = {
    "minimal": _MINIMAL,
    "recommended": _RECOMMENDED,
    "full": _FULL,
}

# 供 UI 展示的顺序与文案（不含 custom，custom 由逐源勾选驱动）。
PROFILE_ORDER = ("minimal", "recommended", "full")
PROFILE_LABELS = {
    "minimal": "最小",
    "recommended": "推荐",
    "full": "完整",
    "custom": "自定义",
}
PROFILE_DESCRIPTIONS = {
    "minimal": "仅 ip2asn + geoip：ASN/BGP 前缀映射与地理库，满足基本离线查询。",
    "recommended": "最小 + RIR 分配 + RPKI + 全部云段 + 主流威胁列表，覆盖日常分析。",
    "full": "全部数据源（含默认关闭的 peeringdb）。体积最大、耗时最长。",
    "custom": "逐源勾选，自由组合。",
}


def configured_keys() -> set:
    """返回当前已配置 key 的 env 变量名集合（绝不返回 key 本身）。"""
    try:
        status = get_config().get_key_status()
    except Exception:
        return set()
    return {var for var, ok in status.items() if ok}


def source_catalog() -> list:
    """
    返回 custom 勾选所需的源清单（注册表顺序）。
    每项：{name, description, enabled_default, requires_key, in_recommended}
    描述取自 sources.yaml；不含任何 key。
    """
    try:
        sources = get_config().get_all_sources()
    except Exception:
        sources = {}
    out = []
    for name in CANONICAL_ORDER:
        scfg = sources.get(name, {}) or {}
        out.append({
            "name": name,
            "description": scfg.get("description", ""),
            "enabled_default": bool(scfg.get("enabled", True)),
            "requires_key": KEY_REQUIRED.get(name),
            "in_recommended": name in _RECOMMENDED,
        })
    return out


def resolve_selection(
    profile: str,
    custom: Optional[Iterable[str]] = None,
    available_keys: Optional[Iterable[str]] = None,
) -> dict:
    """
    把「预设/自定义选择」解析为可下载的有序源列表，并剔除缺 key 的源。

    参数：
      profile         "minimal" / "recommended" / "full" / "custom"
      custom          custom 模式下勾选的源名集合
      available_keys  已配置 key 的 env 变量名集合（None=自动探测）

    返回：{"selected": [name, ...], "skipped": [{"name","reason"}, ...]}
      selected 按 CANONICAL_ORDER 排序，确定可重复。
    """
    if available_keys is None:
        available_keys = configured_keys()
    available_keys = set(available_keys)

    if profile == "custom":
        chosen = set(custom or [])
    else:
        chosen = set(PROFILE_SOURCES.get(profile, set()))

    # 仅保留已注册的源
    chosen = {n for n in chosen if n in PLUGIN_REGISTRY}

    selected, skipped = [], []
    for name in CANONICAL_ORDER:
        if name not in chosen:
            continue
        env_var = KEY_REQUIRED.get(name)
        if env_var and env_var not in available_keys:
            skipped.append({
                "name": name,
                "reason": f"需要 {env_var}：请先在设置页填写对应 Key 后再下载。",
            })
            continue
        selected.append(name)
    return {"selected": selected, "skipped": skipped}


# ── 数据库准备（首次下载前必须建表）────────────────────────────

def prepare_database(db_path: Optional[str] = None) -> str:
    """
    确保数据库文件与**表结构**存在，供首次下载落库前调用。
    与 do_update.py 一致：get_connection 只建空文件、不建表，因此空库直接下载会
    触发 `no such table`；此处先 init_db 创建全部表/索引。

    db_path 为空时经 Config 解析（portable 路径）。返回最终 db_path。
    """
    from utils.schema import init_db
    if db_path is None:
        db_path = get_config().db_path
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    init_db(db_path)
    return db_path


def ensure_runtime_database(db_path: Optional[str] = None) -> str:
    """
    启动期幂等建库：保证 GUI 在全新 / 空 portable 目录首次运行时，任何只读
    查询/统计路径都不会因缺表而 `no such table` 崩溃。

    与 prepare_database() 的区别：本函数额外尝试建立 IPv6 扩展表（geoip_v6 等），
    使 v6 查询同样安全。**只建表、不下载数据、不改变 needs_setup 判断**
    （init_db 建出的 source_meta 为空，needs_setup 仍为 True）。

    设计要点：
      * v4 建表（prepare_database）是 1.1.1.1 等核心查询的硬依赖，先执行；
      * v6 建表放在独立 try/except，任何 v6 失败都不得回滚/影响已建好的 v4 表。
    返回最终 db_path。
    """
    db_path = prepare_database(db_path)
    try:
        from utils.schema_v6 import init_v6_tables
        init_v6_tables(db_path)
    except Exception:
        # v6 不在首次冒烟路径上：建表失败仅记为降级，绝不阻断启动。
        pass
    return db_path


# ── 串行下载执行器（可注入，便于零网络测试）────────────────────

def _default_updater(name: str, progress_cb: Callable) -> dict:
    """
    默认执行器：把源投递到统一协调器（进程内单写者），阻塞等待完成。

    v0.3.0：首次初始化不再直接调用 plugin.update()，而是复用与 GUI/调度器/CLI
    同一套写库执行层。这样即便初始化向导运行时调度器 cron 恰好触发同一源，
    也由协调器串行/去重，绝不并发写 intel.db。
    """
    from update_coordinator import get_coordinator, UpdateTrigger, UpdateState
    job = get_coordinator().enqueue_source(name, UpdateTrigger.FIRST_RUN)
    job.wait()
    return {
        "success": job.status == UpdateState.SUCCESS,
        "record_count": job.records_loaded,
        "error": None if job.status == UpdateState.SUCCESS else job.message,
        "error_type": job.error_type,
        "duration_seconds": job.duration_seconds,
    }


def download_sources(
    names: Iterable[str],
    updater: Optional[Callable[[str, Callable], dict]] = None,
    on_progress: Optional[Callable[[dict], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> dict:
    """
    串行下载/更新给定源（**逐个执行，绝不并发**），失败继续，最终汇总。

    参数：
      names          要下载的源名（有序）
      updater        updater(name, progress_cb)->result；默认走 plugin.update
                     result 至少含 {success, record_count, error}
      on_progress    on_progress(event: dict)；event["phase"] ∈
                       source_start / source_progress / source_done / all_done
      should_cancel  可选；返回 True 时在「下一个源开始前」停止（不会中断进行中的源）。

    返回：{"total","ok","failed","cancelled","results":[{name,...}, ...]}
    """
    updater = updater or _default_updater
    names = list(names)
    total = len(names)
    results = []
    cancelled = False

    def emit(event: dict) -> None:
        if on_progress:
            try:
                on_progress(event)
            except Exception:
                pass

    for i, name in enumerate(names):
        if should_cancel and should_cancel():
            cancelled = True
            break
        emit({"phase": "source_start", "index": i, "total": total, "name": name})

        def pcb(step, pct, _i=i, _name=name):
            emit({"phase": "source_progress", "index": _i, "total": total,
                  "name": _name, "step": step, "pct": pct})

        try:
            res = updater(name, pcb) or {}
        except Exception as e:  # 单源异常不应中断整批
            res = {"success": False, "record_count": 0, "error": str(e)}

        res = dict(res)
        res.setdefault("success", False)
        res.setdefault("record_count", 0)
        res.setdefault("error", None)
        row = {"name": name, "success": bool(res["success"]),
               "record_count": res.get("record_count", 0) or 0,
               "error": res.get("error")}
        results.append(row)
        emit({"phase": "source_done", "index": i, "total": total,
              "name": name, "result": row})

    summary = {
        "total": total,
        "ok": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "cancelled": cancelled,
        "results": results,
    }
    emit({"phase": "all_done", "summary": summary})
    return summary


# ── 数据库状态检测（缺库 或 空库 都视为「需初始化」）─────────────

def db_status(db_path: str) -> dict:
    """
    返回数据库状态：{"exists","ok_sources","total_records","needs_setup"}。
    只读访问，不创建文件、不写 WAL。任何读取异常都安全降级。
    """
    info = {"exists": False, "ok_sources": 0, "total_records": 0, "needs_setup": True}
    if not db_path or not os.path.exists(db_path):
        return info
    info["exists"] = True
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    except Exception:
        try:
            conn = sqlite3.connect(db_path)
        except Exception:
            return info
    try:
        try:
            row = conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(record_count),0) "
                "FROM source_meta WHERE status='ok' AND record_count>0"
            ).fetchone()
            info["ok_sources"] = int(row[0] or 0)
            info["total_records"] = int(row[1] or 0)
            info["needs_setup"] = info["ok_sources"] == 0
        except sqlite3.OperationalError:
            # source_meta 表不存在 → 尚未初始化
            info["needs_setup"] = True
    finally:
        conn.close()
    return info


def needs_setup(db_path: str) -> bool:
    """便捷判断：缺库或空库时返回 True。"""
    return db_status(db_path)["needs_setup"]
