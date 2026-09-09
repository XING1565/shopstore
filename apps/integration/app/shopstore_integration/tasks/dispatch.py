"""任务分派：把 Core Command 路由到对应的同步任务。"""

from __future__ import annotations

from ..commands import Command
from ..errors import IntegrationError
from .base import SyncTask, TaskResult


class TaskDispatcher:
    """按 ``command_type`` 注册并分派同步任务。"""

    def __init__(self) -> None:
        self._tasks: dict[str, SyncTask] = {}

    def register(self, task: SyncTask) -> None:
        if not task.command_type:
            raise ValueError("SyncTask must declare a non-empty command_type")
        self._tasks[task.command_type] = task

    def dispatch(self, command: Command) -> TaskResult:
        task = self._tasks.get(command.command_type)
        if task is None:
            raise IntegrationError(
                f"no sync task registered for command_type {command.command_type!r}",
                request_id=command.request_id,
                trace_id=command.trace_id,
            )
        return task.execute(command)


__all__ = ["TaskDispatcher"]
