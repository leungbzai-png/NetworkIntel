# NetworkIntel 本地离线IP情报平台

> **当前版本：v0.1.0**（首个公开规范化版本）
> 离线查IP，全可视化界面，Windows原生部署，无需Docker

---

## 项目定位

**NetworkIntel 是一个 Windows 本地、离线优先的 IP / 网络情报平台。**

- **离线优先原则**：核心查询 `query_ip` **只读本地 SQLite**（`live/intel.db`），不依赖任何外部网络。
  断网、弱网环境下查询依旧可预测、稳定、即时。首次需联网下载数据，之后查询全程离线。
- **本地数据库**：17 个公开数据源经下载型 Provider 批量落库到 `live/intel.db`（GeoIP / ASN / RPKI /
  RIR / 云 IP 段 / Tor / VPN / 威胁情报 / WHOIS 等），统一只读查询并自动计算风险等级。
- **在线 Provider 旁路能力（可选、默认关闭、不接入主查询）**：另有一层「在线查询 Provider」
  作为**旁路增强**，受缓存 + 限速 + 429 熔断保护，**未接入** `query_ip` 主流程，不影响离线查询。
  详见 [`docs/ONLINE_PROVIDERS.md`](docs/ONLINE_PROVIDERS.md)。

### 已实现在线 Provider（旁路，显式调用）

| Provider | 类别 | 需要 Key | env 变量 |
|---|---|---|---|
| BGPView | ASN/BGP | 否 | — |
| ipinfo | GeoIP/ASN | 是 | `IPINFO_TOKEN` |
| ip2location | GeoIP | 是 | `IP2LOCATION_API_KEY` |
| AbuseIPDB | 威胁情报 | 是 | `ABUSEIPDB_API_KEY` |

> 在线能力仅能通过 `providers.online_runner.run_provider()` 或 `scripts/provider_smoke_test.py`
> **显式旁路调用**，绝不进入离线查询主流程。

### 文档导航

| 文档 | 内容 |
|---|---|
| [`DEVELOPMENT.md`](DEVELOPMENT.md) | 开发环境、目录结构、如何新增 Provider、如何提交代码 |
| [`ROADMAP.md`](ROADMAP.md) | 版本规划（v0.1 → v1.0） |
| [`PROJECT_STATUS.md`](PROJECT_STATUS.md) | 当前完成度、架构状态、风险、下一步 |
| [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md) | 发布前检查清单 |
| [`CLAUDE_HANDOFF.md`](CLAUDE_HANDOFF.md) | 给后续 AI/人接手的红线与交接说明 |
| [`CHANGELOG.md`](CHANGELOG.md) | 项目规范化变更记录 |
| [`docs/ONLINE_PROVIDERS.md`](docs/ONLINE_PROVIDERS.md) | 在线 Provider 说明 |
| [`docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md`](docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md) | 缓存 / 限速 / 熔断设计 |
| [`docs/SQLITE_CONCURRENCY_AUDIT.md`](docs/SQLITE_CONCURRENCY_AUDIT.md) | SQLite 并发写入审计 |
| [`docs/TESTING.md`](docs/TESTING.md) | 测试体系 |
| [`SECURITY.md`](SECURITY.md) | 密钥与安全规范 |

---

## 目录

