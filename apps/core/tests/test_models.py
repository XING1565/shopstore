"""数据模型测试：可在 Core 数据库创建，字段类型与外部 ID 映射完整。"""

from __future__ import annotations

import pytest

from app.models import Brand, Order, OrderLine, Product, Retailer
from app.models.enums import OrderStatus, ProductStatus, RetailerStatus


def _retailer(**overrides) -> Retailer:
    defaults = dict(email="retailer_1@example.test", company_name="Acme Retail")
    defaults.update(overrides)
    return Retailer(**defaults)


def test_retailer_model_creates_and_persists(session) -> None:
    r = _retailer()
    session.add(r)
    session.commit()

    got = session.get(Retailer, r.id)
    assert got is not None
    assert got.status is RetailerStatus.pending
    assert got.created_at is not None
    assert got.updated_at is not None


def test_brand_and_product_with_price_moq_external_ids(session) -> None:
    brand = Brand(name="Demo Brand")
    session.add(brand)
    session.flush()

    product = Product(
        brand_id=brand.id,
        sku="DEMO-SKU-001",
        name="Demo Product",
        wholesale_price_minor=129900,
        wholesale_price_currency="USD",
        moq=10,
        woo_product_id=1234,
        odoo_product_id=567,
    )
    session.add(product)
    session.commit()

    got = session.get(Product, product.id)
    assert got.brand_id == brand.id
    assert got.wholesale_price_minor == 129900
    assert got.wholesale_price_currency == "USD"
    assert got.moq == 10
    assert got.woo_product_id == 1234
    assert got.odoo_product_id == 567
    assert got.status is ProductStatus.draft


def test_order_with_external_ids_and_lines(session) -> None:
    r = _retailer()
    session.add(r)
    session.flush()

    order = Order(
        retailer_id=r.id,
        woo_order_id=789,
        odoo_sale_order_id=1011,
        odoo_delivery_id=1213,
    )
    order.lines.append(
        OrderLine(sku="DEMO-SKU-001", quantity=10, unit_price_minor=129900)
    )
    session.add(order)
    session.commit()

    got = session.get(Order, order.id)
    assert got.woo_order_id == 789
    assert got.odoo_sale_order_id == 1011
    assert got.odoo_delivery_id == 1213
    assert got.status is OrderStatus.draft
    assert len(got.lines) == 1
    assert got.lines[0].sku == "DEMO-SKU-001"


def test_external_ids_null_when_projection_not_created(session) -> None:
    brand = Brand(name="B2")
    session.add(brand)
    session.flush()
    product = Product(
        brand_id=brand.id, sku="DEMO-SKU-002", name="P", wholesale_price_minor=1
    )
    session.add(product)
    session.commit()

    got = session.get(Product, product.id)
    assert got.woo_product_id is None
    assert got.odoo_product_id is None


def test_sku_unique_constraint(session) -> None:
    brand = Brand(name="Brand")
    session.add(brand)
    session.flush()

    def product_with(sku: str) -> Product:
        return Product(
            brand_id=brand.id, sku=sku, name=sku, wholesale_price_minor=1, moq=1
        )

    session.add(product_with("DEMO-SKU-003"))
    session.commit()
    session.add(product_with("DEMO-SKU-003"))
    with pytest.raises(Exception):
        session.commit()
    session.rollback()
