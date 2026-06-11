# 在线 Provider 说明（ONLINE_PROVIDERS.md）

> 阶段：在线 Provider 旁路能力。**当前不接入 `query_ip` 离线主查询流程。**

---

## 1. 现状

| Provider | 类别 | 需要 Key | 状态 | env 变量 |
|---|---|---|---|---|
| `bgpview` | ASN/BGP | 否 | ✅ 已实现 query() | — |
| `ipinfo` | GeoIP/ASN | 是 | ✅ 已实现 query()（带 token） | `IPINFO_TOKEN` |
| `ip2location` | GeoIP | 是 | ✅ 已实现 query()（带 key） | `IP2LOCATION_API_KEY` |
| `abuseipdb` | 威胁情报 | 是 | ✅ 已实现 query()（带 key，旁路） | `ABUSEIPDB_API_KEY` |
| `threatfox` | 威胁情报 | 是 | 🧩 骨架 | `THREATFOX_API_KEY` |

> 缓存 / 限速 / 离线降级的设计与实现见 `docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md`。

### 旁路执行器（缓存 + 限速，已落地）
- `python/providers/online_runner.py::run_provider(name, ip, force_refresh=False, use_cache=True)`
- 顺序：允许列表（默认 `bgpview`/`ipinfo`/`ip2location`）→ `validate_config()` → 限速 `can_call()` → 查缓存 → 未命中才 `query()` → 写缓存。
- 缓存：独立 `cache/online_cache.sqlite`（不碰 `intel.db`）；限速：`cache/online_ratelimit.json`，429 进入冷却。
- **仍未接入 `query_ip`**：只能显式调用或经 smoke 脚本。
- 清理缓存：`python scripts/provider_smoke_test.py --purge-cache` / `--cache-stats`。

### ipinfo 使用
- 配置：在 `.env` 设 `IPINFO_TOKEN=...`（gitignored；token 经 `Authorization: Bearer` 头发送，不进 URL/日志）。
- 手动测试：`python scripts/provider_smoke_test.py --provider ipinfo --query 8.8.8.8`
  - 未配置 token 时**优雅提示缺 key**，不发请求、不打印 token、不崩溃。
- 统一输出字段：`ip / country_code / region / city / latitude / longitude / org / asn / asn_name / timezone / source / fetched_at / raw`。

### ip2location 使用
- 配置：在 `.env` 设 `IP2LOCATION_API_KEY=...`（gitignored；key 经 requests `params` 传递，不进 `HttpResult.url`/日志）。
- 手动测试：`python scripts/provider_smoke_test.py --provider ip2location --query 8.8.8.8`
  - 未配置 key 时**优雅提示缺 key**，不发请求、不打印 key、不崩溃。
- 统一输出字段：`ip / country_code / country_name / region / city / latitude / longitude / isp / domain / usage_type / asn / asn_name / source / fetched_at / raw`。

### abuseipdb 使用（威胁情报，旁路 Provider）
- **配置**：在 `.env` 设 `ABUSEIPDB_API_KEY=...`（gitignored；key 经请求头 `Key: <api_key>` 发送，**不进** URL/日志/异常/缓存/返回对象）。
- **手动测试**：`python scripts/provider_smoke_test.py --provider abuseipdb --query 8.8.8.8`
  - 未配置 key 时**优雅提示缺 key**（`missing_api_key`），不发请求、不打印 key、不崩溃。
  - 缺 key 校验发生在限速检查**之前**，因此即便处于熔断也仍是 `missing_api_key`。
- **统一输出字段**：`ip / abuse_confidence_score / total_reports / num_distinct_users / is_public / is_whitelisted / is_tor / usage_type / isp / domain / country_code / severity / threats / source / fetched_at / raw`。
- **severity 分级**（由 `abuse_confidence_score` 推导）：`0→clean`、`1-24→low`、`25-74→medium`、`75-100→high`。
- **为什么仍是旁路**：威胁结果直接影响风险评级、且免费额度敏感；接入 `query_ip` 主路径会引入网络依赖与额度风险，违背离线定位。当前只能经 `online_runner` / smoke 脚本显式调用。

#### 为什么 AbuseIPDB 默认 `per_day=900`（而非免费额度 1000）
- AbuseIPDB 免费档约 **1000 次/天**。默认 per_day 设为 **900** 而非 1000，是**主动留出 ~10% 安全余量**：
  - 避免与官方计数因时区/边界/并发产生偏差时**恰好触顶被封**；
  - 给手动排查、smoke 测试、缓存未命中的突发查询留缓冲；
  - 触达本地 900 上限即 `rate_limited`，由缓存兜底，**不会**继续打 API 直到官方 429。
