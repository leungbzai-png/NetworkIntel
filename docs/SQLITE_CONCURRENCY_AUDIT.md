# SQLite 并发写入审计（SQLITE_CONCURRENCY_AUDIT.md）

> **状态更新（v0.3.0）**：本审计所列 R1~R5 风险已全部修复。修复方式见
> `docs/RELEASE_NOTES_v0.3.0.md` 与 `docs/SQLITE_CONCURRENCY_TODO.md` 的「v0.3.0 落地对照」。
> 采用**统一更新协调器（单 worker 写入队列）** 作为根治手段（比原 §5 的「全局写锁 / trigger_all 串行化」
> 更彻底：单写者队列同时覆盖 GUI 手动/全部更新、调度器、CLI、首次初始化五个入口）。
> 以下原文保留作为背景与设计依据。
>
> **本文档（原始版本）仅审计、仅出方案，不修改任何源码。** 审计对象为主库 `live/intel.db` 的写入链路。
> 审计日期：2026-06-11 · 审计范围：`do_update.py` / `do_update_v6.py` / `scheduler/scheduler.py` /
> `datasources/{base,plugin_registry}.py` / `datasources/plugins/*` / `utils/schema.py` / `query/engine.py`。

---

## 1. 当前写入链路图

所有主库写入最终都经过 `utils/schema.py::get_connection(db_path)` 拿连接。写入发生在三处：

```
DataSourceBase.update()                       # datasources/base.py
  ├─ download()                               # 仅写 cache/ 文件，不写库
  ├─ parse()                                  # 纯生成器，不写库
  ├─ load(records)                            # ★ 写库
  │     ├─ get_connection() → DELETE FROM <表> WHERE source=? → commit → close   （独立短连接）
  │     └─ _bulk_insert(table, cols):                                            （另一独立连接）
  │            executemany(INSERT OR REPLACE ...)  每 5000 行 commit 一次
  │            收尾 commit → close
  ├─ snapshot()                               # 仅复制文件到 snapshots/ 与 gdrive_sync/，不写库
  └─ _update_meta(status,count,err)           # ★ 写库：INSERT ... ON CONFLICT(source) UPDATE source_meta（独立连接）
```

读取路径（对照）：
```
query/engine.py::query_ip()                   # 只读 SELECT（WAL 下不被写阻塞）
  └─ 末尾写一次 query_history（INSERT），失败被静默吞掉（见 §6）
```

### 触发写入的三个入口及其并发模型

| 入口 | 文件/位置 | 并发模型 | 写库并发度 |
|---|---|---|---|
| CLI 全量更新 | `do_update.py::main()` | `for name, plugin in plugins.items(): plugin.update()` —— **串行** | **1（安全）** |
| CLI IPv6 更新 | `do_update_v6.py::main()` | 同样 `for ... : plugin.update()` —— **串行** | **1（安全）** |
| GUI/TUI「全部更新」、调度器手动/定时触发 | `scheduler/scheduler.py` | 每个源开**独立 daemon 线程** | **最多 ~17（风险）** |

---

## 2. 风险点

### R1（高）`trigger_all()` 一次性拉起约 17 个并发写线程
`scheduler.py::trigger_all()` 遍历所有启用源，对每个调用 `trigger_now()`；
`trigger_now()` 为每个源 `threading.Thread(target=_run_source_update, daemon=True).start()`。
→ 17 个线程几乎同时进入各自的 `plugin.update()` → `load()`，**并发写同一个 `intel.db`**。
`main.py` 的「全部更新」按钮（`get_scheduler().trigger_all()`）正是走这条路径。

### R2（中）APScheduler 定时任务可同时触发多个源
- `BackgroundScheduler` 默认使用 `ThreadPoolExecutor(10)` 执行 job。
- `job_defaults={"coalesce": True, "max_instances": 1}` **只防止同一个 job 自身重叠**，**不**阻止不同 job 并行。
- `configs/sources.example.yaml` 中 6 个云源（`cloud_aws/azure/gcp/cloudflare/hetzner/vultr`）共用同一 cron `0 4 1 * *` → 每月 1 日 04:00 **同时**起跑，最多 ~6 个并发写线程。其它源若 cron 撞点同理。

### R3（高）`get_connection()` 未设置 `busy_timeout`
`utils/schema.py::get_connection()` 设了 `journal_mode=WAL` / `synchronous=NORMAL` / `cache_size` /
`temp_store`，但**没有 `PRAGMA busy_timeout`**（`init_db` 与 `SCHEMA_SQL` 中也都没有）。
SQLite 默认 busy timeout 为 0 → 一旦写锁被别的写者占用，**立即**抛
`sqlite3.OperationalError: database is locked`，不等待、不重试。

