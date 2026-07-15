# NetworkIntel v0.3.0 — Serialized SQLite Update Queue

> 主题：**SQLite 写入串行化 / 数据源更新队列稳定性**。
> 本版本不包含 UI 重构、新 Provider 或数据库 schema 大改造。

## 一句话

v0.3.0 用一个**统一的数据源更新协调器**（进程内单写者队列）替换了旧的
「每源一个后台线程并发写库」模型，从根本上消除了 GUI「全部更新」/ 调度器撞点
导致的 `database is locked` 间歇失败，并让 GUI 手动更新、全部更新、首次初始化向导、
调度器任务、CLI 更新走**同一套写库执行入口**。

---

## v0.3.0 解决了什么

历史问题（见 `docs/SQLITE_CONCURRENCY_AUDIT.md`）：

- GUI/TUI「全部更新」与调度器 `trigger_all()` 会一次性拉起最多 ~17 个后台线程
  **并发写同一个 `intel.db`**；
- `get_connection()` **没有 `busy_timeout`**，写者一遇锁立即抛
  `database is locked`，随机若干数据源在数据源页显示 `status=error`；
- 每个源的 `load()` 里 `DELETE old` 与 `INSERT new` 处于**不同连接/不同事务**，
  中途失败会留下「删了旧的、只写一半」的空窗。

v0.3.0 全部修复：

1. **统一更新协调器**（`python/update_coordinator.py`）：单消费线程串行执行所有源刷新，
   同一时间**最多一个源在写库**。
2. **连接策略统一**（`python/utils/schema.py`）：所有连接带 `busy_timeout=30000`、
   `foreign_keys=ON`、WAL（失败优雅回退）；读/写连接分离，写连接 autocommit +
   显式 `BEGIN IMMEDIATE`。
3. **事务原子化**（`python/datasources/base.py`）：每个源一次刷新 = 一个事务，
   `DELETE old + INSERT new` 同一事务，失败整体回滚，杜绝空窗。
4. **锁错误分类 + 有限重试 + 脱敏日志**：`database is locked` 单独识别（`error_type=db_locked`），
   带上限的退避重试，绝不无限等待；错误消息脱敏（不泄露 MaxMind `license_key` 等）。

---

## 更新队列如何工作

```
GUI 单源更新 ─┐
GUI 全部更新 ─┤
首次初始化   ─┼─► UpdateCoordinator.enqueue_*  ──► 单 worker 线程（串行）──► plugin.update()
调度器 cron  ─┤        （同源去重、状态机）              │  download/parse（事务外）
CLI 更新     ─┘                                          └► load()：BEGIN IMMEDIATE → DELETE+INSERT → COMMIT
```

- **状态机**：`queued → running → success / failed / skipped`（`cancelled` 预留）。
- **去重**：相同源已 `queued`/`running` 时重复触发返回 `skipped(duplicate)`，不会二次并发。
- **失败隔离**：单源失败不终止队列，后续源继续。
- **不阻塞退出**：worker 是 daemon 线程；`shutdown()` 提供有序停止。

## GUI / scheduler / CLI 如何协调

- **GUI**：`SourcesPage` 的单源更新、「全部更新」都经调度器委派到协调器；
  「全部更新」进行中按钮禁用，再次点击提示「更新任务正在执行」；显示当前源、
  完成数/总数与最终「成功/失败/跳过」汇总。后台线程绝不直接操作 QWidget（UI 端轮询）。
- **调度器**：cron 任务只负责**入队**（`trigger=scheduler`），不再自己起写库线程；
  手动「全部更新」进行中，调度器触发的同源被去重、其余排队，不并发写库。
- **CLI**（`do_update.py` / `update.bat`）：复用协调器同步等待接口，按顺序输出每源状态，
  末尾给出汇总；仅在存在 failed 时返回非零退出码；缺 MaxMind Key 的 `geoip` 保持 `skipped`。
- **首次初始化向导**：串行编排逻辑不变，但每个源的实际写库改为投递协调器执行，
  与其它入口共用同一写库实现。

## busy_timeout / WAL / 事务策略

- `busy_timeout=30000ms`（可用 `NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS` 覆盖）：
  写者遇锁**等待重试**而非立即失败。
- `journal_mode=WAL` + `synchronous=NORMAL`：读写分离，离线 `query_ip` 只读不被写阻塞；
  WAL 设置失败会记录告警并优雅回退，不阻断启动。
- 每个源刷新 = 一个 `BEGIN IMMEDIATE` 事务；下载/解析在事务外完成，
  写锁只在真正落库期间持有，缩短锁窗口。

---

## 已知边界

- **跨进程**：进程内队列不覆盖「同时运行 GUI 与 `update.bat`」的情况。此时依靠
  `busy_timeout` + 每源事务 + 有限退避重试兜底：绝大多数情况会排队成功；
  极端长事务（如 geoip 数百万行）仍可能在重试耗尽后返回 `db_locked` 失败——
  这是预期的安全失败，重跑即可。**建议不要同时跑 GUI 与 `update.bat` 做大源更新。**
- **协调器覆盖的是「数据源刷新写入」**：`query_ip` 末尾写 `query_history` 是每次查询的旁路小写入，
  不经协调器（也不该经过）。它现在同样带 `busy_timeout`，撞锁时等待而非硬失败，失败也只记 `debug`、
  不影响查询结果。因此「任一时刻最多一个数据源在写库」是就**数据源刷新**而言。
- **单写者=串行下载**：为保证单写者，`update_all` 的下载也被串行化，
  整体墙钟时间比旧的多线程并发更长。这是**以稳定性换速度**的有意取舍；
  「下载并发 + 写入串行」的流水线属于未来可选优化，本版本不做。

## 如何排查 `database is locked`

1. 看 `logs/networkintel.log`：锁冲突会记录为 `写库锁冲突（database is locked）`，
   并带 `trigger=` 与重试次数，与网络/解析错误分开。
2. 数据源页状态若为 `失败` 且消息含 `database is locked`，通常是同时跑了另一个写进程
   （如 `update.bat`）。等待其完成后重跑该源即可。
3. 需要更长等待可临时调大 `NETWORKINTEL_SQLITE_BUSY_TIMEOUT_MS`。

## 回滚方式

所有改动集中、可独立回滚，且**不涉及表结构变更**（无数据迁移、无不可逆操作）：

- 连接策略：`git revert` `utils/schema.py` 相关 commit。
- 协调器 / 调度器 / GUI / CLI 集成：`git revert` 对应 commit。
- 事务原子化：`git revert` `datasources/base.py` 与插件 `load()` 改动。

回滚到 v0.2.1 后行为与该版本完全一致。v0.1.0 / v0.2.0 / v0.2.1 的 tag 与 Release 资产不受影响。

---

## 测试

- 全量：`python tests/run_tests.py` 与 `python -m pytest` 均 **165/165 passed**（较 v0.2.1 的 133 新增 32）。
- 新增测试：`test_update_coordinator` / `test_update_queue_concurrency` /
  `test_sqlite_connection_policy` / `test_update_transactions` /
  `test_scheduler_update_coordination`（含最大并行度恒为 1、同源去重、
  失败隔离、状态时序、busy_timeout 生效、每线程独立连接、事务提交/回滚、
  锁有限重试、脱敏等）。
- 全程零网络、零真实 key、使用临时目录与临时数据库，不触碰正式 `live/intel.db`。
