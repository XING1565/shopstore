"""健康检查接口测试。"""

from __future__ import annotations


def test_health_returns_ok(client) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {}}


def test_api_v1_health_returns_ok(client) -> None:
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert resp.headers.get("x-request-id")


def test_ready_returns_ok_when_database_up(client) -> None:
    resp = client.get("/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert isinstance(body["checks"]["database"]["latency_ms"], int)


def test_ready_returns_503_when_database_down(client, monkeypatch) -> None:
    def fake_check() -> dict:
        return {"status": "down", "latency_ms": 0}

    monkeypatch.setattr("app.api.health.check_database", fake_check)

    resp = client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"]["code"] == "service_unavailable"
    assert body["error"]["request_id"]


def test_request_id_generated_and_echoed(client) -> None:
    resp = client.get("/health")
    assert resp.headers.get("x-request-id")