- 该值可经 `.env` 的 `ABUSEIPDB_RATE_PER_DAY` 覆盖（连同 `ABUSEIPDB_RATE_PER_MINUTE` / `_PER_HOUR`）。

#### 威胁类 TTL 为什么较短
- 威胁状态时效性强（IP 被举报/洗白随时变化），缓存过久会让风险判定滞后。
- 因此 abuseipdb 缓存 TTL 默认 **6 小时**（`ABUSEIPDB_CACHE_TTL_HOURS`），远短于 GeoIP/ASN 的 14–30 天。

### ipinfo vs ip2location 字段差异
| 维度 | ipinfo | ip2location |
|---|---|---|
| 认证 | `Authorization: Bearer <token>`（请求头） | `?key=<key>`（query param，经 requests `params`） |
| country_name | 无（仅 `country_code`） | ✅ 有 |
| isp / domain / usage_type | 无 | ✅ 有（部分需较高套餐） |
| timezone | ✅ 有 | 本实现未映射（可后续补 `time_zone`） |
| ASN 来源 | 解析 `org`（如 `AS15169 Google LLC`） | 独立 `asn` + `as` 字段 |
| 缓存 TTL | `IPINFO_CACHE_TTL_DAYS`（默认 14） | `IP2LOCATION_CACHE_TTL_DAYS`（默认 14） |

> 两者字段不完全一致 —— 这正是未来**结果合并策略**要解决的问题：合并进 `query_ip` 时需定义统一 GeoIP 字段优先级（多源同字段如何取舍、缺字段如何回退）。该策略留待 enrichment 阶段评审，本阶段不做。

- 代码：`python/providers/online/*.py`
- 注册：`python/providers/online/__init__.py` 的 `ONLINE_PROVIDERS`
- HTTP 工具：`python/providers/http.py`（timeout / UA / 429·5xx 重试 / 退避 / JSON / 统一失败对象）

## 2. 不影响离线查询

在线 provider **未被** `query/engine.py`、`scheduler`、`do_update` 引用。`query_ip` 仍然完全离线、只读 SQLite。要使用在线 provider，只能显式调用 `providers.online`（如 smoke 脚本），不会进入主流程。

## 3. 配置 API key（仅在线 provider 需要）

1. 复制示例：`cp .env.example .env`
2. 在 `.env` 填入对应 key（`.env` 已被 `.gitignore` 忽略，不会提交）：
   ```
   ONLINE_PROVIDERS_ENABLED=false
   IPINFO_TOKEN=...
   ABUSEIPDB_API_KEY=...
   ```
3. key 解析顺序（见 `providers/online/base.py`）：
   - 先查 `configs/sources.yaml` 中该 source 的 `config_keys`（`${VAR}` 已解析）；
   - 回退到环境变量 `ENV_KEY`（`config_loader` 启动时已把 `.env` 载入 `os.environ`）。
4. 校验：`provider.validate_config()` 返回 `ok / missing`，**不打印 key**。

## 4. 手动测试

```
python scripts/provider_smoke_test.py            # 列出 provider + 校验配置 + 实测 BGPView
python scripts/provider_smoke_test.py --no-network
```
默认只对 BGPView（无需 key）发起真实请求；需要 key 的 provider 仅展示配置状态。

## 5. 后续接入步骤（每个在线 provider）

1. 在对应 `online/<name>.py` 实现 `query(ip)`：用 `providers.http.http_get_json` 发请求，鉴权头从 `_resolve_key()` 取。
2. 完善 `normalize_result()`，输出对齐 `query_ip` 结果结构（geoip/asn/threats/...）。
3. 把 name 加入 `online/__init__.py` 的 `IMPLEMENTED`。
4. 加单测（mock 响应；默认不依赖网络）。
5. 仍以**旁路**方式提供；是否合并进 `query_ip` 留待单独评审（见迁移计划第 4 节）。

## 6. 为什么暂不接入主查询链路

- NetworkIntel 定位是**离线查询**；把在线 API 放进 `query_ip` 会引入网络依赖、延迟与额度风险（如 AbuseIPDB 免费约 1000/天）。
- 需要先设计：结果缓存（落 SQLite 或内存）、限速、离线降级、与本地数据的合并优先级。
- 在这些就绪前，在线能力仅作旁路验证。
