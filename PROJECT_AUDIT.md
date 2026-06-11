# PROJECT_AUDIT.md — NetworkIntel 项目审计报告

> 审计类型：只读架构审计（未修改任何代码、未移动任何文件、未重构）
> 审计日期：2026-06-11
> 审计对象：`E:\NetworkIntel`
> 应用版本：`APP_VERSION = 1.2.0` / `APP_BUILD = 2026-06-05`（见 `python/main_gui.py:41-42`）

---

## 0. 一句话结论

NetworkIntel 是一个 **Windows 原生、离线 IP 情报查询平台**：插件化数据源 → SQLite 落库 → TUI/GUI 查询 + 报告导出 + APScheduler 定时更新。
后端架构清晰、解耦良好（插件基类设计是亮点）；**主要问题集中在工程治理层面**：硬编码密钥已落盘、未纳入 Git 版本控制、双份代码/双份 GUI 并行维护、大量一次性调试脚本与构建产物混入仓库。

---

## 1. 当前目录结构

```
E:\NetworkIntel\
├── python\                     ← 【核心源码】主代码根（运行时 chdir 到此）
│   ├── main.py                 ← 入口①：Textual TUI 主程序
│   ├── main_gui.py             ← 入口②：PySide6 桌面 GUI（1728 行，主力 GUI）
│   ├── gui_extensions.py       ← GUI 扩展页（Dashboard / Network / ThreatLibrary）
│   ├── gui_map.py              ← GUI 地图组件（可选，依赖 QtWebEngine）
│   ├── do_update.py            ← 入口③：CLI 全量更新（IPv4）
│   ├── do_update_v6.py         ← 入口④：CLI 更新（IPv6）
│   ├── do_status.py            ← 入口⑤：CLI 状态查看
│   ├── check_db.py / check_v6.py / debug_ip2asn.py        ← 一次性调试脚本
│   ├── fix_index.py / fix_ip2asn_only.py / fix_query_speed.py ← 一次性修复脚本
│   ├── datasources\
│   │   ├── base.py             ← 插件基类 DataSourceBase（download/parse/load/snapshot/update）
│   │   ├── plugin_registry.py  ← 插件注册表（17 个数据源）
│   │   ├── plugins\            ← 17 个 IPv4 数据源插件
│   │   └── plugins_v6.py       ← IPv6 数据源（单文件，未拆分）
│   ├── query\engine.py         ← 查询引擎（v4/v6 全维度子查询）
│   ├── scheduler\scheduler.py  ← APScheduler 调度器（cron + 手动触发）
│   ├── reports\generator.py    ← HTML/CSV 报告生成
│   ├── utils\                  ← config_loader / schema / schema_v6 / ip_utils / logger
│   ├── tui\                    ← （空 __init__）
│   ├── NetworkIntel.spec       ← PyInstaller 打包配置
│   ├── build\ , dist\ , dist_backup\  ← 【构建产物，不应入库】
│   └── *.bat                   ← backup / build_gui_exe / update
├── configs\
│   └── sources.yaml            ← 【唯一配置文件】数据源 + 全局路径 + 含密钥
├── live\
│   └── intel.db                ← 【主数据库】SQLite，约 1.68 GB
├── cache\                      ← 各数据源下载缓存（GeoLite2 / ip2asn / RIR / 云段 / 威胁源…）
├── snapshots\                  ← 数据快照（threats=日 / bgp=周 / registry,geoip=月）
├── gdrive_sync\                ← 与 snapshots 内容重复，供 Google Drive 镜像
├── backups\
│   └── backup_20260605_182216\ ← 【整份代码 + 1.68GB intel.db 的全量副本】
├── logs\startup_error.txt      ← 日志目录（当前几乎为空）
├── reports\                    ← HTML/CSV 报告输出目录
├── scripts\                    ← （空）
├── *.bat                       ← start / update / update_v6 / status / build_exe / 等
├── requirements.txt / requirements_gui.txt
├── README.md / .gitignore
└── （注：根目录非 Git 仓库 — 无 .git）
```

---

## 2. 关键位置标记（按要求识别）

