# 项目状态（PROJECT_STATUS.md）

> 快照日期：**2026-07-15** · 公开版本：**v0.3.0**（串行化 SQLite 更新队列，见
> [`ROADMAP.md`](ROADMAP.md) / [`docs/RELEASE_NOTES_v0.3.0.md`](docs/RELEASE_NOTES_v0.3.0.md) /
> [`docs/SQLITE_CONCURRENCY_AUDIT.md`](docs/SQLITE_CONCURRENCY_AUDIT.md)）。
>
> **v0.3.0 要点**：统一更新协调器（进程内单 worker 写入队列）根治「全部更新 / 调度撞点」并发写
> `database is locked`；连接统一 `busy_timeout` + WAL + `foreign_keys`；每源刷新单事务原子化；
> 锁错误分类 + 有限重试 + 脱敏。GUI/调度器/CLI/首次初始化统一入队。**不改 `query_ip`、不改表结构、
> 不换 SQLite、不新增 Provider、不做 UI 重构。** 测试 165/165。

---

## 1. 当前已完成内容

- ✅ **离线主查询**：17 个下载源落库 `live/intel.db`，`query_ip` 只读离线查询，风险自动分级。
- ✅ **安全规范化**：`git init` + `.gitignore`；`.env` 密钥管理；`sources.yaml` 改 `${VAR}` 引用；真实密钥移出版本库；`SECURITY.md`。
- ✅ **统一 Provider 架构**：`providers/{types,base,registry}` + 兼容适配旧 17 源；HTTP 工具层（timeout/重试/退避/统一失败对象）。
- ✅ **在线旁路 Provider**：BGPView（无 key）、ipinfo、ip2location、AbuseIPDB 已实现真实 `query()`；ThreatFox 仍骨架。
- ✅ **缓存 + 限速 + 熔断**：独立 SQLite 结果缓存；per-provider 限速（分/时/日）；连续 429 熔断；旁路执行器 `online_runner`。
- ✅ **测试体系**：**110** 个测试，默认零网络，零真实 key 输出（含 portable 路径 / 首次初始化 / key 存储 / 数据目录模式 / 数据源预设与串行下载编排）。
- ✅ **文档体系**：README/DEVELOPMENT/ROADMAP/PROJECT_STATUS/RELEASE_CHECKLIST/CLAUDE_HANDOFF/CHANGELOG + `docs/*`。
- ✅ **SQLite 并发写入审计**：`docs/SQLITE_CONCURRENCY_AUDIT.md` + `docs/SQLITE_CONCURRENCY_TODO.md`（只审计、未改源码）。
- ✅ **v0.2.0 Phase 1 — Portable Runtime**：
  - 统一路径模块 `python/utils/paths.py`，支持 `NETWORKINTEL_HOME/CONFIG/DATA_MODE/DATA_DIR`，**任意目录运行**，不再锁定 `E:\NetworkIntel`。
  - 首次运行自动创建 `configs/live/cache/logs/reports/snapshots/backups/gdrive_sync`，自动初始化 `.env` 与 `configs/sources.yaml`（缺库不自动下载、不阻断启动）。
  - GUI 设置页：MaxMind / ipinfo / ip2location / AbuseIPDB key 填写（隐藏 + 显示切换 + 已配置/未配置状态，只写 `.env`）；数据目录 portable / custom 模式切换。
  - 模板与脚本去硬编码（`sources.example.yaml` 相对路径、`.bat` 用 `%~dp0` 与 PATH 的 python）。详见 [`docs/PORTABLE_MODE.md`](docs/PORTABLE_MODE.md)。
- ✅ **v0.2.0 Phase 2 — 首次初始化 / 数据源选择下载**：
  - `python/datasources/setup_profiles.py`：预设分组（最小/推荐/完整）+ 自定义；缺 Key 自动剔除（geoip→MaxMind）。
  - 数据库缺失/空库检测（`db_status`/`needs_setup`），供状态栏横幅与向导复用。
  - **串行**下载执行器 `download_sources()`（逐个 `plugin.update()`，绝不并发，规避空库 `database is locked`），失败继续 + 汇总 + 协作式取消，执行器可注入便于零网络测试。
  - GUI `FirstRunSetupDialog`：首次缺库自动弹出（可关闭、不阻断），「数据源」页「数据初始化…」随时可开；每源 + 整体进度、失败/跳过提示。详见 [`docs/FIRST_RUN_SETUP.md`](docs/FIRST_RUN_SETUP.md)。
  - 正式版本号 `0.2.0`；打包 portable zip 并发布 v0.2.0 Release（不覆盖 v0.1.0）。

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

**165 / 165 passed**（`python tests/run_tests.py` 与 `python -m pytest` 等价）。
v0.3.0 新增 5 个测试文件（更新协调器 / 队列并发 / 连接策略 / 事务原子性 / 调度协调）。覆盖：portable 路径解析、首次运行初始化、
key 存储（.env，不入 yaml）、数据目录 portable/custom、配置加载、Provider 注册表、
bgpview/ipinfo/ip2location/abuseipdb、cache、ratelimit（含 per_day / 熔断 / 清零 / reset）、online_runner、模板、
**数据源预设分组 / key 门控 / 选择顺序 / 串行下载编排与失败汇总 / 取消 / 数据库状态检测**、
**空库首次初始化建表（portable·custom 路径解析，空库串行下载不再 `no such table`）**。

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

| 风险 | 等级 | 说明 | 状态 |
|---|---|---|---|
| GUI/调度「全部更新」并发写库 | ~~高~~ | 旧 `trigger_all` 起 ~17 线程并发写 | ✅ v0.3.0 修复：统一协调器单写者队列 |
| `get_connection` 无 `busy_timeout` | ~~高~~ | 旧连接锁冲突立即抛 `database is locked` | ✅ v0.3.0 修复：统一 `busy_timeout=30000` |
| 定时任务撞点（6 云源同 cron） | ~~中~~ | 每月 1 日 04:00 并发写 | ✅ v0.3.0 修复：调度器入队去重 + 串行 |
| `load()` DELETE/INSERT 非原子 | ~~中~~ | 旧路径中途失败留空窗 | ✅ v0.3.0 修复：单事务原子替换 |
| 跨进程（GUI 与 `update.bat` 同跑）撞锁 | 低 | 进程内队列不覆盖跨进程 | 兜底：busy_timeout + 事务 + 有限重试；见发布说明「已知边界」 |
| ThreatFox 仍骨架 | 低 | 不影响现有功能 | ROADMAP |

> CLI 串行更新（`update.bat`）与离线**读**（WAL 读写分离）本就安全；v0.3.0 后进程内写入并发已根治。

---

## 7. 下一步优先级

1. ~~**v0.3.0 SQLite 写入串行化**~~ ✅ 已完成（统一更新协调器 + busy_timeout/WAL + 事务原子化 + 锁分类）。
2. **v0.4.0 可选 online enrichment**：独立 `enrich()`，可关闭，不动 `query_ip`。
3. 补齐 ThreatFox 真实实现（旁路）。
4. （可选）跨进程更新锁 / 「下载并发 + 写入串行」流水线——仅在确有需要且不破坏 portable 模式时评估。

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
