# 在线 Provider 缓存与限速设计（ONLINE_PROVIDER_CACHE_AND_RATE_LIMIT.md）

> 设计文档 + **基础设施已落地**（旁路，未接入 `query_ip`）。

## 0. 实现状态（基础设施已落地，仍为旁路）

| 模块 | 文件 | 说明 |
|---|---|---|
| 缓存 | `python/providers/cache.py` | 独立 SQLite（`cache/online_cache.sqlite`），表 `online_cache`，不碰 `intel.db` |
| 限速 | `python/providers/ratelimit.py` | 按 provider 维度（per_minute/hour/day）+ 429 冷却 + **连续 429 熔断**；JSON 持久化（`cache/online_ratelimit.json`） |
| 执行器 | `python/providers/online_runner.py` | 旁路编排：允许列表→validate→**缓存→限速/熔断**→query→写缓存 |
| 测试 | `tests/test_provider_cache.py` / `test_provider_ratelimit.py` / `test_online_runner.py` | 默认零网络 |

> 仍**未**接入 `query_ip` / GUI / scheduler；只能经 `online_runner.run_provider()` 或 smoke 脚本显式调用。

### online_cache 表结构
```sql
CREATE TABLE IF NOT EXISTS online_cache (
    provider        TEXT NOT NULL,
    query_type      TEXT NOT NULL,   -- 目前固定 'ip'
    query_value     TEXT NOT NULL,
    normalized_json TEXT,            -- NormalizedResult.data（无 token）
    raw_json        TEXT,            -- API 原始响应（无 token）
    fetched_at      TEXT NOT NULL,   -- ISO8601
    expires_at      REAL,            -- epoch 秒；NULL=永不过期
    status          TEXT,            -- ok / error
    error           TEXT,
    PRIMARY KEY (provider, query_type, query_value)
);
```

### 如何清理缓存
```
python scripts/provider_smoke_test.py --purge-cache    # 删除过期条目
python scripts/provider_smoke_test.py --cache-stats    # 查看统计
# 或直接删除文件： cache/online_cache.sqlite（下次自动重建）
```

### 如何手动测试
```
python scripts/provider_smoke_test.py                                   # 仅列表，不联网
python scripts/provider_smoke_test.py --provider bgpview --query 8.8.8.8 # 经缓存+限速回源
python scripts/provider_smoke_test.py --provider bgpview --query 8.8.8.8 --force-refresh
python scripts/provider_smoke_test.py --rate-limit-status               # 查看各 provider 限速/熔断
python scripts/provider_smoke_test.py --simulate-429 abuseipdb          # 本地模拟连续 429 → 熔断（不联网）
python scripts/provider_smoke_test.py --reset-rate-limit abuseipdb      # 重置某 provider 限速状态
```

---

## 0.1 per-provider 限速护栏（已落地）

`ratelimit.RateLimiter` 纯配置驱动；`build_default_limiter()`（runner/smoke 共用）注入以下默认额度
（保守，保护免费额度；可经 `.env` 覆盖 abuseipdb 三项 + 全局熔断）。

| provider | per_minute | per_hour | per_day | 说明 |
|---|---|---|---|---|
| bgpview | 30 | 1000 | — | 无需 key |
| ipinfo | 30 | 500 | — | 免费月额度大，按分/时护栏 |
| ip2location | 30 | 500 | — | 同上 |
| **abuseipdb** | **10** | **100** | **900** | 免费约 1000/天，**留 ~10% 余量** |
| threatfox | 30 | 500 | — | abuse.ch Auth-Key |

> 各 provider 额度**互相独立**：一个 provider 触顶不影响其他。

