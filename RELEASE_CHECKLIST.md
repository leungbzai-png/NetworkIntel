# 发布前检查清单（RELEASE_CHECKLIST.md）

> 每次发布/打 tag 前逐项确认。任一项不通过则**不发布**。

## A. 密钥与隐私
- [ ] **无真实 key/token**：`git diff` 与 `git ls-files` 中不含真实密钥
      （`git grep -iE "api_key|token|license_key"` 命中的均为 `${VAR}` 或 `your_..._here` 占位符）。
- [ ] `.env`、`configs/sources.yaml` **未被跟踪**（`git ls-files | findstr ".env sources.yaml"` 仅返回 `*.example.*`）。
- [ ] `.env.example` 与 `configs/sources.example.yaml` **完整**：所有需要的变量都有占位符与注释，`copy *.example` 后可跑通。

## B. 数据与大文件
- [ ] **无大数据库误提交**：`live/*.db`、`cache/`、`snapshots/`、`backups/`、`reports/`、`logs/` 均未被跟踪
      （`git ls-files` 不含这些路径；`git status` 干净）。
- [ ] 仓库体积合理（无意外的二进制/数据大文件混入）。

## C. 测试
- [ ] `python tests/run_tests.py` → **76/76 passed, 0 failed**（或随版本递增后的全绿）。
- [ ] 测试默认**零网络**、输出**无真实 key**。

## D. 入口可运行
- [ ] `update.bat` import 测试通过：`cd python && python -c "import do_update"` 无报错（离线 CLI 入口完好）。
- [ ] `start.bat` 能启动界面（或 `python python/main.py` / `python python/main_gui.py` 可运行）。
- [ ] `python scripts/provider_smoke_test.py` 默认模式正常（仅列表，不联网）。

## E. 文档
- [ ] `README.md` / `DEVELOPMENT.md` / `ROADMAP.md` / `PROJECT_STATUS.md` 与本次变更一致。
- [ ] `CHANGELOG.md` 记录了本次发布内容。
- [ ] `docs/*` 中受影响的文档（在线 Provider / 缓存限速 / SQLite 审计 / 测试）已更新。

## F. Git 卫生
- [ ] `git status` **干净**（无未跟踪的敏感文件、无遗留改动）。
- [ ] 提交信息规范（类型前缀 + 一句话 What/Why）。
- [ ] 在正确分支上（功能不直接堆在 `main` 上，除非有意发布）。

## G. 已知风险确认
- [ ] 若本次涉及更高并发/正式发布：确认 **v0.2.0 SQLite 写入串行化** 是否需先落地
      （见 `docs/SQLITE_CONCURRENCY_AUDIT.md`）。否则在发布说明中标注「GUI 全部更新存在并发写风险，建议改用 `update.bat`」。

---

### 快速自检命令
```cmd
python tests/run_tests.py
cd python && python -c "import do_update; print('import OK')" && cd ..
python scripts/provider_smoke_test.py
git status
git ls-files | findstr /R "\.env$ sources.yaml$ \.db$"
git diff | findstr /I "api_key token license_key"
```
