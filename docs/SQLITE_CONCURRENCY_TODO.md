# SQLite 并发写入 — 优先级待办（SQLITE_CONCURRENCY_TODO.md）

> 配套审计：`docs/SQLITE_CONCURRENCY_AUDIT.md`。
> **状态：v0.3.0 已全部落地 ✅**（P0~P4）。见 `docs/RELEASE_NOTES_v0.3.0.md`。
> 说明：v0.3.0 采用比原方案更彻底的**统一更新协调器（单 worker 写入队列）**替代
> 「trigger_all 串行化」与「模块级写锁」——单写者队列天然满足串行化，无需再加写锁。
> 原则：下载在协调器串行执行（以稳定换速度），**SQLite 写入严格串行化**；不改表结构，不引入外部数据库。

## v0.3.0 落地对照

| 优先级 | 任务 | 落地情况 |
|---|---|---|
| **P0** | `busy_timeout` | ✅ `utils/schema.py` 统一 `connect_read/connect_write` 均设 `busy_timeout=30000`（+ `foreign_keys=ON`、WAL 优雅回退）；`schema_v6` 与在线缓存同步 |
| **P1** | 写串行化 | ✅ 新增 `python/update_coordinator.py` 单 worker 队列，GUI/调度器/CLI/首次初始化统一入队；`scheduler.trigger_*` 不再自起写库线程 |
| **P2** | 事务原子化 | ✅ `datasources/base.py::_bulk_insert` 单连接单事务（`BEGIN IMMEDIATE` → `DELETE+INSERT` → `COMMIT`/`ROLLBACK`）；7 个插件 `load()` 改用 `replace_source=True` |
| **P3** | 错误日志分类 | ✅ `update()` 识别 `error_type=db_locked`，脱敏 traceback；`query/engine.py::_save_history` 不再裸 `except: pass`（改 `logger.debug` 且区分锁冲突）；`redaction.py` 防 key 泄露。**遗留（低）**：`gui_extensions.py` 只读侧对 `OperationalError` 的静默吞咽属 GUI，未在本轮改动，仅记录 |
| **P4** | 压测/回归 | ✅ 以确定性并发测试替代随机压测：`test_update_queue_concurrency`（峰值并发==1）等，全量 165/165 |

---

## 原始清单（保留作对照）

| 优先级 | 任务 | 触及文件 | 风险 | 验收标准 |
|---|---|---|---|---|
| **P0** | 确认/补齐 WAL 与 `busy_timeout`。WAL 已开启（`get_connection` + `SCHEMA_SQL`）；**`busy_timeout` 缺失**，建议在 `get_connection()` 加 `PRAGMA busy_timeout=30000` | `utils/schema.py` | 极低（单行 PRAGMA） | 并发写时锁错误数显著下降；CLI 串行路径行为不变 |
| **P1** | 增加写锁或 writer 队列：对 `load()` + `_update_meta()` 加全局 `threading.Lock`，或新增单 worker DB-writer 队列；或把 `trigger_all()` 改为串行执行写 | `scheduler/scheduler.py`（或新增 `db_writer.py`） | 中（集中、可回滚） | `trigger_all()` 后**所有源 status=ok，零 `database is locked`** |
| **P2** | 统一事务：每个源的 `DELETE old + INSERT new` 收进**同一事务/同一连接**，失败整体回滚 | `datasources/base.py`（`load`/`_bulk_insert` 约定） | 中 | 中途注入异常后，表数据非空（要么旧、要么新），无空窗 |
| **P3** | 完善错误日志：在 `update()` 中单独识别 `OperationalError: database is locked`，与网络/解析错误分类；处理 `query/engine.py` 与 GUI 对 `OperationalError` 的静默吞咽 | `datasources/base.py`、`query/engine.py`（、GUI 审计后） | 低 | 日志能区分「锁冲突」与其它错误；锁导致的历史/状态丢失可见 |
| **P4** | 压力测试：脚本并发触发 `trigger_all()`，统计锁错误与丢行，建立修复前/后基线并纳入回归 | 新增 `tests/` 或 `scripts/` 压测脚本 | 低（纯新增） | 修复后压测稳定 0 锁错误；纳入 CI/手动回归清单 |

## 实施顺序与依赖
```
P0 (busy_timeout, 即时止血)
   └─> P1 (写串行化, 根治)   ← 真正消除 database is locked
          └─> P2 (事务原子化, 一致性加固)
                 └─> P3 (错误日志分类)
P4 (压测) 贯穿始终：P0 前建基线，P1/P2 后验证归零
```

## 注意
- **P0 是止血不是根治**：busy_timeout 降低锁冲突概率，但大表长事务仍可能超时；根治在 P1。
- 全程**不改表结构**、**不动 `query_ip` 读路径**、**不改 CLI 串行 `do_update.py` 行为**。
- 每项都应是**独立 commit**，便于单独 `git revert`。
