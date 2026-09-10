"""真实 Odoo Adapter（JSON-RPC）测试：partner/SKU/订单映射、幂等去重、错误分类。"""

from __future__ import annotations

import json

import httpx
import pytest

from shopstore_integration.adapters.odoo_http import HttpOdooAdapter, amount_minor_to_float
from shopstore_integration.errors import ResourceNotFoundError, UpstreamError
from shopstore_integration.http_client import UnifiedHttpClient


class FakeOdooState:
    """最小内存 Odoo 替身：res.partner / product.product / sale.order。"""

    def __init__(self) -> None:
        self.partners: dict[int, dict] = {
            1: {"id": 1, "ref": "DEMO-RTL-001", "name": "Demo Retailer", "email": "r@example.test"},
        }
        self.products: dict[int, dict] = {
            100: {"id": 100, "default_code": "DEMO-SKU-001", "name": "Mug"},
            101: {"id": 101, "default_code": "DEMO-SKU-002", "name": "Tote"},
        }
        self.sale_orders: dict[int, dict] = {}
        self._next_partner = 10
        self._next_so = 1000
        self.created_sale_orders: list[dict] = []

    def _search(self, model: str, domain: list, limit: int) -> list[int]:
        collection = {
            "res.partner": self.partners,
            "product.product": self.products,
            "sale.order": self.sale_orders,
        }[model]
        matched = list(collection.keys())
        for field, op, value in domain:
            if op == "=":
                matched = [i for i in matched if collection[i].get(field) == value]
        return matched[:limit] if limit else matched

    def _read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        collection = {
            "res.partner": self.partners,
            "product.product": self.products,
            "sale.order": self.sale_orders,
        }[model]
        out = []
        for i in ids:
            row = collection[i]
            if fields:
                out.append({f: row[f] for f in fields if f in row})
            else:
                out.append(dict(row))
        return out

    def _create(self, model: str, vals: dict) -> int:
        if model == "res.partner":
            self._next_partner += 1
            record = {"id": self._next_partner, **vals}
            self.partners[record["id"]] = record
            return record["id"]
        if model == "product.product":
            raise RuntimeError("product create not expected in order export tests")
        if model == "sale.order":
            self._next_so += 1
            record = {"id": self._next_so, **vals}
            self.sale_orders[record["id"]] = record
            self.created_sale_orders.append(vals)
            return record["id"]
        raise RuntimeError(f"unknown model {model}")


def make_odoo_client(state: FakeOdooState) -> UnifiedHttpClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        params = body["params"]
        service = params["service"]
        method = params["method"]
        args = params["args"]

        if service == "common":
            if method == "authenticate":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 2})
            if method == "version":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {"server_version": "19.0"}})

        if service == "object" and method == "execute_kw":
            _db, _uid, _pwd, model, meth, margs, kwargs = args
            if meth == "search":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": state._search(model, margs[0], kwargs.get("limit", 0))})
            if meth == "read":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": state._read(model, margs[0], margs[1])})
            if meth == "create":
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": state._create(model, margs[0])})
            if meth == "action_confirm":
                so_id = margs[0]
                state.sale_orders[so_id]["state"] = "sale"
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": True})

        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": None})

    return UnifiedHttpClient(transport=httpx.MockTransport(handler))


def make_adapter(state: FakeOdooState) -> HttpOdooAdapter:
    return HttpOdooAdapter(
        base_url="http://odoo.test",
        db="shopstore_odoo",
        username="admin",
        password="secret",
        client=make_odoo_client(state),
    )


def test_health_check() -> None:
    adapter = make_adapter(FakeOdooState())
    assert adapter.health_check(request_id="req-1") is True


