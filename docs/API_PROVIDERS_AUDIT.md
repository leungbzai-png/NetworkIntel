# API / 数据源现状审计（API_PROVIDERS_AUDIT.md）

> 阶段：Provider 层规范化 — 第一步（只做现状映射，不改代码）
> 日期：2026-06-11
> 范围：`python/datasources/**`、`configs/sources.yaml`、`python/query/engine.py`、调度/CLI 调用链

---

## 0. 关键结论（决定 Provider 统一的难点）

1. **当前 17 个数据源全部是「批量下载型」（DownloadProvider）**：`download → parse → load` 写入 SQLite。
   **目前没有任何「在线逐 IP 查询型」（OnlineQueryProvider）**。
   而用户想接入的 ipinfo / ip2location / AbuseIPDB / BGPView / ThreatFox 多为**在线查询 API** —— 这是一个当前架构尚不存在的执行模型。统一接口必须同时覆盖这两种数据流。
2. **查询路径完全绕过插件**：`query/engine.py` 直接读 SQLite 表，不经过任何 plugin/provider。插件只负责「灌数据」，引擎只负责「读数据」。
3. **代码物理布局有“坑”**（非显而易见，迁移时必须知道）：
   - 6 个威胁情报插件的真实实现**全部集中在 `plugins/tor_exits.py`**；`spamhaus.py / vpn_x4bnet.py / abusech.py / emerging_threats.py / firehol.py` 只是 1 行 re-export 垫片。
   - 6 个云厂商插件的真实实现**全部集中在 `plugins/cloud_aws.py`**；`cloud_gcp.py / cloud_azure.py / cloud_cloudflare.py / cloud_hetzner.py / cloud_vultr.py` 也是 1 行垫片。
   - **IPv6 是一条独立平行链路**：`plugins_v6.py` 中的 `V6_PLUGINS` + `do_update_v6.py`，**不在** `PLUGIN_REGISTRY` 内，GUI/调度器也不管理它。
4. **全局无限速、无重试、无退避**：唯一错误处理在 `base.update()` 的 try/except 与 `_download_file()` 的 `raise_for_status()`（`timeout=120`）。这对在线查询型 API（如 AbuseIPDB 免费额度约 1000/天）是必须补齐的能力。

---

## 1. 已有基类 / 注册表

| 组件 | 位置 | 说明 |
|------|------|------|
| 插件基类 | `python/datasources/base.py` → `DataSourceBase(ABC)` | 抽象 `download/parse/load`；具体 `snapshot/update/_download_file/_update_meta/_bulk_insert` |
| v4 注册表 | `python/datasources/plugin_registry.py` → `PLUGIN_REGISTRY` | 17 个数据源 `name → class`；`get_plugin/get_all_plugins/get_enabled_plugins` |
| v6 注册表 | `python/datasources/plugins_v6.py` → `V6_PLUGINS` + `V6Base` | 独立，未并入 `PLUGIN_REGISTRY` |
| 配置 | `python/utils/config_loader.py` + `configs/sources.yaml` | 单源配置；P0 后支持 `.env` 与 `${VAR}` 解析 |
| 落库 | `python/utils/schema.py`（v4）/ `schema_v6.py`（v6） | 表结构与连接 |
| 查询引擎 | `python/query/engine.py` | 直接读 SQLite，**不经过插件** |

---

## 2. 数据源逐项映射（v4，`PLUGIN_REGISTRY` 内 17 个）

