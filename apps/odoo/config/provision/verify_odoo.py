# -*- coding: utf-8 -*-
"""ISSUE-0004 acceptance verification (idempotent).

Prints one [PASS]/[FAIL] per acceptance check. Running it again after a clean
provision is a no-op: the demo sale order SO-DEMO-001 is created/confirmed only
once, then reused.

Checks map to CESH-24 acceptance criteria:
  - Odoo reachable / admin & warehouse login ........ done out-of-band by login_check.py
  - Sales + Inventory modules installed
  - default warehouse + base stock locations exist
  - company configured
  - test customer / supplier exist
  - products have unique SKU
  - initial stock on hand
  - can create a test sale order
  - can generate a delivery order from the sale order
"""

RESULTS = []


def check(label, ok, detail=''):
    RESULTS.append((label, ok, detail))
    print('[%s] %s%s' % ('PASS' if ok else 'FAIL', label, (' - ' + detail) if detail else ''))


def main(env):
    Modules = env['ir.module.module'].sudo()
    states = {m.name: m.state for m in Modules.search([('name', 'in', ['sale', 'stock', 'sale_stock'])])}
    for mod in ('sale', 'stock'):
        check('module %s installed' % mod, states.get(mod) == 'installed', states.get(mod, 'missing'))

    Company = env['res.company'].sudo()
    company = Company.search([('name', '=', 'ShopStore Demo Co')], limit=1)
    check('company ShopStore Demo Co exists', bool(company))

    Wh = env['stock.warehouse'].sudo()
    wh = Wh.search([('code', '=', 'WH')], limit=1)
    check('default warehouse WH exists', bool(wh))
    if wh:
        check('warehouse WH 1-step delivery (ship_only)', wh.delivery_steps == 'ship_only', wh.delivery_steps)
        locs = [wh.lot_stock_id, wh.wh_input_stock_loc_id, wh.wh_output_stock_loc_id]
        for loc in locs:
            check('stock location %s exists' % (loc.complete_name if loc else '?'), bool(loc))

    Partner = env['res.partner'].sudo()
    check('customer DEMO-RTL-001 exists', bool(Partner.search([('ref', '=', 'DEMO-RTL-001')], limit=1)))
    check('supplier DEMO-SUP-001 exists', bool(Partner.search([('ref', '=', 'DEMO-SUP-001')], limit=1)))

    Users = env['res.users'].sudo()
    check('user admin exists', bool(Users.search([('login', '=', 'admin')], limit=1)))
    check('user warehouse exists', bool(Users.search([('login', '=', 'warehouse')], limit=1)))

    Pt = env['product.template'].sudo()
    expected = {'DEMO-SKU-001': 120.0, 'DEMO-SKU-002': 80.0}
    Quant = env['stock.quant'].sudo()
    products = {}
    for sku, qty in expected.items():
        tmpls = Pt.search([('default_code', '=', sku)])
        check('product %s exists with unique SKU' % sku, len(tmpls) == 1, 'found=%d' % len(tmpls))
        if tmpls:
            variant = tmpls[:1].product_variant_ids[:1]
            products[sku] = variant
            on_hand = 0.0
            if variant and wh:
                loc = wh.lot_stock_id
                on_hand = sum(q.quantity for q in Quant.search([
                    ('product_id', '=', variant.id),
                    ('location_id', '=', loc.id),
                ]))
            check('initial stock %s >= %s at WH/Stock' % (sku, qty), on_hand >= qty, 'on_hand=%.1f' % on_hand)

    # Demo sale order + delivery order generation (idempotent).
    customer = Partner.search([('ref', '=', 'DEMO-RTL-001')], limit=1)
    so_demo = env['sale.order'].sudo().search([('name', '=', 'SO-DEMO-001')], limit=1)
    if not so_demo:
        line_vals = []
        order = 10
        for sku, variant in products.items():
            if variant:
                price = 10.0 if sku == 'DEMO-SKU-001' else 25.0
                qty = 2.0 if sku == 'DEMO-SKU-001' else 1.0
                line_vals.append((0, 0, {
                    'sequence': order,
                    'product_id': variant.id,
                    'name': variant.name,
                    'product_uom_qty': qty,
                    'price_unit': price,
                }))
                order += 10
        so_demo = env['sale.order'].sudo().create({
            'name': 'SO-DEMO-001',
            'partner_id': customer.id if customer else False,
            'partner_invoice_id': customer.id if customer else False,
            'partner_shipping_id': customer.id if customer else False,
            'order_line': line_vals,
        })
        so_demo.action_confirm()
        check('test sale order SO-DEMO-001 confirmed', so_demo.state == 'sale', so_demo.state)
    else:
        check('test sale order SO-DEMO-001 confirmed', so_demo.state in ('sale', 'done'), so_demo.state)

    pickings = so_demo.picking_ids.filtered(lambda p: p.picking_type_id.code == 'outgoing')
    check('delivery order generated from SO-DEMO-001', len(pickings) >= 1, 'pickings=%d' % len(pickings))
    if pickings:
        for pk in pickings:
            check('delivery %s state' % pk.name, pk.state in ('assigned', 'confirmed', 'done'), pk.state)

    env.cr.commit()
    print('[verify] %d PASS / %d FAIL' % (len([r for r in RESULTS if r[1]]), len([r for r in RESULTS if not r[1]])))


main(env)
