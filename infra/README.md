# infra — 基础设施

启动、编排、环境与备份脚本。

| 目录 | 内容 | Owner Agent |
| --- | --- | --- |
| `docker/` | Docker / Compose 编排定义 | ops |
| `scripts/` | start / stop / status / logs / init / seed / backup / restore 等脚本 | ops |
| `env/` | 环境变量模板（*.env.example） | config（模板）、ops（运行） |

本目录由 `config` Agent 在 ISSUE-0001 建立骨架，脚本实现在 ISSUE-0010 由 `ops` 完成。
