# -*- coding: utf-8 -*-
"""
NetworkIntel - 统一数据源更新协调器（v0.3.0）
=================================================
本模块提供**唯一的**数据源写库执行入口，把 GUI 手动更新、GUI「全部更新」、
首次初始化向导、调度器定时/手动触发、CLI 更新统一到同一条串行队列上。

核心保证
--------
1. 同一进程内，任一时刻**最多只有一个数据源在写库**——由单一消费线程实现。
2. GUI 与调度器都通过本协调器投递任务，不再各自起互不知情的写库线程。
3. 相同源已 queued/running 时，重复入队被拒绝并返回 ``skipped`` 状态。
4. 单个源失败不影响队列中的其它源。
5. 每个任务有清晰状态与时间线（queued/running/success/failed/skipped）。

设计要点
--------
* 写库串行化在**这一层**完成（单 worker 线程），因此不需要再在写连接上加
  模块级互斥锁——那会与本层重复。跨**进程**（GUI 与 update.bat 同时跑）的冲突
  由 ``utils.schema`` 的 busy_timeout + ``DataSourceBase`` 的锁重试兜底。
* worker 是 daemon 线程，不会阻止应用退出；``shutdown()`` 另提供有序停止。
* GUI 不直接从 worker 线程操作 QWidget：GUI 侧用轮询（QTimer）读取任务状态，
  或通过 ``add_listener`` 注册回调后自行用 Qt signal 切回主线程。
"""

import queue
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional

from utils.logger import get_logger
from utils.redaction import redact_secrets

logger = get_logger("networkintel")


# ── 状态与触发来源 ────────────────────────────────────────────
class UpdateState:
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    # 终态集合（任务不会再变化）
    TERMINAL = {SUCCESS, FAILED, SKIPPED, CANCELLED}


class UpdateTrigger:
    MANUAL = "manual"
    UPDATE_ALL = "update_all"
    SCHEDULER = "scheduler"
    FIRST_RUN = "first_run"
    CLI = "cli"


# 传给 scheduler.get_job_status 等旧接口的状态映射（协调器状态 → 旧 GUI 词表）。
LEGACY_STATUS = {
    UpdateState.IDLE: "idle",
    UpdateState.QUEUED: "queued",
    UpdateState.RUNNING: "running",
    UpdateState.SUCCESS: "ok",
    UpdateState.FAILED: "error",
    UpdateState.SKIPPED: "skipped",
    UpdateState.CANCELLED: "idle",
}


@dataclass
class UpdateResult:
    """一次刷新的最终结果（成功或失败的归一化视图）。"""
    source_name: str
    status: str
    success: bool
    records_loaded: int = 0
    message: str = ""
    error_type: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class UpdateJob:
    """协调器中的一个更新任务，记录完整时间线与状态。"""
    source_name: str
    trigger: str
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: str = UpdateState.QUEUED
    queued_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    message: str = ""
    error_type: Optional[str] = None
    records_loaded: int = 0
    duration_seconds: float = 0.0
    # 内部：完成事件，供 wait_for_job / 同步 CLI 使用。
    _done: threading.Event = field(default_factory=threading.Event, repr=False)

    def wait(self, timeout: Optional[float] = None) -> bool:
        """阻塞直到任务进入终态；返回是否已完成（超时返回 False）。"""
        return self._done.wait(timeout)

    @property
    def is_done(self) -> bool:
        return self._done.is_set()

    def result(self) -> UpdateResult:
        return UpdateResult(
            source_name=self.source_name,
            status=self.status,
            success=(self.status == UpdateState.SUCCESS),
            records_loaded=self.records_loaded,
            message=self.message,
            error_type=self.error_type,
            duration_seconds=self.duration_seconds,
        )

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "source_name": self.source_name,
            "trigger": self.trigger,
            "status": self.status,
            "queued_at": self.queued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "message": self.message,
            "error_type": self.error_type,
            "records_loaded": self.records_loaded,
            "duration_seconds": self.duration_seconds,
        }


# 执行器签名：executor(source_name, progress_cb) -> dict
# 返回 dict 至少含 {success, record_count, error, error_type, duration_seconds}
Executor = Callable[[str, Callable[[str, int], None]], dict]


