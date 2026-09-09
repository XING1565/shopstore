"""Shared configuration and probe helpers for the QA smoke suite (ISSUE-0009).

Owner: qa. This module has no pytest dependency in its import path: it is plain
stdlib (urllib / xmlrpc / subprocess / json) so the suite keeps a single test
dependency (pytest) and behaves the same on Windows and Linux/macOS.

Design rules enforced here (see tests/smoke/README.md):

- Every check reports one of three states: PASS / FAIL / NOT_TESTED.
  NOT_TESTED is never a pass (see :func:`not_tested`).
- A property probe (e.g. "is module X installed?", "does SKU Y exist?") only
  FAILs on the property itself. When its *mechanism* is unavailable (no
  credentials, no docker, service down) it reports NOT_TESTED, and the
  mechanism is guarded by a dedicated must-succeed positive control test so a
  broken probe never masquerades as a real correctness result.
- Write-path probes (persistence after restart) are profile W and are gated by
  :data:`PROFILE` / :data:`TARGET` so they can never run against production.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import xmlrpc.client
from pathlib import Path
from typing import Any, Optional

# --- path layout -----------------------------------------------------------
# tests/smoke/_smoke.py -> REPO_ROOT = parents[2]
REPO_ROOT = Path(__file__).resolve().parents[2]
WOO_COMPOSE = ["-f", "apps/woo/compose.yaml"]
ODOO_COMPOSE = [
    "-f", "apps/odoo/config/docker/compose.yaml",
    "--project-directory", "apps/odoo/config/docker",
]

# --- environment-driven configuration -------------------------------------
# All endpoints/credentials come from the environment, mirroring the repo's
# "no hardcoded env" rule (infra/env/*.env.example). Defaults match local dev.
WOO_BASE_URL = os.environ.get("WOO_BASE_URL", "http://localhost:8080").rstrip("/")
CORE_BASE_URL = os.environ.get("CORE_BASE_URL", "http://localhost:8000").rstrip("/")
ODOO_BASE_URL = os.environ.get("ODOO_BASE_URL", "http://localhost:8069").rstrip("/")

ODOO_DB_NAME = os.environ.get("ODOO_DB_NAME", "shopstore_odoo")
ODOO_SMOKE_USER = os.environ.get("ODOO_SMOKE_USER", "admin")
ODOO_SMOKE_PASSWORD = os.environ.get(
    "ODOO_SMOKE_PASSWORD", os.environ.get("ODOO_TEST_USER_PASSWORD", "")
)

# Optional WooCommerce REST API credentials (stage 0 leaves them unset; when
# present they are the preferred read mechanism for the Woo SKU probe).
WOO_CONSUMER_KEY = os.environ.get("WOO_CONSUMER_KEY", "")
WOO_CONSUMER_SECRET = os.environ.get("WOO_CONSUMER_SECRET", "")

# Profiles. "r" = read-only (default, safe for live/staging parity);
# "w" = write-path (staging ONLY, never production); "all" = both.
PROFILE = os.environ.get("SMOKE_PROFILE", "r").strip().lower()
TARGET = os.environ.get("SMOKE_TARGET", "local").strip().lower()

# When set (e.g. "1"), a run that finishes with any NOT_TESTED check exits
# non-zero so CI cannot silently treat an untested run as green.
STRICT = os.environ.get("SMOKE_STRICT", "").strip() in ("1", "true", "yes", "on")

CANONICAL_SKUS = ("DEMO-SKU-001", "DEMO-SKU-002")

# Global tally of NOT_TESTED checks (read by the sessionfinish hook).
not_tested_count = 0


def not_tested(reason: str) -> None:
    """Report a check as NOT_TESTED and skip it (never recorded as a pass)."""
    global not_tested_count
    not_tested_count += 1
    import pytest

    pytest.skip("NOT_TESTED: " + reason)


def is_production() -> bool:
    return TARGET in ("live", "prod", "production")


def profile_runs_w() -> bool:
    return PROFILE in ("w", "all")


# --- HTTP ---------------------------------------------------------------
def http_get(url: str, timeout: int = 10) -> tuple[Optional[int], bytes, str]:
    """Return ``(status, body, error)``.

    ``status`` is ``None`` when the connection itself failed (service down);
    ``error`` carries a human-readable reason for the failure.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "shopstore-smoke/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read(), ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), "HTTP %s" % exc.code
    except urllib.error.URLError as exc:
        return None, b"", "connection error: %s" % exc.reason
    except Exception as exc:  # noqa: BLE001 - surface any transport failure
        return None, b"", "error: %s" % exc


def http_json(url: str, timeout: int = 10) -> tuple[Optional[int], Any, str]:
    status, body, error = http_get(url, timeout)
    if error or body == b"":
        return status, None, error
    try:
        return status, json.loads(body.decode("utf-8")), ""
    except ValueError as exc:
        return status, None, "invalid JSON: %s" % exc


# --- Odoo XML-RPC ---------------------------------------------------------
class OdooError(Exception):
    """Raised when the Odoo XML-RPC probe mechanism is unavailable."""


