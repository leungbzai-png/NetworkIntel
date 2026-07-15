# -*- coding: utf-8 -*-
"""
v0.3.0 - 调度器与手动更新的协调：都走同一协调器，不并发写库。
把全局协调器替换为注入 mock 执行器的实例（测试后还原）；零网络、零数据库。
"""
import threading
import time

import _bootstrap  # noqa: F401

import update_coordinator as uc
from update_coordinator import UpdateCoordinator, UpdateState, UpdateTrigger
import scheduler.scheduler as sched_mod
from scheduler.scheduler import IntelScheduler


class _install_coordinator:
    """上下文管理器：临时把全局协调器换成注入 executor 的实例。"""

    def __init__(self, executor):
        self.executor = executor
        self._saved = None
        self._saved_flag = None

    def __enter__(self):
        self._saved = uc._coordinator
        self._saved_flag = sched_mod._listener_installed
        self.coord = UpdateCoordinator(executor=self.executor)
        uc._coordinator = self.coord
        sched_mod._listener_installed = False
        return self.coord

    def __exit__(self, *exc):
        try:
            self.coord.shutdown()
        except Exception:
            pass
        uc._coordinator = self._saved
        sched_mod._listener_installed = self._saved_flag
        return False


class _Peak:
    def __init__(self, dwell=0.03):
        self.dwell = dwell
        self.cur = 0
        self.peak = 0
        self.order = []
        self.lock = threading.Lock()

    def __call__(self, name, cb):
        with self.lock:
            self.cur += 1
            self.peak = max(self.peak, self.cur)
            self.order.append(name)
        try:
            time.sleep(self.dwell)
            if name == "bad":
                raise RuntimeError("scheduled job failure")
            return {"success": True, "record_count": 1}
        finally:
            with self.lock:
                self.cur -= 1


def test_manual_and_scheduler_same_source_deduped():
    exe = _Peak(dwell=0.2)
    with _install_coordinator(exe) as coord:
        s = IntelScheduler()
        manual = s.trigger_now("geoip")           # 手动
        sched_mod._scheduler_enqueue("geoip")      # 调度器 cron 路径（同源）
        # 同源在 running/queued 时重复触发被跳过
        dup = coord.get_source_job("geoip")
        coord.wait_for_job(manual, timeout=5)
        assert exe.peak == 1
        # 只执行了一次
        assert exe.order.count("geoip") == 1


def test_manual_and_scheduler_never_write_concurrently():
    exe = _Peak(dwell=0.03)
    with _install_coordinator(exe) as coord:
        s = IntelScheduler()
        jobs = []
        # 交替经手动与调度器路径投递不同源
        for i in range(6):
            n = f"src{i}"
            if i % 2 == 0:
                jobs.append(s.trigger_now(n))
            else:
                sched_mod._scheduler_enqueue(n)
                jobs.append(coord.get_source_job(n))
        assert coord.wait_all([j for j in jobs if j], timeout=10)
        assert exe.peak == 1  # 手动 + 调度器混合触发，写库仍严格串行


def test_scheduler_job_failure_does_not_break_queue():
    exe = _Peak(dwell=0.01)
    with _install_coordinator(exe) as coord:
        j1 = coord.enqueue_source("ok1", UpdateTrigger.SCHEDULER)
        jbad = coord.enqueue_source("bad", UpdateTrigger.SCHEDULER)
        j2 = coord.enqueue_source("ok2", UpdateTrigger.SCHEDULER)
        assert coord.wait_all([j1, jbad, j2], timeout=10)
        assert j1.status == UpdateState.SUCCESS
        assert jbad.status == UpdateState.FAILED
        assert j2.status == UpdateState.SUCCESS  # 失败源不影响后续


def test_get_job_status_maps_states_to_legacy():
    exe = _Peak(dwell=0.01)
    with _install_coordinator(exe) as coord:
        s = IntelScheduler()
        job = s.trigger_now("geoip")
        coord.wait_for_job(job, timeout=5)
        view = s.get_job_status("geoip")
        assert view["status"] == "ok"          # success → ok（旧词表）
        assert view["record_count"] == 1
        # 未知源 → idle
        assert s.get_job_status("never_seen")["status"] == "idle"


def test_scheduler_enqueue_swallows_errors(monkeypatch=None):
    """_scheduler_enqueue 内部异常不得抛出（否则会杀死调度线程）。"""
    def boom_executor(name, cb):
        return {"success": True, "record_count": 1}

    with _install_coordinator(boom_executor) as coord:
        # 让 enqueue_source 抛异常，验证 _scheduler_enqueue 吞掉不外泄
        def raising(*a, **k):
            raise RuntimeError("enqueue blew up")
        orig = coord.enqueue_source
        coord.enqueue_source = raising  # type: ignore
        try:
            sched_mod._scheduler_enqueue("x")  # 不应抛出
        finally:
            coord.enqueue_source = orig  # type: ignore
