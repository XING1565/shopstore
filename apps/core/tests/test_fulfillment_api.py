"""履约状态回传（Odoo -> Core）API 测试。

覆盖：推进到 shipped、外部 ID 记录、重复回传幂等、乱序回传被拒绝（不倒退）、鉴权。
"""

from __future__ import annotations

OPERATOR = {"X-Actor-Role": "operator", "X-Operator-Name": "integration"}
RETAILER = {"X-Actor-Role": "retailer", "X-Retailer-Id": "buyer-1"}


def _seed_brand() -> str:
    from app.db import get_session_factory
    from app.models import Brand

    s = get_session_factory()()
    try:
        b = Brand(name="Fulfillment Brand")
        s.add(b)
        s.commit()
        return b.id
    finally:
        s.close()


def _seed_product_and_buyer(db_client) -> str:
    brand = _seed_brand()
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-FULFILL-001",
            "name": "Fulfillment Product",
            "brand_id": brand,
            "wholesale_price": {"amount_minor": 10000, "currency": "USD"},
            "moq": 10,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 201, resp.text
    db_client.post(f"/api/v1/products/{resp.json()['product_id']}/publish", headers=OPERATOR)

    buyer = db_client.post(
        "/api/v1/retailers",
        json={"email": "fulfillment_buyer@example.test", "company_name": "Acme"},
    ).json()
    db_client.post(
        f"/api/v1/retailers/{buyer['retailer_id']}/approve",
        json={"note": "ok"},
        headers=OPERATOR,
    )
    return buyer["retailer_id"]


def _place_order(db_client) -> str:
    retailer_id = _seed_product_and_buyer(db_client)
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-FULFILL-001", "quantity": 10}]},
        headers={"X-Actor-Role": "retailer", "X-Retailer-Id": retailer_id},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["marketplace_order_id"]


def _advance_to(order_id: str, target: str) -> None:
    """用状态机把订单推进到 ``target``（模拟 ISSUE-0107 及此前回传）。"""
    from app.db import get_session_factory
    from app.models import Order
    from app.models.enums import OrderStatus

    path = [
        OrderStatus.sent_to_odoo,
        OrderStatus.odoo_confirmed,
        OrderStatus.inventory_reserved,
        OrderStatus.picking_ready,
        OrderStatus.shipped,
    ]
    s = get_session_factory()()
    try:
        order = s.get(Order, order_id)
        for st in path:
            order.transition_to(st, reason="test_setup", actor="test")
            if st.value == target:
                break
        s.commit()
    finally:
        s.close()


def _report(db_client, order_id: str, status: str, **extra):
    return db_client.post(
        f"/api/v1/orders/{order_id}/fulfillment",
        json={"status": status, **extra},
        headers=OPERATOR,
    )


def test_shipped_advances_status_and_records_external_ids(db_client) -> None:
    order_id = _place_order(db_client)
    _advance_to(order_id, "picking_ready")

    resp = _report(
        db_client,
        order_id,
        "shipped",
        odoo_delivery_id=1001,
        odoo_sale_order_id=2002,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "shipped"
    assert body["external_ids"]["odoo_delivery_id"] == 1001
    assert body["external_ids"]["odoo_sale_order_id"] == 2002


def test_duplicate_report_is_idempotent(db_client) -> None:
    order_id = _place_order(db_client)
    _advance_to(order_id, "shipped")

    first = _report(db_client, order_id, "shipped", odoo_delivery_id=1001)
    assert first.status_code == 200
    assert first.json()["status"] == "shipped"

    second = _report(db_client, order_id, "shipped", odoo_delivery_id=1001)
    assert second.status_code == 200
    assert second.json()["status"] == "shipped"

    from app.db import get_session_factory
    from app.models import OrderStatusEvent

    s = get_session_factory()()
    try:
        events = s.query(OrderStatusEvent).filter_by(order_id=order_id).all()
        shipped_events = [e for e in events if e.to_status == "shipped"]
        assert len(shipped_events) == 1
    finally:
        s.close()


def test_out_of_order_report_rejected_without_regression(db_client) -> None:
    order_id = _place_order(db_client)
    _advance_to(order_id, "shipped")

    resp = _report(db_client, order_id, "picking_ready", odoo_delivery_id=1001)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"

    got = db_client.get(f"/api/v1/orders/{order_id}", headers=OPERATOR)
    assert got.json()["status"] == "shipped"


def test_fulfillment_requires_operator(db_client) -> None:
    order_id = _place_order(db_client)
    _advance_to(order_id, "picking_ready")

    resp = db_client.post(
        f"/api/v1/orders/{order_id}/fulfillment",
        json={"status": "shipped", "odoo_delivery_id": 1001},
        headers=RETAILER,
    )
    assert resp.status_code == 403

    anon = db_client.post(
        f"/api/v1/orders/{order_id}/fulfillment",
        json={"status": "shipped", "odoo_delivery_id": 1001},
    )
    assert anon.status_code == 403


def test_unknown_order_returns_404(db_client) -> None:
    resp = _report(db_client, "00000000-0000-0000-0000-000000000000", "shipped")
    assert resp.status_code == 404


def test_report_emits_status_changed_event(db_client) -> None:
    order_id = _place_order(db_client)
    _advance_to(order_id, "picking_ready")
    _report(db_client, order_id, "shipped", odoo_delivery_id=1001)

    from app.db import get_session_factory
    from app.models.outbox import OutboxEvent

    s = get_session_factory()()
    try:
        events = (
            s.query(OutboxEvent)
            .filter_by(event_type="commerce.order.status_changed")
            .all()
        )
        assert len(events) == 1
        assert events[0].data["marketplace_order_id"] == order_id
        assert events[0].data["status"] == "shipped"
        assert events[0].data["external_ids"]["odoo_delivery_id"] == 1001
    finally:
        s.close()
