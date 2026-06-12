# Release Notes — NetworkIntel v0.2.0

> **v0.2.0 = Portable Runtime + First-Run Setup。** 本版本把 v0.1.0 的「锁死在
> `E:\NetworkIntel` 绝对路径」限制彻底解除：解压到任意目录即可运行，首次启动自动创建运行目录，
> 并提供 GUI 设置页与数据源初始化向导。**离线主查询 `query_ip` 不变**，未新增任何 Provider。

---

## 这是什么

NetworkIntel 是一个 **Windows 本地、离线优先的 IP / 网络情报查询工具**：
查一个 IP 即可得到地理位置、ASN、RIR、RPKI、云归属、Tor/VPN、威胁情报、WHOIS 等信息，
并自动计算风险等级。**核心查询只读本地 SQLite，全程离线、可预测。**

v0.2.0 解决的是「**怎么把它装到任意机器、任意目录，并完成首次数据初始化**」，
而不是新增查询能力。

---

## 本版本新增（v0.2.0 包含）

### 1. Portable Runtime（任意目录运行）
- 解压到**任意目录**即可运行，不再依赖硬编码的 `E:\NetworkIntel`（修复 v0.1.0 的路径锁定限制）。
- **默认数据目录跟随程序目录**（portable 模式）：运行根目录 = exe 所在目录 / 源码项目根目录。
- 支持 **custom 自定义数据目录**：把 `live/cache/logs/...` 放到指定盘符/目录，配置仍留在程序目录。
- 路径解析集中在 `python/utils/paths.py` + `config_loader`，由环境变量
  `NETWORKINTEL_HOME / NETWORKINTEL_CONFIG / NETWORKINTEL_DATA_MODE / NETWORKINTEL_DATA_DIR` 驱动，
  通常无需手动设置（GUI 设置页可写入）。

### 2. First-Run Setup（首次运行自动初始化）
- 首次运行自动创建运行目录：`configs/ live/ cache/ logs/ reports/ snapshots/ backups/ gdrive_sync/`。
- 自动从 `.env.example` / `configs/sources.example.yaml` 生成 `.env` 与 `configs/sources.yaml`（已存在则不覆盖，幂等）。
- **空库首次初始化建表修复**：下载落库前先 `init_db` 建好全部表，避免每个源更新时报
  `no such table`（这是本次收口的阻断级修复，详见下文）。

### 3. GUI 设置页（key 管理）
- GUI 设置页支持填写 **MaxMind / ipinfo / ip2location / AbuseIPDB** 的 key。
- **key 只写入 `.env`，绝不进入 Git**，也不写入 `configs/sources.yaml`（后者用 `${VAR}` 引用）。
- key 绝不出现在日志 / 异常 / URL 中。

### 4. 数据源初始化向导
- GUI 提供「数据初始化 / 数据源下载」向导，识别 `needs_setup`（缺库或空库都视为需初始化）。
- 四种模式：**最小 / 推荐 / 完整 / 自定义**。
  - 最小：`ip2asn + geoip`，满足基本离线查询。
  - 推荐：最小 + RIR 分配 + RPKI + 全部云段 + 主流威胁列表。
  - 完整：注册表全部 17 个源（含默认关闭的 peeringdb）。
  - 自定义：逐源勾选。
- **MaxMind/GeoIP 需要 `MAXMIND_LICENSE_KEY`**，缺 key 时该源被**自动跳过并给出提示**（绝不读取/打印 key）。
- 下载**串行执行**（逐个 `plugin.update()`），规避空库并发写的 `database is locked`；单源失败汇总后继续，不让 GUI 崩溃。

---

## 本次收口修复（阻断级）

**空库 / 首次运行场景下，下载前未建表会导致每个源更新报 `no such table`。**

- 修复：首次下载入口（`SetupDownloadWorker.run()`）在调用 `download_sources()` **之前**
  统一调用 `setup_profiles.prepare_database()` → `utils.schema.init_db()`，
  一次性创建全部表与索引（`source_meta / asn_info / geoip / rpki / rir_delegated / cloud_ranges /
  threat_intel / peeringdb / whois_cache / query_history / batch_jobs`）。
