# 项目状态（PROJECT_STATUS.md）

> 快照日期：**2026-06-11** · 当前版本：**v0.1.0 public-ready**（首个公开规范化版本，见 [`ROADMAP.md`](ROADMAP.md)）。

---

## 1. 当前已完成内容

- ✅ **离线主查询**：17 个下载源落库 `live/intel.db`，`query_ip` 只读离线查询，风险自动分级。
- ✅ **安全规范化**：`git init` + `.gitignore`；`.env` 密钥管理；`sources.yaml` 改 `${VAR}` 引用；真实密钥移出版本库；`SECURITY.md`。
- ✅ **统一 Provider 架构**：`providers/{types,base,registry}` + 兼容适配旧 17 源；HTTP 工具层（timeout/重试/退避/统一失败对象）。
- ✅ **在线旁路 Provider**：BGPView（无 key）、ipinfo、ip2location、AbuseIPDB 已实现真实 `query()`；ThreatFox 仍骨架。
- ✅ **缓存 + 限速 + 熔断**：独立 SQLite 结果缓存；per-provider 限速（分/时/日）；连续 429 熔断；旁路执行器 `online_runner`。
- ✅ **测试体系**：**76** 个测试，默认零网络，零真实 key 输出。
- ✅ **文档体系**：README/DEVELOPMENT/ROADMAP/PROJECT_STATUS/RELEASE_CHECKLIST/CLAUDE_HANDOFF/CHANGELOG + `docs/*`。
- ✅ **SQLite 并发写入审计**：`docs/SQLITE_CONCURRENCY_AUDIT.md` + `docs/SQLITE_CONCURRENCY_TODO.md`（只审计、未改源码）。

---

## 2. 当前架构状态

```
离线主路径（稳定）：  下载源 ──do_update(串行)──> intel.db ──query_ip(只读)──> 结果+风险分级
                                                          └── GUI / TUI 展示
在线旁路（隔离）：     online_runner ─ validate ─ 缓存 ─ 限速/熔断 ─ query ─ normalize
                      （bgpview/ipinfo/ip2location/abuseipdb）   ✗ 未接入 query_ip
```
- **两套 Provider 并存**：旧下载体系（`datasources/`，写库主力）+ 新统一抽象（`providers/`，旁路）。
- **离线与在线彻底隔离**：在线层不被 `query/engine.py`、`scheduler`、`do_update` 引用。

---

## 3. 当前测试数量

**76 / 76 passed**（`python tests/run_tests.py`）。覆盖：配置加载、Provider 注册表、
bgpview/ipinfo/ip2location/abuseipdb、cache、ratelimit（含 per_day / 熔断 / 清零 / reset）、online_runner、模板。

---

## 4. 已实现 Provider

| 体系 | Provider | 状态 |
|---|---|---|
| 下载型（落库） | geoip, ip2asn, rir_delegated, rpki, cloud_aws/azure/gcp/cloudflare/hetzner/vultr, tor_exits, vpn_x4bnet, spamhaus_drop, firehol, abusech, emerging_threats, peeringdb(默认关) | ✅ 运行中（17 源） |
| 在线旁路 | BGPView | ✅ 已实现（无需 key） |
| 在线旁路 | ipinfo / ip2location / AbuseIPDB | ✅ 已实现（需 key，旁路） |
| 在线旁路 | ThreatFox | 🧩 骨架 |

---

## 5. 未接入主查询的内容

- **全部在线 Provider**（bgpview/ipinfo/ip2location/abuseipdb/threatfox）—— 仅旁路，未进 `query_ip`。
- **online enrichment** —— 规划中（v0.3.0），将以独立 `enrich()` 模块、可选、可关闭方式接入，**不改 `query_ip` 内部**。

---

## 6. 当前风险点

| 风险 | 等级 | 说明 | 去处 |
|---|---|---|---|
| GUI/调度「全部更新」并发写库 | **高** | `trigger_all` 起 ~17 线程并发写 `intel.db` | `docs/SQLITE_CONCURRENCY_AUDIT.md` |
| `get_connection` 无 `busy_timeout` | **高** | 锁冲突立即抛 `database is locked`，随机源 status=error | TODO P0 |
| 定时任务撞点（6 云源同 cron） | 中 | 每月 1 日 04:00 并发写 | TODO P1 |
| `load()` DELETE/INSERT 非原子 | 中 | 中途失败留空窗 | TODO P2 |
| `query_history` / GUI 对锁错误静默吞咽 | 低 | 历史行可能悄悄丢失 | TODO P3 |
| ThreatFox 仍骨架 | 低 | 不影响现有功能 | ROADMAP |

> CLI 串行更新（`update.bat`）**不受**上述并发风险影响；离线**读**因 WAL 读写分离亦不受影响。

---

## 7. 下一步优先级

1. **v0.2.0 SQLite 写入串行化**（审计已就绪，**最高优先**）：busy_timeout(P0) → 写锁/writer 队列(P1) → 事务原子化(P2)。
2. **v0.3.0 可选 online enrichment**：独立 `enrich()`，可关闭，不动 `query_ip`。
3. 补齐 ThreatFox 真实实现（旁路）。
4. 发布前过 `RELEASE_CHECKLIST.md`。

---

## 8. 今日规范化改造总结（2026-06-11）

- 完成 AbuseIPDB 旁路实现 + 限速护栏增强（per_day=900、连续 429 熔断），测试增至 76。
- 完成项目级文档收尾（README 定位/启动/配置/安全/测试；DEVELOPMENT/ROADMAP/PROJECT_STATUS/RELEASE_CHECKLIST/CLAUDE_HANDOFF/CHANGELOG）。
- 完成 SQLite 并发写入**审计**（只出文档、未改源码）：定位 17 线程并发写 + 无 busy_timeout 为 `database is locked` 主因，给出 P0~P4 分步修复方案与回滚策略。

---

## 9. 当前是否适合长期维护

**适合。** 依据：
- 离线主路径稳定、隔离良好；在线能力以受控旁路引入，可随时关闭。
- 有 76 个零网络测试、完整文档体系与明确红线（`CLAUDE_HANDOFF.md`），接手成本低。
- 已知最大风险（并发写库）**已审计、有可回滚的分步方案**，未被掩盖。
- 待办清晰、版本规划明确。**唯一需在接入更高并发/正式发布前先落地的是 v0.2.0 写入串行化。**
