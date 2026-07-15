# 版本规划（ROADMAP.md）

> 语义化版本，轻量路线，可能随实际情况调整。当前进度见 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)。

## 当前公开版本：**v0.3.0**（串行化 SQLite 更新队列）

v0.3.0 已包含（主题：SQLite 写入串行化 / 数据源更新队列稳定性）：
- **统一更新协调器**（`python/update_coordinator.py`）：进程内单 worker 写入队列，GUI 手动/全部更新、
  调度器、CLI、首次初始化向导统一入队；同源去重、失败隔离、清晰状态机。
- **连接策略统一**：`busy_timeout=30000` + `foreign_keys=ON` + WAL（优雅回退）；读/写连接分离。
- **事务原子化**：每源一次刷新 = 一个 `BEGIN IMMEDIATE` 事务，`DELETE+INSERT` 同事务，失败整体回滚。
- **锁错误分类 + 有限重试 + 脱敏**：`database is locked` 单独识别，绝不无限重试，不泄露 key。
- 不变量：未改 `query_ip`、未改表结构、未换 SQLite、未新增 Provider、未做 UI 重构。测试 165/165。
- 详见 [`docs/RELEASE_NOTES_v0.3.0.md`](docs/RELEASE_NOTES_v0.3.0.md) 与 [`docs/SQLITE_CONCURRENCY_AUDIT.md`](docs/SQLITE_CONCURRENCY_AUDIT.md)。

v0.2.0 已包含：
- **Phase 1**：统一 `paths` 模块、任意目录运行、首次运行自动建目录/模板、GUI key 设置、portable/custom 数据目录模式。
- **Phase 2**：数据库缺失/空库检测、首次初始化向导、数据源选择下载（最小/推荐/完整/自定义）、
  串行下载 + 进度/失败汇总 + 缺 Key 跳过、正式版本号 0.2.0、打包 portable zip 并发布 Release。
- 不变量：未新增 Provider、未接入在线 Provider 到主查询、未改 `query_ip`。

v0.1.0 已包含（首个公开版本一次性纳入的工程化主体）：
- 17 个下载源落库 `intel.db`，`query_ip` 离线只读查询 + 风险分级；TUI / GUI / exe 可运行。
- Git 初始化 + `.gitignore` 加固；密钥迁移至 `.env`，`sources.yaml` 改 `${VAR}` 引用。
- 统一 Provider 架构 + HTTP 工具层；在线旁路 Provider：BGPView / ipinfo / ip2location / AbuseIPDB。
- 在线结果缓存 + per-provider 限速 + 429 熔断（旁路，未接入 `query_ip`）。
- 测试体系（76/76 passed，默认零网络）。
- 文档体系 + SQLite 并发写入**审计**（仅审计，未修复）。

## 后续路线（forward-looking）

| 版本 | 主题 | 内容（简） |
|---|---|---|
| **v0.2.0**（已发布） | Portable Runtime + First Run Setup | 统一 `paths`；任意目录运行；首次运行自动建目录/模板；GUI key 设置；portable/custom 数据目录；首次初始化向导 + 数据源选择串行下载（最小/推荐/完整/自定义）+ 发布包。 |
| **v0.3.0**（已发布） | SQLite 写入串行化 / 更新队列稳定性 | 统一更新协调器（单 worker 写入队列）+ busy_timeout/WAL/foreign_keys 连接策略 + 事务原子化 + 锁错误分类/脱敏；GUI/调度器/CLI/首次初始化统一入队 |
| **v0.4.0** | 可选 online enrichment 接入 GUI | 独立 `enrich()` 模块，离线结果可选并入在线字段；可关闭；**不改 `query_ip` 内部** |
| **v0.5.0** | Provider 状态页 | Provider 状态 / 缓存与限速状态展示；响应性与错误提示优化 |
| **v1.0.0** | 稳定版 | 离线主路径稳定；在线增强可选可关；并发写安全；文档完备 |

## 贯穿所有版本的不变量（红线）
- 离线查询 `query_ip` 始终只读本地 SQLite，**永不**直接依赖在线 API。
- 不修改 SQLite 表结构；不移动数据/缓存/日志/报告/快照/备份目录。
- 真实密钥只在 `.env`；模板只放占位符；测试默认零网络、零真实 key。
