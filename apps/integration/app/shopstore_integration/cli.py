"""Integration Layer 后台运维 CLI：同步失败可见 + 人工重试。

用法：

    python -m shopstore_integration list [--status failed|dead|completed|running|all] [--due]
    python -m shopstore_integration retry <idempotency-key>
    python -m shopstore_integration retry-dead
    python -m shopstore_integration poll-fulfillment [--interval N] [--limit N] [--once]

``retry`` / ``retry-dead`` 把失败 / 死信任务重新置为立即到期，由运行中的重试
Worker 在下一轮拉取执行；幂等键保证重试不会重复创建 Odoo 销售单。

``poll-fulfillment`` 启动长驻轮询 worker（ISSUE-0115），读取 Odoo 交货单状态并
回传 Core，自动把订单推进到 Shipped（幂等 + 重试 / 退避）。
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


def cmd_poll_fulfillment(args: argparse.Namespace) -> None:
    """长驻轮询 Odoo 交货单状态并回传 Core（ISSUE-0115）。"""
    from .config import get_settings
    from .runtime import build_runtime

    settings = get_settings()
    runtime = build_runtime(settings)
    interval = args.interval or settings.sync_poll_interval_seconds
    if args.once:
        count = runtime.fulfillment_worker.run_once(limit=args.limit)
        print(f"polled {count} order(s)", file=sys.stderr)
        return
    print(
        f"polling every {interval}s (Ctrl-C to stop)", file=sys.stderr
    )
    try:
        runtime.fulfillment_worker.run(
            interval_seconds=interval, limit=args.limit
        )
    except KeyboardInterrupt:
        print("stopped", file=sys.stderr)


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

    p_poll = sub.add_parser(
        "poll-fulfillment", help="长驻轮询 Odoo 交货单状态并回传 Core（ISSUE-0115）"
    )
    p_poll.add_argument(
        "--interval",
        type=int,
        default=None,
        help="轮询间隔秒数（默认取 SYNC_POLL_INTERVAL_SECONDS）",
    )
    p_poll.add_argument(
        "--limit", type=int, default=50, help="每轮拉取的订单数上限（默认 50）"
    )
    p_poll.add_argument(
        "--once", action="store_true", help="只执行一轮后退出（测试 / 单次触发）"
    )
    p_poll.set_defaults(func=cmd_poll_fulfillment)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = build_parser().parse_args(argv)
    create_all()
    args.func(args)


if __name__ == "__main__":
    main()
