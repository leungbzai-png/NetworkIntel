# Release Notes — NetworkIntel v0.1.0

> **v0.1.0 是 NetworkIntel 的首个公开规范化版本。** 本版本完成了工程化、安全去敏与版本化，
> 把此前的内部开发阶段一次性整合为可安全公开的首个 GitHub 发布。

---

## 这是什么

NetworkIntel 是一个 **Windows 本地、离线优先的 IP / 网络情报查询工具**：
查一个 IP 即可得到地理位置、ASN、RIR、RPKI、云归属、Tor/VPN、威胁情报、WHOIS 等信息，
并自动计算风险等级。**核心查询只读本地 SQLite，全程离线、可预测。**

---

## 已完成（v0.1.0 包含）

- **离线主查询**：17 个公开数据源落库，`query_ip` 离线只读查询 + 风险分级；TUI / GUI / exe 可运行。
- **Git 初始化**：仓库初始化 + `.gitignore` 加固。
- **密钥迁移到 `.env`**：真实密钥移出版本库，`configs/sources.yaml` 改 `${VAR}` 引用，仅留 `*.example.*` 占位模板。
- **`.gitignore` 加固**：忽略 `.env` / `sources.yaml` / 数据库 / `cache` / `logs` / `reports` / `snapshots` /
  `backups` / `dist` / `build` / `*.log` / `.claude/settings.local.json`。
- **Provider 架构文档**：统一 Provider 抽象 + HTTP 工具层 + 兼容适配旧 17 源。
- **在线旁路 Provider**：**BGPView**（无 key）、**ipinfo**、**ip2location**、**AbuseIPDB**（需 key，缺 key 优雅失败）。
- **在线缓存 / 限速 / 429 熔断**：独立 SQLite 缓存（不碰主库）；per-provider 限速；连续 429 熔断；
  AbuseIPDB 默认 `per_day=900`。
- **测试体系**：**76 / 76 passed**，默认零网络、零真实 key 输出。
- **文档体系**：README / DEVELOPMENT / ROADMAP / PROJECT_STATUS / RELEASE_CHECKLIST / CLAUDE_HANDOFF /
  CONTRIBUTING + `docs/*`。
- **SQLite 并发风险审计**：`docs/SQLITE_CONCURRENCY_AUDIT.md` + `SQLITE_CONCURRENCY_TODO.md`（仅审计，未改源码）。

---

## 未包含（不随源码发布）

| 内容 | 说明 |
|---|---|
| 数据库文件 | `live/*.db` 等不入库；克隆后需自行 `update.bat` 下载 |
| API key | 任何真实 key 都不在仓库；用户自行在 `.env` 配置 |
| 缓存 | `cache/`（含在线缓存与限速状态） |
| 日志 | `logs/`、`*.log` |
| 报告 / 快照 / 备份 | `reports/`、`snapshots/`、`backups/` |
| exe / 构建产物 | `dist/`、`build/`、`*.spec`（exe 不随源码发布） |

---

## 如何本地运行

```cmd
:: 1) 取得源码后，准备配置
copy .env.example .env
copy configs\sources.example.yaml configs\sources.yaml

:: 2) 安装依赖
pip install -r requirements.txt

:: 3) 首次联网下载数据（串行，安全）
update.bat

:: 4) 启动界面
start.bat
:: 或： python python\main.py   /   python python\main_gui.py
```

---

## 如何配置 API key

仅**在线 Provider** 需要 key（离线查询不需要任何在线 key）。在 `.env` 填入：

```
MAXMIND_LICENSE_KEY=...     # 离线 GeoIP 下载需要（注册 https://www.maxmind.com/en/geolite2/signup）
IPINFO_TOKEN=...            # 在线 ipinfo（旁路）
IP2LOCATION_API_KEY=...     # 在线 ip2location（旁路）
ABUSEIPDB_API_KEY=...       # 在线 AbuseIPDB（旁路，免费约 1000/天）
```

key 经请求头/params 发送，**绝不进入** URL / 日志 / 异常 / 缓存。未配置时在线 Provider 优雅提示缺 key、不发请求。

---

## 已知限制

- **SQLite 并发写入风险已审计但 v0.1.0 未修复**：GUI/调度器「全部更新」并发写库可能偶发
  `database is locked`（随机源 status=error）。**规避：改用 `update.bat`（串行更新）**。
  已在 `docs/SQLITE_CONCURRENCY_AUDIT.md` 完整审计，并列为 **v0.2.0 优先处理**项。
- **exe 不随源码仓库发布**：`dist/` / `build/` / exe 均不入库；需本地 `build_exe.bat` 自行构建。
  未来若提供预编译版本，将通过 **GitHub Releases** 分发，而非提交进 Git 仓库。
- **API key 与数据库不随源码仓库发布**：仓库不含任何真实 key，也不含数据库文件；
  克隆后需自行在 `.env` 配置 key 并运行 `update.bat` 下载数据（之后查询离线）。
- **在线 Provider 不接入 `query_ip` 主流程**：在线能力仅旁路，离线主查询不依赖任何外部网络。

---

## 下一步计划

- **v0.2.0** SQLite 写入串行化（**优先**：busy_timeout → 写锁或 writer queue → 事务原子化）。
- **v0.3.0** 可选 online enrichment（独立 `enrich()`，可关闭，不改 `query_ip`）。
- **v0.4.0** GUI 状态页：Provider 状态 / 缓存与限速状态展示。
- **v0.5.0** 发布包 / 数据分离。
- **v1.0.0** 稳定版。

完整路线见 [`ROADMAP.md`](../ROADMAP.md)。
