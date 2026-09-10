"""Integration Layer 后台运维 CLI：同步失败可见 + 人工重试。

用法：

    python -m shopstore_integration list [--status failed|dead|completed|running|all] [--due]
    python -m shopstore_integration retry <idempotency-key>
    python -m shopstore_integration retry-dead

``retry`` / ``retry-dead`` 把失败 / 死信任务重新置为立即到期，由运行中的重试
Worker 在下一轮拉取执行；幂等键保证重试不会重复创建 Odoo 销售单。
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .db import create_all, get_session_factory
from .sync_jobs import STATUS_DEAD, SyncJobsStore

__all__ = ["build_parser", "main"]


def _store() -> SyncJobsStore:
    return SyncJobsStore(get_session_factory())


def cmd_list(args: argparse.Namespace) -> None:
    status = args.status
    if status == "all":
        status = None
    jobs = _store().list_jobs(status=status, due_only=args.due)
    for job in jobs:
        print(json.dumps(job.to_dict(), ensure_ascii=False))
    print(f"{len(jobs)} job(s)", file=sys.stderr)


def cmd_retry(args: argparse.Namespace) -> None:
    _store().retry(args.key)
    print(f"requeued {args.key}")


def cmd_retry_dead(args: argparse.Namespace) -> None:
    store = _store()
    dead = store.list_jobs(status=STATUS_DEAD)
    for job in dead:
        store.retry(job.idempotency_key)
    print(f"requeued {len(dead)} dead job(s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="shopstore_integration")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="列出同步任务")
    p_list.add_argument(
        "--status",
        default="failed",
        choices=["failed", "dead", "completed", "running", "all"],
        help="按状态过滤（默认 failed）",
    )
    p_list.add_argument(
        "--due",
        action="store_true",
        help="只显示已到期可重试的失败任务",
    )
    p_list.set_defaults(func=cmd_list)

    p_retry = sub.add_parser("retry", help="人工重试单个任务（按幂等键）")
    p_retry.add_argument("key", help="幂等键，如 core.order.export.ORDER-1")
    p_retry.set_defaults(func=cmd_retry)

    p_dead = sub.add_parser("retry-dead", help="重试全部死信任务")
    p_dead.set_defaults(func=cmd_retry_dead)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    create_all()
    args.func(args)


if __name__ == "__main__":
    main()
