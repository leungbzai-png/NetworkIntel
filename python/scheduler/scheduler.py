"""
NetworkIntel - APScheduler 调度器（v0.3.0：统一走 UpdateCoordinator）
=====================================================================
调度器**不再**自己起写库线程。cron 任务、手动触发、「全部更新」全部投递到
``update_coordinator``（单消费线程串行写库），因此：
  * 手动「全部更新」进行中时，定时任务不会并发写库——重复源被跳过、其余排队。
  * 调度器 job 只负责「入队」，不阻塞、不写库；单任务失败不会拖垮调度线程。
本模块保留旧的 ``register_update_callback`` / ``get_job_status`` 接口，供 TUI/GUI
沿用；其数据来源改为协调器。
"""

import threading
from typing import Callable, Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from utils.config_loader import get_config, reload_config
from utils.logger import get_logger
from update_coordinator import (
    get_coordinator, UpdateTrigger, UpdateState, LEGACY_STATUS,
)

logger = get_logger("networkintel")

_update_callbacks: list = []  # UI更新回调列表
_listener_installed = False
_listener_lock = threading.Lock()


def register_update_callback(cb: Callable) -> None:
    """注册调度状态变更回调（供TUI订阅）"""
    _update_callbacks.append(cb)
    _ensure_coordinator_listener()


def _notify_callbacks(source_name: str, status: str, message: str = "") -> None:
    for cb in _update_callbacks:
        try:
            cb(source_name, status, message)
        except Exception:
            pass


def _coordinator_listener(job) -> None:
    """协调器任务状态变更 → 映射为旧 GUI/TUI 词表并转发。"""
    legacy = LEGACY_STATUS.get(job.status, job.status)
    _notify_callbacks(job.source_name, legacy, job.message)


def _ensure_coordinator_listener() -> None:
    """幂等安装协调器监听器（把协调器事件桥接到旧回调体系）。"""
    global _listener_installed
    with _listener_lock:
        if _listener_installed:
            return
        get_coordinator().add_listener(_coordinator_listener)
        _listener_installed = True


def _scheduler_enqueue(source_name: str) -> None:
    """
    APScheduler cron 任务的执行体：仅把源投递到协调器（trigger=scheduler）。
    不写库、不阻塞；若该源已 queued/running 会被协调器跳过（返回 skipped）。
    任何异常都被吞掉并记录，绝不让调度线程死亡。
    """
    try:
        _ensure_coordinator_listener()
        job = get_coordinator().enqueue_source(source_name, UpdateTrigger.SCHEDULER)
        logger.info(f"[调度器] trigger=scheduler source={source_name} "
                    f"-> {job.status} (job={job.job_id})")
    except Exception as e:
        logger.error(f"[调度器] 入队失败 source={source_name}: {e}", exc_info=True)