| 类别 | 位置 | 说明 |
|------|------|------|
| **主入口（TUI）** | `python/main.py` → `main()` (`:902`) | Textual 全可视化界面，`start.bat` 调用 |
| **GUI 入口** | `python/main_gui.py` → `if __name__=="__main__"`（文件尾，1728 行） | PySide6 桌面端，功能更全（含地图/仪表盘），实际主力 |
| **CLI 入口** | `python/do_update.py`、`do_update_v6.py`、`do_status.py` | 命令行全量更新 / 状态；`update.bat`、`status.bat` 调用 |
| **数据库文件** | `live/intel.db`（≈1.68 GB） | 默认路径 `configs/sources.yaml > global.db_path`，回退值在 `utils/config_loader.py:85` |
| **数据库 Schema** | `python/utils/schema.py`、`schema_v6.py` | 全表 DDL；`init_db()` / `get_connection()` |
| **配置文件** | `configs/sources.yaml` | 唯一配置源；默认路径硬编码在 `utils/config_loader.py:13` |
| **缓存目录** | `cache/`（`global.cache_dir`） | 每个数据源一个子目录，`base.py:49` |
| **日志目录** | `logs/`（`global.logs_dir`），另有 `python/error.log`、`logs/startup_error.txt` | `utils/logger.py` |
| **快照目录** | `snapshots/`（`global.snapshots_dir`） | `base.py:snapshot()` 按类别分目录 |
| **报告目录** | `reports/` | `reports/generator.py:55` |
| **GDrive 同步目录** | `gdrive_sync/`（`global.gdrive_sync_dir`） | 快照同时写入此处（`base.py:105`） |
| **更新脚本** | `python/do_update*.py` + `update.bat` / `update_v6.bat` + 调度器自动触发 | — |
| **API/网络调用代码** | `python/datasources/base.py:162-173`（`_download_file` 统一 `requests.get`）；各 `plugins/*.py` 的 `download()`；URL 全在 `configs/sources.yaml` | 唯一对外 HTTP 出口，便于审计 |

### API/外部端点清单（全部来自 `configs/sources.yaml`，均为公开数据源）
MaxMind GeoLite2、iptoasn.com、五大 RIR（ARIN/RIPE/APNIC/LACNIC/AFRINIC）、Cloudflare RPKI、AWS/Azure/GCP/Cloudflare/Hetzner/Vultr IP 段、Tor 项目、X4BNet VPN、Spamhaus DROP、FireHOL、Abuse.ch、EmergingThreats、PeeringDB（默认禁用）。

---

## 3. 安全风险：密钥/凭证扫描结果（仅标记位置，不输出真实内容）

> 约定：以下仅标记**位置**，真实值已脱敏。

| 严重度 | 类型 | 位置 | 说明 |
|--------|------|------|------|
| 🔴 严重 | **明文 API Key（MaxMind License Key）** | `configs/sources.yaml:15` `license_key: ********` | 真实密钥已写入磁盘明文（非占位符） |
| 🔴 严重 | **同一密钥的副本** | `backups\backup_20260605_182216\sources.yaml:15` | 备份目录中存在第二份明文密钥 |
| 🟠 高危 | **.gitignore 未保护该配置** | `.gitignore`（`# configs/sources.yaml` 被注释掉） | 一旦 `git add`，含密钥的 yaml 会被提交；保护规则处于关闭状态 |
| 🟡 中危 | 占位/示例 Key | `README.md:160,165`、`python/main.py:682`（`YOUR_MAXMIND_LICENSE_KEY_HERE`） | 仅占位符，非真实凭证（可忽略） |
| 🟢 信息 | 第三方数据自带 token | `snapshots/.../cloud_gcp_*.json`、`cloud_aws_*.json` 中的 `syncToken` | 属下载到的数据内容（GCP/AWS 同步游标），非本项目凭证 |

**未发现**：硬编码 Password、Secret、Bearer Token、私有 Access Key（除上述 MaxMind Key 外，代码中无其他凭证）。

> 备注：`main.py:684` / `main_gui.py` 设置页对 Key 输入框使用了 `password=True` 掩码显示，处理意识到位；问题在于**落盘存储为明文且无加密/无环境变量隔离**。

---

## 4. 模块关系（架构图）

```
                         ┌────────────────────────────────────────────┐
   入口层                │  main.py (TUI)   main_gui.py (PySide6 GUI)  │
                         │  do_update.py / do_status.py (CLI)          │
                         └───────┬─────────────────────┬──────────────┘
                                 │ 调用                 │ 调用
                 ┌───────────────┴───────┐    ┌─────────┴───────────────┐
   服务层        │  query/engine.py       │    │ scheduler/scheduler.py  │
                 │  (query_ip/query_batch)│    │ (cron + trigger_now)    │
                 │  reports/generator.py  │    └─────────┬───────────────┘
                 └───────────┬────────────┘              │ _run_source_update
                             │ 读                        │ get_plugin()
                             │                ┌──────────┴──────────────┐
                             │                │ datasources/            │
                             │                │   plugin_registry.py    │
                             │                │   base.py (DataSourceBase)
                             │                │   plugins/*.py (17)     │
                             │                │   plugins_v6.py         │
                             │                └──────────┬──────────────┘
                             │   download→parse→load→snapshot
                             ▼                           ▼
                 ┌─────────────────────────────────────────────────────┐
   基础层        │  utils/  schema.py · config_loader.py · ip_utils.py  │
                 │          logger.py · schema_v6.py                    │
                 └───────────┬──────────────────────┬──────────────────┘
                             ▼                       ▼
                    live/intel.db (SQLite)   configs/sources.yaml
                             │
              cache/ → snapshots/ → gdrive_sync/   reports/*.html,*.csv
```