def _odoo_common() -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(
        "%s/xmlrpc/2/common" % ODOO_BASE_URL, allow_none=True
    )


def _odoo_models() -> xmlrpc.client.ServerProxy:
    return xmlrpc.client.ServerProxy(
        "%s/xmlrpc/2/object" % ODOO_BASE_URL, allow_none=True
    )


def odoo_credentials_present() -> bool:
    pwd = ODOO_SMOKE_PASSWORD
    return bool(pwd) and pwd not in ("change_me", "change_me_in_env_file", "")


def odoo_authenticate() -> int:
    """Authenticate against Odoo; raise :class:`OdooError` when unavailable."""
    if not odoo_credentials_present():
        raise OdooError(
            "ODOO_SMOKE_PASSWORD / ODOO_TEST_USER_PASSWORD not configured"
        )
    try:
        uid = _odoo_common().authenticate(
            ODOO_DB_NAME, ODOO_SMOKE_USER, ODOO_SMOKE_PASSWORD, {}
        )
    except Exception as exc:  # noqa: BLE001
        raise OdooError("xmlrpc common.authenticate failed: %s" % exc) from exc
    if not uid:
        raise OdooError(
            "authentication rejected for user '%s' on db '%s'"
            % (ODOO_SMOKE_USER, ODOO_DB_NAME)
        )
    return uid


def odoo_execute(model: str, method: str, args: list[Any], kwargs: dict[str, Any] | None = None) -> Any:
    """Execute an Odoo XML-RPC call; raise :class:`OdooError` on mechanism failure."""
    uid = odoo_authenticate()
    try:
        return _odoo_models().execute_kw(
            ODOO_DB_NAME, uid, ODOO_SMOKE_PASSWORD, model, method, args, kwargs or {}
        )
    except Exception as exc:  # noqa: BLE001
        raise OdooError("%s.%s failed: %s" % (model, method, exc)) from exc


def odoo_version() -> dict[str, Any]:
    try:
        return _odoo_common().version()
    except Exception as exc:  # noqa: BLE001
        raise OdooError("xmlrpc common.version failed: %s" % exc) from exc


# --- docker / shell -------------------------------------------------------
def docker_available() -> bool:
    return shutil.which("docker") is not None


def run_docker(args: list[str], timeout: int = 120) -> tuple[int, str, str]:
    """Run a ``docker`` sub-command from the repo root; return (rc, stdout, stderr)."""
    return run_cmd(["docker"] + args, timeout=timeout)


def run_compose(compose_args: list[str], sub: list[str], timeout: int = 120) -> tuple[int, str, str]:
    return run_docker(["compose"] + compose_args + sub, timeout=timeout)


def run_cmd(argv: list[str], timeout: int = 120) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            argv,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return 127, "", "command not found: %s" % argv[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timed out after %ds" % timeout
    except Exception as exc:  # noqa: BLE001
        return 1, "", "error: %s" % exc
    return proc.returncode, proc.stdout, proc.stderr


def woo_sku_ids() -> Optional[set[str]]:
    """Return the set of CANONICAL_SKUS present in Woo, or ``None`` if NOT_TESTED.

    Prefers the WooCommerce REST API when consumer credentials are provided
    (stage 0 leaves them unset); otherwise falls back to `wp` inside the running
    Woo container. Returns ``None`` (NOT_TESTED) when neither mechanism is
    available, rather than failing for the wrong reason.
    """
    if WOO_CONSUMER_KEY and WOO_CONSUMER_SECRET:
        return _woo_sku_ids_via_rest()

    if not docker_available():
        return None

    present: set[str] = set()
    for sku in CANONICAL_SKUS:
        rc, out, _ = run_compose(
            WOO_COMPOSE,
            ["exec", "-T", "woo", "wp", "--allow-root", "--path=/var/www/html",
             "post", "list", "--post_type=product", "--meta_key=_sku",
             "--meta_value=%s" % sku, "--format=count"],
        )
        if rc != 0:
            # wp-cli / container unavailable -> mechanism broken, NOT_TESTED
            return None
        try:
            count = int(out.strip() or "0")
        except ValueError:
            return None
        if count >= 1:
            present.add(sku)
    return present


def _woo_sku_ids_via_rest() -> Optional[set[str]]:
    present: set[str] = set()
    import base64

    token = base64.b64encode(
        ("%s:%s" % (WOO_CONSUMER_KEY, WOO_CONSUMER_SECRET)).encode("utf-8")
    ).decode("ascii")
    for sku in CANONICAL_SKUS:
        url = "%s/wp-json/wc/v3/products?sku=%s&per_page=1" % (WOO_BASE_URL, sku)
        req = urllib.request.Request(
            url, headers={"Authorization": "Basic %s" % token}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if data:
            present.add(sku)
    return present


def wait_for_http(url: str, timeout: int = 90, interval: int = 3) -> bool:
    """Poll ``url`` until it returns a 2xx/3xx status or the timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status, _, _ = http_get(url, timeout=5)
        if status is not None and 200 <= status < 400:
            return True
        time.sleep(interval)
    return False
