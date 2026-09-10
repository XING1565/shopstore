# -*- coding: utf-8 -*-
"""Odoo base environment + canonical test data - idempotent provisioning.

Runs inside `odoo shell` (see apps/odoo/config/README.md / provision/run.ps1).
Idempotency contract: safe to re-run; re-running changes nothing when the
target state already exists. Reset = re-create the database, never rely on
manual undo.

Target state (local demo, no real data):
  - company        ShopStore Demo Co
  - warehouse      WH (1-step delivery: ship_only)
  - locations      WH/Stock, WH/Input, WH/Output (auto-created by warehouse)
  - customers      Demo Retailer (Approved) ref DEMO-RTL-001 (retailer_approved@example.test)
                   Demo Retailer (Pending)  ref DEMO-RTL-002 (retailer_pending@example.test)
  - vendor         Demo Supplier              ref DEMO-SUP-001
  - products       DEMO-SKU-001 / DEMO-SKU-002 (storable, sale_ok, unique SKU)
  - initial stock  DEMO-SKU-001: 120, DEMO-SKU-002: 80 at WH/Stock
  - users          admin (system), warehouse (Inventory User)

Stage 1 (ISSUE-0106) adds the mapping guarantees ISSUE-0107 relies on:
  - partner mapping  res.partner.ref        == Core retailer external id (e.g. DEMO-RTL-001)
                     res.partner.customer_rank >= 1 so sale orders can use them
  - SKU mapping      product.product.default_code == Core/Woo SKU (unique)
  - order mapping    sale.order.client_order_ref == Core marketplace_order_id (idempotency key)
  - delivery flow    confirm SO -> outgoing picking generated -> validate = shipped
  The canonical rules live in apps/odoo/config/mapping/odoo_mapping.rules.json
  and are documented in apps/odoo/config/MAPPING.md.

Env (set on the odoo container, from apps/odoo/config/docker/.env):
  ODOO_DB_NAME, ODOO_TEST_USER_PASSWORD
"""

import os

PRODUCTS = [
    # (sku, display name, initial on-hand qty at WH/Stock)
    ('DEMO-SKU-001', 'Demo Product A - White Ceramic Mug', 120.0),
    ('DEMO-SKU-002', 'Demo Product B - Canvas Tote Bag', 80.0),
]


def info(msg):
    print('[provision] %s' % msg)


def require_module(env, name):
    mod = env['ir.module.module'].sudo().search([('name', '=', name)], limit=1)
    if not mod or mod.state != 'installed':
        raise RuntimeError('module %s is not installed; run DB init with -i sale,stock first' % name)
    return mod


def get_or_create(env, model, domain, vals):
    rec = env[model].sudo().search(domain, limit=1)
    if not rec:
        rec = env[model].sudo().create(vals)
        info('created %s %s' % (model, rec.id))
    else:
        info('exists %s %s' % (model, rec.id))
    return rec


def configure_company(env):
    Company = env['res.company'].sudo()
    company = Company.search([], order='id', limit=1)
    if not company:
        company = Company.create({'name': 'ShopStore Demo Co'})
    if company.name != 'ShopStore Demo Co':
        company.write({'name': 'ShopStore Demo Co'})
        info('renamed main company to ShopStore Demo Co')
    else:
        info('main company already ShopStore Demo Co (id=%s)' % company.id)
    return company


def configure_warehouse(env, company):
    Wh = env['stock.warehouse'].sudo()
    wh = Wh.search([('company_id', '=', company.id)], order='id', limit=1)
    if not wh:
        wh = Wh.create({'name': 'WH', 'code': 'WH', 'company_id': company.id})
    vals = {'delivery_steps': 'ship_only'}
    if wh.name != company.name:
        vals['name'] = company.name
    wh.write(vals)
    info('warehouse %s (code=%s) delivery_steps=%s' % (wh.name, wh.code, wh.delivery_steps))
    return wh


def configure_sales_delivery(env, company, wh):
    """Ensure Sales + Inventory + Delivery support the 1-step fulfilment flow.

    Stage 1 flow (ISSUE-0106 acceptance):
      create+confirm sale order -> outgoing delivery picking generated
      -> warehouse validates the picking = shipped.

    With ``delivery_steps == 'ship_only'`` Odoo creates the outgoing picking
    directly in WH/Stock -> Customers. This function pins that contract and
    fails loudly if the warehouse's picking type is not laid out that way.
    """
    PickingType = env['stock.picking.type'].sudo()
    outgoing = PickingType.search([
        ('code', '=', 'outgoing'),
        ('warehouse_id', '=', wh.id),
    ], limit=1)
    if not outgoing:
        raise RuntimeError('no outgoing picking type on warehouse %s' % wh.code)
    stock_loc = wh.lot_stock_id
    if not stock_loc:
        raise RuntimeError('warehouse %s has no stock location' % wh.code)
    if outgoing.default_location_src_id != stock_loc:
        raise RuntimeError(
            'outgoing picking type source is %s, expected %s'
            % (outgoing.default_location_src_id.complete_name, stock_loc.complete_name)
        )
    info('sales/delivery ready: outgoing=%s src=%s dst=%s' % (
        outgoing.name,
        outgoing.default_location_src_id.complete_name,
        outgoing.default_location_dest_id.complete_name,
    ))
    return outgoing


