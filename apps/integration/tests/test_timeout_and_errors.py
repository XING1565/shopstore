"""验证超时与异常可被捕获，以及统一请求客户端的错误分类。"""

from __future__ import annotations

import httpx
import pytest

from shopstore_integration.config import IntegrationSettings, TimeoutConfig
from shopstore_integration.errors import (
    IdempotencyConflictError,
    IntegrationError,
    PayloadValidationError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
    UpstreamTimeoutError,
)
from shopstore_integration.http_client import UnifiedHttpClient


def test_client_maps_timeout_to_timeout_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    client = UnifiedHttpClient(transport=httpx.MockTransport(handler))
    with pytest.raises(UpstreamTimeoutError) as excinfo:
        client.request("GET", "http://example.test/", request_id="req-1")
    assert excinfo.value.code == "upstream_timeout"
    assert excinfo.value.request_id == "req-1"
    client.close()


def test_client_maps_http_status_codes() -> None:
    cases = [
        (401, UpstreamAuthError),
        (404, ResourceNotFoundError),
        (409, IdempotencyConflictError),
        (422, PayloadValidationError),
        (500, UpstreamError),
    ]
    for status, error_cls in cases:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, json={"error": {"code": "x", "message": "y"}})

        client = UnifiedHttpClient(transport=httpx.MockTransport(handler))
        with pytest.raises(error_cls):
            client.request("GET", "http://example.test/", request_id="req-1")
        client.close()


def test_client_injects_request_id_header() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["x-request-id"] = request.headers.get("X-Request-Id", "")
        return httpx.Response(200, json={"ok": True})

    client = UnifiedHttpClient(transport=httpx.MockTransport(handler))
    result = client.request("GET", "http://example.test/", request_id="req-abc")
    assert result == {"ok": True}
    assert captured["x-request-id"] == "req-abc"
    client.close()


def test_task_captures_adapter_timeout_as_failure() -> None:
    from shopstore_integration.adapters import MockAdapter
    from shopstore_integration.commands import publish_product_command
    from shopstore_integration.idempotency import InMemoryIdempotencyStore
    from shopstore_integration.tasks import TaskStatus
    from shopstore_integration.tasks.publish_product import PublishProductTask

    woo = MockAdapter(
        name="woo",
        fail_with=UpstreamTimeoutError("woo timed out", request_id="x"),
        fail_count=1,
    )
    odoo = MockAdapter(name="odoo")
    task = PublishProductTask(
        woo=woo, odoo=odoo, idempotency_store=InMemoryIdempotencyStore()
    )

    command = publish_product_command(
        sku="DEMO-SKU-001", name="Demo", amount_minor=100, currency="USD"
    )
    result = task.execute(command)

    assert result.status == TaskStatus.FAILED
    assert result.error is not None
    assert result.error.code == "upstream_timeout"


def test_error_envelope_serialization() -> None:
    error = PayloadValidationError(
        "bad payload",
        request_id="req-1",
        details=[{"field": "lines[0].quantity", "reason": "below MOQ"}],
    )
    envelope = error.to_envelope()
    assert envelope["error"]["code"] == "validation_error"
    assert envelope["error"]["request_id"] == "req-1"
    assert envelope["error"]["details"][0]["field"] == "lines[0].quantity"


def test_settings_load_from_env() -> None:
    settings = IntegrationSettings.from_env(
        {
            "APP_ENV": "staging",
            "APP_DEBUG": "false",
            "WOO_BASE_URL": "http://woo:8080",
            "HTTP_TIMEOUT_READ_SECONDS": "5",
            "SYNC_RETRY_MAX": "9",
        }
    )
    assert settings.app_env == "staging"
    assert settings.app_debug is False
    assert settings.woo_base_url == "http://woo:8080"
    assert settings.timeout.read_seconds == 5.0
    assert settings.sync_retry_max == 9


def test_timeout_config_defaults() -> None:
    timeout = TimeoutConfig()
    assert timeout.connect_seconds == 5.0
    assert timeout.read_seconds == 30.0


def test_base_error_http_status() -> None:
    assert IntegrationError("x").http_status == 500
    assert UpstreamTimeoutError("x").http_status == 504
