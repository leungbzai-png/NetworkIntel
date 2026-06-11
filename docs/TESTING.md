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
| `test_provider_cache.py` | online_cache set/get；过期不命中；purge_expired；stats；upsert（临时库+可控时钟） |
| `test_provider_ratelimit.py` | 限额生效与窗口恢复；429 冷却；Retry-After；stats（临时 JSON+可控时钟） |
| `test_online_runner.py` | 缓存命中不回源；force_refresh 绕过；use_cache=False；缺 key 优雅；不允许的 provider |

## 3. 网络策略

- **自动测试默认零网络**：BGPView 的 `query()` 通过 monkeypatch `providers.http.http_get_json` 注入模拟响应；模板 `query()` 是骨架（直接返回 `not_implemented`）。
- **真实网络查询**走手动脚本：`python scripts/provider_smoke_test.py`（仅 BGPView 无需 key）。

## 4. 密钥安全

- 测试只读 `configs/sources.example.yaml`（占位符），断言无真实长 token；不读真实 `.env`。
- 需要 key 的用例用 `os.environ` 注入 `dummy` 值并在 `finally` 还原，绝不写入文件、不打印真实值。

## 5. 当前结果

```
44/44 passed, 0 failed
```
