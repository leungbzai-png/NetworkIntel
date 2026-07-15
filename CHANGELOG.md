# 变更记录（CHANGELOG.md）

> 项目**工程化/发布**轨道的变更记录（与 `python/CHANGELOG.md` 的 GUI 功能记录互补，二者版本轴独立）。
> 遵循语义化版本，最新在上。后续版本规划见 [`ROADMAP.md`](ROADMAP.md)。

---

## [0.3.0] - 2026-07-15 — 串行化 SQLite 更新队列 / 数据源更新稳定性

主题严格限定为 **SQLite 写入串行化 / 数据源更新队列稳定性**。
**不含** UI 重构、新 Provider、数据库 schema 大改造；不改 `query_ip` 只读离线路径；不换 SQLite。
详见 [`docs/RELEASE_NOTES_v0.3.0.md`](docs/RELEASE_NOTES_v0.3.0.md)。

### 新增
- **统一更新协调器** `python/update_coordinator.py`：单消费线程串行化所有数据源写库，
  同一进程内任一时刻最多一个源在写库。含 `UpdateCoordinator` / `UpdateJob` / `UpdateResult` /
  `UpdateState`，接口 `enqueue_source` / `enqueue_many` / `is_busy` / `queue_size` /
  `get_source_state` / `wait_for_job` / `shutdown`，全局单例 `get_coordinator()`。
  相同源已 queued/running 时重复触发返回 `skipped(duplicate)`；单源失败不终止队列；daemon worker 不阻塞退出。
- **敏感值脱敏** `python/utils/redaction.py`：异常/日志/GUI 文案中的 `license_key` / `token` /
  `api_key` / `Authorization` 等替换为 `***`（修复失败下载 URL 可能带出 MaxMind key 的泄露面）。

### 变更
- **连接策略统一**（`utils/schema.py`）：新增 `connect_read` / `connect_write` 工厂，统一
  `busy_timeout=30000`、`foreign_keys=ON`、WAL（失败优雅回退 + 告警）、`synchronous=NORMAL`；
  写连接 `isolation_level=None`（autocommit）以显式 `BEGIN IMMEDIATE`；`get_connection` 保留为只读别名。
  `schema_v6` 建表与在线缓存连接同步加 `busy_timeout`。
- **事务原子化**（`datasources/base.py` + 7 个插件 `load()`）：`_bulk_insert` 改为单连接单事务，
  `__enter__` 取写锁（带有限退避重试）后在**同一事务**内 `DELETE old + INSERT new`，
  退出时一次性 COMMIT / 异常整体 ROLLBACK；杜绝「删旧插一半」空窗。插件 `load()` 改用
  `replace_source=True`（download/parse/load 签名不变）。修复 `_update_meta` 连接泄漏。
- **锁错误分类**：`update()` 单独识别 `database is locked`（`error_type=db_locked`），
  日志与普通网络/解析错误区分，并记录脱敏 traceback。
- **调度器改造**（`scheduler/scheduler.py`）：`trigger_now` / `trigger_all` / cron 任务全部委派协调器，
  不再自起写库线程；`get_job_status` 数据源改为协调器；`stop()` 有序关闭协调器。
- **CLI**（`do_update.py`）：走协调器串行队列，按序输出每源状态 + 汇总；仅失败时返回非零码；
  缺 MaxMind Key 的 `geoip` 标记 `skipped`。
- **首次初始化向导**：`setup_profiles.download_sources` 的默认执行器改为投递协调器，
  与 GUI/调度器/CLI 共用同一写库实现。
- **GUI**（`main_gui.py`）：「全部更新」进行中禁用按钮 / 提示「更新任务正在执行」，
  显示当前源、完成数/总数与成功/失败/跳过汇总；新增 `queued` / `skipped` 状态色；
  v0.2.1 的 `SourcesPage` 容错逻辑保持不退化。

### 测试
- 新增 `test_update_coordinator` / `test_update_queue_concurrency` /
  `test_sqlite_connection_policy` / `test_update_transactions` /
  `test_scheduler_update_coordination`：最大并行度恒为 1、同源去重、两次「全部更新」不并行、
  失败隔离、状态时序、busy_timeout 生效/WAL 回退、每线程独立连接、事务提交/中途回滚保留旧数据、
  锁有限重试后失败（不死锁）、脱敏、队列 shutdown 不挂死。
- 全量 **165 / 165 passed**（`run_tests.py` 与 `pytest` 等价），零网络、零真实 key、临时库隔离。