| 数据源 (name) | 实现文件 | 类型 | 写入表 | 需要 Key | 默认启用 | 调度 (cron) | 备注 |
|---|---|---|---|---|---|---|---|
| `geoip` | `plugins/geoip.py` | GeoIP / 下载 | `geoip` | ✅ MaxMind | 是 | `0 3 1 * *` | 下载 City+ASN CSV(zip)，先 `DELETE WHERE source` 再灌 |
| `ip2asn` | `plugins/ip2asn.py` | ASN/BGP / 下载 | `asn_info` | ❌ | 是 | `0 2 * * 1` | iptoasn tsv.gz |
| `rpki` | `plugins/rpki.py` | 路由(ROA) / 下载 | `rpki` | ❌ | 是 | `0 1 * * 1` | Cloudflare rpki.json，仅 valid ROA |
| `rir_delegated` | `plugins/rir_delegated.py` | 注册/ASN / 下载 | `rir_delegated` | ❌ | 是 | `0 2 1 * *` | 五大 RIR delegated-extended |
| `cloud_aws` | `plugins/cloud_aws.py` (`CloudBaseSource`) | 云/注册 / 下载 | `cloud_ranges` | ❌ | 是 | `0 4 1 * *` | provider=aws |
| `cloud_azure` | `plugins/cloud_aws.py` (垫片 `cloud_azure.py`) | 云/注册 / 下载 | `cloud_ranges` | ❌ | 是 | `0 4 1 * *` | 需先抓页面解析下载链接 |
| `cloud_gcp` | `plugins/cloud_aws.py` (垫片 `cloud_gcp.py`) | 云/注册 / 下载 | `cloud_ranges` | ❌ | 是 | `0 4 1 * *` | — |
| `cloud_cloudflare` | `plugins/cloud_aws.py` (垫片) | 云/注册 / 下载 | `cloud_ranges` | ❌ | 是 | `0 4 1 * *` | v4+v6 文本 |
| `cloud_hetzner` | `plugins/cloud_aws.py` (垫片) | 云/注册 / 下载 | `cloud_ranges` | ❌ | 是 | `0 4 1 * *` | 多 URL 兜底 + 静态网段 fallback |
| `cloud_vultr` | `plugins/cloud_aws.py` (垫片) | 云/注册 / 下载 | `cloud_ranges` | ❌ | 是 | `0 4 1 * *` | geofeed json |
| `tor_exits` | `plugins/tor_exits.py` (`ThreatBaseSource`) | 威胁情报 / 下载 | `threat_intel` | ❌ | 是 | `0 */6 * * *` | threat_type=tor |
| `vpn_x4bnet` | `plugins/tor_exits.py` (垫片 `vpn_x4bnet.py`) | 威胁情报 / 下载 | `threat_intel` | ❌ | 是 | `0 3 1 * *` | threat_type=vpn |
| `spamhaus_drop` | `plugins/tor_exits.py` (垫片 `spamhaus.py`) | 威胁情报 / 下载 | `threat_intel` | ❌ | 是 | `0 5 * * *` | drop+edrop, severity=high |
| `firehol` | `plugins/tor_exits.py` (垫片 `firehol.py`) | 威胁情报 / 下载 | `threat_intel` | ❌ | 是 | `0 5 * * 1` | level1/2/3 → critical/high/medium |
| `abusech` | `plugins/tor_exits.py` (垫片 `abusech.py`) | 威胁情报 / 下载 | `threat_intel` | ❌ | 是 | `0 6 * * *` | Feodo C2, severity=critical |
| `emerging_threats` | `plugins/tor_exits.py` (垫片 `emerging_threats.py`) | 威胁情报 / 下载 | `threat_intel` | ❌ | 是 | `0 6 * * *` | severity=high |
| `peeringdb` | `plugins/peeringdb.py` | 注册/Peering / 下载 | `peeringdb` | ❌ | **否** | `0 2 1 * *` | API 但当前按整表下载使用 |

> v6 平行链路（`V6_PLUGINS`，不在注册表内）：`geoip_v6 / ip2asn_v6 / rpki_v6 / rir_v6 / cloud_v6 / spamhaus_v6 / tor_v6` 等，写 `*_v6` 表（hex 范围）。

---

## 3. 按统一 Provider 分类的归并视图

| 拟定 Provider 类别 | 现有成员 | 执行模型 |
|---|---|---|
| **GeoIPProvider** | geoip（+ geoip_v6） | 下载 |
| **ASNProvider** | ip2asn, rpki, rir_delegated, peeringdb | 下载 |
| **CloudProvider**（注册型） | cloud_aws/azure/gcp/cloudflare/hetzner/vultr | 下载 |
| **ThreatIntelProvider** | tor_exits, vpn_x4bnet, spamhaus_drop, firehol, abusech, emerging_threats | 下载 |
| **OnlineQueryProvider**（**当前为空**） | 未来：ipinfo, ip2location, AbuseIPDB, BGPView, ThreatFox | 在线逐 IP 查询 |

