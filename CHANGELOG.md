# 变更记录（CHANGELOG.md）

> 项目**工程化/发布**轨道的变更记录（与 `python/CHANGELOG.md` 的 GUI 功能记录互补，二者版本轴独立）。
> 遵循语义化版本，最新在上。后续版本规划见 [`ROADMAP.md`](ROADMAP.md)。

---

## [v0.1.0] - 2026-06-11 — 首个公开规范化版本

NetworkIntel 的**首个公开发布版本**。把此前的内部开发阶段（脚手架 / 安全整改 / Provider /
缓存限速 / AbuseIPDB / 文档 / 并发审计）一次性整合、去敏、版本化为 v0.1.0。

### 离线主功能（基线）
- 17 个下载型数据源（GeoIP / ASN / RPKI / RIR / 云 IP 段 / Tor / VPN / 威胁情报 / WHOIS）落库 `live/intel.db`。
- `query_ip` 只读离线查询 + 风险自动分级；TUI、PySide6 GUI、可运行 exe；`start.bat` / `update.bat` 等入口。

### 安全规范化
- `git init` + `.gitignore` 加固（忽略 `.env` / `sources.yaml` / `live` / `cache` / `logs` / `reports` /
  `snapshots` / `backups` / `dist` / `build` / `*.log` / `.claude/settings.local.json`）。
- 密钥迁移至 `.env`；`configs/sources.yaml` 改 `${VAR}` 引用；真实密钥移出版本库（仅留 `*.example.*` 占位符）。
- `config_loader` 支持 `.env` 加载与 `${VAR}` 解析（不覆盖已有环境变量）；`SECURITY.md`。

### Provider 架构与在线旁路
- 统一 Provider 抽象 `providers/{types,base,registry}`，兼容适配旧 17 源（不实例化、不读配置）。
- HTTP 工具层 `providers/http.py`（timeout / 重试 / 退避 / 统一失败对象，不记录 headers / key）。
- 在线旁路 Provider：**BGPView**（无 key）、**ipinfo**、**ip2location**、**AbuseIPDB**（均需 key 者缺 key 优雅失败）。
- ThreatFox 暂为骨架。**所有在线 Provider 未接入 `query_ip`，仅显式旁路调用。**

### 缓存 / 限速 / 熔断
- 在线结果缓存 `providers/cache.py`（独立 `cache/online_cache.sqlite`，不碰 `intel.db`）。
- per-provider 限速（分/时/日）+ 连续 429 熔断 `providers/ratelimit.py`；旁路执行器 `providers/online_runner.py`。
- AbuseIPDB 默认 `per_day=900`（免费额度留余量），威胁类缓存 TTL 默认 6h。缓存命中不消耗限额；`force_refresh` 仍受限速。

### 测试与文档
- 测试体系 **76 / 76 passed**（默认零网络，零真实 key 输出）。
- 文档：`README` / `DEVELOPMENT` / `ROADMAP` / `PROJECT_STATUS` / `RELEASE_CHECKLIST` / `CLAUDE_HANDOFF` /
  `CONTRIBUTING` / `docs/RELEASE_NOTES_v0.1.0` + `docs/*`（在线 Provider / 缓存限速 / 测试）。
- **SQLite 并发写入审计**：`docs/SQLITE_CONCURRENCY_AUDIT.md` + `docs/SQLITE_CONCURRENCY_TODO.md`（**仅审计，未改源码**）。

### 发布工程
- `VERSION` = `0.1.0`；`python/__init__.py` `__version__ = "0.1.0"`（GUI `APP_VERSION` 独立保留 1.2.0）。
- MIT `LICENSE`（NetworkIntel Contributors）；最小 GitHub Actions 测试 workflow（`.github/workflows/tests.yml`）。

### 未包含（不随源码发布）
- 数据库文件、API key、缓存、日志、报告、快照、备份、exe / 构建产物（均 gitignore）。

---

> v0.1.0 之前没有公开发布；早期内部阶段已合并入本版本。
> GUI 界面自有版本（v1.0→v1.2）记录见 `python/CHANGELOG.md`。