- 修复集中、低侵入：未改 `query_ip`、未改 updater / provider、未改主库表结构。
- 已用端到端测试覆盖：portable / custom 两种数据目录下，空库 → 建表 → 串行写库均无 `no such table`。

> 提交溯源：建表调用点首见于 `c3f3f66`；本次收口补充端到端集成测试、Release Notes 与打包脚本。

---

## 版本轴说明

- **Project release version = v0.2.0**（GitHub tag / Release 轴）。
- **GUI `APP_VERSION` 仍独立保持 1.2.0**（GUI 自有 changelog，见 `python/CHANGELOG.md`），二者互不影响。

---

## 在线增强 key 是可选项（不影响本地初始化）

- 在线 Provider（BGPView / ipinfo / ip2location / AbuseIPDB）是**旁路能力，默认关闭，不接入离线主查询**。
- 在线增强 key 是**可选项**，**不是本地数据库初始化的必需项**。
- 唯一影响本地初始化的 key 是 **MaxMind `MAXMIND_LICENSE_KEY`**（仅 geoip 源下载需要）；缺它只是跳过 geoip，其余源照常。

---

## 发布形式 & 未包含内容

本版本**只发布 portable zip，不发布裸 exe**。

`NetworkIntel-v0.2.0-windows-x64-portable.zip` **不包含**：

| 内容 | 说明 |
|---|---|
| 数据库文件 | `live/*.db` 等不随包；首次运行后由用户自行选择数据源初始化 |
| API key | 任何真实 key 都不随包；用户在 GUI 设置页 / `.env` 自行配置 |
| `.env` / `configs/sources.yaml` | 只随包提供 `.env.example` / `sources.example.yaml` 模板 |
| 缓存 / 日志 / 报告 | `cache/`、`logs/`、`reports/` |
| 快照 / 备份 | `snapshots/`、`backups/` |
| 构建产物 | 整个 `dist/` / `build/`；只放单个 `NetworkIntel.exe` |

> **包体积约 220MB**：由 PySide6 + QtWebEngine 的 PyInstaller onefile 打包导致（内嵌 Chromium）。
> 本阶段**暂不瘦身**，不为减小体积裁剪 GUI/地图功能。

---

## 如何运行（portable zip）

1. 解压到任意目录。
2. 双击 `NetworkIntel.exe`。首次运行自动在本目录创建 `configs/ live/ cache/ logs/ reports/ snapshots/ backups/`。
3. 在 GUI **设置页**填写 MaxMind Key（写入 `.env`）。
4. 在**数据初始化向导**选择 最小 / 推荐 / 完整 / 自定义，串行下载数据源。
5. 默认数据目录跟随程序目录；如需独立数据盘，可在设置页改为自定义数据目录。

源码模式仍照常：`copy .env.example .env` → `copy configs\sources.example.yaml configs\sources.yaml`
→ `pip install -r requirements.txt` → `update.bat` → `start.bat`（详见 `README.md` / `docs/PORTABLE_MODE.md` / `docs/FIRST_RUN_SETUP.md`）。

---

## 测试

- **116 / 116 passed**，默认零网络、零真实 key 输出。
- 新增覆盖：空库 `needs_setup`、`prepare_database` 建表、portable/custom 数据目录解析、
  空库串行下载不再 `no such table`、最小模式串行执行、缺 MaxMind key 跳过 geoip。
- Phase 1 portable 测试与 Phase 2 数据源选择测试全部保留通过。

---

## 已知限制

- **SQLite 并发写入仍未根治**：首次初始化下载已**强制串行**规避，但 GUI/调度器「全部更新」
  并发路径的串行化留待 v0.3.0。审计见 `docs/SQLITE_CONCURRENCY_AUDIT.md`。
- **在线 Provider 不接入 `query_ip` 主流程**：在线能力仅旁路，离线主查询不依赖外部网络。
- **包体积约 220MB**：PyInstaller onefile + QtWebEngine 所致，本阶段不瘦身。

---

## 下一步计划

- **v0.3.0** SQLite 写入串行化 / 更新队列稳定性。
- **v0.4.0** 可选 online enrichment 接入 GUI。
- **v0.5.0** Provider 状态 / 缓存与限速状态展示。
- **v1.0.0** 稳定版。

完整路线见 [`ROADMAP.md`](../ROADMAP.md)。
