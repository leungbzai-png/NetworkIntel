# 开发指南（DEVELOPMENT.md）

> 面向贡献者与后续维护（含 Claude Code / Codex）。红线与交接见 [`CLAUDE_HANDOFF.md`](CLAUDE_HANDOFF.md)。

---

## 1. 开发环境

- **OS**：Windows 10/11（64 位）。项目为 Windows 原生，不依赖 Docker。
- **Python**：3.10+（已验证 `D:\Python\Python 3.11.9`）。**推荐 3.11**。
- **Shell**：PowerShell（仓库自带 `.bat` 入口）。
- 依赖：`pip install -r requirements.txt`（GUI 另见 `requirements_gui.txt`）。
- 测试无需额外依赖即可跑（`tests/run_tests.py` 内置运行器）；`pytest` 可选。

---

## 2. 项目目录说明

```
NetworkIntel/
├── python/                     程序源码
│   ├── do_update.py            CLI 全量更新（串行，单写者）
│   ├── do_update_v6.py         IPv6 数据更新（串行）
│   ├── main.py / main_gui.py   程序入口（TUI / PySide6 GUI）
│   ├── datasources/            下载型 Provider（旧体系，写库主力）
│   │   ├── base.py             DataSourceBase：download/parse/load/snapshot
│   │   ├── plugin_registry.py  PLUGIN_REGISTRY（17 源注册）
│   │   └── plugins/            各下载源实现
│   ├── providers/              统一 Provider 抽象（新体系，旁路）
│   │   ├── types.py base.py registry.py   接口与兼容适配
│   │   ├── http.py             统一 HTTP（timeout/重试/退避/统一失败对象）
│   │   ├── cache.py            在线结果缓存（独立 SQLite，不碰 intel.db）
│   │   ├── ratelimit.py        per-provider 限速 + 429 熔断
│   │   ├── online_runner.py    在线旁路执行器（validate→缓存→限速→query）
│   │   └── online/             在线 Provider（bgpview/ipinfo/ip2location/abuseipdb/threatfox）
│   ├── query/engine.py         query_ip：只读 SQLite（离线主查询）
│   ├── scheduler/scheduler.py  APScheduler 调度 + 手动触发
│   └── utils/                  config_loader / schema / logger / ip_utils
├── configs/                    sources.yaml(真实,gitignore) + sources.example.yaml(模板)
├── tests/                      76 用例，默认零网络
├── scripts/provider_smoke_test.py   Provider 手动自检
├── docs/                       架构 / 在线 Provider / 缓存限速 / SQLite 审计 / 测试
├── .env(真实,gitignore) / .env.example(模板)
└── live/ cache/ logs/ reports/ snapshots/ backups/   （均 gitignore，勿移动）
```

---

## 3. 如何运行测试

```cmd
python tests/run_tests.py            # 无需 pytest，发现 tests/test_*.py 的 test_*
python -m pytest                     # 等价（读 pytest.ini）
```
- 全部默认**零网络**：在线 Provider 的 `query()` 用 monkeypatch `providers.http.http_get_json` 注入 mock。
- 限速/熔断测试用临时 JSON + 可注入时钟，不触碰真实 `cache/online_ratelimit.json`。
- 新增功能必须配套测试；保持「默认不联网、不打印真实 key」。

---

## 4. 如何新增**在线** Provider（旁路）

1. 在 `python/providers/online/<name>.py` 继承 `OnlineApiProvider`（需 key）或 `OnlineQueryProvider`：
   - 定义 `name / category / requires_api_key / config_keys / ENV_KEY / timeout`。
   - 实现 `query(ip)`：用 `providers.http.http_get_json` 发请求，鉴权头从 `_resolve_key()` 取
     （**key 不进 URL/日志/异常/缓存**）；401/403/429/5xx/超时统一返回 `NormalizedResult(error=...)`。
   - 实现 `normalize_result(raw, ip)`：输出对齐统一字段（可处理离线 mock）。
