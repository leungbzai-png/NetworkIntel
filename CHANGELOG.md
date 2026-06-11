# 变更记录（CHANGELOG.md）

> 项目**工程化/规范化**轨道的变更记录（与 `python/CHANGELOG.md` 的 GUI 功能记录互补）。
> 遵循语义化版本，最新在上。

---

## [v0.4.0] - 2026-06-11 — 缓存 / 限速 / AbuseIPDB / 文档收尾 / 并发审计

### Added
- **AbuseIPDB 在线 Provider**（旁路）：真实 `query()`（认证头 `Key:`，key 不进 URL/日志/异常/缓存）；
  统一字段（abuse_confidence_score/severity/threats/...）；severity 分级 `0 clean / 1-24 low / 25-74 medium / 75-100 high`。
- **限速护栏增强**：per-provider `per_minute/per_hour/per_day`；**连续 429 熔断**（`max_consecutive_429` + `circuit_breaker_seconds`）；
  `DEFAULT_PROVIDER_LIMITS`（AbuseIPDB 10/100/900，免费额度留余量）；`build_default_limiter`、`reset()`、`in_circuit()`。
- **online_runner 增强**：执行顺序调整为 validate→缓存→限速/熔断→query；缓存命中**零额度消耗**；
  `force_refresh` 仍受限速；熔断期返回 `circuit_open` 且不调用 `query()`。
- **smoke 脚本**：`--rate-limit-status` / `--simulate-429` / `--reset-rate-limit` / `--provider abuseipdb`（均默认不联网）。
- **项目文档体系**：`DEVELOPMENT.md`、`ROADMAP.md`、`PROJECT_STATUS.md`、`RELEASE_CHECKLIST.md`、`CLAUDE_HANDOFF.md`、根 `CHANGELOG.md`；README 增项目定位/启动/配置/安全/测试。
- **SQLite 并发写入审计**：`docs/SQLITE_CONCURRENCY_AUDIT.md` + `docs/SQLITE_CONCURRENCY_TODO.md`（**只审计、未改源码**）。

### Changed
- 测试体系扩充至 **76** 用例（新增 `test_abuseipdb_provider.py`，扩充 ratelimit/runner/templates），默认零网络、零真实 key。
- `.env.example` / `configs/sources.example.yaml`：补全 AbuseIPDB 限速/TTL 与全局熔断占位。

---

## [v0.3.0] - 2026-06 — Provider 规范与在线旁路 Provider

### Added
- **统一 Provider 抽象**：`providers/{types,base,registry}`，兼容适配旧 17 个下载源（不实例化、不读配置）。
- **HTTP 工具层** `providers/http.py`：timeout / UA / 429·5xx 重试 / 退避 / JSON / 统一失败对象（不记录 headers）。
- **在线旁路 Provider**：BGPView（无 key）、ipinfo（`Authorization: Bearer`）、ip2location（key 经 params）真实实现。
- **在线缓存** `providers/cache.py`：独立 `cache/online_cache.sqlite`，不碰 `intel.db`。
- **限速基础** `providers/ratelimit.py` + **旁路执行器** `providers/online_runner.py`。
- 文档：`docs/API_PROVIDER_*`、`ONLINE_PROVIDERS.md`、`ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md`、`TESTING.md`。

### Notes
- 所有在线 Provider **未接入** `query_ip`，仅显式旁路调用。

---

## [v0.2.0] - 2026-06 — Git / 密钥 / 安全配置规范化（P0 安全整改）

### Added
- `git init` + `.gitignore`（忽略 `.env` / `sources.yaml` / `live` / `cache` / `logs` / `reports` / `snapshots` / `backups`）。
- `.env` 密钥管理 + `.env.example` 模板；`SECURITY.md`。

### Changed
- `configs/sources.yaml` 中密钥改为 `${VAR}` 引用，真实密钥移出版本库（仅留 `*.example.*` 占位符）。
- `config_loader` 支持 `.env` 加载与 `${VAR}` 解析（不覆盖已有环境变量）。

### Security
- 真实 API key 从被跟踪文件中清除；配置加载测试断言模板无明文长 token。

---

## [v0.1.0] - 2026-06（基线） — 现有离线查询可运行

### Added
- 17 个下载型数据源（GeoIP/ASN/RPKI/RIR/云/Tor/VPN/威胁情报/WHOIS）落库 `live/intel.db`。
- `query_ip` 只读离线查询 + 风险自动分级；TUI 与 PySide6 GUI。
- `start.bat` / `update.bat` / `status.bat` 等 Windows 原生入口。

> GUI 细节变更见 `python/CHANGELOG.md`。