def configure_users(env, company):
    Users = env['res.users'].sudo()
    demo_pwd = os.environ.get('ODOO_TEST_USER_PASSWORD', '')
    if not demo_pwd or demo_pwd == 'change_me' or demo_pwd == 'change_me_in_env_file':
        raise RuntimeError('ODOO_TEST_USER_PASSWORD is not configured in .env')

    admin = Users.search([('login', '=', 'admin')], limit=1)
    if not admin:
        raise RuntimeError('built-in admin user not found')
    admin.write({'password': demo_pwd})
    info('admin user ready (login=admin)')

    warehouse = Users.search([('login', '=', 'warehouse')], limit=1)
    if not warehouse:
        warehouse = Users.create({
            'name': 'Warehouse User',
            'login': 'warehouse',
            'email': 'warehouse@example.test',
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [(6, 0, [
                env.ref('base.group_user').id,
                env.ref('stock.group_stock_user').id,
            ])],
        })
    warehouse.write({
        'password': demo_pwd,
        'group_ids': [(4, env.ref('base.group_user').id), (4, env.ref('stock.group_stock_user').id)],
    })
    info('warehouse user ready (login=warehouse)')
    return admin, warehouse


CUSTOMERS = [
    # (ref, name, email, customer_rank) - ref is the Core retailer external id.
    ('DEMO-RTL-001', 'Demo Retailer (Approved)', 'retailer_approved@example.test', 1),
    ('DEMO-RTL-002', 'Demo Retailer (Pending)', 'retailer_pending@example.test', 1),
]


def configure_partners(env):
    """Create/ensure the canonical partners used by the marketplace mapping.

    Partner mapping rule (ISSUE-0106 -> ISSUE-0107): a Core retailer maps to
    exactly one ``res.partner`` whose ``ref`` equals the retailer external id.
    ``customer_rank >= 1`` marks it as a sellable customer so a sale order can
    reference it.
    """
    customers = []
    for ref, name, email, rank in CUSTOMERS:
        partner = get_or_create(
            env, 'res.partner',
            [('ref', '=', ref)],
            {
                'name': name,
                'ref': ref,
                'company_type': 'company',
                'email': email,
                'customer_rank': rank,
            },
        )
        # backfill mapping invariants on pre-existing rows (idempotent)
        vals = {}
        if partner.customer_rank < rank:
            vals['customer_rank'] = rank
        if not partner.email:
            vals['email'] = email
        if vals:
            partner.write(vals)
            info('updated partner %s %s' % (ref, vals))
        customers.append(partner)

    vendor = get_or_create(
        env, 'res.partner',
        [('ref', '=', 'DEMO-SUP-001')],
        {
            'name': 'Demo Supplier',
            'ref': 'DEMO-SUP-001',
            'company_type': 'company',
            'email': 'supplier@example.test',
            'supplier_rank': 1,
        },
    )
    return customers, vendor


def ensure_storable_product(env, sku, name):
    Pt = env['product.template'].sudo()
    tmpl = Pt.search([('default_code', '=', sku)], limit=1)
    if not tmpl:
        vals = {
            'name': name,
            'default_code': sku,
            'sale_ok': True,
            'purchase_ok': True,
        }
        if 'is_storable' in Pt._fields:
            vals['is_storable'] = True
        else:
            vals['type'] = 'product'
        tmpl = Pt.create(vals)
        info('created product template %s (sku=%s)' % (tmpl.id, sku))
    else:
        info('product template exists (sku=%s, id=%s)' % (sku, tmpl.id))
        # backfill sellability/storable invariants (idempotent)
        vals = {}
        if not tmpl.sale_ok:
            vals['sale_ok'] = True
        if 'is_storable' in Pt._fields:
            if not tmpl.is_storable:
                vals['is_storable'] = True
        elif tmpl.type == 'service':
            vals['type'] = 'product'
        if vals:
            tmpl.write(vals)
            info('updated product template %s %s' % (sku, vals))
    variant = tmpl.product_variant_ids[:1]
    if not variant:
        raise RuntimeError('no product variant for sku %s' % sku)
    uniques = Pt.search([('default_code', '=', sku)])
    if len(uniques) != 1:
        raise RuntimeError('SKU %s is not unique (%d templates found)' % (sku, len(uniques)))
    return variant


def set_initial_stock(env, product, location, qty):
    Quant = env['stock.quant'].sudo()
    current = sum(q.quantity for q in Quant.search([
        ('product_id', '=', product.id),
        ('location_id', '=', location.id),
    ]))
    if current and current > 0:
        info('SKIP initial stock sku=%s qty already on hand at %s = %s' % (product.default_code, location.complete_name, current))
        return
    quant = Quant.with_context(inventory_mode=True).create({
        'product_id': product.id,
        'location_id': location.id,
        'inventory_quantity': qty,
    })
    quant.action_apply_inventory()
    info('set initial stock sku=%s qty=%s at %s' % (product.default_code, qty, location.complete_name))


def main(env):
    require_module(env, 'sale')
    require_module(env, 'stock')
    company = configure_company(env)
    wh = configure_warehouse(env, company)
    configure_sales_delivery(env, company, wh)
    configure_users(env, company)
    configure_partners(env)

    stock_loc = wh.lot_stock_id
    if not stock_loc:
        raise RuntimeError('no WH/Stock location on warehouse %s' % wh.name)
    info('stock locations: stock=%s input=%s output=%s' % (
        stock_loc.complete_name,
        wh.wh_input_stock_loc_id.complete_name,
        wh.wh_output_stock_loc_id.complete_name,
    ))

    for sku, name, qty in PRODUCTS:
        product = ensure_storable_product(env, sku, name)
        set_initial_stock(env, product, stock_loc, qty)

    env.cr.commit()
    info('provisioning done.')


main(env)