**依赖方向（健康）**：入口 → 服务 → 数据源/基础，单向、无循环依赖。
`utils.config_loader` 与 `utils.schema` 是全局单例汇聚点，被所有层引用。

**模块耦合评价**
- ✅ 插件系统通过 `DataSourceBase` + `PLUGIN_REGISTRY` 实现良好解耦：新增数据源「三步、零核心改动」（README 已文档化，名副其实）。
- ✅ `query.engine` / `scheduler` / `reports` 仅依赖后端接口，GUI 与 TUI 共享同一后端（`main_gui.py` 注释明确「后端零改动」）。
- ⚠️ `config_loader._config`、`scheduler._scheduler`、`_job_status` 为模块级全局单例，跨线程共享 —— 见技术债/并发风险。

---

## 5. 技术债（Technical Debt）

| # | 技术债 | 位置/证据 | 影响 |
|---|--------|-----------|------|
| TD-1 | **未纳入版本控制** | 根目录无 `.git`（已有 `.gitignore` 却无仓库） | 无历史、无回滚、无协作基线；最高优先级治理问题 |
| TD-2 | **整份代码 + 1.68GB 数据库的全量副本入目录** | `backups\backup_20260605_182216\code\*` + `intel.db` | 双份源码漂移风险；占用 ~1.7GB；密钥二次泄漏面 |
| TD-3 | **两套 GUI 并行维护** | `main.py`(Textual TUI) 与 `main_gui.py`(PySide6) | 同样 6 个页面双份实现，逻辑重复、易不一致 |
| TD-4 | **大量一次性脚本散落源码根** | `check_db.py`、`check_v6.py`、`debug_ip2asn.py`、`fix_index.py`、`fix_ip2asn_only.py`、`fix_query_speed.py` | 污染源码树，分不清正式入口与临时脚本 |
| TD-5 | **构建产物入库** | `python/build/`、`dist/NetworkIntel.exe`(219MB)、`dist_backup/`（两个 exe 共 268MB） | 仓库膨胀 ~700MB；`dist_backup` 文件名含中文时间戳 |
| TD-6 | **路径全程硬编码** | `config_loader.py:13` 默认 `E:\NetworkIntel\...`；所有 `.bat` 写死 `D:\Python\python.exe`、`E:\NetworkIntel` | 不可移植，换盘/换机即失效 |
| TD-7 | **IPv4/IPv6 实现不对称** | 插件：`plugins/*.py`(17 个独立文件) vs `plugins_v6.py`(单文件聚合)；引擎 `_query_*` 与 `_query_*_v6` 成对重复 | 维护需双改，易遗漏一侧 |
| TD-8 | **snapshots 与 gdrive_sync 数据完全重复** | `base.py:105` 同一文件写两份 | 磁盘占用翻倍 |
| TD-9 | **空壳目录/模块** | `scripts/`（空）、`python/tui/`（空 `__init__`） | 残留结构，意图不明 |
| TD-10 | **`requirements.txt` 缺 GUI 依赖** | GUI 依赖 PySide6 在 `requirements_gui.txt`；`.bat` 安装命令手写包列表，与 requirements 不同步 | 依赖声明分散、易漂移 |
| TD-11 | **`calculate_risk` 控制流冗余** | `query/engine.py:29-31`（`if not threats: pass`） | 死分支，可读性噪音（仅风格债，逻辑正确） |

---

## 6. 风险点（运行时/正确性/并发）

| # | 风险 | 位置 | 说明 |
|---|------|------|------|
| R-1 | **跨线程共享 SQLite 连接** | `utils/schema.py:261` `check_same_thread=False`；GUI/调度器各自起线程 | WAL 模式下读多写少尚可，但写并发（多源同时 `trigger_all`）+ 全局单例可能出现锁竞争/`database is locked` |
| R-2 | **`trigger_all` 同时起 N 个后台线程并发写库** | `scheduler.py:129-134` 每源一个 daemon 线程 | 17 源并发 `INSERT OR REPLACE`，无写串行化，可能争锁 |
| R-3 | **geoip 范围查询依赖隐式假设** | `engine.py:176-187`（`WHERE start<=ip ORDER BY start DESC LIMIT 1` 再判 end） | 依赖网段不重叠；若数据含重叠段可能命中错误行（其余表用 `start<=ip AND end>=ip` 更稳健） |
| R-4 | **异常被静默吞掉** | 多处 `except Exception: pass`（如 `engine.py:381`、`main.py` 各 `_refresh`） | 故障无声化，排障困难 |
| R-5 | **报告/CSV 路径直接拼接打开浏览器** | `main.py:486`、`main_gui.py` `webbrowser/os.startfile` | 文件名来自查询结果，正常可控；若引入外部不可信 IP 列表需留意路径注入 |
| R-6 | **首启数据库为空无强约束** | `main.py:850-857` 仅 notify 提示 | 用户未跑 update 时查询全空，体验/误判风险（已有提示，属低危） |
| R-7 | **调度器时区写死 Asia/Shanghai** | `scheduler.py:91` | 跨时区部署 cron 行为偏移 |
| R-8 | **PyInstaller exe 杀软误报** | README 已知问题 | 分发摩擦（非代码缺陷） |

