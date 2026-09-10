# -*- coding: utf-8 -*-
"""ISSUE-0106 acceptance verification: Sales + Inventory + Delivery mapping & flow.

Runs inside `odoo shell` (see apps/odoo/config/README.md / provision/run.ps1,
action: `fulfill`). Prints one [PASS]/[FAIL] per acceptance check.

Idempotent contract: the demo order SO-DEMO-SHIP-001 is created + confirmed and
its outgoing delivery validated (= shipped) exactly once. Re-running reuses the
already-shipped order and changes nothing.

Checks map to CESH-35 / ISSUE-0106 acceptance criteria:
  - partner mapping rule is usable (res.partner.ref -> exactly one partner)
  - SKU mapping rule is usable (product.product.default_code -> exactly one variant)
  - order mapping rule is usable (sale.order.client_order_ref = idempotency key)
  - can create + confirm a sale order
  - can generate a delivery order from the sale order
  - can complete the shipment (validate the outgoing picking)

The mapping rules themselves are documented in apps/odoo/config/MAPPING.md and
declared in apps/odoo/config/mapping/odoo_mapping.rules.json (consumed by
ISSUE-0107).
"""

ORDER_NAME = 'SO-DEMO-SHIP-001'
MARKETPLACE_ORDER_ID = 'DEMO-MKT-ORDER-001-SHIP'
CUSTOMER_REF = 'DEMO-RTL-001'
SHIP_LINES = [
    # (sku, qty)
    ('DEMO-SKU-001', 1.0),
]

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok, detail))
    print('[%s] %s%s' % ('PASS' if ok else 'FAIL', label, (' - ' + detail) if detail else ''))


def resolve_partner(env, ref):
    return env['res.partner'].sudo().search([('ref', '=', ref)], limit=2)


def resolve_variant(env, sku):
    return env['product.product'].sudo().search([('default_code', '=', sku)], limit=2)


def is_storable(variant):
    tmpl = variant.product_tmpl_id
    if 'is_storable' in tmpl._fields:
        return bool(tmpl.is_storable)
    return tmpl.type == 'product'


def main(env):
    # --- partner mapping rule -------------------------------------------------
    partner = resolve_partner(env, CUSTOMER_REF)
    check('partner mapping: ref %s resolves exactly one partner' % CUSTOMER_REF,
          len(partner) == 1, 'found=%d' % len(partner))
    if partner:
        check('partner mapping: %s is a customer (customer_rank >= 1)' % CUSTOMER_REF,
              partner.customer_rank >= 1, 'customer_rank=%s' % partner.customer_rank)

    # --- SKU mapping rule -----------------------------------------------------
    variants = {}
    for sku, _qty in SHIP_LINES:
        variant = resolve_variant(env, sku)
        check('SKU mapping: default_code %s resolves exactly one variant' % sku,
              len(variant) == 1, 'found=%d' % len(variant))
        if variant:
            check('SKU mapping: %s is storable (deliverable)' % sku,
                  is_storable(variant))
            variants[sku] = variant

    # --- order mapping rule (idempotency key for ISSUE-0107) ------------------
    SaleOrder = env['sale.order'].sudo()
    by_ref = SaleOrder.search([('client_order_ref', '=', MARKETPLACE_ORDER_ID)], limit=2)
    check('order mapping: client_order_ref %s resolves at most one order' % MARKETPLACE_ORDER_ID,
          len(by_ref) <= 1, 'found=%d' % len(by_ref))

    # --- create + confirm sale order -----------------------------------------
    order = by_ref[:1]
    if not order:
        order = SaleOrder.search([('name', '=', ORDER_NAME)], limit=1)
    if not order:
        if not partner or len(variants) != len(SHIP_LINES):
            check('create + confirm sale order %s' % ORDER_NAME, False,
                  'missing partner or variant; run provision first')
            return finish(env)
        line_vals = []
        for seq, (sku, qty) in enumerate(SHIP_LINES, start=1):
            variant = variants[sku]
            line_vals.append((0, 0, {
                'sequence': seq * 10,
                'product_id': variant.id,
                'name': variant.name,
                'product_uom_qty': qty,
                'price_unit': 10.0,
            }))
        order = SaleOrder.create({
            'name': ORDER_NAME,
            'client_order_ref': MARKETPLACE_ORDER_ID,
            'partner_id': partner.id,
            'partner_invoice_id': partner.id,
            'partner_shipping_id': partner.id,
            'order_line': line_vals,
        })
    if order.state == 'draft':
        order.action_confirm()
    check('sale order %s confirmed' % ORDER_NAME, order.state in ('sale', 'done'), order.state)

    # order mapping resolves the order we just used
    resolved = SaleOrder.search([('client_order_ref', '=', MARKETPLACE_ORDER_ID)], limit=2)
    check('order mapping: client_order_ref resolves the confirmed order',
          len(resolved) == 1 and resolved.id == order.id, 'found=%d' % len(resolved))

    # --- delivery order -------------------------------------------------------
    pickings = order.picking_ids.filtered(lambda p: p.picking_type_id.code == 'outgoing')
    check('delivery order generated from %s' % ORDER_NAME, len(pickings) >= 1,
          'pickings=%d' % len(pickings))
    if not pickings:
        return finish(env)

    picking = pickings[:1]
    if picking.state != 'done':
        # full stock is available, so validate fully (no backorder wizard)
        picking.with_context(skip_backorder=True, skip_sms=True).button_validate()
        picking.invalidate_recordset()
    check('shipment completed (delivery %s state done)' % picking.name,
          picking.state == 'done', 'state=%s' % picking.state)
    check('shipment recorded date_done', bool(picking.date_done),
          'date_done=%s' % picking.date_done)

    return finish(env)


def finish(env):
    env.cr.commit()
    passed = len([r for r in RESULTS if r[1]])
    failed = len([r for r in RESULTS if not r[1]])
    print('[fulfill] %d PASS / %d FAIL' % (passed, failed))
    if failed:
        raise SystemExit(1)


main(env)