def test_create_sale_order_resolves_partner_and_sku() -> None:
    state = FakeOdooState()
    adapter = make_adapter(state)

    result = adapter.create_sale_order(
        {
            "marketplace_order_id": "ORDER-1",
            "retailer_ref": "DEMO-RTL-001",
            "lines": [
                {"sku": "DEMO-SKU-001", "quantity": 3, "unit_price": {"amount_minor": 129900, "currency": "USD"}},
            ],
        },
        request_id="req-1",
    )

    assert result["created"] is True
    assert result["odoo_sale_order_id"] == 1001
    created = state.created_sale_orders[0]
    assert created["client_order_ref"] == "ORDER-1"
    assert created["partner_id"] == 1
    line = created["order_line"][0][2]
    assert line["product_id"] == 100
    assert line["product_uom_qty"] == 3
    assert line["price_unit"] == 1299.0


def test_create_sale_order_creates_partner_when_missing() -> None:
    state = FakeOdooState()
    adapter = make_adapter(state)

    adapter.create_sale_order(
        {
            "marketplace_order_id": "ORDER-2",
            "retailer_ref": "RTL-NEW",
            "retailer_name": "New Co",
            "retailer_email": "new@example.test",
            "lines": [{"sku": "DEMO-SKU-001", "quantity": 1, "unit_price": {"amount_minor": 100, "currency": "USD"}}],
        },
        request_id="req-1",
    )

    created_partner = state.partners[state._next_partner]
    assert created_partner["ref"] == "RTL-NEW"
    assert created_partner["customer_rank"] == 1
    so = state.created_sale_orders[0]
    assert so["partner_id"] == state._next_partner


def test_create_sale_order_is_idempotent_by_client_order_ref() -> None:
    state = FakeOdooState()
    adapter = make_adapter(state)

    order = {
        "marketplace_order_id": "ORDER-3",
        "retailer_ref": "DEMO-RTL-001",
        "lines": [{"sku": "DEMO-SKU-001", "quantity": 2, "unit_price": {"amount_minor": 100, "currency": "USD"}}],
    }
    first = adapter.create_sale_order(order, request_id="req-1")
    second = adapter.create_sale_order(order, request_id="req-2")

    assert first["created"] is True
    assert second["created"] is False
    assert first["odoo_sale_order_id"] == second["odoo_sale_order_id"]
    assert len(state.created_sale_orders) == 1


def test_same_retailer_two_orders_reuse_single_partner() -> None:
    state = FakeOdooState()
    adapter = make_adapter(state)

    base = {
        "retailer_ref": "DEMO-RTL-001",
        "retailer_name": "Demo Retailer",
        "retailer_email": "r@example.test",
        "lines": [
            {"sku": "DEMO-SKU-001", "quantity": 1, "unit_price": {"amount_minor": 100, "currency": "USD"}},
        ],
    }
    first = adapter.create_sale_order({**base, "marketplace_order_id": "ORDER-A"}, request_id="req-1")
    second = adapter.create_sale_order({**base, "marketplace_order_id": "ORDER-B"}, request_id="req-2")

    assert first["odoo_partner_id"] == 1
    assert second["odoo_partner_id"] == 1
    assert first["odoo_partner_ref"] == "DEMO-RTL-001"
    partners_with_ref = [p for p in state.partners.values() if p.get("ref") == "DEMO-RTL-001"]
    assert len(partners_with_ref) == 1


def test_create_sale_order_unknown_sku_raises_not_found() -> None:
    adapter = make_adapter(FakeOdooState())
    with pytest.raises(ResourceNotFoundError):
        adapter.create_sale_order(
            {
                "marketplace_order_id": "ORDER-4",
                "retailer_ref": "DEMO-RTL-001",
                "lines": [{"sku": "DEMO-SKU-NOPE", "quantity": 1, "unit_price": {"amount_minor": 100, "currency": "USD"}}],
            },
            request_id="req-1",
        )


