# Provider 迁移计划（API_PROVIDER_MIGRATION_PLAN.md）

> 阶段：Provider 层规范化 — 第三步（最小改造计划）
> 原则：**新增兼容层，不替换旧逻辑**；保证 `start.bat` / `update.bat` 持续可用。

---

## 1. 现状与目标差距

- 现状：17 个批量下载源（`DataSourceBase` + `PLUGIN_REGISTRY`），查询引擎直读 SQLite，无在线查询能力、无限速/重试。
- 目标：统一 Provider 抽象，既容纳现有下载源，又为 ipinfo/AbuseIPDB/BGPView/ThreatFox 等**在线查询源**预留位置。

---

## 2. 分批策略

### 第 0 批（本阶段，已做）— 零风险脚手架
- 新增 `python/providers/{__init__,types,base,registry}.py`，**不接入运行链路**。
- `registry` 以**兼容适配器**方式把现有 17 个源「视图化」为 DownloadProvider（仅注册类/工厂，**不实例化、不读配置**）。
- 文档三件套（audit / spec / plan）。

### 第 1 批（**本阶段已完成** — 旁路能力，低风险）— 在线查询脚手架
**已落地（全新代码，未接入主流程）：**
| Provider | 状态 |
|---|---|
| **BGPView** | ✅ 已实现 `query()` + `normalize_result()`（无需 Key），离线 mock 测试通过 |
| **AbuseIPDB** | 🧩 骨架 + `validate_config()`（`rate_limit` 已声明，免费约 1000/天） |
| **ThreatFox** | 🧩 骨架 + `validate_config()` |
| **ipinfo** | 🧩 骨架 + `validate_config()` |
| **ip2location** | 🧩 骨架 + `validate_config()` |

已新增的支撑件：
- `python/providers/http.py`：统一 HTTP（timeout/UA/429·5xx 重试/退避/JSON/统一失败对象）。
- `python/providers/online/`：`base.py`（OnlineApiProvider 密钥解析）+ 5 个 provider。
- `tests/`（21 用例，默认零网络）+ `tests/run_tests.py`（无 pytest 回退）+ `pytest.ini`。
- `scripts/provider_smoke_test.py`：手动自检（仅 BGPView 真实请求）。
- 模板：`.env.example` / `configs/sources.example.yaml` 增加在线 provider 占位与 `ONLINE_PROVIDERS_ENABLED=false`。
- 文档：`ONLINE_PROVIDERS.md` / `BGPVIEW_PROVIDER.md` / `TESTING.md`。

> 它们都实现 `OnlineQueryProvider.query()` + `normalize_result()` + `validate_config()`，不实现 `update()`。当前以「独立查询/旁路」方式验证，**未接入 `query_ip`**。

### 第 1.5 批（下阶段，低风险）— 把骨架补成真实实现
逐个把 ipinfo / ip2location / abuseipdb / threatfox 的 `query()` 从骨架补成真实请求（用 `providers.http`），加 mock 单测；仍保持旁路。

### 第 2 批（中期，中风险）— 下载源「双轨」纳管
- 让 `LegacyDownloadAdapter` 在 `do_update.py` 中**可选**地枚举（feature flag），与旧 `PLUGIN_REGISTRY` 并存验证一致性。
- 仍不删除旧路径。

### 第 3 批（远期，需评审）— 收敛
- 在线 provider 接入 `query_ip` 合并结果；下载源逐个迁为原生 Provider。

---

## 3. 暂时保持旧逻辑（不动）

- `query/engine.py` 读路径、SQLite 表结构、`_bulk_insert`/`snapshot` 流程。
- `scheduler.py` 与 `do_update.py` / `do_update_v6.py` 的现有调用链。
- 6 个威胁垫片（`tor_exits.py` 内聚）、6 个云垫片（`cloud_aws.py` 内聚）—— **不�afactor**。

---

## 4. 高风险、现在不建议动

| 项 | 风险 | 原因 |
|---|---|---|
| 把在线 provider 直接并进 `query_ip` | 高 | 引入网络依赖到「离线查询」主路径，违背离线定位；需缓存/限速设计 |
| 统一 v4/v6 插件 | 高 | `V6_PLUGINS` 平行链路 + hex 范围表，改动面大 |
| 拆分 `tor_exits.py` / `cloud_aws.py` 聚合文件 | 中高 | 牵动垫片与注册表，纯整理无功能收益 |
| 改 `_download_file` 加全局重试/限速 | 中 | 影响所有现有下载源行为，需单独回归 |

---

## 5. 预计修改的文件

**本阶段（第 0 批）实际改动：**
- 新增：`python/providers/__init__.py`、`types.py`、`base.py`、`registry.py`
- 新增：`docs/API_PROVIDERS_AUDIT.md`、`API_PROVIDER_SPEC.md`、`API_PROVIDER_MIGRATION_PLAN.md`
- **修改现有源码：0 个**（满足「≤10 文件、优先新增兼容层」约束）

**第 1 批（下阶段预计）：**
- 新增：`python/providers/online/{bgpview,abuseipdb,threatfox,ipinfo}.py`
- 修改：`configs/sources.example.yaml`（加在线源配置模板）、`.env.example`（加 `*_API_KEY` 占位）
- 可选新增：`python/providers/http.py`（带超时/重试/限速的 HTTP 小工具）

---

## 6. 测试方案

| 层级 | 测试 | 命令 |
|---|---|---|
| 导入惰性 | providers 包导入不触发 `get_config()`/网络/实例化 | `python -c "import providers.registry"`（在 `python/` 下） |
| 旧链路完好 | update 入口仍可导入 | `python -c "import do_update"` |
| 注册表内容 | 适配器枚举出 17 个源的元数据，且**不实例化** | `python -c "import providers.registry as r; print(len(r.get_provider_registry().list()))"` |
| 配置解析 | `.env` + `${VAR}` 仍解析（P0 回归） | 见第五步验证脚本 |
| 第 1 批（未来） | 每个在线 provider：`validate_config()`、`query()`、`normalize_result()` 单测 | `pytest`（待引入） |

---

## 7. 回滚方案

- 本阶段是**纯新增**：回滚 = 删除 `python/providers/` 与 `docs/API_PROVIDER_*.md`，或 `git revert <commit>`。
- 因未接入任何运行链路，**回滚不影响** `start.bat` / `update.bat` / 查询功能。
- 第 1 批起所有接入均以 **feature flag / 旁路** 方式引入，保证可单独关闭。
