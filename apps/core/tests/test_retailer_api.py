"""买家 API 测试：注册（默认 pending）、运营审核。"""

from __future__ import annotations

OPERATOR = {"X-Actor-Role": "operator", "X-Operator-Name": "ops"}


def _register(db_client, email="buyer@example.test", company="Acme Retail"):
    resp = db_client.post(
        "/api/v1/retailers",
        json={"email": email, "company_name": company},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _buyer_headers(retailer_id: str) -> dict:
    return {"X-Actor-Role": "retailer", "X-Retailer-Id": retailer_id}


def test_register_retailer_defaults_to_pending(db_client) -> None:
    body = _register(db_client)
    assert body["status"] == "pending"
    assert body["retailer_id"]
    assert body["email"] == "buyer@example.test"


def test_register_duplicate_email_conflict(db_client) -> None:
    _register(db_client)
    resp = db_client.post(
        "/api/v1/retailers",
        json={"email": "buyer@example.test", "company_name": "Other"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_operator_approves_retailer(db_client) -> None:
    body = _register(db_client)
    rid = body["retailer_id"]

    resp = db_client.post(
        f"/api/v1/retailers/{rid}/approve",
        json={"note": "ok"},
        headers=OPERATOR,
    )
    assert resp.status_code == 200, resp.text
    got = resp.json()
    assert got["status"] == "approved"
    assert got["reviewed_by"] == "ops"
    assert got["reviewed_at"]


def test_operator_rejects_retailer(db_client) -> None:
    body = _register(db_client)
    rid = body["retailer_id"]
    resp = db_client.post(
        f"/api/v1/retailers/{rid}/reject",
        json={"note": "spam"},
        headers=OPERATOR,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_non_operator_cannot_approve(db_client) -> None:
    body = _register(db_client)
    rid = body["retailer_id"]
    resp = db_client.post(
        f"/api/v1/retailers/{rid}/approve",
        json={"note": "ok"},
        headers=_buyer_headers(rid),
    )
    assert resp.status_code == 403


def test_approve_unknown_retailer_not_found(db_client) -> None:
    resp = db_client.post(
        "/api/v1/retailers/00000000-0000-0000-0000-000000000000/approve",
        json={"note": "x"},
        headers=OPERATOR,
    )
    assert resp.status_code == 404


def test_list_retailers_requires_operator(db_client) -> None:
    _register(db_client)
    anon = db_client.get("/api/v1/retailers")
    assert anon.status_code == 403

    ok = db_client.get("/api/v1/retailers", headers=OPERATOR)
    assert ok.status_code == 200
    body = ok.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "pending"


def test_retailer_cannot_view_other_retailer(db_client) -> None:
    a = _register(db_client, email="a@example.test")
    b = _register(db_client, email="b@example.test")

    resp = db_client.get(
        f"/api/v1/retailers/{b['retailer_id']}",
        headers=_buyer_headers(a["retailer_id"]),
    )
    assert resp.status_code == 403


def test_writeback_odoo_partner_external_ids(db_client) -> None:
    body = _register(db_client)
    rid = body["retailer_id"]
    assert body.get("odoo_partner_ref") is None

    resp = db_client.post(
        f"/api/v1/retailers/{rid}/external-ids",
        json={"odoo_partner_ref": "DEMO-RTL-001", "odoo_partner_id": 44},
        headers=OPERATOR,
    )
    assert resp.status_code == 200, resp.text
    got = resp.json()
    assert got["odoo_partner_ref"] == "DEMO-RTL-001"
    assert got["odoo_partner_id"] == 44


def test_writeback_odoo_partner_conflict_for_different_ref(db_client) -> None:
    body = _register(db_client)
    rid = body["retailer_id"]

    first = db_client.post(
        f"/api/v1/retailers/{rid}/external-ids",
        json={"odoo_partner_ref": "DEMO-RTL-001"},
        headers=OPERATOR,
    )
    assert first.status_code == 200

    second = db_client.post(
        f"/api/v1/retailers/{rid}/external-ids",
        json={"odoo_partner_ref": "DEMO-RTL-002"},
        headers=OPERATOR,
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_writeback_odoo_partner_requires_operator(db_client) -> None:
    body = _register(db_client)
    rid = body["retailer_id"]
    resp = db_client.post(
        f"/api/v1/retailers/{rid}/external-ids",
        json={"odoo_partner_ref": "DEMO-RTL-001"},
        headers=_buyer_headers(rid),
    )
    assert resp.status_code == 403
