"""
NetworkIntel - APScheduler 调度器
管理所有数据源的定期更新任务
支持：cron调度、手动触发、任务状态查询
"""

import threading
from datetime import datetime
from typing import Callable, Optional, Dict, Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from utils.config_loader import get_config, reload_config
from utils.logger import get_logger

logger = get_logger("networkintel")

# 全局任务状态追踪
_job_status: Dict[str, dict] = {}
_status_lock = threading.Lock()
_update_callbacks: list = []  # UI更新回调列表


def register_update_callback(cb: Callable) -> None:
    """注册调度状态变更回调（供TUI订阅）"""
    _update_callbacks.append(cb)


def _notify_callbacks(source_name: str, status: str, message: str = "") -> None:
    for cb in _update_callbacks:
        try:
            cb(source_name, status, message)
        except Exception:
            pass


def _run_source_update(source_name: str) -> None:
    """执行单个数据源更新"""
    try:
        from datasources.plugin_registry import get_plugin
        plugin = get_plugin(source_name)

        with _status_lock:
            _job_status[source_name] = {
                "status": "running",
                "started_at": datetime.now().isoformat(),
                "message": "更新中...",
            }
        _notify_callbacks(source_name, "running", "更新中...")
        logger.info(f"[调度器] 开始更新: {source_name}")

        def progress(step, pct):
            with _status_lock:
                _job_status[source_name]["message"] = f"{step} ({pct}%)"
            _notify_callbacks(source_name, "running", f"{step} ({pct}%)")

        result = plugin.update(progress_callback=progress)

        with _status_lock:
            _job_status[source_name] = {
                "status": "ok" if result["success"] else "error",
                "finished_at": datetime.now().isoformat(),
                "record_count": result.get("record_count", 0),
                "message": f"完成，{result.get('record_count', 0)} 条记录" if result["success"]
                           else f"失败: {result.get('error', '')}",
                "error": result.get("error"),
            }
        status = "ok" if result["success"] else "error"
        _notify_callbacks(source_name, status, _job_status[source_name]["message"])
        logger.info(f"[调度器] {source_name} 更新{'成功' if result['success'] else '失败'}")

    except Exception as e:
        logger.error(f"[调度器] {source_name} 异常: {e}", exc_info=True)
        with _status_lock:
            _job_status[source_name] = {
                "status": "error",
                "finished_at": datetime.now().isoformat(),
                "message": f"异常: {str(e)}",
                "error": str(e),
            }
        _notify_callbacks(source_name, "error", str(e))


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
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        logger.info("[调度器] 已停止")

    def trigger_now(self, source_name: str) -> None:
        """立即手动触发指定数据源更新（在后台线程执行）"""
        t = threading.Thread(
            target=_run_source_update,
            args=(source_name,),
            daemon=True,
            name=f"update-{source_name}",
        )
        t.start()

    def trigger_all(self) -> None:
        """立即触发所有已启用数据源更新"""
        cfg = get_config()
        for name, scfg in cfg.get_all_sources().items():
            if scfg.get("enabled", True):
                self.trigger_now(name)

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
        """获取任务状态"""
        with _status_lock:
            if source_name:
                return _job_status.get(source_name, {"status": "idle"})
            return dict(_job_status)

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
            status_info = _job_status.get(name, {})
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
                func=_run_source_update,
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
