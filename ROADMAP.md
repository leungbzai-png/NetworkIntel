# 版本规划（ROADMAP.md）

> 语义化版本。✅ 已完成 · 🚧 进行中 · ⬜ 计划中。当前进度见 [`PROJECT_STATUS.md`](PROJECT_STATUS.md)。

| 版本 | 主题 | 状态 | 内容 |
|---|---|---|---|
| **v0.1.0** | 现有离线查询可运行 | ✅ | 17 个下载源落库 `intel.db`；`query_ip` 只读离线查询；TUI/GUI 可用；风险分级 |
| **v0.2.0** | Git / 密钥 / 安全配置规范化 | ✅ | `git init` + `.gitignore`；`.env` 密钥管理；`sources.yaml` 改 `${VAR}` 引用；`SECURITY.md`；真实密钥移出版本库 |
| **v0.3.0** | Provider 规范与在线旁路 Provider | ✅ | 统一 Provider 抽象（`types/base/registry`）；兼容适配 17 旧源；HTTP 工具层；BGPView/ipinfo/ip2location 在线旁路实现 |
| **v0.4.0** | 缓存 / 限速 / AbuseIPDB | ✅ | 在线结果缓存（独立 SQLite）；per-provider 限速 + 429 熔断；AbuseIPDB 旁路实现；76 用例测试体系；文档收尾；SQLite 并发审计 |
| **v0.5.0** | 可选 online enrichment | ⬜ | 新增独立 `enrich()` 模块，由调用方在拿到离线结果后**可选**并入在线字段；受开关 + 缓存 + 限速保护；**仍不改 `query_ip` 内部** |
| **v0.6.0** | SQLite 写入串行化 | ⬜ | 落地 `docs/SQLITE_CONCURRENCY_TODO.md`：busy_timeout（P0）→ 写锁/writer 队列（P1）→ 事务原子化（P2）→ 错误分类（P3）→ 压测（P4） |
| **v0.7.0** | GUI 优化 | ⬜ | GUI 审计后再改：响应性、错误提示、在线 enrichment 展示（可关闭）；改前先审计 |
| **v0.8.0** | 发布包 / 数据分离 | ⬜ | 打包 exe 与数据目录分离；首次运行向导；模板与真实配置/数据彻底解耦；发布走 `RELEASE_CHECKLIST.md` |
| **v1.0.0** | 稳定版 | ⬜ | 离线主路径稳定；在线增强可选可关；并发写安全；文档完备；发布清单全绿 |

## 当前里程碑
已完成至 **v0.4.0**。下一步优先 **v0.6.0（SQLite 写入串行化，审计已就绪）** 与 **v0.5.0（可选 enrichment）**。

## 贯穿所有版本的不变量（红线）
- 离线查询 `query_ip` 始终只读本地 SQLite，**永不**直接依赖在线 API。
- 不修改 SQLite 表结构；不移动数据/缓存/日志/报告/快照/备份目录。
- 真实密钥只在 `.env`；模板只放占位符；测试默认零网络、零真实 key。