### R4（中）`load()` 的 DELETE 与 INSERT 不在同一事务
`load()` 先用一个连接 `DELETE ... WHERE source=?` 并 `commit()`、`close()`，再用
`_bulk_insert` 的**另一个连接**分批 INSERT。两步之间若崩溃/被 kill/抛锁异常，
该源的表会处于「已删旧数据、未写新数据」的空窗状态（非原子）。

### R5（低）每次操作新建连接
`load()` 内有 2~3 个独立连接（DELETE 一个、bulk_insert 一个、`_update_meta` 一个）。
功能正确，但放大了「获取写锁 → 释放」的次数，在并发场景下增加碰撞窗口。

### 非风险（已正确）
- **WAL 已开启**：读写分离，`query_ip` 的只读 SELECT **不会**被写入阻塞，离线查询体验不受影响。
- **CLI 路径串行**：`update.bat`（`do_update.py`）与 `do_update_v6.py` 都是串行，单写者，天然安全。
- **写失败不致崩溃**：`update()` 用 `try/except` 包裹，捕获后 `logger.error(..., exc_info=True)` 并写
  `source_meta.status='error'`，不会让进程崩溃。

---

## 3. 可能触发 `database is locked` 的场景

1. **用户在 GUI/TUI 点「全部更新」** → R1 的 17 线程并发写 → 因 R3 无 busy_timeout，
   抢不到写锁的线程**立即**抛 `database is locked`。
2. **每月 1 日 04:00 六个云源定时撞点**（R2）→ 同样并发写 → 部分线程报锁。
3. **定时任务正在跑时用户又手动「全部更新」**（R1 × R2 叠加）→ 碰撞窗口最大。
4. 大表源（如 `geoip` 数百万行）的 `DELETE` + 多批 `executemany` 持锁时间长，
   会拉长其它写者的等待/失败窗口。

> **可观测症状（给未来维护者）**：不是崩溃、也不是 traceback 弹窗，而是
> **「全部更新」后，随机若干数据源在数据源页显示 `status=error`，`logs/networkintel.log`
> 里对应行写着 `database is locked`**。因为锁冲突被 `update()` 的 `except` 吸收进了
> 普通错误路径（记录到 `source_meta` + 日志），表象与「网络失败」等其它错误混在一起。
> 重跑常常「碰巧」成功（线程调度不同），这种**间歇性、可复现性差**正是锁竞争的典型特征。

---

## 4. 短期低风险修复建议（推荐优先）

> 以下均为**建议**，本阶段不落地（受「SQLite 部分只审计」约束）。按风险从低到高排序。

### S1 ⭐ 给 `get_connection()` 增加 `busy_timeout`（最低风险、最高性价比）
在 `get_connection()` 增加一行 `conn.execute("PRAGMA busy_timeout=30000")`（30s，可配置）。
- 效果：写者遇到锁时**等待并自动重试**到超时，而非立即失败；配合既有 WAL，把「并发写」退化为
  「排队写」，绝大多数 `database is locked` 消失。
- 风险：极低（单行 PRAGMA，不改表结构、不改业务逻辑、CLI 串行路径无感知）。
- **局限（不可过度宣传）**：busy_timeout 是**必要但不充分**。在 17 线程风暴下，大表的长事务
  仍可能拖垮几秒级超时；它降低概率，不根治。真正的根治是 §5 的写入串行化。

### S2 让 `trigger_all()` 串行化（不改并发下载，仅串行写）
把 `trigger_all()` 从「每源一线程」改为「单后台线程顺序执行各源 `update()`」，
或投递到一个单 worker 队列。GUI 仍异步、不卡界面，但写库恢复单写者。风险低、改动集中在 `scheduler.py`。

---

## 5. 中期改造方案

### 推荐方案（择一或组合）
- **下载并发可保留**：`download()` 是纯网络 IO、只写 `cache/` 文件，并行无害，应保留以缩短总耗时。
- **仅对 SQLite 写入串行化**，三种等价实现，按改动面从小到大：
  1. **全局写锁**：模块级 `threading.Lock()`，在 `load()` + `_update_meta()` 的写区间 `with lock:`。
     最小改动即可保证任一时刻只有一个写者。
  2. **单独 DB writer 队列**：所有写操作（delete/insert/meta）封装成任务投递到一个**单 worker**
     的队列线程，由它顺序落库。彻底单写者，且天然给「写」与「下载/解析」解耦。
  3. **WAL + busy_timeout + retry 包装**：保留多线程，但所有写经过统一的「带指数退避重试」包装，
     遇 `database is locked` 自动重试 N 次。实现简单，但本质是「碰运气排队」，不如 1/2 干净。
- **事务原子化（对应 R4）**：把每个源的 `DELETE old + INSERT new` 包进**同一个事务/同一连接**，
  失败整体回滚，避免空窗。属于 plugin/base 改动，归入中期。

