# -*- coding: utf-8 -*-
"""ISSUE-0004 login / reachability check over XML-RPC.

Checks:
  - Odoo XML-RPC endpoint reachable
  - admin login works
  - warehouse login works

Env: ODOO_DB_NAME, ODOO_TEST_USER_PASSWORD, ODOO_HTTP_PORT (host side).
Exit code 0 when all pass, 1 otherwise.
"""

import os
import sys
import urllib.request
import xmlrpc.client

db = os.environ.get('ODOO_DB_NAME', 'shopstore_odoo')
pwd = os.environ.get('ODOO_TEST_USER_PASSWORD', '')
port = os.environ.get('ODOO_HTTP_PORT', '8069')
url = 'http://127.0.0.1:%s' % port

failures = []

try:
    req = urllib.request.urlopen('%s/web/login' % url, timeout=10)
    if req.status == 200:
        print('[PASS] Odoo web UI reachable at %s/web/login' % url)
    else:
        failures.append('web-ui')
        print('[FAIL] Odoo web UI - HTTP %s' % req.status)
except Exception as exc:  # noqa: BLE001
    failures.append('web-ui')
    print('[FAIL] Odoo web UI reachable - %s' % exc)

try:
    common = xmlrpc.client.ServerProxy('%s/xmlrpc/2/common' % url)
    version = common.version()
    print('[PASS] Odoo XML-RPC reachable at %s (%s)' % (url, version.get('server_version', '?')))
except Exception as exc:  # noqa: BLE001
    print('[FAIL] Odoo XML-RPC reachable - %s' % exc)
    sys.exit(1)

if not pwd or pwd in ('change_me', 'change_me_in_env_file'):
    print('[FAIL] ODOO_TEST_USER_PASSWORD is not configured')
    sys.exit(1)

for login in ('admin', 'warehouse'):
    try:
        models = xmlrpc.client.ServerProxy('%s/xmlrpc/2/object' % url)
        uid = common.authenticate(db, login, pwd, {})
        if uid:
            print('[PASS] login %s works (uid=%s)' % (login, uid))
        else:
            failures.append(login)
            print('[FAIL] login %s rejected' % login)
    except Exception as exc:  # noqa: BLE001
        failures.append(login)
        print('[FAIL] login %s - %s' % (login, exc))

if failures:
    sys.exit(1)
print('[login-check] all PASS')