2. 在 `python/providers/online/__init__.py` 的 `ONLINE_PROVIDERS` 注册，必要时加入 `IMPLEMENTED`。
3. 限速：在 `ratelimit.DEFAULT_PROVIDER_LIMITS` 加该源默认额度；如需 env 覆盖在 `build_default_limiter` 处理。
4. 允许列表：如需经 runner 调用，加入 `online_runner.ALLOWED_PROVIDERS`。
5. 配置模板：`.env.example` 加 `*_API_KEY` 占位；`configs/sources.example.yaml` 加 `${VAR}` 条目。
6. 测试：`tests/test_<name>_provider.py`（缺 key / 占位符 / 已配置 / normalize / query 各状态 / key 不泄露）。
7. **保持旁路**：不接入 `query_ip`（见红线）。

参考实现：`providers/online/abuseipdb.py` + `tests/test_abuseipdb_provider.py`。

---

## 5. 如何新增**下载型** Provider（落库）

1. 在 `python/datasources/plugins/<name>.py` 继承 `DataSourceBase`，实现 `download/parse/load`：
   - `download()` 用 `self._download_file(url, filename)` 落到 `cache/`。
   - `parse()` 是生成器，yield 字段对齐目标表列名。
   - `load()` 用 `self._bulk_insert(table, columns)` 批量写（通常先 `DELETE WHERE source=?`）。
2. 在 `datasources/plugin_registry.py` 注册 `"<name>": YourClass`。
3. 在 `configs/sources.yaml`（及 `*.example.yaml`）加 `enabled/schedule/snapshot_category/description`。
4. **不需要改核心文件**。新增源默认走串行 CLI 安全；并发写注意事项见 SQLite 审计。

参考：`README.md` 末尾「新增数据源插件」三步示例。

---

## 6. 如何维护配置模板

- 真实值只进 `.env` 与 `configs/sources.yaml`（均 gitignore）。
- 模板 `.env.example` / `configs/sources.example.yaml` **只放占位符**（`your_..._here` 或 `${VAR}`）。
- 改了真实配置项时，**同步**更新对应模板的占位与注释，让 `copy *.example` 即可跑通。
- `tests/test_config_loader.py` 会断言模板里 `api_key/token/license_key` 均为 `${...}`，防止误提交明文。

---

## 7. 如何避免泄露 key

- key 永远只读自 `.env` / `${VAR}`；**禁止**硬编码、禁止写入被 git 跟踪的文件。
- 发请求时 key 走**请求头或 params**，不拼进 URL；HTTP 层不记录 headers。
- 不把 key 写进日志、异常信息、缓存、返回对象。测试用 `dummy-...` 值并断言其不出现在输出中。
- 提交前 `git diff | grep -i key`（或见 `RELEASE_CHECKLIST.md`）自检。

---

## 8. 如何提交代码

- **分支**：`main` 为默认分支；功能在特性分支或当前开发分支（如 `master`）上做，避免直接污染 `main`。
- **不提交**：`.env`、`configs/sources.yaml`、`cache/`、`logs/`、`reports/`、`snapshots/`、`backups/`、
  `live/*.db`（已 gitignore，提交前再 `git status` 确认）。
- **提交信息**：祈使句、类型前缀（`feat:` / `fix:` / `docs:` / `chore:`），一句话说清 What/Why。
- **提交前**：跑 `python tests/run_tests.py`（应 126/126）；`git diff` 确认无真实 key、无大文件。

---

## 9. Claude Code / Codex 后续维护注意事项

- **先读** [`CLAUDE_HANDOFF.md`](CLAUDE_HANDOFF.md) 的红线，再动手。
- **不要**把在线 API 接进 `query_ip` 主流程；在线能力只做旁路增强。
- **不要**修改 SQLite 表结构、不要移动 `live/cache/logs/reports/snapshots/backups`。
- 改 GUI 前先审计（GUI 文件大、副作用多）。SQLite 并发只按 `docs/SQLITE_CONCURRENCY_TODO.md` 分步走，
  每步独立 commit、可回滚。
- 任何改动都应保持「离线查询主路径纯净、默认不联网测试、零真实 key 输出」三条底线。