### 推荐组合
> **S1（busy_timeout）作为即时止血** → **方案 5.1 全局写锁或 5.2 writer 队列作为根治** →
> **R4 事务原子化作为数据一致性加固**。下载并发不动。

---

## 6. 异常吞咽审计（与锁相关）

| 位置 | 代码 | 是否写库 | 评估 |
|---|---|---|---|
| `datasources/base.py::update()` | `except Exception: logger.error(exc_info=True); _update_meta(status='error')` | 是（间接） | ✅ 不静默：锁冲突会被记录为 error，但**与其它错误混在一起**，建议未来单独识别 `database is locked` |
| `query/engine.py:381` | `except Exception: pass # 历史记录写失败不影响主流程` | 是（`query_history` INSERT） | ⚠ 写历史失败被静默吞掉；并发更新时该 INSERT 可能撞锁而**悄悄丢历史行**（不影响查询结果） |
| `scheduler.py:35` | `_notify_callbacks` `except Exception: pass` | 否（UI 回调） | ✅ 可接受（UI 通知失败不应影响更新） |
| `scheduler.py:148` | `update_schedule` 的 `remove_job` `except Exception: pass` | 否（调度管理） | ✅ 可接受 |
| `datasources/plugins/cloud_aws.py:204` | `parse()` JSON→文本回退 `except Exception: pass` | 否（解析回退） | ✅ 可接受（解析降级，非写库） |
| `gui_extensions.py:215/224/461` | `except sqlite3.OperationalError: pass` | 否（GUI 只读） | ⚠ GUI 侧把锁错误静默吞掉；属 GUI，本阶段不动，仅记录 |

> 核心结论：**写库主路径没有「裸 except: pass 吞掉锁异常」**，但 `query_history` 写入与 GUI 只读侧
> 存在对 `OperationalError` 的静默吞咽，未来完善错误日志时一并处理（见 TODO P3）。

---

## 7. 不推荐方案

| 方案 | 为什么不推荐 |
|---|---|
| **继续让 17 线程同时写** | 现状即此，正是 `database is locked` 间歇失败的根因；不可作为「正常」保留 |
| **大改数据库表结构** | 违背「不改表结构」约束；并发问题是**访问模式**问题，不是 schema 问题，改表无收益 |
| **直接换 PostgreSQL** | 本项目定位是**单用户、本地、离线、零外部依赖、Windows 原生**；引入 PG 服务进程会摧毁「双击即用」的部署模型，是杀鸡用牛刀 |

---

## 8. 未来实施步骤（落地时）

1. **基线压测**：写一个脚本并发触发 `trigger_all()`，统计 `source_meta.status=error` 且日志含
   `database is locked` 的源数量，作为「修复前」基线。
2. **S1 busy_timeout**：`get_connection()` 加 `PRAGMA busy_timeout`；重跑压测，对比锁错误数。
3. **写串行化**：实现全局写锁或 writer 队列（方案 5.1/5.2）；重跑压测，目标锁错误数 = 0。
4. **事务原子化**：把各源 `DELETE+INSERT` 收进单事务；用「中途模拟异常」验证表不出现空窗。
5. **错误识别**：在 `update()` 中区分 `OperationalError: database is locked` 与其它错误，日志/状态分类。
6. **回归**：跑 `tests/run_tests.py`（76 用例）+ `update.bat` 串行路径 + GUI「全部更新」人工验证。

---

## 9. 回滚方案

- 所有建议改动都**集中且可独立回滚**：
  - S1：删掉 `get_connection()` 里那一行 `PRAGMA busy_timeout` 即恢复。
  - 写锁/队列：改动集中在 `scheduler.py`（或新增一个 `db_writer.py`），`git revert` 单个 commit 即可。
  - 事务原子化：集中在 `datasources/base.py`，同样单 commit 可回滚。
- **不涉及表结构变更**，故无数据迁移、无不可逆操作；回滚后行为与今日完全一致。

---

## 10. 测试建议

- **并发压测**：N 个线程同时 `trigger_all()`，断言所有源最终 `status=ok`、无 `database is locked`。
- **锁等待验证**：人为持有写事务，另一线程在 busy_timeout 内应等待成功而非立即报错。
- **原子性验证**：在 `load()` 的 DELETE 与 INSERT 之间注入异常，断言表数据要么是旧的、要么是新的，不为空。
- **回归**：`python tests/run_tests.py` 应保持全绿（当前 126/126）；`do_update.py` 串行路径行为不变。
- **离线读不受影响**：写入进行时并发执行 `query_ip`，断言读取始终成功（验证 WAL 读写分离）。

---

> 配套优先级清单见 **`docs/SQLITE_CONCURRENCY_TODO.md`**。
