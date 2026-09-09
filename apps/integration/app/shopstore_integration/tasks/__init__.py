"""同步任务（Sync Task）抽象与任务分派。"""

from __future__ import annotations

from .base import SyncTask, TaskResult, TaskStatus

__all__ = ["SyncTask", "TaskResult", "TaskStatus"]