### 429 连续熔断（circuit breaker）
- `record_429(provider)` 累加 `consecutive_429`，并按 `cooldown_seconds`（或 `Retry-After`）设单次冷却。
- 当 `consecutive_429 >= max_consecutive_429`（默认 `ONLINE_MAX_CONSECUTIVE_429=3`）→ 进入**熔断**：
  - 熔断期 `circuit_breaker_seconds`（默认 `ONLINE_CIRCUIT_BREAKER_SECONDS=3600`）内 `can_call()` 恒为 `False`；
  - `next_available_at()` 返回**所有当前约束中最晚的恢复时刻**（熔断 > 冷却时取熔断）；
  - runner 在熔断期返回 `circuit_open=True` 的统一失败对象，**绝不调用** `provider.query()`。
- `record_success(provider)` 把 `consecutive_429` **清零**（额度/冷却到期自然恢复）。
- `record_failure(provider)` 仅记录一次普通失败（占额度），**不**像 429 那样累计熔断。
- 单次 429 不熔断（`consecutive_429=1 < 阈值`），仅短冷却，避免偶发限流误伤。

### 缓存命中为什么不消耗额度
- runner 调用顺序为 **validate → 缓存 → 限速/熔断 → query**：缓存命中**先于**限速检查直接返回，
  既不调用 `record_*`、也不被限速/熔断拦截 → **缓存命中零额度消耗**，且限速/熔断期间缓存仍可服务。
- 只有真正**回源**（缓存未命中或 `force_refresh`）才检查 `can_call()` 并在成功/失败/429 后 `record_*`。

### force_refresh 为什么仍受限速保护
- `force_refresh=True` 只**跳过缓存读取**，不跳过限速 —— 它必然走到「回源」分支，因此仍经过
  `can_call()` 与熔断检查；超额/熔断时同样返回 `rate_limited`/`circuit_open`，**不**强制打 API。
- 这样既能手动强制刷新单个 IP，又不会绕开额度护栏耗尽免费额度。

---

> 以下为原始设计说明，指导后续把在线 provider 安全地合并进查询能力。

---

## 1. 为什么在线 Provider 不能直接接入离线主查询

NetworkIntel 的核心定位是**离线、可预测、零外部依赖**的 IP 情报查询（`query_ip` 直读 SQLite）。直接在 `query_ip` 里调用在线 API 会带来：

- **网络依赖**：离线/弱网环境下主查询会变慢或失败，违背产品定位。
- **延迟抖动**：每次查询叠加外部 RTT（数百 ms ～ 秒级），批量查询尤甚。
- **额度风险**：免费 API 有日/分钟额度（如 AbuseIPDB 约 1000/天、ipinfo 免费档有月限），主路径直连极易触限。
- **结果不稳定**：同一 IP 多次查询结果可能不同，影响风险判定一致性。
- **密钥暴露面**：主路径频繁用 key，出错处理不当易泄露。

因此在线能力先作**旁路**；接入主查询前必须先有缓存 + 限速 + 离线降级。

---

## 2. 在线结果如何缓存

**原则**：在线结果应落地为可复用、可过期的缓存，主查询优先读缓存，未命中再（受限地）回源。

两种可选载体：
1. **SQLite 缓存表（推荐）**：新增**独立**表（不改现有表结构），如 `online_cache`，与现有只读查询表解耦。
   - 字段建议：`provider, query_key, ip, payload_json, fetched_at, expires_at, status`。
   - 优点：与现有 `whois_cache` 模式一致、可持久、可被 `query_ip` 只读消费。
2. **内存 LRU（轻量）**：进程内 dict + TTL，适合 GUI 单次会话；重启失效。

> 注：本阶段两者都不实现；仅记录方向。落地时新增表属于「新增」，不修改既有表。

### 2.1 缓存 key 设计
```
cache_key = f"{provider}:{normalized_ip}:{schema_version}"
```
- `provider`：如 `ipinfo` / `abuseipdb`，避免跨源串味。
- `normalized_ip`：归一化后的 IP（IPv6 压缩、去端口）。
- `schema_version`：normalize_result 输出结构版本号，升级 normalize 时整体失效旧缓存。
- 命中判断：`now < expires_at` 且 `status == ok`。

---