class IntelScheduler:
    """情报调度器，管理所有数据源的定时任务"""

    def __init__(self):
        self.scheduler = BackgroundScheduler(
            timezone="Asia/Shanghai",
            job_defaults={"coalesce": True, "max_instances": 1},
        )
        self.scheduler.add_listener(self._on_job_event,
                                    EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
        self._jobs: Dict[str, Any] = {}

    def start(self) -> None:
        """启动调度器并注册所有已启用的数据源任务"""
        cfg = get_config()
        sources = cfg.get_all_sources()

        for source_name, source_cfg in sources.items():
            if not source_cfg.get("enabled", True):
                continue
            schedule = source_cfg.get("schedule", "")
            if schedule:
                self._add_job(source_name, schedule)

        self.scheduler.start()
        logger.info(f"[调度器] 已启动，{len(self._jobs)} 个任务已注册")

    def stop(self) -> None:
        """停止调度器，并有序关闭协调器 worker（daemon，即使不关也不阻塞退出）。"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        try:
            get_coordinator().shutdown(wait=True, timeout=5.0)
        except Exception as e:
            logger.debug(f"[调度器] 协调器关闭异常（忽略）: {e}")
        logger.info("[调度器] 已停止")

    def trigger_now(self, source_name: str, trigger: str = UpdateTrigger.MANUAL):
        """立即手动触发指定数据源更新（投递到协调器串行队列）。返回 UpdateJob。"""
        _ensure_coordinator_listener()
        return get_coordinator().enqueue_source(source_name, trigger)

    def trigger_all(self):
        """立即触发所有已启用数据源更新（统一入队，写库串行、不并发）。"""
        _ensure_coordinator_listener()
        cfg = get_config()
        names = [name for name, scfg in cfg.get_all_sources().items()
                 if scfg.get("enabled", True)]
        return get_coordinator().enqueue_many(names, UpdateTrigger.UPDATE_ALL)

    def update_schedule(self, source_name: str, new_cron: str) -> None:
        """
        运行时修改数据源调度频率
        同时更新 sources.yaml
        """
        cfg = get_config()
        cfg.set_source_schedule(source_name, new_cron)

        # 重新注册任务
        if source_name in self._jobs:
            try:
                self.scheduler.remove_job(source_name)
            except Exception:
                pass
        self._add_job(source_name, new_cron)
        logger.info(f"[调度器] {source_name} 调度已更新: {new_cron}")

    def get_job_status(self, source_name: str = None) -> dict:
        """获取任务状态（数据来源：协调器）。状态词表兼容旧 GUI/TUI。"""
        coord = get_coordinator()

        def _view(job) -> dict:
            if job is None:
                return {"status": "idle"}
            return {
                "status": LEGACY_STATUS.get(job.status, job.status),
                "message": job.message,
                "record_count": job.records_loaded,
                "error": job.message if job.status == UpdateState.FAILED else None,
                "trigger": job.trigger,
                "started_at": job.started_at,
                "finished_at": job.finished_at,
            }

        if source_name:
            return _view(coord.get_source_job(source_name))
        # 全量：返回所有已知源的最近状态
        snap = coord.snapshot()
        out = {}
        for name in snap.get("sources", {}):
            out[name] = _view(coord.get_source_job(name))
        return out

    def get_next_run(self, source_name: str) -> Optional[str]:
        """获取下次运行时间"""
        job = self.scheduler.get_job(source_name)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%Y-%m-%d %H:%M")
        return None

    def get_all_jobs_info(self) -> list:
        """获取所有任务的完整信息（用于TUI调度页）"""
        cfg = get_config()
        sources = cfg.get_all_sources()
        result = []

        for name, scfg in sources.items():
            status_info = self.get_job_status(name)
            next_run = self.get_next_run(name)
            result.append({
                "source":      name,
                "description": scfg.get("description", ""),
                "enabled":     scfg.get("enabled", True),
                "schedule":    scfg.get("schedule", ""),
                "next_run":    next_run,
                "status":      status_info.get("status", "idle"),
                "message":     status_info.get("message", ""),
                "last_count":  status_info.get("record_count", 0),
                "error":       status_info.get("error"),
            })
        return result

    def _add_job(self, source_name: str, cron_expr: str) -> None:
        """解析cron表达式并注册任务"""
        try:
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                logger.warning(f"[调度器] {source_name}: 无效cron表达式 '{cron_expr}'")
                return

            minute, hour, day, month, day_of_week = parts
            trigger = CronTrigger(
                minute=minute, hour=hour, day=day,
                month=month, day_of_week=day_of_week,
            )
            job = self.scheduler.add_job(
                func=_scheduler_enqueue,
                trigger=trigger,
                args=[source_name],
                id=source_name,
                name=f"update_{source_name}",
                replace_existing=True,
            )
            self._jobs[source_name] = job
            logger.debug(f"[调度器] {source_name} 已注册: {cron_expr}")
        except Exception as e:
            logger.error(f"[调度器] {source_name} 注册失败: {e}")

    def _on_job_event(self, event) -> None:
        source = event.job_id
        if event.exception:
            logger.error(f"[调度器] 任务异常: {source}: {event.exception}")
        else:
            logger.debug(f"[调度器] 任务完成: {source}")


# 全局调度器单例
_scheduler: Optional[IntelScheduler] = None


def get_scheduler() -> IntelScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = IntelScheduler()
    return _scheduler
