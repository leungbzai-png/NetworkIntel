# 统一 Provider 规范（API_PROVIDER_SPEC.md）

> 阶段：Provider 层规范化 — 第二步（设计接口，不强制旧 provider 立即实现）
> 配套代码骨架：`python/providers/{types,base,registry}.py`（兼容层，**未接入现有运行链路**）

---

## 1. 设计原则

1. **双数据流是一等公民**：统一接口必须同时表达
   - `update()` —— 批量下载型，把数据灌入 SQLite（现有 17 个源）；
   - `query(ip)` —— 在线逐 IP 查询型，实时返回（未来 ipinfo / AbuseIPDB / BGPView / ThreatFox …）。
   不强行让两种模型实现对方的方法：不适用者声明为 no-op 或抛 `ProviderNotSupported`。
2. **不破坏、不替换**：旧 `DataSourceBase` 插件保持原样；通过适配器纳入统一视图。
3. **渐进实现**：基类只规定签名与默认行为，允许 provider 仅实现与自己相关的子集。
4. **对齐既有结果结构**：`query()` 的 `normalize_result()` 输出须对齐 `query/engine.py::query_ip()` 的结果字典（`geoip/asn/rpki/cloud/threats/is_tor/is_vpn/...`），便于未来与本地数据合并。
5. **对接 P0 密钥规范**：`requires_api_key` / `validate_config()` 基于 `.env` + `${VAR}` 的**解析后**值判断，占位符（`${...}` / `YOUR_..._HERE`）视为未配置。

---

## 2. 统一接口字段与方法

每个 Provider 暴露以下**属性**（元数据）与**方法**（行为）：

### 2.1 属性（元数据）

| 字段 | 类型 | 含义 | 默认 |
|---|---|---|---|
| `name` | `str` | 唯一标识，对应 `sources.yaml` 的 key | 必填 |
| `category` | `ProviderCategory` | GEOIP / ASN / ROUTING / CLOUD / THREAT_INTEL / ONLINE_QUERY / REGISTRY | 必填 |
| `kind` | `ProviderKind` | DOWNLOAD / ONLINE_QUERY（决定主数据流） | 必填 |
| `enabled` | `bool` | 是否启用（取自配置） | `True` |
| `requires_api_key` | `bool` | 是否需要密钥 | `False` |
| `config_keys` | `list[str]` | 需要的配置键名（如 `["license_key"]` / `["api_key"]`） | `[]` |
| `rate_limit` | `RateLimit \| None` | 速率限制（次/窗口、并发） | `None` |
| `timeout` | `float` | 单次请求超时（秒） | `30.0` |

### 2.2 方法（行为）

| 方法 | 签名 | 适用 | 默认/约定 |
|---|---|---|---|
| `query(ip)` | `(str) -> NormalizedResult` | OnlineQuery | DownloadProvider 抛 `ProviderNotSupported` |
| `update()` | `() -> UpdateResult` | Download | OnlineQueryProvider 为 no-op（返回 skipped） |
| `normalize_result(raw)` | `(Any) -> NormalizedResult` | OnlineQuery | 把原始 API 响应映射到统一结构（对齐 `query_ip`） |
| `validate_config()` | `() -> ConfigValidation` | 全部 | 检查 `config_keys` 解析后非空、非占位符 |
| `error_handler(exc, ctx)` | `(Exception, dict) -> ProviderError` | 全部 | 归一化异常（网络/限速/鉴权/解析），含是否可重试 |

---

## 3. 数据结构（`providers/types.py`）

```text
ProviderCategory(Enum): GEOIP | ASN | ROUTING | CLOUD | THREAT_INTEL | REGISTRY | ONLINE_QUERY
ProviderKind(Enum):     DOWNLOAD | ONLINE_QUERY

RateLimit:        max_calls:int, period_seconds:float, max_concurrency:int=1
ConfigValidation: ok:bool, missing:list[str], messages:list[str]
UpdateResult:     success:bool, record_count:int=0, skipped:bool=False, error:str|None=None
ProviderError:    category:str ('network'|'rate_limit'|'auth'|'parse'|'unknown'), message:str, retryable:bool
NormalizedResult: ip:str, source:str, category:str, data:dict, raw:Any=None, error:str|None=None
                  # data 的键对齐 query_ip：geoip/asn/rpki/cloud/threats/is_tor/is_vpn/...
```

> 这些是**轻量 dataclass / Enum**，零第三方依赖，可被未来代码与测试直接使用。

---

## 4. 抽象层级（`providers/base.py`）

```
Provider (ABC)  ── 定义全部字段 + 5 个方法的默认/抽象
│
├── DownloadProvider        kind=DOWNLOAD
│     • update() 抽象（子类或适配器实现）
│     • query() → 抛 ProviderNotSupported
│     特化（仅语义标注 category，便于注册与未来归一）：
│       ├── GeoIPProvider        category=GEOIP
│       ├── ASNProvider          category=ASN
│       └── ThreatIntelProvider  category=THREAT_INTEL
│
└── OnlineQueryProvider     kind=ONLINE_QUERY
      • query(ip) 抽象
      • update() → no-op（UpdateResult(skipped=True)）
      • 内置 rate_limit / timeout / error_handler 默认实现
```

**渐进性保证**：
- 旧的 17 个源 → 由 `LegacyDownloadAdapter`（DownloadProvider 子类）包装，`update()` 委托给原 `DataSourceBase.update()`，**无需实现 `query()`**。
- 未来在线源 → 继承 `OnlineQueryProvider`，**只实现 `query()` + `normalize_result()` + `validate_config()`**，无需实现 `update()`。

---

## 5. `validate_config()` 与密钥（对接 P0）

- `requires_api_key=True` 时，`validate_config()` 读取 `get_config().get_source(name)`（已解析 `${VAR}`），逐个检查 `config_keys`：
  - 缺失 / 空 / 等于占位符（`${MAXMIND_LICENSE_KEY}`、`YOUR_MAXMIND_LICENSE_KEY_HERE` 等）→ 记入 `missing`，`ok=False`。
- 真实密钥来源仍是 `.env`（gitignored）→ `sources.yaml` 占位符 → `config_loader` 解析。Provider 层**不持久化密钥**。

示例（未来）：
```yaml
abuseipdb:
  enabled: false
  requires_api_key: true
  api_key: ${ABUSEIPDB_API_KEY}     # 真实值在 .env
  rate_limit: { max_calls: 1000, period_seconds: 86400 }
  timeout: 15
```

---

## 6. 各类别建议映射（用于未来实现，不强制现在做）

| Provider | category | kind | requires_api_key | config_keys |
|---|---|---|---|---|
| ipinfo | GEOIP/ASN | ONLINE_QUERY | 视套餐 | `api_key` |
| ip2location | GEOIP | DOWNLOAD 或 ONLINE_QUERY | 是 | `api_key` |
| MaxMind（现有 geoip） | GEOIP | DOWNLOAD | 是 | `license_key` |
| AbuseIPDB | THREAT_INTEL | ONLINE_QUERY | 是 | `api_key` |
| BGPView | ASN/ROUTING | ONLINE_QUERY | 否 | — |
| ThreatFox（abuse.ch） | THREAT_INTEL | ONLINE_QUERY/DOWNLOAD | 视端点 | `api_key?` |

---

## 7. 明确的非目标（本规范不做）

- 不改 SQLite 表结构；不改 `query_ip` 读路径。
- 不把在线 provider 接入实时查询（仅定义接口，后续阶段再 wiring）。
- 不要求旧 provider 立刻实现 `query()` / `normalize_result()`。
