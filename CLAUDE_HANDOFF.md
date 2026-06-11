# 交接文档（CLAUDE_HANDOFF.md）

> **给未来接手的 Claude Code / Codex / 人类维护者。动手前先读完红线。**
> 配套：[`DEVELOPMENT.md`](DEVELOPMENT.md) · [`PROJECT_STATUS.md`](PROJECT_STATUS.md) · [`ROADMAP.md`](ROADMAP.md)。

---

## 0. 红线（不能随便动）

1. **不要把在线 API 接进 `query_ip` 主流程。** `query/engine.py::query_ip` 必须保持**纯离线、只读 SQLite**。
   在线 Provider 永远是旁路增强；要接入只能走 v0.3.0 的独立 `enrich()`（可选、可关闭，不改 `query_ip` 内部）。
2. **不要移动主数据库**，也不要移动 `cache/ logs/ reports/ snapshots/ backups/ live/`。路径写在配置与 `.gitignore` 里，移动会破坏备份/快照/同步链路。
3. **不要修改 SQLite 表结构**（`utils/schema.py` 的表定义）。并发问题是访问模式问题，不是 schema 问题。
4. **改 GUI 前先审计。** GUI 文件大、副作用多（`main_gui.py` / `gui_extensions.py` / `gui_map.py`），盲改易回归。
5. **不要提交** `.env` / `configs/sources.yaml` / `cache/` / `logs/` / `reports/` / `snapshots/` / `backups/` / `live/*.db`。
   真实 key 只进 `.env`，模板只放占位符。提交前 `git status` + `git diff` 自检。
6. **SQLite 并发只按** `docs/SQLITE_CONCURRENCY_TODO.md` **分步走**，每步独立 commit、可回滚；不要一次性大改。

---

## 1. 当前 Provider 架构

两套并存，职责分明：

- **下载型（旧体系，写库主力）**：`python/datasources/`。`DataSourceBase`（download/parse/load/snapshot）+
  `PLUGIN_REGISTRY`（17 源）。经 `do_update.py`（串行）或 `scheduler`（并发）落库 `intel.db`。
- **统一抽象（新体系，旁路）**：`python/providers/`。`types/base/registry` 定义接口并兼容适配旧源；
  `http.py` 统一 HTTP；`online/` 是在线 Provider；`cache.py`/`ratelimit.py`/`online_runner.py` 是旁路基础设施。
- **离线主查询**：`query/engine.py::query_ip` 只读 `intel.db`，与在线层零耦合。

---

## 2. 当前在线 Provider 状态

| Provider | 类别 | Key | 状态 |
|---|---|---|---|
| BGPView | ASN/BGP | 否 | ✅ 已实现（旁路） |
| ipinfo | GeoIP/ASN | `IPINFO_TOKEN` | ✅ 已实现（旁路） |
| ip2location | GeoIP | `IP2LOCATION_API_KEY` | ✅ 已实现（旁路） |
| AbuseIPDB | 威胁情报 | `ABUSEIPDB_API_KEY` | ✅ 已实现（旁路，默认 per_day=900） |
| ThreatFox | 威胁情报 | `THREATFOX_API_KEY` | 🧩 骨架（下一个补实现） |

调用方式：`providers.online_runner.run_provider(name, ip)` 或 `scripts/provider_smoke_test.py --provider <name> --query <ip>`。缺 key 优雅失败、不发请求。

---

## 3. 当前缓存 / 限速 / 熔断机制

- **缓存**：`providers/cache.py`，独立 `cache/online_cache.sqlite`（**不碰** `intel.db`）。威胁类 TTL 短（AbuseIPDB 默认 6h），GeoIP/ASN 14~30 天。缓存命中**不消耗限额**。
- **限速**：`providers/ratelimit.py`，per-provider `per_minute/per_hour/per_day`，状态存 `cache/online_ratelimit.json`。默认额度见 `DEFAULT_PROVIDER_LIMITS`（AbuseIPDB 10/100/900）。
- **熔断**：连续 429 达 `ONLINE_MAX_CONSECUTIVE_429`（默认 3）→ 熔断 `ONLINE_CIRCUIT_BREAKER_SECONDS`（默认 3600s）；`record_success` 清零计数。
- **执行顺序**（`online_runner`）：allowed → validate → **缓存 → 限速/熔断** → query → record → 写缓存。
  `force_refresh` 跳过缓存但**仍受限速/熔断**。

---

## 4. 当前测试入口

```cmd
python tests/run_tests.py            # 76 用例，无需 pytest
python -m pytest                     # 等价
```
默认零网络（HTTP 层 monkeypatch）；限速测试用临时 JSON + 注入时钟；输出无真实 key。

---

## 5. 当前推荐下一步（路线优先级）

1. **v0.2.0 SQLite 写入串行化**（审计已就绪，**最高优先**）：busy_timeout → 写锁或 writer queue →
   事务原子化 → 错误分类 → 压测。按 `docs/SQLITE_CONCURRENCY_TODO.md` 分步、每步独立可回滚。
2. **v0.3.0 可选 online enrichment**：独立 `enrich()` 模块，可关闭，不改 `query_ip`。
3. **v0.4.0 GUI 状态页**：Provider 状态 / 缓存与限速状态展示（审计后再改 GUI）。
4. **v0.5.0 发布包 / 数据分离**；**v1.0.0 稳定版**。
5. 旁路补全：**ThreatFox** 真实实现（参考 abuseipdb）。

> 路线与 `README.md` / `ROADMAP.md` / `PROJECT_STATUS.md` 保持一致：v0.2.0=SQLite 串行化，
> v0.3.0=enrichment，v0.4.0=GUI 状态页，v0.5.0=发布包/数据分离，v1.0.0=稳定版。

---

## 6. 常用命令

```cmd
:: 测试
python tests/run_tests.py

:: 离线 CLI 更新（串行，安全）
update.bat
cd python && python -c "import do_update"          :: import 自检

:: Provider 自检（默认不联网）
python scripts/provider_smoke_test.py
python scripts/provider_smoke_test.py --rate-limit-status
python scripts/provider_smoke_test.py --simulate-429 abuseipdb
python scripts/provider_smoke_test.py --reset-rate-limit abuseipdb
python scripts/provider_smoke_test.py --provider abuseipdb --query 8.8.8.8   :: 缺 key 会优雅提示

:: 安全自检
git status
git diff | findstr /I "api_key token license_key"
```

---

## 7. 最近重要 commit 说明

| commit | 说明 |
|---|---|
| `docs: finalize project handoff and sqlite concurrency audit` | 本轮：项目文档收尾 + SQLite 并发审计（只审计未改源码） |
| `feat: add abuseipdb provider with rate limit safeguards` | AbuseIPDB 旁路实现；限速增强（per_day=900、连续 429 熔断）；测试增至 76 |
| `feat: implement ip2location online provider in bypass mode` | ip2location 在线旁路实现 |
| `feat: add online provider cache and rate limiting foundation` | 在线缓存 + 限速基础设施 |
| `feat: implement ipinfo online provider in bypass mode` | ipinfo 在线旁路实现（首个带 key） |
| `feat: scaffold online provider layer and tests` | 在线 Provider 层脚手架 + 测试 |
| `feat: document and scaffold unified provider architecture` | 统一 Provider 抽象 + 兼容适配 17 源 |
| `chore: secure local secrets and initialize project safeguards` | git 初始化 + `.env` 密钥管理 + 安全整改（P0） |

> 完整历史：`git log --oneline`。
