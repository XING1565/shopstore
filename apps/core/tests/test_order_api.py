"""订单 API 测试：无支付下单、MOQ 校验、认证鉴权、领域事件。"""

from __future__ import annotations

OPERATOR = {"X-Actor-Role": "operator", "X-Operator-Name": "ops"}


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


def _seed_product(db_client, sku="DEMO-SKU-001", moq=10, amount_minor=129900) -> str:
    brand = _seed_brand()
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": sku,
            "name": "Demo Product",
            "brand_id": brand,
            "wholesale_price": {"amount_minor": amount_minor, "currency": "USD"},
            "moq": moq,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 201, resp.text
    pid = resp.json()["product_id"]
    pub = db_client.post(f"/api/v1/products/{pid}/publish", headers=OPERATOR)
    assert pub.status_code == 200, pub.text
    return pid


def _register_buyer(db_client, email="buyer@example.test", approve=False) -> dict:
    resp = db_client.post(
        "/api/v1/retailers",
        json={"email": email, "company_name": "Acme"},
    )
    assert resp.status_code == 201, resp.text
    buyer = resp.json()
    if approve:
        r = db_client.post(
            f"/api/v1/retailers/{buyer['retailer_id']}/approve",
            json={"note": "ok"},
            headers=OPERATOR,
        )
        assert r.status_code == 200, r.text
        buyer = r.json()
    return buyer


def test_unapproved_buyer_cannot_place_order(db_client) -> None:
    _seed_product(db_client)
    buyer = _register_buyer(db_client)  # pending
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 10}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "forbidden"


def test_below_moq_rejected_with_reason(db_client) -> None:
    _seed_product(db_client, moq=10)
    buyer = _register_buyer(db_client, approve=True)
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 5}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "moq_not_met"
    reason = err["details"][0]["reason"]
    assert "5" in reason and "10" in reason


def test_approved_buyer_places_order_submitted(db_client) -> None:
    _seed_product(db_client, moq=10, amount_minor=129900)
    buyer = _register_buyer(db_client, approve=True)
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 20}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "submitted"
    assert body["marketplace_order_id"]
    assert body["retailer_id"] == buyer["retailer_id"]
    assert body["lines"][0] == {
        "sku": "DEMO-SKU-001",
        "quantity": 20,
        "unit_price": {"amount_minor": 129900, "currency": "USD"},
    }
    assert body["total"] == {"amount_minor": 20 * 129900, "currency": "USD"}


def test_order_emits_domain_event(db_client) -> None:
    _seed_product(db_client, moq=10)
    buyer = _register_buyer(db_client, approve=True)
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 10}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 201

    from app.db import get_session_factory
    from app.models.outbox import OutboxEvent

    s = get_session_factory()()
    try:
        events = s.query(OutboxEvent).filter_by(event_type="commerce.order.created").all()
        assert len(events) == 1
        data = events[0].data
        assert data["marketplace_order_id"] == resp.json()["marketplace_order_id"]
        assert data["status"] == "submitted"
    finally:
        s.close()


def test_unknown_sku_rejected(db_client) -> None:
    buyer = _register_buyer(db_client, approve=True)
    resp = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-NOPE", "quantity": 1}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 400


def test_cannot_order_unpublished_product(db_client) -> None:
    brand = _seed_brand()
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-SKU-002",
            "name": "Draft",
            "brand_id": brand,
            "wholesale_price": {"amount_minor": 100, "currency": "USD"},
            "moq": 1,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 201
    buyer = _register_buyer(db_client, approve=True)
    order = db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-002", "quantity": 1}]},
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert order.status_code == 409


def test_buyer_can_list_own_orders_only(db_client) -> None:
    _seed_product(db_client, moq=10)
    a = _register_buyer(db_client, email="a@example.test", approve=True)
    b = _register_buyer(db_client, email="b@example.test", approve=True)

    db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 10}]},
        headers=_buyer_headers(a["retailer_id"]),
    )
    db_client.post(
        "/api/v1/orders",
        json={"lines": [{"sku": "DEMO-SKU-001", "quantity": 10}]},
        headers=_buyer_headers(b["retailer_id"]),
    )

    own = db_client.get("/api/v1/orders", headers=_buyer_headers(a["retailer_id"]))
    assert own.status_code == 200
    assert own.json()["total"] == 1

    all_orders = db_client.get("/api/v1/orders", headers=OPERATOR)
    assert all_orders.json()["total"] == 2
