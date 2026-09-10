"""Integration 面向 Core 的端点测试：事件轮询 / ack / 订单外部 ID 写回。"""

from __future__ import annotations

OPERATOR = {"X-Actor-Role": "operator", "X-Operator-Name": "integration"}


def _buyer_headers(retailer_id: str) -> dict:
    return {"X-Actor-Role": "retailer", "X-Retailer-Id": retailer_id}


def _seed_brand(name: str = "Demo Brand") -> str:
    from app.db import get_session_factory
    from app.models import Brand

    s = get_session_factory()()
    try:
        b = Brand(name=name)
        s.add(b)
        s.commit()
        return b.id
    finally:
        s.close()


def _seed_product(db_client, sku="DEMO-SKU-001", moq=10) -> str:
    brand = _seed_brand()
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": "Demo Product",
            "brand_id": brand,
            "wholesale_price": {"amount_minor": 129900, "currency": "USD"},
            "moq": moq,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["product_id"]
    pub = db_client.post(f"/api/v1/products/{pid}/publish", headers=OPERATOR)
    assert pub.status_code == 200, pub.text
    return pid


def _register_buyer(db_client, email="buyer@example.test") -> dict:
    resp = db_client.post(
        "/api/v1/retailers",
        json={"email": email, "company_name": "Acme"},
    )
    assert resp.status_code == 201, resp.text
    buyer = resp.json()
    r = db_client.post(
        f"/api/v1/retailers/{buyer['retailer_id']}/approve",
        json={"note": "ok"},
        headers=OPERATOR,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _place_order(db_client, buyer: dict) -> dict:
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 10}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_order_emits_pending_event_visible_to_integration(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    _place_order(db_client, buyer)

    resp = db_client.get(
        "/api/v1/events", params={"event_type": "commerce.order.created"}, headers=OPERATOR
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    event = body["items"][0]
    assert event["event_type"] == "commerce.order.created"
    assert event["data"]["marketplace_order_id"]
    assert event["data"]["lines"][0]["sku"] == "DEMO-SKU-001"


def test_events_endpoint_requires_operator(db_client) -> None:
    resp = db_client.get("/api/v1/events")
    assert resp.status_code == 403


def test_ack_event_marks_published(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    _place_order(db_client, buyer)

    events = db_client.get(
        "/api/v1/events", params={"event_type": "commerce.order.created"}, headers=OPERATOR
    ).json()["items"]
    assert len(events) == 1
    event_id = events[0]["event_id"]

    ack = db_client.post(f"/api/v1/events/{event_id}/ack", headers=OPERATOR)
    assert ack.status_code == 204

    after = db_client.get(
        "/api/v1/events", params={"event_type": "commerce.order.created"}, headers=OPERATOR
    ).json()
    assert after["total"] == 0


def test_writeback_odoo_sale_order_advances_to_sent(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)
    assert order["status"] == "submitted"
    assert order["external_ids"].get("odoo_sale_order_id") is None

    resp = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"odoo_sale_order_id": 1011},
        headers=OPERATOR,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "sent_to_odoo"
    assert body["external_ids"]["odoo_sale_order_id"] == 1011


def test_writeback_is_idempotent_for_same_id(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)

    first = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"odoo_sale_order_id": 1011},
        headers=OPERATOR,
    )
    second = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"odoo_sale_order_id": 1011},
        headers=OPERATOR,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["external_ids"]["odoo_sale_order_id"] == 1011
    assert second.json()["status"] == "sent_to_odoo"


def test_writeback_conflict_for_different_id(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)

    db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"odoo_sale_order_id": 1011},
        headers=OPERATOR,
    )
    resp = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"odoo_sale_order_id": 2022},
        headers=OPERATOR,
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_writeback_requires_operator(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)
    resp = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"odoo_sale_order_id": 1011},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 403


def test_writeback_woo_order_id_records_mapping(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)
    assert order["external_ids"].get("woo_order_id") is None

    resp = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"woo_order_id": 789},
        headers=OPERATOR,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["external_ids"]["woo_order_id"] == 789
    assert body["status"] == "submitted"


def test_writeback_woo_order_id_idempotent_then_conflict(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)

    first = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"woo_order_id": 789},
        headers=OPERATOR,
    )
    assert first.status_code == 200

    second = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"woo_order_id": 789},
        headers=OPERATOR,
    )
    assert second.status_code == 200
    assert second.json()["external_ids"]["woo_order_id"] == 789

    conflict = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={"woo_order_id": 987},
        headers=OPERATOR,
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"


def test_writeback_requires_external_id(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)
    order = _place_order(db_client, buyer)
    resp = db_client.post(
        f"/api/v1/orders/{order['marketplace_order_id']}/external-ids",
        json={},
        headers=OPERATOR,
    )
    assert resp.status_code == 400
