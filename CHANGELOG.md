# 变更记录（CHANGELOG.md）

> 项目**工程化/发布**轨道的变更记录（与 `python/CHANGELOG.md` 的 GUI 功能记录互补，二者版本轴独立）。
> 遵循语义化版本，最新在上。后续版本规划见 [`ROADMAP.md`](ROADMAP.md)。

---

## [0.2.0] - 2026-06-11 — Portable Runtime + 首次初始化向导

v0.2.0 正式版：在 Phase 1（Portable Runtime）基础上完成 Phase 2（首次初始化 / 数据源选择下载 / 打包发布）。
本版本不新增 Provider、不接入在线 Provider 到主查询、不改 `query_ip`。

### 首次初始化 / 数据源选择下载（Phase 2 新增）
- 新增 `python/datasources/setup_profiles.py`：预设分组（最小 / 推荐 / 完整）+ 自定义逐源勾选；
  解析选择时自动剔除缺 Key 的源（目前仅 geoip 依赖 `MAXMIND_LICENSE_KEY`），绝不读 key 明文。
- **数据库状态检测**：缺库 **或** 空库（无任何成功落库的源）都判定为「需初始化」，供状态栏横幅与向导复用。
- **串行下载执行器** `download_sources()`：逐个执行 `plugin.update()`（**绝不并发**），失败继续、最终汇总；
  与 `do_update.py` 的串行 CLI 安全路径一致，规避空库并发写触发的 `database is locked`（见并发审计）。
  执行器可注入，便于零网络测试；支持「下一个源开始前」协作式取消。
- **GUI 数据初始化向导**（`FirstRunSetupDialog`）：选择方案 → 串行下载，展示每源进度 / 整体进度 /
  成功失败汇总 / 缺 Key 跳过提示。首次运行（缺库/空库）自动弹出（可关闭、不强制、不阻断启动）；
  「数据源」页新增「数据初始化…」按钮随时可再次打开；状态栏横幅指引入口。

### 版本 / 测试 / 文档
- 正式版本号 `0.2.0`（`VERSION` 与 `python/__init__.py` `__version__`）；GUI `APP_VERSION` 保持独立。
- 测试增至 **110**（新增 `test_setup_profiles`：预设关系 / key 门控 / 选择顺序 / 串行编排 / 失败汇总 / 取消 / 库状态检测，零网络）。
- 新增 `docs/FIRST_RUN_SETUP.md`；更新 README / ROADMAP / PROJECT_STATUS。
- 打包 portable zip 并发布 v0.2.0 Release（不覆盖 v0.1.0；不改仓库可见性）。

> 以下 Phase 1 内容已并入 v0.2.0：

## [0.2.0-phase1] - 2026-06-11 — Portable Runtime（Phase 1 checkpoint，已并入 0.2.0）

v0.2.0 开发的**第一个 checkpoint**：让 NetworkIntel 从锁定 `E:\NetworkIntel` 变成真正支持任意目录运行的 portable 软件。**只 commit，不 tag，不 Release。**

### Portable 路径系统
- 新增统一路径模块 `python/utils/paths.py`：home 解析优先级 `NETWORKINTEL_HOME` → exe 目录 → 源码项目根 → cwd。
- 支持环境变量 `NETWORKINTEL_HOME` / `NETWORKINTEL_CONFIG` / `NETWORKINTEL_DATA_MODE` / `NETWORKINTEL_DATA_DIR`。
- `config_loader` 与 `logger` 的所有路径改为经 `paths` 解析；遗留 `E:\NetworkIntel` 绝对路径仅作兼容 fallback。

### 首次运行自动初始化
- 自动创建 `configs/live/cache/logs/reports/snapshots/backups/gdrive_sync`。
- 缺 `.env` 时从 `.env.example` 生成（缺模板用内置占位符模板）；缺 `configs/sources.yaml` 时从 `sources.example.yaml` 生成（缺模板报清晰错误）。
- 缺 `live/intel.db` **不自动下载、不阻断启动**，仅状态栏提示填 MaxMind Key 后更新。

### 数据目录模式 & GUI Key 设置
- portable（默认，数据跟随程序目录）/ custom（自定义数据目录，仅写 `.env`，不入版本库）。
- GUI 设置页可填写 MaxMind / ipinfo / ip2location / AbuseIPDB key：默认隐藏 + 显示切换 + 已配置/未配置状态；只写 `.env`，不写 `sources.yaml` 明文。

### 模板 / 脚本 / 测试
- `configs/sources.example.yaml` 改相对路径；`.env.example` 增补 portable 变量注释；`.bat` 改用 `%~dp0` 与 PATH 中的 `python`。
- `.gitignore` 增补 `*.exe` / `*.zip`。
- 测试增至 **95**（新增 `test_paths` / `test_portable_init` / `test_env_key_storage` / `test_data_dir_mode`）。
- 新增 `docs/PORTABLE_MODE.md`。

### 留待 v0.2.0 Phase 2（已在上方 0.2.0 完成）
- 首次运行向导、数据源选择下载（最小/推荐/完整/自定义）、打包 Release zip、改正式 `0.2.0` 并打 tag / 发 Release。

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
