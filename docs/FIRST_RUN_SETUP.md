# 首次初始化 / 数据源选择下载（v0.2.0）

> 自 **v0.2.0** 起，NetworkIntel 在首次启动检测到「缺库或空库」时，会提供**数据初始化向导**，
> 让你选择要下载的离线数据源并**串行**下载落库。本功能不新增 Provider、不接入在线 Provider 到主查询、
> 不改 `query_ip`。实现见 `python/datasources/setup_profiles.py` 与 GUI 的 `FirstRunSetupDialog`。

## 1. 何时触发

- **自动**：GUI 启动后，若 `live/intel.db` **不存在**，或存在但**无任何成功落库的数据源**
  （`source_meta` 中没有 `status='ok' 且 record_count>0` 的行），状态栏显示橙色提示，并自动弹出向导一次。
  向导**可关闭**（「稍后」），不强制、不阻断程序使用（保留 Phase 1 的「缺库不阻断启动」契约）。
- **手动**：任何时候在「数据源」页点击「**数据初始化…**」按钮重新打开（可用于重建 / 补齐数据库）。

数据库状态判定由 `setup_profiles.db_status(db_path)` / `needs_setup(db_path)` 提供（只读访问，不创建文件）。

## 2. 四种方案

| 方案 | 含义 |
|---|---|
| **最小** | `ip2asn` + `geoip`：ASN/BGP 前缀映射与地理库，满足基本离线查询。 |
| **推荐** | 最小 + `rir_delegated` / `rpki` / 全部 `cloud_*` / `tor_exits` / `vpn_x4bnet` / `spamhaus_drop` / `firehol` / `abusech` / `emerging_threats`。 |
| **完整** | 注册表中**全部 17 个**数据源（含默认关闭的 `peeringdb`）。体积最大、耗时最长。 |
| **自定义** | 逐源勾选，自由组合（默认勾选「推荐」集合）。 |

预设之间满足包含关系：`最小 ⊆ 推荐 ⊆ 完整`。下载与展示顺序固定为插件注册表顺序，结果可重复。

## 3. geoip 的 Key 依赖

`geoip`（MaxMind GeoLite2）需要 `MAXMIND_LICENSE_KEY`。

- 解析选择时，**若未配置该 Key，则自动把 geoip 从下载列表剔除**，并在摘要中标注「跳过（缺 Key）」。
- 自定义页中，缺 Key 的源复选框会被禁用并提示「需要 …，请先在设置页填写」。
- 填写 Key：设置页（F8）→「API KEY」→ MaxMind Key（只写入 `.env`，不写入 `sources.yaml` 明文）。填好后重新打开向导即可下载 geoip。

> Key 状态只读「已配置 / 未配置」，**绝不回显或记录真实 Key**。

## 4. 串行下载（为什么不是并发）

向导通过 `setup_profiles.download_sources()` **逐个**执行 `plugin.update()`（download→parse→load→snapshot）：

- **下载前先建表**。空库直接 `load()` 会 `no such table`，因此下载入口
  （`SetupDownloadWorker.run()`）在任何 `plugin.update()` 之前先调用
  `setup_profiles.prepare_database()` → `utils.schema.init_db()`，一次性创建全部表/索引
  （portable 解析到 `home/live/intel.db`，custom 解析到 `<data_dir>/live/intel.db`）。
- **绝不并发**。首次初始化面对的是空库，多源并发写 `intel.db` 会触发已审计的
  `database is locked`（见 [`SQLITE_CONCURRENCY_AUDIT.md`](SQLITE_CONCURRENCY_AUDIT.md)）。
  串行路径与命令行 `update.bat` / `do_update.py` 的安全模型一致。
- **失败继续**：单个源失败（或抛异常）不会中断整批，结尾汇总「成功 / 失败 / 总数」，逐源标注 `[OK]` / `[FAIL]`。
- **进度**：展示当前源的步骤与百分比 + 整体「已完成 / 总数」进度条。
- **取消**：取消在「下一个源开始前」生效（不会中断进行中的源），剩余源跳过。

下载执行器可注入（`updater` 参数），因此编排逻辑（顺序、失败聚合、取消）在**零网络**下可测，见 `tests/test_setup_profiles.py`。

## 5. 与「全部更新 / 调度器」的区别

| 入口 | 模型 | 适用 |
|---|---|---|
| 数据初始化向导（本页） | **串行** | 首次初始化 / 重建数据库，空库安全。 |
| `update.bat` / `do_update.py` | **串行** | 命令行批量更新。 |
| 数据源页「全部更新」/ 调度器 | 并发（~17 线程） | 增量刷新；空库或高并发下仍有 `database is locked` 风险，串行化修复列入 v0.3.0。 |

## 6. 安全红线（与全项目一致）

- 不新增 Provider；不把在线 Provider 接入 `query_ip` 主查询；不改 `query_ip`。
- 真实 Key 只存在于 `.env`；模板只放占位符；日志 / 弹窗不输出完整 Key。
- 不修改 SQLite 表结构；不移动数据 / 缓存 / 日志目录。