def _default_executor(source_name: str, progress_cb) -> dict:
    """默认执行器：实例化插件并执行 update（真实下载 + 原子落库）。"""
    from datasources.plugin_registry import get_plugin
    return get_plugin(source_name).update(progress_callback=progress_cb)


_SENTINEL = object()  # 关闭 worker 的哨兵


class UpdateCoordinator:
    """串行化的数据源更新协调器（单消费线程）。"""

    def __init__(self, executor: Optional[Executor] = None,
                 name: str = "update-coordinator"):
        self._executor = executor or _default_executor
        self._name = name
        self._queue: "queue.Queue" = queue.Queue()
        self._lock = threading.RLock()
        # 活动任务（queued 或 running），保证同源不重复入队。
        self._active: Dict[str, UpdateJob] = {}
        self._running: Optional[UpdateJob] = None
        # 每个源最近一次任务（含终态），供 get_source_state / GUI 读取。
        self._last: Dict[str, UpdateJob] = {}
        self._listeners: List[Callable[[UpdateJob], None]] = []
        self._worker: Optional[threading.Thread] = None
        self._shutdown = False

    # ── worker 生命周期 ──────────────────────────────────────
    def _ensure_worker(self) -> None:
        with self._lock:
            if self._shutdown:
                raise RuntimeError("coordinator 已 shutdown，无法再入队")
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._run, name=self._name, daemon=True)
                self._worker.start()

    def _run(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is _SENTINEL:
                    return
                self._execute(item)
            finally:
                self._queue.task_done()

    # ── 入队 ────────────────────────────────────────────────
    def enqueue_source(self, source_name: str, trigger: str,
                       executor: Optional[Executor] = None) -> UpdateJob:
        """
        投递一个源更新任务。若该源已 queued/running，则**拒绝重复入队**，
        返回一个 status=skipped（error_type=duplicate）的任务。
        """
        with self._lock:
            existing = self._active.get(source_name)
            if existing is not None:
                job = UpdateJob(source_name=source_name, trigger=trigger,
                                status=UpdateState.SKIPPED,
                                error_type="duplicate")
                now = datetime.now().isoformat()
                job.queued_at = now
                job.finished_at = now
                job.message = f"已在队列/执行中（{existing.status}），跳过重复触发"
                job._done.set()
                self._last[source_name] = job
                self._notify(job)
                logger.info(f"[协调器] {source_name} 重复触发被跳过 "
                            f"(trigger={trigger}, 现有={existing.status})")
                return job

            job = UpdateJob(source_name=source_name, trigger=trigger)
            job.queued_at = datetime.now().isoformat()
            job._executor = executor  # type: ignore[attr-defined]
            self._active[source_name] = job
            self._last[source_name] = job
            self._ensure_worker()
            self._queue.put(job)
        logger.info(f"[协调器] queued source={source_name} trigger={trigger} "
                    f"job={job.job_id}")
        self._notify(job)
        return job

    def enqueue_many(self, source_names, trigger: str) -> List[UpdateJob]:
        """批量投递（如「全部更新」）。返回每个源对应的任务（含被跳过的）。"""
        return [self.enqueue_source(n, trigger) for n in source_names]

    # ── 执行单个任务 ─────────────────────────────────────────
    def _execute(self, job: UpdateJob) -> None:
        start = datetime.now()
        with self._lock:
            self._running = job
            job.status = UpdateState.RUNNING
            job.started_at = start.isoformat()
        logger.info(f"[协调器] started source={job.source_name} "
                    f"trigger={job.trigger} job={job.job_id}")
        self._notify(job)

        def progress_cb(step: str, pct: int) -> None:
            job.message = f"{step} ({pct}%)"
            self._notify(job)

        executor = getattr(job, "_executor", None) or self._executor
        try:
            res = executor(job.source_name, progress_cb) or {}
            success = bool(res.get("success"))
            if success:
                job.status = UpdateState.SUCCESS
                job.records_loaded = int(res.get("record_count", 0) or 0)
                job.message = f"完成，{job.records_loaded:,} 条记录"
                job.error_type = None
            else:
                job.status = UpdateState.FAILED
                job.error_type = res.get("error_type") or "error"
                job.message = redact_secrets(res.get("error") or "更新失败")
        except Exception as e:  # 执行器本身抛异常也不能让 worker 挂掉
            job.status = UpdateState.FAILED
            job.error_type = type(e).__name__
            job.message = redact_secrets(str(e))
            logger.error(f"[协调器] source={job.source_name} 执行异常: "
                         f"{job.message}", exc_info=True)
        finally:
            job.finished_at = datetime.now().isoformat()
            job.duration_seconds = (datetime.now() - start).total_seconds()
            with self._lock:
                self._running = None
                # 仅当活动表里仍是本任务时移除（防御重复）
                if self._active.get(job.source_name) is job:
                    del self._active[job.source_name]
                self._last[job.source_name] = job
            job._done.set()  # 必须在 finally：保证 wait_for_job 永不悬挂
            logger.info(f"[协调器] finished source={job.source_name} "
                        f"trigger={job.trigger} status={job.status} "
                        f"records={job.records_loaded} "
                        f"duration={job.duration_seconds:.1f}s job={job.job_id}")
            self._notify(job)

    # ── 查询接口 ─────────────────────────────────────────────
    def is_busy(self) -> bool:
        """是否有任务在排队或执行。"""
        with self._lock:
            return bool(self._active)

    def queue_size(self) -> int:
        """尚未开始执行的排队任务数（不含正在执行的）。"""
        with self._lock:
            return sum(1 for j in self._active.values()
                       if j.status == UpdateState.QUEUED)

    def running_source(self) -> Optional[str]:
        with self._lock:
            return self._running.source_name if self._running else None

    def get_source_job(self, source_name: str) -> Optional[UpdateJob]:
        """返回某源当前/最近一次任务（活动优先，其次历史）。"""
        with self._lock:
            return self._active.get(source_name) or self._last.get(source_name)

    def get_source_state(self, source_name: str) -> str:
        job = self.get_source_job(source_name)
        return job.status if job else UpdateState.IDLE

    def snapshot(self) -> dict:
        """整体进度快照（供 GUI 展示队列进度/当前源/汇总）。"""
        with self._lock:
            active = list(self._active.values())
            last = dict(self._last)
            running = self._running.source_name if self._running else None
        return {
            "busy": bool(active),
            "running": running,
            "queued": sum(1 for j in active if j.status == UpdateState.QUEUED),
            "active_total": len(active),
            "sources": {n: j.status for n, j in last.items()},
        }

    # ── 等待与关闭 ───────────────────────────────────────────
    def wait_for_job(self, job: UpdateJob, timeout: Optional[float] = None) -> bool:
        return job.wait(timeout)

    def wait_all(self, jobs, timeout: Optional[float] = None) -> bool:
        """等待一批任务全部完成；超时返回 False。"""
        import time
        deadline = None if timeout is None else (time.monotonic() + timeout)
        for job in jobs:
            remaining = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
            if not job.wait(remaining):
                return False
        return True

    def shutdown(self, wait: bool = True, timeout: float = 10.0) -> None:
        """有序停止 worker。daemon 线程即使不停止也不会阻塞退出。"""
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
            worker = self._worker
        self._queue.put(_SENTINEL)
        if wait and worker is not None and worker.is_alive():
            worker.join(timeout)

    # ── 监听器 ───────────────────────────────────────────────
    def add_listener(self, cb: Callable[[UpdateJob], None]) -> None:
        with self._lock:
            if cb not in self._listeners:
                self._listeners.append(cb)

    def remove_listener(self, cb: Callable[[UpdateJob], None]) -> None:
        with self._lock:
            if cb in self._listeners:
                self._listeners.remove(cb)

    def _notify(self, job: UpdateJob) -> None:
        with self._lock:
            listeners = list(self._listeners)
        for cb in listeners:
            try:
                cb(job)
            except Exception:
                # 监听器（UI 回调等）失败绝不影响更新流程。
                pass


# ── 全局单例 ─────────────────────────────────────────────────
_coordinator: Optional[UpdateCoordinator] = None
_coordinator_lock = threading.Lock()


def get_coordinator() -> UpdateCoordinator:
    global _coordinator
    with _coordinator_lock:
        if _coordinator is None:
            _coordinator = UpdateCoordinator()
        return _coordinator
