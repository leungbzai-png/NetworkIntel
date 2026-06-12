# 贡献指南（CONTRIBUTING.md）

感谢参与 NetworkIntel。完整开发说明见 [`DEVELOPMENT.md`](DEVELOPMENT.md)，
接手红线见 [`CLAUDE_HANDOFF.md`](CLAUDE_HANDOFF.md)。

## 开发

- 平台：Windows 10/11，Python **3.11**（3.10+ 可）。
- 安装：`pip install -r requirements.txt`（GUI 另见 `requirements_gui.txt`）。
- 目录与架构说明见 `DEVELOPMENT.md` 第 2 节。

## 测试

```cmd
python tests/run_tests.py     # 内置运行器，无需 pytest
python -m pytest              # 等价
```

- 所有测试**默认零网络**（HTTP 层用 monkeypatch 注入 mock）。
- 新增功能必须配套测试；保持「默认不联网、不打印真实 key」。
- 提交前确保全绿（当前 116/116）。

## 提交规范

- 提交信息用祈使句 + 类型前缀：`feat:` / `fix:` / `docs:` / `chore:` / `test:`，一句话说清 What/Why。
- **不要提交**：`.env`、`configs/sources.yaml`、`cache/`、`logs/`、`reports/`、`snapshots/`、
  `backups/`、`live/*.db`、exe / 构建产物（均已 `.gitignore`）。
- 提交前自检：
  ```cmd
  python tests/run_tests.py
  git status
  git diff
  ```
  确认无真实 key/token、无大数据库文件。

## 红线（务必遵守）

- **不要**把在线 API 接进 `query_ip` 主流程；在线能力只做旁路增强。
- **不要**修改 SQLite 表结构；**不要**移动 `live/cache/logs/reports/snapshots/backups`。
- 改 GUI 前先审计。SQLite 并发改造按 `docs/SQLITE_CONCURRENCY_TODO.md` 分步、每步独立可回滚。
- 真实密钥只写 `.env`；模板（`*.example.*`）只放占位符。

## 安全

发现安全问题或疑似密钥泄漏，请参考 [`SECURITY.md`](SECURITY.md) 的处置流程。
