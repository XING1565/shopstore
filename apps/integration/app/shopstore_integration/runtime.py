"""Integration 运行时装配：把配置与真实 Adapter / 客户端 / worker 组装起来。

供后台 CLI（``python -m shopstore_integration poll-fulfillment``）使用；测试
用各自替身直接构造对象，不经由本模块。
"""

from __future__ import annotations

from dataclasses import dataclass

from .adapters import HttpCoreAdapter, HttpOdooAdapter
from .config import IntegrationSettings, get_settings
from .core_client import CoreClient
from .db import create_all, get_session_factory
from .fulfillment_worker import FulfillmentSyncWorker
from .http_client import UnifiedHttpClient
from .sync_jobs import SyncJobsStore
from .tasks.dispatch import TaskDispatcher
from .tasks.report_fulfillment import ReportFulfillmentTask

__all__ = ["Runtime", "build_runtime"]


@dataclass
class Runtime:
    """装配好的真实运行时组件。"""

    settings: IntegrationSettings
    client: UnifiedHttpClient
    core: CoreClient
    core_adapter: HttpCoreAdapter
    odoo: HttpOdooAdapter
    store: SyncJobsStore
    dispatcher: TaskDispatcher
    fulfillment_worker: FulfillmentSyncWorker


def build_runtime(settings: IntegrationSettings | None = None) -> Runtime:
    """按配置组装真实 Integration 运行时（Core 客户端 + Odoo Adapter + worker）。"""
    settings = settings or get_settings()

    create_all()

    client = UnifiedHttpClient(timeout=settings.timeout)
    core = CoreClient(base_url=settings.core_base_url, client=client)
    core_adapter = HttpCoreAdapter(base_url=settings.core_base_url, client=client)
    odoo = HttpOdooAdapter(
        base_url=settings.odoo_base_url,
        db=settings.odoo_db,
        username=settings.odoo_user,
        password=settings.odoo_password,
        client=client,
    )

    store = SyncJobsStore(get_session_factory())
    report_task = ReportFulfillmentTask(core=core_adapter, idempotency_store=store)
    dispatcher = TaskDispatcher()
    dispatcher.register(report_task)

    fulfillment_worker = FulfillmentSyncWorker(
        core=core, odoo=odoo, dispatcher=dispatcher
    )

    return Runtime(
        settings=settings,
        client=client,
        core=core,
        core_adapter=core_adapter,
        odoo=odoo,
        store=store,
        dispatcher=dispatcher,
        fulfillment_worker=fulfillment_worker,
    )
