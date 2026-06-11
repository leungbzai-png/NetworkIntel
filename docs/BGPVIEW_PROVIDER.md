# BGPView Provider（BGPVIEW_PROVIDER.md）

> 在线 ASN/BGP 查询 provider。**无需 API key**。旁路能力，未接入离线主查询。

---

## 1. 概览

| 项 | 值 |
|---|---|
| name | `bgpview` |
| 类别 | `asn`（ASN/BGP） |
| kind | `online_query` |
| requires_api_key | `false` |
| 端点 | `GET https://api.bgpview.io/ip/{ip}` |
| timeout | 15s（429/5xx 自动重试，见 `providers/http.py`） |
| 代码 | `python/providers/online/bgpview.py` |

## 2. 统一输出字段（`normalize_result`）

`NormalizedResult.data` 含：

| 字段 | 含义 |
|---|---|
| `ip` | 查询 IP |
| `asn` | 自治系统号（int） |
| `asn_name` | AS 名称 / 机构 |
| `prefix` | 命中的 BGP 前缀 |
| `country_code` | 国家码 |
| `rir` | 分配该地址的 RIR |
| `source` | `bgpview` |
| `fetched_at` | UTC ISO 时间戳 |
| `raw` | 原始响应（便于调试/未来字段） |

失败时返回 `NormalizedResult(error=...)`，`data={}`，**不抛异常**。

## 3. 手动测试

```
python scripts/provider_smoke_test.py --query 8.8.8.8
```
或直接：
```python
from providers.online.bgpview import BGPViewProvider
r = BGPViewProvider().query("8.8.8.8")
print(r.data if not r.error else r.error)
```

## 4. 输出示例（基于离线单测的模拟响应）

> 实测需联网；下例来自 `tests/test_bgpview_provider.py` 的 mock，与真实结构一致：

```
IP        : 8.8.8.8
ASN       : AS15169  GOOGLE
Prefix    : 8.8.8.0/24
Country   : US
RIR       : ARIN
fetched_at: 2026-06-11T...Z
```

## 5. 错误处理

- DNS/连接/超时 → `http.py` 重试（最多 3 次，指数退避）后返回 `ok=False`；`query()` 包装为 `NormalizedResult(error=...)`。
- BGPView 业务失败（`status != "ok"`）→ 返回带 `error` 的结果。
- 解析异常 → `normalize_result` 捕获并降级，字段为 `None`。

## 6. 边界

- 不写 SQLite、不接 `query_ip`、不被 scheduler/do_update 调用。
- 仅作为在线 provider 的参考实现与旁路验证。
