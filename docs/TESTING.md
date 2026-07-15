# 测试说明（TESTING.md）

> 本项目此前无测试体系。本阶段新增 `tests/`，覆盖配置加载、Provider 注册表、BGPView 与在线模板。

---

## 1. 运行方式

### 方式 A：pytest（推荐，若已安装）
```
D:\Python\python.exe -m pip install pytest
D:\Python\python.exe -m pytest          # 读取 pytest.ini，发现 tests/
```

### 方式 B：内置最小运行器（无需 pytest）
```
D:\Python\python.exe tests/run_tests.py
```
两者等价：都把 `python/` 加入 `sys.path`（见 `tests/conftest.py` 与 `tests/_bootstrap.py`），
所有测试函数均为无参 `test_*`，不依赖 pytest fixture。

## 2. 测试清单

| 文件 | 覆盖 |
|---|---|
| `test_config_loader.py` | 示例配置不含真实 key；`${VAR}` 解析；`.env` 不覆盖已有环境变量；占位符识别 |
| `test_provider_registry.py` | 导入惰性（不构建/不实例化）；17 个源；元数据；适配器持类非实例 |
| `test_bgpview_provider.py` | 导入不联网；`validate_config`；`normalize_result`（mock）；`query`（monkeypatch http，成功+失败） |
| `test_online_provider_templates.py` | `requires_api_key`/`config_keys`/`ENV_KEY`；缺 key 优雅校验；`query` 骨架不联网；`normalize_result` mock |
| `test_ipinfo_provider.py` | ipinfo 缺 key/占位符/已配置；normalize；query 成功/401/429/超时（mock）；token 不泄露 |
| `test_ip2location_provider.py` | ip2location 缺 key/占位符/已配置；normalize；query 成功/401/429/超时；经 runner 的缓存命中 + force_refresh；key 不泄露 |
| `test_abuseipdb_provider.py` | abuseipdb 缺 key/占位符/dummy 已配置；severity 分级；normalize 完整字段集 + clean 无 threats；query 成功/401/403/429/5xx/超时；429→rate_limited；key 不泄露 |
| `test_provider_cache.py` | online_cache set/get；过期不命中；purge_expired；stats；upsert（临时库+可控时钟） |
| `test_provider_ratelimit.py` | 限额生效与窗口恢复；per_day 边界；provider 额度独立；429 冷却/Retry-After；**连续 429 熔断**；record_success 清零 consecutive_429；record_failure 不熔断；reset；`build_default_limiter` abuseipdb per_day=900（临时 JSON+可控时钟） |
| `test_online_runner.py` | 缓存命中不回源/不消耗额度；force_refresh 绕过缓存但仍受限速；use_cache=False；缺 key 优雅；不允许的 provider；限速/熔断时不调用 query 并返回统一失败；abuseipdb 在默认允许列表 |
| `test_sqlite_connection_policy.py` | **（v0.3.0）** `busy_timeout` 生效（读/写连接、env 覆盖动态生效）；`foreign_keys=ON`；WAL 或优雅回退；写连接 `isolation_level=None` 可显式 `BEGIN IMMEDIATE`；`is_locked_error` 分类；每线程独立连接并发只读无错 |
| `test_update_coordinator.py` | **（v0.3.0）** 状态时序 queued→running→success；失败/执行器异常→failed + error_type；同源活动中重复入队→skipped(duplicate)；完成后可再次入队；`is_busy`/`queue_size`；`get_source_state`；`shutdown` 不挂死且拒绝新任务；`wait_for_job` 超时；错误消息脱敏 + `redact_secrets` 单元 |
| `test_update_queue_concurrency.py` | **（v0.3.0）** 多线程同时入队时最大并行执行数恒为 1（峰值计数器）；两次「全部更新」不并行（同源去重）；单源失败后续源继续 |
| `test_update_transactions.py` | **（v0.3.0）** 成功 commit 持久化；中途异常 rollback 保留旧数据；`replace_source` 原子替换；busy_timeout 等待后成功；锁重试有限耗尽抛 locked（不死锁）；完整 `update()` 分类 `db_locked` 且旧数据不损 |
| `test_scheduler_update_coordination.py` | **（v0.3.0）** 手动与调度器同源去重；手动+调度器混合触发写库串行（峰值 1）；调度器任务失败不断队；`get_job_status` 状态映射旧词表；`_scheduler_enqueue` 吞异常不杀调度线程 |

## 3. 网络策略

- **自动测试默认零网络**：bgpview/ipinfo/ip2location/abuseipdb 的 `query()` 通过 monkeypatch `providers.http.http_get_json` 注入模拟响应；剩余模板 `query()` 是骨架（直接返回 `not_implemented`）。限速/熔断测试用临时 JSON + 可注入时钟，不触碰真实 `cache/online_ratelimit.json`。
- **真实网络查询**走手动脚本：`python scripts/provider_smoke_test.py --provider <name> --query <ip>`（仅 BGPView 无需 key；需 key 者缺 key 时优雅提示）。
- **限速维护/模拟均不联网**：`--rate-limit-status` / `--simulate-429 <provider>` / `--reset-rate-limit <provider>` 只读写本地限速 JSON。

## 4. 密钥安全

- 测试只读 `configs/sources.example.yaml`（占位符），断言无真实长 token；不读真实 `.env`。
- 需要 key 的用例用 `os.environ` 注入 `dummy` 值并在 `finally` 还原，绝不写入文件、不打印真实值。

## 5. 当前结果

```
165/165 passed, 0 failed   （v0.3.0；run_tests.py 与 pytest 等价）
```

> 并发相关测试全部**确定性**：用事件 / Barrier（仅入队侧）/ 峰值计数器 / 临时 SQLite 文件与竞争写锁，
> 不依赖随机 sleep 制造偶现结果。所有测试零网络、零真实 key、临时目录与临时数据库，绝不触碰正式 `live/intel.db`。
