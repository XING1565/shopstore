"""商品 API 测试：批发价 / MOQ 鉴权、创建 / 发布 / 下架。"""

from __future__ import annotations

OPERATOR = {"X-Actor-Role": "operator", "X-Operator-Name": "ops"}


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


def _seed_product(
    db_client,
    sku: str = "DEMO-SKU-001",
    *,
    moq: int = 10,
    amount_minor: int = 129900,
    publish: bool = False,
    brand_id: str | None = None,
) -> dict:
    brand = brand_id or _seed_brand()
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
    product = resp.json()
    if publish:
        pub = db_client.post(
            f"/api/v1/products/{product['product_id']}/publish", headers=OPERATOR
        )
        assert pub.status_code == 200, pub.text
        product = pub.json()
    return product


def _buyer_headers(retailer_id: str) -> dict:
    return {"X-Actor-Role": "retailer", "X-Retailer-Id": retailer_id}


def _register_buyer(db_client, email="buyer@example.test"):
    resp = db_client.post(
        "/api/v1/retailers",
        json={"email": email, "company_name": "Acme"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_product_requires_operator(db_client) -> None:
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-SKU-001",
            "name": "P",
            "brand_id": "x",
            "wholesale_price": {"amount_minor": 100, "currency": "USD"},
            "moq": 1,
        },
    )
    assert resp.status_code == 403


def test_anonymous_cannot_see_wholesale_price(db_client) -> None:
    product = _seed_product(db_client)

    resp = db_client.get(f"/api/v1/products/{product['product_id']}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sku"] == "DEMO-SKU-001"
    assert "wholesale_price" not in body
    assert "moq" not in body


def test_pending_buyer_cannot_see_wholesale_price(db_client) -> None:
    product = _seed_product(db_client)
    buyer = _register_buyer(db_client)

    resp = db_client.get(
        f"/api/v1/products/{product['product_id']}",
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "wholesale_price" not in body
    assert "moq" not in body


def test_approved_buyer_sees_wholesale_price_and_moq(db_client) -> None:
    product = _seed_product(db_client, moq=10, amount_minor=129900)
    buyer = _register_buyer(db_client)
    db_client.post(
        f"/api/v1/retailers/{buyer['retailer_id']}/approve",
        json={"note": "ok"},
        headers=OPERATOR,
    )

    resp = db_client.get(
        f"/api/v1/products/{product['product_id']}",
        headers=_buyer_headers(buyer["retailer_id"]),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["wholesale_price"] == {"amount_minor": 129900, "currency": "USD"}
    assert body["moq"] == 10


def test_operator_sees_wholesale_price(db_client) -> None:
    product = _seed_product(db_client)
    resp = db_client.get(
        f"/api/v1/products/{product['product_id']}", headers=OPERATOR
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["wholesale_price"] == {"amount_minor": 129900, "currency": "USD"}
    assert body["moq"] == 10


def test_publish_and_archive(db_client) -> None:
    product = _seed_product(db_client, publish=True)
    assert product["status"] == "published"

    arch = db_client.post(
        f"/api/v1/products/{product['product_id']}/archive", headers=OPERATOR
    )
    assert arch.status_code == 200
    assert arch.json()["status"] == "archived"


def test_archive_draft_rejected(db_client) -> None:
    product = _seed_product(db_client, publish=False)
    assert product["status"] == "draft"

    arch = db_client.post(
        f"/api/v1/products/{product['product_id']}/archive", headers=OPERATOR
    )
    assert arch.status_code == 409


def test_duplicate_sku_conflict(db_client) -> None:
    _seed_product(db_client, sku="DEMO-SKU-001")
    brand = _seed_brand("Other Brand")
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-SKU-001",
            "name": "Dup",
            "brand_id": brand,
            "wholesale_price": {"amount_minor": 100, "currency": "USD"},
            "moq": 1,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 409
