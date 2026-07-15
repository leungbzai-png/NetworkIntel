# -*- coding: utf-8 -*-
"""
v0.3.0 - UpdateCoordinator 基础行为：状态时间线 / 去重 / 等待 / shutdown。
使用注入的 mock 执行器，零网络、零真实 key、不触碰任何数据库。
"""
import threading
import time

import _bootstrap  # noqa: F401

from update_coordinator import (
    UpdateCoordinator, UpdateState, UpdateTrigger, UpdateJob,
)


def _ok_executor(records=7):
    def exe(name, cb):
        cb("working", 50)
        return {"success": True, "record_count": records}
    return exe


def test_state_timeline_queued_running_success():
    seen = []
    coord = UpdateCoordinator(executor=_ok_executor())
    coord.add_listener(lambda job: seen.append(job.status))
    try:
        job = coord.enqueue_source("s1", UpdateTrigger.MANUAL)
        assert job.queued_at is not None
        assert coord.wait_for_job(job, timeout=5)
        assert job.status == UpdateState.SUCCESS
        assert job.started_at is not None and job.finished_at is not None
        assert job.records_loaded == 7
        assert job.duration_seconds >= 0
        # 状态经过 queued → running → success
        assert UpdateState.QUEUED in seen
        assert UpdateState.RUNNING in seen
        assert UpdateState.SUCCESS in seen
    finally:
        coord.shutdown()


def test_failure_sets_failed_and_records_error_type():
    def boom(name, cb):
        raise RuntimeError("kaboom")
    coord = UpdateCoordinator(executor=boom)
    try:
        job = coord.enqueue_source("s1", UpdateTrigger.MANUAL)
        assert coord.wait_for_job(job, timeout=5)
        assert job.status == UpdateState.FAILED
        assert job.error_type == "RuntimeError"
        assert "kaboom" in job.message
    finally:
        coord.shutdown()


def test_executor_error_result_becomes_failed_with_type():
    def failer(name, cb):
        return {"success": False, "error": "boom", "error_type": "db_locked"}
    coord = UpdateCoordinator(executor=failer)
    try:
        job = coord.enqueue_source("s1", UpdateTrigger.CLI)
        assert coord.wait_for_job(job, timeout=5)
        assert job.status == UpdateState.FAILED
        assert job.error_type == "db_locked"
    finally:
        coord.shutdown()


def test_duplicate_enqueue_while_active_is_skipped():
    gate = threading.Event()

    def slow(name, cb):
        gate.wait(5)  # 保持 running 直到放行
        return {"success": True, "record_count": 1}

    coord = UpdateCoordinator(executor=slow)
    try:
        first = coord.enqueue_source("dup", UpdateTrigger.MANUAL)
        # first 正在排队/执行时再次入队 → skipped(duplicate)
        second = coord.enqueue_source("dup", UpdateTrigger.SCHEDULER)
        assert second.status == UpdateState.SKIPPED
        assert second.error_type == "duplicate"
        assert second.is_done
        gate.set()
        assert coord.wait_for_job(first, timeout=5)
        assert first.status == UpdateState.SUCCESS
    finally:
        gate.set()
        coord.shutdown()


def test_same_source_can_run_again_after_finishing():
    coord = UpdateCoordinator(executor=_ok_executor())
    try:
        j1 = coord.enqueue_source("s", UpdateTrigger.MANUAL)
        coord.wait_for_job(j1, timeout=5)
        # 完成后不再是活动任务，可以再次入队
        j2 = coord.enqueue_source("s", UpdateTrigger.MANUAL)
        assert j2.status != UpdateState.SKIPPED
        coord.wait_for_job(j2, timeout=5)
        assert j2.status == UpdateState.SUCCESS
        assert j1.job_id != j2.job_id
    finally:
        coord.shutdown()


def test_is_busy_and_queue_size():
    gate = threading.Event()

    def slow(name, cb):
        gate.wait(5)
        return {"success": True, "record_count": 1}

    coord = UpdateCoordinator(executor=slow)
    try:
        jobs = coord.enqueue_many(["a", "b", "c"], UpdateTrigger.UPDATE_ALL)
        assert coord.is_busy()
        # a 正在跑，b/c 排队 → queue_size ~2（允许调度抖动，至少 >=1）
        assert coord.queue_size() >= 1
        gate.set()
        assert coord.wait_all(jobs, timeout=5)
        assert not coord.is_busy()
        assert coord.queue_size() == 0
    finally:
        gate.set()
        coord.shutdown()


def test_get_source_state_transitions():
    coord = UpdateCoordinator(executor=_ok_executor())
    try:
        assert coord.get_source_state("nope") == UpdateState.IDLE
        job = coord.enqueue_source("s", UpdateTrigger.MANUAL)
        coord.wait_for_job(job, timeout=5)
        assert coord.get_source_state("s") == UpdateState.SUCCESS
    finally:
        coord.shutdown()


def test_shutdown_does_not_hang_and_rejects_new_work():
    coord = UpdateCoordinator(executor=_ok_executor())
    coord.enqueue_source("s", UpdateTrigger.MANUAL)
    t0 = time.monotonic()
    coord.shutdown(wait=True, timeout=5)
    assert time.monotonic() - t0 < 5
    # shutdown 后再入队应报错而非静默挂起
    try:
        coord.enqueue_source("x", UpdateTrigger.MANUAL)
        assert False, "应拒绝 shutdown 后入队"
    except RuntimeError:
        pass


def test_failed_message_is_redacted_of_secrets():
    """执行器返回含 license_key 的错误消息时，协调器写入的 message 必须脱敏。"""
    leaky = ("HTTPError: 401 for url: https://download.maxmind.com/geoip_download"
             "?edition_id=GeoLite2-City&license_key=SUPERSECRET123&suffix=zip")

    def failer(name, cb):
        return {"success": False, "error": leaky, "error_type": "HTTPError"}

    coord = UpdateCoordinator(executor=failer)
    try:
        job = coord.enqueue_source("geoip", UpdateTrigger.CLI)
        assert coord.wait_for_job(job, timeout=5)
        assert "SUPERSECRET123" not in job.message
        assert "license_key=***" in job.message
    finally:
        coord.shutdown()


def test_redact_secrets_helper():
    from utils.redaction import redact_secrets
    assert redact_secrets("license_key=ABC123&x=1") == "license_key=***&x=1"
    assert "TOKEN" not in redact_secrets("token=TOKENVAL")
    assert redact_secrets("Authorization: Bearer abc.def") == "Authorization: ***"
    # 普通文本不受影响
    assert redact_secrets("no such table: geoip") == "no such table: geoip"
    assert redact_secrets(None) == ""


def test_wait_for_job_timeout_returns_false():
    gate = threading.Event()

    def slow(name, cb):
        gate.wait(5)
        return {"success": True, "record_count": 1}

    coord = UpdateCoordinator(executor=slow)
    try:
        job = coord.enqueue_source("s", UpdateTrigger.MANUAL)
        assert coord.wait_for_job(job, timeout=0.05) is False
        gate.set()
        assert coord.wait_for_job(job, timeout=5) is True
    finally:
        gate.set()
        coord.shutdown()