---

## 4. 当前调用链路

### 4.1 数据更新（写）
```
GUI(SourcesPage/SchedulePage) / scheduler(cron) / CLI(do_update.py)
        │
        ▼
scheduler.trigger_now(name) ──► _run_source_update(name)
        │                              │
        │                              ▼
        │                 plugin_registry.get_plugin(name)  → DataSourceBase 子类实例
        │                              ▼
        │                 plugin.update()  =  download() → parse() → load() → snapshot() → _update_meta()
        ▼
do_update.py: get_enabled_plugins() → 逐个 plugin.update()
do_update_v6.py: V6_PLUGINS → 逐个 plugin.update()   （平行链路）
```

### 4.2 IP 查询（读）—— 不经过任何 provider/plugin
```
GUI/TUI/CLI ──► query.engine.query_ip(ip)
                    │
                    ▼
        get_connection(db) → 直接 SELECT geoip/asn_info/rpki/rir_delegated/
                              cloud_ranges/threat_intel/peeringdb/whois_cache
                    ▼
        calculate_risk(result) → 返回统一结果 dict（geoip/asn/rpki/cloud/threats/...）
```
> 含义：未来 OnlineQueryProvider 的 `normalize_result()` 应**对齐 `query_ip()` 的结果字典结构**，才能与本地数据合并。

---

## 5. 缓存逻辑现状

| 环节 | 行为 | 位置 |
|---|---|---|
| 下载缓存 | 写入 `cache/<source>/<filename>`，**整文件覆盖** | `base._download_file()` (`base.py:162`) |
| 无 HTTP 缓存 | 无 ETag / If-Modified-Since / Last-Modified；每次全量重下 | `base.py` |
| 快照归档 | `snapshot()` 复制到 `snapshots/<cat>/<period>/` **和** `gdrive_sync/<cat>/<period>/`（双写） | `base.py:81-114` |
| 落库去重 | 各 plugin `load()` 先 `DELETE FROM <table> WHERE source=?` 再 `INSERT OR REPLACE`，批量 5000 提交 | 各 `plugins/*.py` + `base._bulk_insert` |
| 查询缓存 | 引擎无结果缓存（`query_batch` 仅 session 内 dict 去重） | `engine.query_batch` |

---

## 6. 错误处理 & 限速现状

| 维度 | 现状 | 证据 |
|---|---|---|
| 下载错误 | `requests.get(timeout=120)` + `raise_for_status()`，异常向上抛 | `base.py:167-168` |
| 更新错误 | `base.update()` try/except 捕获 → 写 `source_meta.status='error'` + 记日志 | `base.py:153-156` |
| 调度错误 | `_run_source_update` try/except → `_job_status[...]='error'` + 回调通知 | `scheduler.py:74-83` |
| 查询错误 | `query_ip` 内子查询少量 try/except；引擎层 `except: pass` 偏多 | `engine.py` |
| **限速 / 重试 / 退避** | **完全没有**（无 `time.sleep`/`retry`/`backoff`/`Retry-After`/`429` 处理） | 全仓 grep 命中 0 |
| API Key 校验 | 仅 geoip 在 `download()` 内判空 + 占位符（`geoip.py:23`） | — |

> 对在线查询型 API：必须新增 `rate_limit` / `timeout` / 重试与 `429` 处理，这是当前架构的能力缺口。

---

## 7. 给 Provider 规范的输入要点（供第二步）

- 统一接口需同时表达两种数据流：`update()`（下载型，落库）与 `query(ip)`（在线型，实时返回并 `normalize_result()` 对齐 `query_ip` 结构）。
- 字段需覆盖：`name / category / enabled / requires_api_key / config_keys / rate_limit / timeout`。
- `requires_api_key` + `validate_config()` 必须对接 P0 的 `.env` + `${VAR}`：校验**解析后**的值非空且非占位符。
- 兼容优先：用适配器把现有 17 个 `DataSourceBase` 暴露为 Provider，**不迁移、不改动**旧实现。
