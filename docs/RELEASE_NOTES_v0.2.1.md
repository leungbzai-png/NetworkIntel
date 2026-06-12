# Release Notes — NetworkIntel v0.2.1 (hotfix)

> **v0.2.1 = 仅修复 portable 版「数据源页面列表空白」的 hotfix。** 不做功能重构、
> **不改数据库格式**、**不改 key 配置方式**、**不改 v0.2.0 的 portable 使用方式**。
> 已使用 v0.2.0 的用户无需迁移数据：直接替换程序目录中的 `NetworkIntel.exe` 即可。

---

## 修复内容

### 数据源页面初始化完成后列表可能空白（阻断级显示 bug）

**现象**：portable 版首次初始化成功下载全部数据源后，进入 GUI 左侧「数据源」页，
只显示标题、说明与底部按钮（刷新 / 数据初始化… / 全部更新），**中间数据源列表整页空白**，
看不到任何已下载的数据源行。

**根因**：`SourcesPage` 的「表格」创建段（`QTableWidget` 创建 + `addWidget` 到布局）
历史上被误置于 `_open_setup()` 方法作用域内，而不是 `_build()` 内。结果 `self.table`
**从未在页面构造时创建**，`refresh()` 一进来访问 `self.table` 即抛 `AttributeError`，
又被一个宽泛的 `except` 静默吞掉 —— 页面框架照常显示，唯独中间的列表永远不被创建、
不被加入布局，于是整页空白。该缺陷自 v0.2.0 数据源向导特性引入起即存在。

**修复**：
- 把表格创建段移回 `_build()`，确保 `self.table` 在页面构造时即创建并加入布局。
- 把「配置源 + DB 元数据 + 调度器实时状态」的合并抽成**纯函数**
  `compute_source_status_rows()`，便于无 GUI 单元测试覆盖。
- **容错强化**：
  - 即使数据库为空 / 无 `source_meta` 表 / schema 不匹配，也照常列出**全部已配置数据源**，
    记录数显示 0、状态显示 `never`（未下载），而不是整页空白。
  - **单个数据源**状态合并出错只把该行降级为 `error` 状态，**绝不**因单源失败而丢行或清空整页。
  - 各类读取异常都会记录到日志/控制台，而不是被静默吞掉后留下空白页面。
- 「刷新」「数据初始化…」完成、「全部更新」触发后，页面都会重新加载并显示最新状态。

---

## 不变事项（与 v0.2.0 完全一致）

- **数据库格式不变**：沿用 v0.2.0 的 `intel.db` 与全部表结构，**无需重建库、无需迁移数据**。
- **key 配置方式不变**：仍只写入 `.env`，绝不进入 Git / `configs/sources.yaml`；GUI 设置页用法不变。
- **portable 使用方式不变**：解压到任意目录运行；运行根目录跟随 exe；首次运行自动建目录。
- **离线主查询 `query_ip` 不变**：未新增 / 改动任何 Provider 或查询逻辑。
- **GUI `APP_VERSION` 仍独立保持 `1.2.0`**（GUI 自有 changelog 轴）；本次只升项目发布版本到 `0.2.1`。

---

## 升级方式

1. 从 GitHub Release 下载 `NetworkIntel-v0.2.1-windows-x64-portable.zip`。
2. 解压后用其中的 `NetworkIntel.exe` **覆盖**你现有 v0.2.0 程序目录下的 `NetworkIntel.exe`。
   - 你现有的 `configs/sources.yaml`、`.env`、`live/intel.db` 等运行时数据**原样保留**，无需改动。
3. 重新启动，进入「数据源」页即可看到完整的数据源列表与状态。

> 全新安装的用户：解压到任意干净目录，双击 `NetworkIntel.exe`，按 v0.2.0 的首次初始化流程操作即可。

---

## 测试

- **133 / 133 passed**，默认零网络、零真实 key 输出。
- 本次新增 `tests/test_sources_page.py`：
  - 空库下数据源状态列表非空、返回全部配置源（status=never）。
  - 含数据的 `source_meta` 能回带记录数 / 状态 / 时间。
  - 调度器实时状态覆盖 DB 元数据。
  - 单源合并异常被隔离，不影响其它源（不丢行）。
  - headless（offscreen Qt）构造 `SourcesPage`，断言 `table` 已创建且行数 == 配置源数量
    —— 直接钉住本次回归。

---

## 发布形式 & 安全

- 与 v0.2.0 一致：**只发布 portable zip**，包内不含数据库 / 真实 key / `.env` /
  `configs/sources.yaml` / 缓存 / 日志 / 报告 / 快照 / 备份 / 构建产物。
- **不改动 v0.2.0 的 tag、Release 或其 asset**；v0.2.1 作为 Latest 发布。
