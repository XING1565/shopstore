# infra — 基础设施

启动、编排、环境与备份脚本。

| 目录 | 内容 | Owner Agent |
| --- | --- | --- |
| `docker/` | Docker / Compose 编排定义（`compose.yaml`：Core + Integration 测试镜像） | ops |
| `scripts/` | 一键编排：`shopstore.ps1` / `shopstore.sh`（start / stop / status / logs / init / seed / backup / restore / test-smoke） | ops |
| `env/` | 环境变量模板（*.env.example） | config（模板）、ops（运行） |

本目录由 `config` Agent 在 ISSUE-0001 建立骨架，脚本实现已在 ISSUE-0010 由 `ops` 完成。

## 快速开始

```powershell
# Windows
.\infra\scripts\shopstore.ps1 init
.\infra\scripts\shopstore.ps1 status
```

```bash
# Linux / macOS / Git Bash
bash infra/scripts/shopstore.sh init
bash infra/scripts/shopstore.sh status
```

## 文档

- 命令与备份/恢复：`infra/scripts/README.md`
- 数据恢复说明：`infra/RESTORE.md`
- staging 启动说明：`infra/STAGING.md`