---

## 7. 推荐改进项

> 仅为建议清单，**本次审计未执行任何改动**。

**A. 安全（立即）**
- A1. 轮换/作废 `configs/sources.yaml:15` 中已落盘的 MaxMind License Key（视为已泄漏）。
- A2. 将密钥迁出 yaml：改用环境变量或单独的 `secrets.local.yaml`（不入库）；yaml 仅保留 `${MAXMIND_KEY}` 占位。
- A3. 删除 `backups\...\sources.yaml` 中的密钥副本；规范备份不含凭证。
- A4. 启用 `.gitignore` 中被注释的 `configs/sources.yaml` 保护规则（或改为忽略 `*.local.yaml`）。

**B. 版本控制与仓库瘦身（短期）**
- B1. `git init` 建立基线；确认 `.gitignore` 已覆盖 `live/ cache/ snapshots/ gdrive_sync/ backups/ dist/ build/ *.exe`。
- B2. 将 `python/build/`、`dist/`、`dist_backup/`、`backups/` 移出工作树（构建产物与备份不应与源码同栈）。
- B3. 一次性脚本（`check_*`、`debug_*`、`fix_*`）收敛到 `python/tools/` 或 `scripts/`，与正式入口分离。

**C. 架构与可维护性（中期）**
- C1. 统一依赖声明：合并/分层 `requirements.txt`（core）+ `requirements_gui.txt`（extras），让 `.bat` 改为 `pip install -r`。
- C2. 路径去硬编码：以「可执行文件所在目录 / 环境变量」推导 `base_dir`，移除 `config_loader.py:13` 与各 `.bat` 的绝对盘符。
- C3. IPv4/IPv6 收敛：将 `plugins_v6.py` 拆入 `plugins/` 并复用基类；引擎 `_query_*` 用版本参数化，减少成对重复。
- C4. 明确单一主 GUI（建议 PySide6 为正式版，TUI 降级为可选/轻量入口），避免双份页面逻辑漂移。

**D. 健壮性（中期）**
- D1. 写库串行化：为 `_run_source_update` 引入写锁/队列，或单写连接，缓解 R-1/R-2。
- D2. 用具体异常替换 `except Exception: pass`，至少 `logger.warning`，恢复可观测性。
- D3. geoip 查询补 `AND network_end_int >= ip`（与其它表一致），消除 R-3 隐患。
- D4. 调度器时区改为可配置（读 `global.timezone`）。

---

## 8. 优先级排序（行动顺序）

| 优先级 | 行动 | 对应项 | 理由 |
|--------|------|--------|------|
| **P0 立即** | 轮换 MaxMind 密钥 + 迁出明文 + 清备份副本 + 开启 gitignore 保护 | A1–A4 | 凭证已明文落盘且有副本，泄漏面最大、修复成本最低 |
| **P1 本周** | `git init` 建基线；构建产物/备份/大文件移出工作树 | B1–B2, TD-1/2/5 | 没有 VCS 等于无安全网；仓库 ~2.4GB 膨胀拖累一切后续操作 |
| **P2 短期** | 收敛一次性脚本；统一依赖声明；路径去硬编码 | B3, C1–C2, TD-4/6/10 | 提升可移植性与可读性，为协作铺路 |
| **P3 中期** | 写库串行化 + 异常可观测化 + geoip 查询修正 | D1–D3, R-1/2/3/4 | 消除并发与正确性隐患，提升稳定性 |
| **P4 中期** | IPv4/IPv6 收敛；确定单一主 GUI；时区可配置 | C3–C4, D4, TD-3/7 | 降低长期双份维护成本（架构债，非紧急） |

---

## 9. 审计边界声明

- 本报告为**只读审计**：未修改任何源代码、未移动/删除任何文件、未执行重构。
- 未运行应用、未连接数据库写操作、未触发任何数据源更新。
- 凭证类发现仅标注**位置并脱敏**，未在本报告中复制任何真实密钥值。
- 数据库内部数据质量（记录正确性/覆盖率）不在本次源码审计范围内。

*— 审计结束 —*