### 版本
- 项目发布版本 `0.3.0`（`VERSION` 与 `python/__init__.py` `__version__`）；GUI `APP_VERSION` 保持独立（1.2.0）。
- 不重写 / 不删除 v0.1.0 / v0.2.0 / v0.2.1 的 tag、Release 或 asset；v0.3.0 作为 Latest 发布。

---

## [0.2.1] - 2026-06-12 — Hotfix：数据源页面列表空白

仅修复 portable 版「数据源」页面在初始化完成后列表可能整页空白的显示 bug。
**不改数据库格式、不改 key 配置方式、不改 v0.2.0 的 portable 使用方式**，不新增功能。

### 修复
- **数据源页面列表空白（阻断级显示 bug）**：`SourcesPage` 的表格创建段历史上被误置于
  `_open_setup()` 作用域内，导致 `self.table` 从未在 `_build()` 中创建；`refresh()` 访问
  `self.table` 即抛 `AttributeError` 并被宽泛 `except` 静默吞掉，页面框架照常但中间列表永远空白。
  将表格创建段移回 `_build()`，确保构造时即创建并加入布局。该缺陷自 v0.2.0 数据源向导引入起即存在。
- **状态合并抽为纯函数 + 容错强化**：新增 `compute_source_status_rows()`（纯函数，可无 GUI 测试）。
  空库 / 无 `source_meta` 表 / schema 不匹配时照常列出全部配置源（记录数 0、状态 never）；
  单个数据源状态读取失败只把该行降级为 `error`，绝不因单源失败丢行或清空整页；异常记入日志而非静默吞掉。
- 「刷新」「数据初始化…」「全部更新」后页面均会重新加载并刷新状态。

### 测试
- 新增 `tests/test_sources_page.py`：纯函数空库/含数据/实时覆盖/单源隔离用例，
  以及 headless（offscreen Qt）构造 `SourcesPage` 断言 `table` 已创建且行数 == 配置源数量。
- 全量 **133 / 133 passed**，零网络、零真实 key 输出。

### 版本
- 项目发布版本 `0.2.1`（`VERSION` 与 `python/__init__.py` `__version__`）；GUI `APP_VERSION` 保持独立（1.2.0）。
- 不重写 / 不删除 v0.2.0 的 tag、Release 或 asset；v0.2.1 作为 Latest 发布。

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

### 发布前收口（阻断级修复）
- **修复空库首次初始化 `no such table`**：首次下载入口在 `download_sources()` 前统一调用
  `setup_profiles.prepare_database()` → `utils.schema.init_db()`，一次性建好全部表/索引；
  修复集中、低侵入，未改 `query_ip` / updater / provider / 主库表结构。
- 新增端到端测试：portable / custom 数据目录下，空库 → 建表 → 串行写库均无 `no such table`。

### 发布前 UI 收口（首次初始化体验打磨）
- **数据初始化向导单选选中态修复**：全局 `QWidget { background-color }` 规则会抑制原生 QRadioButton
  indicator 渲染（Windows 上表现为「圈没有颜色」）。为 `QRadioButton::indicator`（及同源的
  `QCheckBox::indicator`）显式补充未选/悬停/选中/禁用样式，选中后填充强调色且对应方案整行加粗高亮，
  浅色 / 深色主题下均清晰可见。仅修 UI 显示，不改分组逻辑、不改缺 Key 跳过 geoip 的逻辑、不改下载执行。
- **状态栏 DB 长路径显示优化**：新增 `utils.paths.short_db_path()`，状态栏只显示 `...\live\intel.db`
  形式的短路径，完整路径通过 tooltip 查看；不影响真实 `db_path`、portable/custom data_dir、
  设置页「当前路径」完整显示。

### 版本 / 测试 / 文档
- 正式版本号 `0.2.0`（`VERSION` 与 `python/__init__.py` `__version__`）；GUI `APP_VERSION` 保持独立（1.2.0）。
- 测试增至 **126**（`test_setup_profiles`：预设关系 / key 门控 / 选择顺序 / 串行编排 / 失败汇总 / 取消 / 库状态检测；
  `test_first_run_db_init`：空库建表 / portable·custom 路径解析 / 空库串行下载不再 `no such table` / 最小模式串行；
  `test_paths`：`short_db_path` 状态栏短路径格式化；零网络、零真实 key）。
- 新增 `docs/FIRST_RUN_SETUP.md`、`docs/RELEASE_NOTES_v0.2.0.md`；更新 README / ROADMAP / PROJECT_STATUS。
- 仅发布 portable zip（不发布裸 exe）；不覆盖 v0.1.0；不改仓库可见性。

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
