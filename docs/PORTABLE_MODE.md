# Portable 运行模式（v0.2.0 Phase 1）

> 自 **v0.2.0 Phase 1** 起，NetworkIntel 不再锁定 `E:\NetworkIntel`，可从**任意目录**运行。
> 路径解析全部由 `python/utils/paths.py` 统一负责，配置/数据/日志均围绕「程序根目录」展开。

## 1. 核心概念

| 名称 | 含义 |
|---|---|
| **home（程序根目录）** | 存放 `configs/` 与 `.env` 的目录。portable 模式下也存放全部运行时数据。 |
| **data_dir（数据目录）** | 存放 `live/cache/logs/reports/snapshots/backups/gdrive_sync` 的目录。 |

## 2. home 解析优先级

1. 环境变量 `NETWORKINTEL_HOME`
2. 打包 exe 所在目录（`sys.frozen`）
3. 源码运行时的项目根目录（`python/utils/paths.py` 的上三级）
4. 当前工作目录（fallback）

## 3. 支持的环境变量

| 变量 | 作用 | 默认 |
|---|---|---|
| `NETWORKINTEL_HOME` | 程序运行根目录 | exe 所在目录 / 源码项目根目录 |
| `NETWORKINTEL_CONFIG` | `sources.yaml` 完整路径 | `<home>/configs/sources.yaml` |
| `NETWORKINTEL_DATA_MODE` | `portable` 或 `custom` | `portable` |
| `NETWORKINTEL_DATA_DIR` | custom 模式下的数据目录 | 仅 custom 模式生效 |

这些变量可写入 `<home>/.env`，也可由 GUI 设置页写入。

## 4. 两种数据目录模式

### Portable（默认）
- `data_dir = home`
- 所有运行时目录都在程序目录下，整包可随 U 盘 / 文件夹迁移。
- **portable 模式会忽略 `NETWORKINTEL_DATA_DIR`**（即使设置了也不生效）。

### Custom
- `data_dir = NETWORKINTEL_DATA_DIR`
- `live/cache/logs/reports/snapshots/backups/gdrive_sync` 放在自定义数据目录下。
- `configs/` 与 `.env` 仍保留在 home 下。
- 自定义数据目录只写入 `.env`（被 `.gitignore` 忽略），**绝不写入 Git tracked 文件**。

## 5. 首次运行自动初始化

首次运行（`config_loader.ensure_initialized()`，由 `get_config()` 自动触发）会：

1. 创建 `configs/live/cache/logs/reports/snapshots/backups/gdrive_sync` 目录。
2. 若缺 `.env`：从 `.env.example` 复制；缺模板则写入内置占位符模板（**不含真实 key**）。
3. 若缺 `configs/sources.yaml`：从 `configs/sources.example.yaml` 复制；缺模板则报清晰错误。
4. **不会自动下载数据库**。若 `live/intel.db` 不存在，程序正常启动，仅在状态栏提示：
   「数据库未初始化，请在设置页填写 MaxMind Key 后运行更新」。

## 6. sources.yaml 路径解析规则

`global.*` 路径按 portable 规则解析：

- 相对路径 → 相对 `data_dir`（如 `live/intel.db` → `<data_dir>/live/intel.db`）。
- 遗留绝对路径 `E:\NetworkIntel\...` → 若该路径真实存在则保留（兼容老用户），否则转换为 portable 默认路径。
- 其它绝对路径 → 原样保留（高级用户显式覆盖）。

模板 `sources.example.yaml` 已改为相对路径，新用户解压到任意目录即可运行，无需手改。

## 7. GUI 设置页

设置页（F8）提供：

- **API KEY**：填写 MaxMind / ipinfo / ip2location / AbuseIPDB key。
  - 默认隐藏（密码框），可点「显示」切换。
  - 留空表示不修改；保存只写入 `.env`，**不写入 `sources.yaml` 明文**。
  - 每个 key 显示「已配置 / 未配置」状态（占位符视为未配置，**不回显真实 key**）。
- **数据目录模式**：选择 Portable / Custom，展示 home 与 data_dir；切换后需重启生效。
  - 不会自动搬迁旧数据；不提供「迁移数据」按钮。

## 8. 安全红线

- 真实 key 只存在于 `.env`；模板只放占位符。
- custom data_dir 只写 `.env`，不进版本库。
- 日志 / 异常 / 弹窗均不输出完整 key。

## 9. 仍属于 Phase 2 的内容

- 首次运行向导（First Run Setup）。
- 数据源选择下载界面（最小 / 推荐 / 完整 / 自定义）。
- 最终打包与 Release。