## 3. TTL 建议（按类别）

| 类别 | 示例 provider | 建议 TTL | 理由 |
|---|---|---|---|
| BGP/ASN | bgpview | 7–30 天 | BGP 归属变化缓慢 |
| GeoIP | ipinfo, ip2location | 7–30 天 | 地理归属相对稳定 |
| ThreatIntel | abuseipdb, threatfox | 1–24 小时 | 威胁状态时效性强，需较快刷新 |

- 失败结果也应短 TTL 负缓存（如 5–15 分钟），避免错误风暴重复打 API。
- TTL 应可在 `sources.yaml` 的 provider 配置项覆盖（如 `cache_ttl_seconds`）。

---

## 4. 免费 API 如何限速

- 在 provider 元数据声明 `rate_limit`（已在 `providers/types.py::RateLimit` 定义：`max_calls / period_seconds / max_concurrency`）。AbuseIPDB 已声明 1000/天。
- 执行层（未来）：进程内**令牌桶 / 滑动窗口**计数器，按 `provider` 维度限流；超额时不发请求，直接返回 `rate_limited` 失败对象（由缓存兜底）。
- 并发：`max_concurrency=1` 起步，避免突发并发触发风控。
- 与缓存协同：命中缓存不计入额度；只有回源才消耗令牌。

---

## 5. 429 后如何退避

- HTTP 层 `providers/http.py` 已支持：`429` 与 `5xx` 重试，优先遵循 `Retry-After`，否则指数退避（`backoff * 2^(n-1)`）。
- Provider 层补充策略（未来）：
  - 连续 429 时**熔断**该 provider 一段时间（如 60–300s），期间直接走缓存/降级。
  - 把熔断状态记入内存，避免在额度耗尽时继续打 API。

---

## 6. 离线模式如何降级

优先级链（未来合并进查询时）：
```
1) 本地 SQLite 离线数据（geoip/asn/...）        ← 始终可用，最高优先
2) online_cache 未过期结果                      ← 有则补充
3) 受限回源（额度+熔断允许时）→ 写回缓存         ← 可选增强
4) 都不可用 → 标记 online 字段为 unavailable     ← 不阻断主结果
```
- **关键**：在线数据只做**增强**，永不成为主查询的必要条件；离线结果必须独立成立。
- 提供全局开关 `ONLINE_PROVIDERS_ENABLED`（已在 `.env.example`），默认 `false`。

---

## 7. 将来如何合并进 query_ip（不在本阶段做）

建议的最小侵入式接入（待评审）：
1. 新增**独立**模块（如 `providers/enrich.py`），提供 `enrich(result: dict) -> dict`，只读缓存 + 受限回源，**不修改** `query_ip` 内部。
2. 由调用方（GUI/CLI）在拿到 `query_ip` 离线结果后**可选**调用 `enrich()`，把在线字段并入返回 dict 的独立命名空间（如 `result["online"]["ipinfo"]`）。
3. normalize_result 的输出结构对齐既有键，便于展示层复用。
4. 全程受 `ONLINE_PROVIDERS_ENABLED` + 缓存 + 限速 + 熔断保护。

> 这样 `query_ip` 主路径保持纯离线；在线增强是上层、可关闭的旁挂。

---

## 8. 为什么 AbuseIPDB 必须在缓存和限速落地后再实现

- AbuseIPDB 免费额度约 **1000 次/天**，且为**威胁类**（TTL 短、刷新频繁），没有缓存与限速时极易在批量查询中**当天耗尽额度**甚至触发封禁。
- 威胁结果直接影响风险评级，错误的速率失败可能误导判定。
- 因此顺序应为：**先落地 `online_cache` + 令牌桶限速 + 429 熔断**，再实现 AbuseIPDB 的真实 `query()`。
- 相较之下，ipinfo（GeoIP，TTL 长、容忍度高）适合作为**首个**带 key 在线实现来验证 token 链路 —— 即本阶段所做。
