# NetworkIntel 本地离线IP情报平台

> 离线查IP，全可视化TUI界面，Windows原生部署，无需Docker

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

**方法一：程序界面设置**
- 启动程序 → F6设置页 → 粘贴 License Key → 保存

**方法二：直接编辑配置文件**
打开 `E:\NetworkIntel\configs\sources.yaml`，找到：
```yaml
geoip:
  license_key: "YOUR_MAXMIND_LICENSE_KEY_HERE"
```
替换为你的 Key：
```yaml
geoip:
  license_key: "AbCdEfGhIjKlMnOp"
```

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

*NetworkIntel v1.0 · 数据仅供参考，不构成任何安全建议*
