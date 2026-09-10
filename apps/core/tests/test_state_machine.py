"""状态机测试：单向推进、非法迁移（含倒退）被拒绝并记录、cancelled / sync_failed 规则。"""

from __future__ import annotations

import pytest

from app.models import Order, OrderStatusEvent, Retailer
from app.models.enums import OrderStatus, RetailerStatus
from app.models.state_machine import InvalidStateTransitionError


def _order(session, status=OrderStatus.draft) -> Order:
    r = Retailer(email="retailer_sm@example.test", company_name="SM Retail")
    session.add(r)
    session.flush()
    o = Order(retailer_id=r.id, status=status)
    session.add(o)
    session.flush()
    return o


def test_order_forward_path_is_allowed(session) -> None:
    o = _order(session)
    path = [
        OrderStatus.submitted,
        OrderStatus.sent_to_odoo,
        OrderStatus.odoo_confirmed,
        OrderStatus.inventory_reserved,
        OrderStatus.picking_ready,
        OrderStatus.shipped,
        OrderStatus.completed,
    ]
    for s in path:
        o.transition_to(s)
    assert o.status is OrderStatus.completed
    assert len(o.status_events) == len(path)


def test_order_backward_transition_rejected(session) -> None:
    o = _order(session, status=OrderStatus.shipped)
    with pytest.raises(InvalidStateTransitionError):
        o.transition_to(OrderStatus.inventory_reserved)
    assert o.status is OrderStatus.shipped


def test_order_cancelled_only_before_shipment_and_terminal(session) -> None:
    o = _order(session, status=OrderStatus.sent_to_odoo)
    o.transition_to(OrderStatus.cancelled)
    assert o.status is OrderStatus.cancelled
    with pytest.raises(InvalidStateTransitionError):
        o.transition_to(OrderStatus.shipped)


def test_order_cannot_cancel_after_shipped(session) -> None:
    o = _order(session, status=OrderStatus.shipped)
    with pytest.raises(InvalidStateTransitionError):
        o.transition_to(OrderStatus.cancelled)


def test_order_sync_failed_records_resume_point_and_recovers(session) -> None:
    o = _order(session, status=OrderStatus.sent_to_odoo)
    o.transition_to(OrderStatus.sync_failed)
    assert o.status is OrderStatus.sync_failed
    assert o.sync_failed_from == OrderStatus.sent_to_odoo.value

    o.transition_to(OrderStatus.sent_to_odoo)
    assert o.status is OrderStatus.sent_to_odoo
    assert o.sync_failed_from is None


def test_order_sync_failed_cannot_resume_to_wrong_state(session) -> None:
    o = _order(session, status=OrderStatus.sent_to_odoo)
    o.transition_to(OrderStatus.sync_failed)
    with pytest.raises(InvalidStateTransitionError):
        o.transition_to(OrderStatus.odoo_confirmed)


def test_status_event_persisted(session) -> None:
    o = _order(session)
    o.transition_to(OrderStatus.submitted, reason="checkout", actor="system")
    session.commit()

    events = session.query(OrderStatusEvent).filter_by(order_id=o.id).all()
    assert len(events) == 1
    assert events[0].from_status == OrderStatus.draft.value
    assert events[0].to_status == OrderStatus.submitted.value
    assert events[0].reason == "checkout"


def test_retailer_approval_state_machine(session) -> None:
    r = Retailer(email="retailer_appr@example.test", company_name="C")
    session.add(r)
    session.flush()
    assert r.status is RetailerStatus.pending

    r.transition_to(RetailerStatus.approved, actor="ops", note="ok")
    assert r.status is RetailerStatus.approved
    assert r.reviewed_by == "ops"
    assert r.reviewed_at is not None


def test_retailer_illegal_transition_rejected(session) -> None:
    r = Retailer(email="retailer_rej@example.test", company_name="D")
    session.add(r)
    session.flush()

    r.transition_to(RetailerStatus.rejected)
    with pytest.raises(InvalidStateTransitionError):
        r.transition_to(RetailerStatus.approved)
    assert r.status is RetailerStatus.rejected
