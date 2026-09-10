"""幂等键抽象与幂等存储。

对齐契约 `conventions.md` 第 5 节：

- 命名格式 ``{scope}.{entity}.{action}.{source_id}``，四段点分隔；
- 总长 <= 255，``scope`` / ``entity`` / ``action`` 小写，``source_id`` 保留原值；
- 语义：同一键 + 同一负载 = 至多执行一次（可安全重试）；
  同一键 + 不同负载 = 拒绝并返回 409 Conflict。

阶段 0 提供接口 :class:`IdempotencyStore` 与进程内实现
:class:`InMemoryIdempotencyStore`；阶段一改用数据库任务表（``sync_jobs``）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Optional, Protocol, runtime_checkable

from .errors import IdempotencyConflictError

_MAX_KEY_LENGTH = 255
_ALLOWED_SCOPES = {"core", "woo", "odoo", "integration"}


@dataclass(frozen=True)
class IdempotencyKey:
    """四段点分隔的幂等键值对象。"""

    scope: str
    entity: str
    action: str
    source_id: str

    def __post_init__(self) -> None:
        scope = self.scope.lower()
        if scope not in _ALLOWED_SCOPES:
            raise ValueError(f"invalid scope {self.scope!r}")
        for segment_name, segment in (
            ("entity", self.entity),
            ("action", self.action),
        ):
            if not segment or not segment.islower():
                raise ValueError(f"{segment_name} must be non-empty lowercase, got {segment!r}")
        if not self.source_id:
            raise ValueError("source_id must be non-empty")
        if len(self.value) > _MAX_KEY_LENGTH:
            raise ValueError(f"idempotency key exceeds {_MAX_KEY_LENGTH} chars")

    @property
    def value(self) -> str:
        return f"{self.scope}.{self.entity}.{self.action}.{self.source_id}"

    @classmethod
    def parse(cls, key: str) -> "IdempotencyKey":
        parts = key.split(".")
        if len(parts) != 4:
            raise ValueError(f"expected 4 dot-separated segments, got {len(parts)} in {key!r}")
        scope, entity, action, source_id = parts
        return cls(scope=scope, entity=entity, action=action, source_id=source_id)

    def __str__(self) -> str:
        return self.value


def hash_payload(payload: Any) -> str:
    """计算负载的稳定哈希，用于判断「同一键 + 不同负载」。"""
    canonical = repr(payload).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True)
class IdempotencyRecord:
    """begin() 的返回结果，指示调用方下一步动作。"""

    key: str
    status: str  # "new" | "running" | "completed"
    result: Optional[dict[str, Any]] = None


@runtime_checkable
class IdempotencyStore(Protocol):
    """幂等存储接口（阶段一由数据库任务表实现）。"""

    def begin(self, key: str, payload_hash: str) -> IdempotencyRecord:
        """预留一个幂等键。冲突时抛 :class:`IdempotencyConflictError`。"""
        ...

    def commit(self, key: str, result: dict[str, Any]) -> None:
        """标记键已完成并保存结果。"""
        ...

    def abort(self, key: str) -> None:
        """释放预留（执行失败时允许用同一键重试）。"""
        ...


@runtime_checkable
class RetryableIdempotencyStore(IdempotencyStore, Protocol):
    """扩展了失败记录（重试 / 退避 / 死信）的幂等存储接口（ISSUE-0109）。

    ``begin`` 额外接受 ``command_type`` / ``payload`` / ``trace_id`` 以便在
    重试时重建命令；:meth:`mark_failed` 记录失败并按退避排期重试或进入死信。
    """

    def begin(
        self,
        key: str,
        payload_hash: str,
        *,
        command_type: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        max_attempts: Optional[int] = None,
        now: Any = None,
    ) -> IdempotencyRecord:
        """预留幂等键（记录命令信息）；返回 new/running/completed/deferred/dead。"""
        ...

    def mark_failed(self, key: str, error: BaseException, *, now: Any = None) -> str:
        """记录失败，返回新状态（``failed`` 或 ``dead``）。"""
        ...


class InMemoryIdempotencyStore:
    """进程内实现，用于阶段 0 Mock 验证与测试。"""

    def __init__(self) -> None:
        self._entries: dict[str, dict[str, Any]] = {}

    def begin(self, key: str, payload_hash: str) -> IdempotencyRecord:
        entry = self._entries.get(key)
        if entry is None:
            self._entries[key] = {
                "payload_hash": payload_hash,
                "status": "running",
                "result": None,
            }
            return IdempotencyRecord(key=key, status="new")

        if entry["payload_hash"] != payload_hash:
            raise IdempotencyConflictError(
                "idempotency key reused with a different payload",
                details=[{"field": "idempotency_key", "reason": "payload mismatch"}],
            )

        if entry["status"] == "completed":
            return IdempotencyRecord(
                key=key, status="completed", result=entry["result"]
            )
        return IdempotencyRecord(key=key, status="running")

    def commit(self, key: str, result: dict[str, Any]) -> None:
        entry = self._entries.get(key)
        if entry is None:
            raise KeyError(f"cannot commit unknown idempotency key {key!r}")
        entry["status"] = "completed"
        entry["result"] = result

    def abort(self, key: str) -> None:
        self._entries.pop(key, None)

    def reset(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)


__all__ = [
    "IdempotencyKey",
    "IdempotencyRecord",
    "IdempotencyStore",
    "RetryableIdempotencyStore",
    "InMemoryIdempotencyStore",
    "hash_payload",
]