1. [功能概览](#功能概览)
2. [系统要求](#系统要求)
3. [从零部署（完整步骤）](#从零部署)
4. [注册 MaxMind GeoLite2](#注册-maxmind-geolite2)
5. [首次初始化数据](#首次初始化数据)
6. [使用说明](#使用说明)
7. [配置说明](#配置说明)
8. [GDrive备份设置](#gdrive备份设置)
9. [打包为exe](#打包为exe)
10. [新增数据源插件](#新增数据源插件)
11. [常见问题](#常见问题)

---

## 功能概览

查一个IP能得到：

| 维度 | 内容 |
|------|------|
| 🌍 地理位置 | 国家/省份/城市/经纬度（GeoLite2） |
| 🏢 ASN | 自治系统号、机构名称、BGP前缀 |
| 🗂 RIR | ARIN/RIPE/APNIC/LACNIC/AFRINIC分配记录 |
| 🔐 RPKI | Valid / Invalid / Not-Found 路由验证 |
| ☁ 云服务商 | AWS / Azure / GCP / Cloudflare / Hetzner / Vultr |
| 🧅 Tor | 是否为Tor出口节点 |
| 🔒 VPN | 是否为已知VPN出口（X4BNet） |
| ⚠ 威胁情报 | Spamhaus / FireHOL / Abuse.ch / EmergingThreats |
| 📋 WHOIS | 本地缓存的注册信息 |

**风险等级自动计算**：🔴严重 / 🟠高危 / 🟡中危 / 🟢低危 / 🔵注意 / ✅正常

---

## 系统要求

- Windows 10/11（64位）
- Python 3.10+（已确认：`D:\Python\Python 3.11.9`）
- 磁盘空间：建议预留 20GB（数据库 + 快照 + 备份）
- 内存：4GB+
- 首次更新需要联网；查询时完全离线

---

## 从零部署

### 第一步：创建目录结构

以管理员身份运行 PowerShell：

```powershell
# 创建所有必要目录
$dirs = @(
    "E:\NetworkIntel\live",
    "E:\NetworkIntel\snapshots\threats",
    "E:\NetworkIntel\snapshots\bgp",
    "E:\NetworkIntel\snapshots\registry",
    "E:\NetworkIntel\snapshots\geoip",
    "E:\NetworkIntel\gdrive_sync\threats",
    "E:\NetworkIntel\gdrive_sync\bgp",
    "E:\NetworkIntel\gdrive_sync\registry",
    "E:\NetworkIntel\gdrive_sync\geoip",
    "E:\NetworkIntel\backups",
    "E:\NetworkIntel\configs",
    "E:\NetworkIntel\scripts",
    "E:\NetworkIntel\logs",
    "E:\NetworkIntel\cache",
    "E:\NetworkIntel\reports"
)
foreach ($d in $dirs) { New-Item -ItemType Directory -Force -Path $d }
Write-Host "目录创建完成"
```

### 第二步：复制项目文件

将 `python\` 目录和所有 `.bat` 文件、`configs\` 目录、`requirements.txt` 复制到 `E:\NetworkIntel\`

最终结构：
```
E:\NetworkIntel\
├── python\               ← 程序源码
├── configs\
│   └── sources.yaml      ← 配置文件
├── live\                 ← SQLite数据库（自动创建）
├── snapshots\            ← 数据快照
├── gdrive_sync\          ← GDrive同步目录
├── logs\                 ← 运行日志
├── cache\                ← 下载缓存
├── reports\              ← 导出的HTML/CSV报告
├── start.bat             ← 启动程序
├── update.bat            ← 手动全量更新
├── status.bat            ← 查看状态
├── build_exe.bat         ← 打包exe
└── requirements.txt
```

### 第三步：安装Python依赖

双击运行 `start.bat`，首次运行会自动安装依赖。

或者手动安装：
```cmd
D:\Python\python.exe -m pip install -r E:\NetworkIntel\requirements.txt
```

### 第四步：注册 MaxMind（见下节）

### 第五步：初始化数据

双击 `update.bat`，等待所有数据源下载完成（首次约需30-60分钟，主要取决于网速）。

### 第六步：启动程序

双击 `start.bat` 启动可视化界面。

---

## 注册 MaxMind GeoLite2

GeoLite2 提供免费的城市级地理位置数据，需要注册账号获取 License Key。

### 注册步骤

1. 访问 **https://www.maxmind.com/en/geolite2/signup**

2. 填写注册表单：
   - 姓名（随便填）
   - 邮箱（需要验证）
   - 公司名（可填"Personal"）
   - 点击 **Submit**

3. 查收邮件，点击验证链接，设置密码

4. 登录后，点击右上角账户名 → **My License Key**

5. 点击 **Generate new license key**
   - Description: `NetworkIntel`
   - 选 **No** (不用于 GeoIP Update 程序)
   - 点击 **Confirm**

6. 复制生成的 License Key（只显示一次，记得保存！）

### 填入配置

**推荐方式：写入 `.env`（绝不进 Git）**

1. 复制示例为 `.env`：
   ```cmd
   copy .env.example .env
   ```
2. 在 `.env` 中填写你的真实 Key（`.env` 已被 `.gitignore` 忽略，不会提交）：
   ```
   MAXMIND_LICENSE_KEY=your_key_here
   ```
3. `configs/sources.yaml` 中用占位符引用（**不写真实 Key**）：
   ```yaml
   geoip:
     license_key: "${MAXMIND_LICENSE_KEY}"
   ```
   程序启动时由 `config_loader` 自动把 `${MAXMIND_LICENSE_KEY}` 解析为 `.env` 中的值。

**也可：程序界面设置**
- 启动程序 → F6 设置页 → 粘贴 License Key → 保存（写入 `.env`，不写回 yaml）。

> ⚠ **不推荐**把真实 Key 直接写进 `configs/sources.yaml`。
> 直接编辑 yaml 填明文 Key **仅限本地临时测试**，且 **绝不要提交到 Git**
> （`configs/sources.yaml` 已被 `.gitignore` 忽略，但明文 Key 仍可能被误复制/泄漏）。

---

## 首次初始化数据

数据源更新顺序建议：

```
1. ip2asn       （最快，几MB，立刻有ASN查询）
2. tor_exits    （几十KB）
3. spamhaus_drop（几百KB）
4. abusech      （快速）
5. emerging_threats（快速）
6. firehol      （几MB）
7. rir_delegated（几十MB，需要几分钟）
8. rpki         （几十MB）
9. cloud_*      （各云厂商，合计几MB）
10. geoip       （最大，需要MaxMind Key，约100MB，解析需要几分钟）
```

在程序的「数据源」页点击 **全部更新**，或运行 `update.bat`。

---

## 使用说明

### 启动

双击 `start.bat` 或打包后的 `NetworkIntel.exe`

### 主界面快捷键

| 键 | 功能 |
|----|------|
| F1 | 单IP查询页 |
| F2 | 批量查询页 |
| F3 | 数据源状态页 |
| F4 | 调度任务管理 |
| F5 | 历史报告列表 |
| F6 | 系统设置 |
| Ctrl+Q | 退出 |

### 单IP查询

在 F1 页面输入框输入IP，按回车或点击查询按钮。

支持：
- IPv4：`1.1.1.1`
- IPv6：`2606:4700:4700::1111`

### 批量查询

在 F2 页面：
- 直接粘贴多个IP（每行一个）
- 或输入文件路径，如 `E:\myips.txt`

查询完成后自动生成 HTML 报告并用浏览器打开，同时生成 CSV 文件。

报告保存在 `E:\NetworkIntel\reports\`

### 修改更新频率

**方法一**：在 F4 调度页，选中数据源行，在下方输入新的 cron 表达式，点击应用。

**方法二**：编辑 `configs\sources.yaml` 中的 `schedule` 字段。

cron 表达式说明：
```
分钟 小时 日 月 星期
 0    3   *  *  *    ← 每天凌晨3点
 0    4   *  *  1    ← 每周一凌晨4点
 0    2   1  *  *    ← 每月1日凌晨2点
 0   */6  *  *  *    ← 每6小时
```

---

## 配置说明

`configs\sources.yaml` 主要配置项：

```yaml
global:
  theme: "system"          # system=跟随系统 / dark / light

sources:
  geoip:
    enabled: true          # 是否启用
    schedule: "0 3 1 * *"  # 调度频率（cron）
    license_key: "..."     # MaxMind License Key

  peeringdb:
    enabled: false         # 默认关闭，需要改为 true 启用
```

---

## GDrive备份设置

1. 下载安装 **Google Drive 桌面客户端**
   - 访问 https://www.google.com/drive/download/

2. 登录你的 Google 账号

3. 在 Google Drive 设置中，添加「镜像文件夹」：
   - 选择 `E:\NetworkIntel\gdrive_sync\`

4. 完成！每次数据源更新时，快照会自动同步到 Google Drive

备份内容：
```
gdrive_sync\
├── threats\    ← Tor/VPN/Spamhaus等威胁情报（每日）
├── bgp\        ← ASN/RPKI数据（每周）
├── registry\   ← RIR/云IP段（每月）
└── geoip\      ← 地理数据（每月）
```

---

## 打包为exe

运行 `build_exe.bat`，完成后 exe 位于：
```
E:\NetworkIntel\python\dist\NetworkIntel.exe
```

> **exe 需要本地自行构建。** `dist/`、`build/` 与 exe **不随源码仓库发布**（已在 `.gitignore`）：
> 它们体积大、与本机环境相关，且 GitHub 源码仓库只放源代码。
> 未来若提供预编译版本，会通过 **GitHub Releases** 分发（作为 Release 附件），
> 而**不会**提交进 Git 仓库。

**注意**：PyInstaller 打包的 exe 可能被杀毒软件（360、火绒等）误报。
解决方法：将 `dist\` 目录加入杀毒软件白名单/信任区。

---

## 新增数据源插件

只需三步，无需修改任何核心文件：

**第一步**：在 `python\datasources\plugins\` 新建 `my_source.py`：

```python
from datasources.base import DataSourceBase
from utils.ip_utils import network_to_range

class MySource(DataSourceBase):
    SOURCE_NAME = "my_source"
    SOURCE_DESCRIPTION = "我的新数据源"

    def download(self) -> str:
        return self._download_file("https://example.com/list.txt", "my_list.txt")

    def parse(self, file_path):
        with open(file_path) as f:
            for line in f:
                ip = line.strip()
                if ip:
                    start, end = network_to_range(f"{ip}/32")
                    yield {
                        "network": f"{ip}/32",
                        "network_start_int": start,
                        "network_end_int": end,
                        "threat_type": "custom",
                        "list_name": "my_source",
                        "severity": "medium",
                        "source": self.SOURCE_NAME,
                        "snapshot_date": self.today_str,
                    }

    def load(self, records) -> int:
        # 写入已有的 threat_intel 表即可
        columns = ["network","network_start_int","network_end_int",
                   "threat_type","list_name","severity","source","snapshot_date"]
        count = 0
        with self._bulk_insert("threat_intel", columns) as insert:
            for rec in records:
                insert(rec)
                count += 1
        return count
```

**第二步**：在 `python\datasources\plugin_registry.py` 添加一行：
```python
from datasources.plugins.my_source import MySource
# 在 PLUGIN_REGISTRY 字典中添加：
"my_source": MySource,
```

**第三步**：在 `configs\sources.yaml` 添加配置：
```yaml
my_source:
  enabled: true
  schedule: "0 6 * * *"
  snapshot_category: "threats"
  description: "我的新数据源"
```

重启程序，新数据源就会出现在数据源列表中。

---

## 常见问题

**Q: 程序启动后查询全部返回空/无数据**
A: 需要先运行 `update.bat` 下载数据。首次必须联网。

**Q: GeoIP查询没有结果**
A: 检查 MaxMind License Key 是否正确填写，以及 `geoip` 数据源是否已更新。

**Q: 打包的exe被杀毒软件删除**
A: 将 `E:\NetworkIntel\python\dist\` 目录加入杀毒软件白名单。

**Q: 想修改数据库路径到其他磁盘**
A: 编辑 `configs\sources.yaml` 中 `global.db_path` 和 `global.base_dir`。

**Q: 更新失败提示网络错误**
A: 部分数据源（如Spamhaus）可能需要代理。检查 `logs\networkintel.log` 查看具体错误。

**Q: PeeringDB数据怎么启用**
A: 编辑 `sources.yaml`，将 `peeringdb.enabled` 改为 `true`，然后触发更新。

**Q: 如何查询多个IP但不生成报告**
A: 在 F2 批量页查询后，关闭浏览器弹出的报告即可。报告文件保存在 `reports\`，可以删除。

---

## 启动方式

| 入口 | 用途 |
|---|---|
| `start.bat` | 启动可视化界面（推荐，自动装依赖） |
| `update.bat` | 手动全量更新数据（CLI，串行执行 `python/do_update.py`） |
| `python python/main.py` | 直接运行主程序（TUI/CLI 入口） |
| `python python/main_gui.py` | 直接运行 PySide6 图形界面 |

> CLI 更新（`update.bat` → `do_update.py`）**串行**执行各数据源，单写者，安全。
> GUI/调度器的「全部更新」为并发触发，写库并发性请参阅
> [`docs/SQLITE_CONCURRENCY_AUDIT.md`](docs/SQLITE_CONCURRENCY_AUDIT.md)。

---

## 配置方式

| 文件 | 作用 | 是否提交 git |
|---|---|---|
| `.env` | **真实密钥**（MaxMind / ipinfo / AbuseIPDB 等） | ❌ 已 gitignore，绝不提交 |
| `.env.example` | 密钥模板（仅占位符） | ✅ 提交 |
| `configs/sources.yaml` | **真实**数据源/调度配置（密钥写 `${VAR}` 引用 `.env`） | ❌ 已 gitignore |
| `configs/sources.example.yaml` | 配置模板（仅 `${VAR}` 占位符） | ✅ 提交 |

首次配置：
```cmd
copy .env.example .env
copy configs\sources.example.yaml configs\sources.yaml
```
然后编辑 `.env` 填入真实 key。`sources.yaml` 里用 `${MAXMIND_LICENSE_KEY}` 等引用，
由 `config_loader` 在加载时从 `.env` 解析（不把明文写进被 git 跟踪的文件）。

### API key 配置说明

仅**在线 Provider** 需要 key（离线查询不需要任何 key）。在 `.env` 设置：
```
MAXMIND_LICENSE_KEY=...          # 离线 GeoIP 下载需要
IPINFO_TOKEN=...                 # 在线 ipinfo（旁路）
IP2LOCATION_API_KEY=...          # 在线 ip2location（旁路）
ABUSEIPDB_API_KEY=...            # 在线 AbuseIPDB（旁路，免费约 1000/天）
```
key 解析顺序：先查 `sources.yaml` 对应源的 `${VAR}`，回退环境变量。
key 经请求头/params 发送，**绝不进入** URL / 日志 / 异常 / 缓存 / 返回对象。
未配置 key 时在线 Provider **优雅提示缺 key**，不发请求、不崩溃。

---

## 哪些文件不会上传 GitHub

为保护隐私与控制仓库体积，以下内容**不随源码发布**（已在 `.gitignore`）：

| 类型 | 路径 |
|---|---|
| 真实密钥 | `.env`、`.env.*`（保留 `.env.example`） |
| 真实配置 | `configs/sources.yaml`、`configs/*.local.yaml`（保留 `sources.example.yaml`） |
| 数据库 | `live/*.db`、`*.db` / `*.sqlite` / `*.sqlite3`（含 WAL/SHM） |
| 缓存/快照/备份 | `cache/`、`snapshots/`、`gdrive_sync/`、`backups/` |
| 日志/报告 | `logs/`、`reports/`、`*.log` |
| 构建产物 | `dist/`、`build/`、`*.spec`（**exe 不随源码发布**） |
| 本地工具配置 | `.claude/settings.local.json`、`.vscode/`、`.idea/` |

> 克隆源码后需自行 `copy .env.example .env`、`copy configs\sources.example.yaml configs\sources.yaml`，
> 填入自己的 key，并运行 `update.bat` 下载数据。**数据库与 key 都不在仓库里。**

---

## 安全注意事项

- **绝不提交**：`.env`、`configs/sources.yaml`、`cache/`、`logs/`、`reports/`、`snapshots/`、
  `backups/`、`live/*.db`、exe / 构建产物（均已在 `.gitignore`）。
- 真实 key 只写 `.env`；模板文件（`*.example.*`）只放占位符。
- 提交前用 `git status` / `git diff` 自检，确认无真实 key、无大数据库文件。
- 详见 [`SECURITY.md`](SECURITY.md) 与 [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md)。

---

## 已知限制（v0.1.0）

- **数据库不随源码发布**：克隆后需自行运行 `update.bat` 首次联网下载（之后查询全程离线）。
- **API key 需用户自行配置**：在线 Provider（ipinfo / ip2location / AbuseIPDB）需在 `.env` 填入各自 key；
  离线查询本身不需要任何在线 key（仅 GeoIP 下载需 MaxMind Key）。
- **SQLite 并发写入风险已审计但 v0.1.0 未修复**：GUI/调度器「全部更新」会并发写库，可能偶发
  `database is locked`（随机源 status=error）。**规避：改用 `update.bat`（串行更新）**。
  详见 [`docs/SQLITE_CONCURRENCY_AUDIT.md`](docs/SQLITE_CONCURRENCY_AUDIT.md)，修复列入后续路线。
- **在线 Provider 不接入 `query_ip` 主流程**：在线能力仅旁路，离线主查询不依赖任何外部网络。

---

## 后续路线

当前公开版本 **v0.1.0**。后续规划（轻量、可能调整，见 [`ROADMAP.md`](ROADMAP.md)）：

- **v0.2.0** SQLite 写入串行化（busy_timeout → 写锁或 writer queue → 事务原子化）
- **v0.3.0** 可选 online enrichment（独立 `enrich()`，可关闭，不改 `query_ip`）
- **v0.4.0** GUI 状态页：Provider 状态 / 缓存与限速状态展示
- **v0.5.0** 发布包 / 数据分离
- **v1.0.0** 稳定版

---

## 测试方式

```cmd
python tests/run_tests.py            # 内置最小运行器（无需 pytest）
python -m pytest                     # 若已安装 pytest
python scripts/provider_smoke_test.py                 # Provider 自检（默认不联网）
python scripts/provider_smoke_test.py --rate-limit-status
```
- 当前 **76 个测试，默认零网络**（HTTP 层用 monkeypatch 注入模拟响应）。
- 测试只读 `*.example.*` 模板，断言无真实 key；不读真实 `.env`。
- 详见 [`docs/TESTING.md`](docs/TESTING.md)。

---

## 数据源版权说明

| 数据源 | 许可 |
|--------|------|
| MaxMind GeoLite2 | Creative Commons 4.0 (需署名，不可商用) |
| ip2asn | 公共域 |
| RIR Delegated | 各RIR公开数据 |
| Cloudflare RPKI | 公开API |
| 云服务商IP段 | 各厂商公开发布 |
| Tor Exit List | 公开数据 |
| Spamhaus DROP | 免费用于非商业目的 |
| FireHOL | GPL v3 |
| Abuse.ch | 公开数据 |
| EmergingThreats | 社区规则免费使用 |

---

*NetworkIntel v0.1.0 · 数据仅供参考，不构成任何安全建议*
