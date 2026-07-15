# -*- coding: utf-8 -*-
"""
v0.3.0 - 更新队列并发性：无论多少线程同时入队，实际最大并行执行数恒为 1。
用共享峰值计数器（进入 +1 / 退出 -1，记录峰值）做确定性断言，
不用随机 sleep、不用 Barrier(2) 于执行侧（单 worker 下会死锁）。
零网络、零数据库。
"""
import threading
import time

import _bootstrap  # noqa: F401

from update_coordinator import UpdateCoordinator, UpdateState, UpdateTrigger


class _PeakExecutor:
    """记录同时进入执行体的最大并发数。"""

    def __init__(self, dwell=0.02):
        self.dwell = dwell
        self.cur = 0
        self.peak = 0
        self.count = 0
        self.lock = threading.Lock()

    def __call__(self, name, cb):
        with self.lock:
            self.cur += 1
            self.count += 1
            self.peak = max(self.peak, self.cur)
        try:
            time.sleep(self.dwell)  # 制造重叠窗口（若真并发会被峰值捕获）
            return {"success": True, "record_count": 1}
        finally:
            with self.lock:
                self.cur -= 1


def test_max_parallel_execution_is_one_under_many_enqueuers():
    exe = _PeakExecutor()
    coord = UpdateCoordinator(executor=exe)
    try:
        names = [f"s{i}" for i in range(12)]
        # 用 Barrier 在**入队侧**让多线程尽量同时冲入 enqueue（制造 dedup/竞态压力）
        start = threading.Barrier(len(names))
        jobs = []
        jobs_lock = threading.Lock()

        def fire(n):
            start.wait()
            j = coord.enqueue_source(n, UpdateTrigger.UPDATE_ALL)
            with jobs_lock:
                jobs.append(j)

        threads = [threading.Thread(target=fire, args=(n,)) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert coord.wait_all(jobs, timeout=10)
        # 核心断言：任一时刻只有 1 个源在执行
        assert exe.peak == 1, f"peak={exe.peak}"
        assert exe.count == len(names)
        assert all(j.status == UpdateState.SUCCESS for j in jobs)
    finally:
        coord.shutdown()


def test_two_update_all_do_not_run_in_parallel():
    """连续两次「全部更新」不产生并行队列：同名源第二批被去重跳过。"""
    exe = _PeakExecutor(dwell=0.03)
    coord = UpdateCoordinator(executor=exe)
    try:
        names = ["a", "b", "c", "d"]
        batch1 = coord.enqueue_many(names, UpdateTrigger.UPDATE_ALL)
        batch2 = coord.enqueue_many(names, UpdateTrigger.UPDATE_ALL)
        coord.wait_all(batch1, timeout=10)
        coord.wait_all([j for j in batch2 if not j.is_done], timeout=10)
        # 仍然串行：峰值 1
        assert exe.peak == 1
        # 第二批大多在第一批未完成时投递 → 至少部分被 skipped，且绝不并发
        skipped = sum(1 for j in batch2 if j.status == UpdateState.SKIPPED)
        assert skipped >= 1
    finally:
        coord.shutdown()


def test_single_source_failure_does_not_stop_queue():
    """队列中一个源失败，后续源仍然执行。"""
    order = []
    lock = threading.Lock()

    def exe(name, cb):
        with lock:
            order.append(name)
        if name == "bad":
            raise RuntimeError("fail on purpose")
        return {"success": True, "record_count": 1}

    coord = UpdateCoordinator(executor=exe)
    try:
        jobs = coord.enqueue_many(["ok1", "bad", "ok2"], UpdateTrigger.UPDATE_ALL)
        assert coord.wait_all(jobs, timeout=10)
        by = {j.source_name: j.status for j in jobs}
        assert by["ok1"] == UpdateState.SUCCESS
        assert by["bad"] == UpdateState.FAILED
        assert by["ok2"] == UpdateState.SUCCESS  # 失败后继续执行
        assert order == ["ok1", "bad", "ok2"]
    finally:
        coord.shutdown()
