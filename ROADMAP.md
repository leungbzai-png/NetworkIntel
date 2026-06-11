# 版本规划（ROADMAP.md）

> 语义化版本，轻量路线，可能随实际情况调整。当前进度见 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)。

## 当前公开版本：**v0.2.0**（Portable Runtime + 首次初始化向导）

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
| **v0.3.0** | SQLite 写入串行化 / 更新队列稳定性 | 按 `docs/SQLITE_CONCURRENCY_TODO.md`：busy_timeout → 写锁或 writer queue → 事务原子化 → 错误分类 → 压测 |
| **v0.4.0** | 可选 online enrichment 接入 GUI | 独立 `enrich()` 模块，离线结果可选并入在线字段；可关闭；**不改 `query_ip` 内部** |
| **v0.5.0** | Provider 状态页 | Provider 状态 / 缓存与限速状态展示；响应性与错误提示优化 |
| **v1.0.0** | 稳定版 | 离线主路径稳定；在线增强可选可关；并发写安全；文档完备 |

## 贯穿所有版本的不变量（红线）
- 离线查询 `query_ip` 始终只读本地 SQLite，**永不**直接依赖在线 API。
- 不修改 SQLite 表结构；不移动数据/缓存/日志/报告/快照/备份目录。
- 真实密钥只在 `.env`；模板只放占位符；测试默认零网络、零真实 key。
