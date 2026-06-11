# 在线 Provider 说明（ONLINE_PROVIDERS.md）

> 阶段：在线 Provider 旁路能力。**当前不接入 `query_ip` 离线主查询流程。**

---

## 1. 现状

| Provider | 类别 | 需要 Key | 状态 | env 变量 |
|---|---|---|---|---|
| `bgpview` | ASN/BGP | 否 | ✅ 已实现 query() | — |
| `ipinfo` | GeoIP/ASN | 是 | ✅ 已实现 query()（带 token） | `IPINFO_TOKEN` |
| `ip2location` | GeoIP | 是 | 🧩 骨架 | `IP2LOCATION_API_KEY` |
| `abuseipdb` | 威胁情报 | 是 | 🧩 骨架 | `ABUSEIPDB_API_KEY` |
| `threatfox` | 威胁情报 | 是 | 🧩 骨架 | `THREATFOX_API_KEY` |

> 缓存 / 限速 / 离线降级的设计见 `docs/ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md`（合并进主查询前的前置条件）。

### ipinfo 使用
- 配置：在 `.env` 设 `IPINFO_TOKEN=...`（gitignored；token 经 `Authorization: Bearer` 头发送，不进 URL/日志）。
- 手动测试：`python scripts/provider_smoke_test.py --provider ipinfo --query 8.8.8.8`
  - 未配置 token 时**优雅提示缺 key**，不发请求、不打印 token、不崩溃。
- 统一输出字段：`ip / country_code / region / city / latitude / longitude / org / asn / asn_name / timezone / source / fetched_at / raw`。

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
