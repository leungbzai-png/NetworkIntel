# 安全说明（SECURITY.md）

本项目为本地离线 IP 情报平台。以下约定用于保护凭证与本地数据，**所有维护者必须遵守**。

## 1. API Key 绝不写入 Git

- 任何真实凭证（如 MaxMind License Key）**不得**出现在被 Git 跟踪的文件中。
- 真实密钥只能存在于：
  - 项目根目录的 `.env`（已被 `.gitignore` 忽略），或
  - 本地私有配置 `configs/sources.yaml` / `configs/*.local.yaml`（已被忽略）。

## 2. 真实配置使用 .env 或本地私有配置

- 复制示例并填入真实值：
  ```
  cp .env.example .env
  # 编辑 .env，填入 MAXMIND_LICENSE_KEY
  ```
- 程序通过 `python/utils/config_loader.py` 在启动时自动加载 `.env`，
  并把 `configs/sources.yaml` 中的 `${MAXMIND_LICENSE_KEY}` 占位符解析为环境变量值。
- 在 GUI「设置」页保存的 MaxMind Key 会写入 `.env`（不写回 yaml）。

## 3. sources.example.yaml 只放占位符

- `configs/sources.example.yaml` 是入库的配置模板，**只能包含占位符**
  （如 `${MAXMIND_LICENSE_KEY}`），严禁出现真实密钥。
- 实际运行使用 `configs/sources.yaml`（从示例复制而来，本地私有，不入库）。

## 4. 本地数据不提交

以下目录/文件含本地数据或体积庞大，**不提交**（已在 `.gitignore` 中忽略）：

| 内容 | 路径 |
|------|------|
| 数据库 | `live/*.db`、`*.db` / `*.sqlite` / `*.sqlite3` |
| 缓存 | `cache/` |
| 快照 | `snapshots/`、`gdrive_sync/` |
| 备份 | `backups/` |
| 日志 | `logs/`、`*.log` |
| 报告 | `reports/` |
| 构建产物 | `dist/`、`dist_backup*/`、`build/`、`*.spec` |
| 本地密钥 | `.env`、`.env.*`、`configs/sources.yaml`、`configs/*.local.yaml` |

## 5. 密钥泄漏处置

如果某个 Key 曾经被提交到任何远程仓库（或被推送 / 共享）：

1. **立即到对应平台后台轮换 / 作废该 Key**（例如 MaxMind 控制台重新生成 License Key）。
2. 更新本地 `.env` 为新 Key。
3. 即使随后从历史中删除，也必须视该 Key 为已泄漏 —— 轮换是唯一可靠的补救。

> 本仓库在初始化 Git 前已将历史明文 MaxMind Key 从 `configs/sources.yaml` 与备份副本中移出/脱敏。
> 该 Key 此前以明文存在于本地磁盘，**建议到 MaxMind 后台轮换一次**以彻底消除风险。
