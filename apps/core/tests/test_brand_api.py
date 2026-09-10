"""品牌 API 测试：CRUD、鉴权、与产品创建的品牌引用。"""

from __future__ import annotations

OPERATOR = {"X-Actor-Role": "operator", "X-Operator-Name": "ops"}


def _create_brand(
    db_client,
    *,
    name: str = "Demo Brand A",
    description: str | None = None,
    logo_url: str | None = None,
) -> dict:
    body: dict = {"name": name}
    if description is not None:
        body["description"] = description
    if logo_url is not None:
        body["logo_url"] = logo_url
    resp = db_client.post("/api/v1/brands", json=body, headers=OPERATOR)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_create_brand_defaults_to_active(db_client) -> None:
    body = _create_brand(db_client)
    assert body["brand_id"]
    assert body["name"] == "Demo Brand A"
    assert body["status"] == "active"
    assert "description" not in body
    assert "logo_url" not in body


def test_create_brand_requires_operator(db_client) -> None:
    resp = db_client.post("/api/v1/brands", json={"name": "Brand X"})
    assert resp.status_code == 403


def test_create_brand_duplicate_name_conflict(db_client) -> None:
    _create_brand(db_client)
    resp = db_client.post(
        "/api/v1/brands", json={"name": "Demo Brand A"}, headers=OPERATOR
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_get_brand(db_client) -> None:
    created = _create_brand(db_client, description="desc", logo_url="https://x/logo.png")
    resp = db_client.get(
        f"/api/v1/brands/{created['brand_id']}", headers=OPERATOR
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Demo Brand A"
    assert body["description"] == "desc"
    assert body["logo_url"] == "https://x/logo.png"


def test_get_brand_requires_operator(db_client) -> None:
    created = _create_brand(db_client)
    resp = db_client.get(f"/api/v1/brands/{created['brand_id']}")
    assert resp.status_code == 403


def test_get_unknown_brand_not_found(db_client) -> None:
    resp = db_client.get(
        "/api/v1/brands/00000000-0000-0000-0000-000000000000", headers=OPERATOR
    )
    assert resp.status_code == 404


def test_list_brands(db_client) -> None:
    _create_brand(db_client, name="Brand A")
    _create_brand(db_client, name="Brand B")

    resp = db_client.get("/api/v1/brands", headers=OPERATOR)
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    names = {item["name"] for item in body["items"]}
    assert names == {"Brand A", "Brand B"}


def test_list_brands_requires_operator(db_client) -> None:
    resp = db_client.get("/api/v1/brands")
    assert resp.status_code == 403


def test_update_brand(db_client) -> None:
    created = _create_brand(db_client)

    resp = db_client.patch(
        f"/api/v1/brands/{created['brand_id']}",
        json={"name": "Renamed", "description": "new desc", "status": "inactive"},
        headers=OPERATOR,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["name"] == "Renamed"
    assert body["description"] == "new desc"
    assert body["status"] == "inactive"


def test_update_brand_clear_description_and_logo(db_client) -> None:
    created = _create_brand(db_client, description="d", logo_url="https://x/l.png")

    resp = db_client.patch(
        f"/api/v1/brands/{created['brand_id']}",
        json={"description": None, "logo_url": None},
        headers=OPERATOR,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "description" not in body
    assert "logo_url" not in body


def test_update_brand_name_conflict(db_client) -> None:
    _create_brand(db_client, name="Brand A")
    b = _create_brand(db_client, name="Brand B")

    resp = db_client.patch(
        f"/api/v1/brands/{b['brand_id']}",
        json={"name": "Brand A"},
        headers=OPERATOR,
    )
    assert resp.status_code == 409


def test_update_unknown_brand_not_found(db_client) -> None:
    resp = db_client.patch(
        "/api/v1/brands/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
        headers=OPERATOR,
    )
    assert resp.status_code == 404


def test_delete_brand(db_client) -> None:
    created = _create_brand(db_client)
    resp = db_client.delete(
        f"/api/v1/brands/{created['brand_id']}", headers=OPERATOR
    )
    assert resp.status_code == 204

    get = db_client.get(f"/api/v1/brands/{created['brand_id']}", headers=OPERATOR)
    assert get.status_code == 404


def test_delete_brand_with_products_conflict(db_client) -> None:
    created = _create_brand(db_client)

    product = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-SKU-001",
            "name": "Demo Product",
            "brand_id": created["brand_id"],
            "wholesale_price": {"amount_minor": 100, "currency": "USD"},
            "moq": 1,
        },
        headers=OPERATOR,
    )
    assert product.status_code == 201, product.text

    resp = db_client.delete(
        f"/api/v1/brands/{created['brand_id']}", headers=OPERATOR
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "conflict"


def test_delete_brand_requires_operator(db_client) -> None:
    created = _create_brand(db_client)
    resp = db_client.delete(f"/api/v1/brands/{created['brand_id']}")
    assert resp.status_code == 403


def test_product_creation_references_api_managed_brand(db_client) -> None:
    brand = _create_brand(db_client, name="API Brand")

    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-SKU-002",
            "name": "Demo Product",
            "brand_id": brand["brand_id"],
            "wholesale_price": {"amount_minor": 129900, "currency": "USD"},
            "moq": 10,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["brand_id"] == brand["brand_id"]


def test_product_creation_with_unknown_brand_rejected(db_client) -> None:
    resp = db_client.post(
        "/api/v1/products",
        json={
            "sku": "DEMO-SKU-003",
            "name": "Demo Product",
            "brand_id": "00000000-0000-0000-0000-000000000000",
            "wholesale_price": {"amount_minor": 100, "currency": "USD"},
            "moq": 1,
        },
        headers=OPERATOR,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"
