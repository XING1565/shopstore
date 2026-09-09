"""统一错误响应格式测试。"""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.testclient import TestClient


def test_not_found_uses_error_envelope(client) -> None:
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert err["code"] == "not_found"
    assert "message" in err
    assert err["request_id"]


def test_method_not_allowed_uses_error_envelope(client) -> None:
    resp = client.post("/health")
    assert resp.status_code == 405
    assert resp.json()["error"]["code"] == "method_not_allowed"


def test_request_id_echoed_on_error(client) -> None:
    rid = "11111111-2222-3333-4444-555555555555"
    resp = client.get("/does-not-exist", headers={"X-Request-Id": rid})
    assert resp.status_code == 404
    assert resp.headers["x-request-id"] == rid
    assert resp.json()["error"]["request_id"] == rid


def test_validation_error_uses_error_envelope() -> None:
    from app.errors import register_exception_handlers
    from app.middleware import RequestContextMiddleware

    test_app = FastAPI()
    test_app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(test_app)

    @test_app.get("/validate")
    def validate(q: int = Query(...)):
        return {"q": q}

    with TestClient(test_app) as c:
        resp = c.get("/validate")
        assert resp.status_code == 422
        err = resp.json()["error"]
        assert err["code"] == "validation_error"
        assert err["details"][0]["field"] == "query.q"


def test_error_envelope_omits_none_fields() -> None:
    from app.errors import error_response
    from starlette.responses import JSONResponse

    resp = error_response(500, "internal_error", "服务器内部错误")
    body = resp.body.decode("utf-8")
    import json

    parsed = json.loads(body)
    assert "details" not in parsed["error"]
    assert "request_id" not in parsed["error"]