def test_rpc_error_raises_upstream_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": 1, "error": {"code": 2, "message": "boom"}},
        )

    adapter = HttpOdooAdapter(
        base_url="http://odoo.test",
        db="shopstore_odoo",
        username="admin",
        password="secret",
        client=UnifiedHttpClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(UpstreamError):
        adapter.health_check(request_id="req-1")


def test_amount_minor_to_float() -> None:
    assert amount_minor_to_float(129900, "USD") == 1299.0
    assert amount_minor_to_float(500, "JPY") == 500.0
    assert amount_minor_to_float(50, "USD") == 0.5


class DeliveryState:
    """get_delivery_for_sale_order 的内存替身：sale.order.picking_ids + stock.picking。"""

    def __init__(self) -> None:
        self.sale_orders: dict[int, dict] = {1: {"id": 1, "picking_ids": [10, 11]}}
        self.pickings: dict[int, dict] = {
            10: {"id": 10, "state": "done", "name": "WH/OUT/00001", "picking_type_id": (5, "Deliveries")},
            11: {"id": 11, "state": "assigned", "name": "WH/INT/00001", "picking_type_id": (6, "Internal")},
        }
        self.picking_types: dict[int, str] = {5: "outgoing", 6: "internal"}

    def _search(self, model: str, domain: list, limit: int) -> list[int]:
        if model == "sale.order":
            ids = list(self.sale_orders.keys())
            for field, op, value in domain:
                if op == "=":
                    ids = [i for i in ids if self.sale_orders[i].get(field) == value]
            return ids[:limit] if limit else ids
        if model == "stock.picking":
            ids = list(self.pickings.keys())
            for field, op, value in domain:
                if field == "id" and op == "in":
                    ids = [i for i in ids if i in value]
                elif field == "picking_type_id.code" and op == "=":
                    ids = [
                        i
                        for i in ids
                        if self.picking_types.get(self.pickings[i]["picking_type_id"][0]) == value
                    ]
            return ids[:limit] if limit else ids
        raise RuntimeError(f"unknown model {model}")

    def _read(self, model: str, ids: list[int], fields: list[str]) -> list[dict]:
        collection = {"sale.order": self.sale_orders, "stock.picking": self.pickings}[model]
        return [{f: collection[i][f] for f in fields} for i in ids]


def make_delivery_client(state: DeliveryState) -> UnifiedHttpClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        params = body["params"]
        if params["service"] == "common" and params["method"] == "authenticate":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": 2})
        if params["service"] == "object" and params["method"] == "execute_kw":
            _db, _uid, _pwd, model, method, margs, kwargs = params["args"]
            if method == "search":
                result = state._search(model, margs[0], kwargs.get("limit", 0))
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
            if method == "read":
                result = state._read(model, margs[0], margs[1])
                return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": None})

    return UnifiedHttpClient(transport=httpx.MockTransport(handler))


def make_delivery_adapter(state: DeliveryState) -> HttpOdooAdapter:
    return HttpOdooAdapter(
        base_url="http://odoo.test",
        db="shopstore_odoo",
        username="admin",
        password="secret",
        client=make_delivery_client(state),
    )


def test_get_delivery_for_sale_order_resolves_outgoing_picking() -> None:
    state = DeliveryState()
    adapter = make_delivery_adapter(state)

    result = adapter.get_delivery_for_sale_order(1, request_id="req-1")

    assert result == {"odoo_sale_order_id": 1, "odoo_delivery_id": 10, "status": "done"}


def test_get_delivery_for_sale_order_returns_none_without_picking() -> None:
    state = DeliveryState()
    state.sale_orders = {2: {"id": 2, "picking_ids": []}}
    adapter = make_delivery_adapter(state)

    assert adapter.get_delivery_for_sale_order(2, request_id="req-1") is None


def test_get_delivery_for_sale_order_unknown_sale_order_raises_not_found() -> None:
    adapter = make_delivery_adapter(DeliveryState())
    with pytest.raises(ResourceNotFoundError):
        adapter.get_delivery_for_sale_order(999, request_id="req-1")
