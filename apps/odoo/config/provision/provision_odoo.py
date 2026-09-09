# -*- coding: utf-8 -*-
"""Odoo base environment + ISSUE-0008 canonical test data - idempotent provisioning.

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
  - products       DEMO-SKU-001 / DEMO-SKU-002 (storable, unique SKU)
  - initial stock  DEMO-SKU-001: 120, DEMO-SKU-002: 80 at WH/Stock
  - users          admin (system), warehouse (Inventory User)

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


def configure_partners(env):
    customer_approved = get_or_create(
        env, 'res.partner',
        [('ref', '=', 'DEMO-RTL-001')],
        {
            'name': 'Demo Retailer (Approved)',
            'ref': 'DEMO-RTL-001',
            'company_type': 'company',
            'email': 'retailer_approved@example.test',
        },
    )
    customer_pending = get_or_create(
        env, 'res.partner',
        [('ref', '=', 'DEMO-RTL-002')],
        {
            'name': 'Demo Retailer (Pending)',
            'ref': 'DEMO-RTL-002',
            'company_type': 'company',
            'email': 'retailer_pending@example.test',
        },
    )
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
    return customer_approved, customer_pending, vendor


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
