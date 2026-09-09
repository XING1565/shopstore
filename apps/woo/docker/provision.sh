#!/usr/bin/env bash
#
# Phase-0 idempotent WordPress + WooCommerce provisioning (config / ISSUE-0003).
# Runs at every container start; every step is a no-op once already applied, so
# re-runs change nothing. All inputs come from environment (.env), never from
# files edited inside the container.
#
# Owned configuration it applies:
#   - WordPress core install / site URL (WOO_BASE_URL)
#   - WooCommerce plugin install + activation (pinned WOOCOMMERCE_VERSION)
#   - store settings (currency/region/no-payment checkout baseline)
#   - WooCommerce core pages (shop/cart/checkout/my-account)
#   - test administrator + test buyer accounts (WOO_*)
#   - base product test data (DEMO-SKU-001/002)
set -euo pipefail

WP=(wp --allow-root --path=/var/www/html)

log()  { echo "[woo-provision] $*"; }
fail() { echo "[woo-provision] ERROR: $*" >&2; exit 1; }

# ---- defaults (mirror infra/env/woo.env.example) ----
: "${WOO_BASE_URL:=http://localhost:8080}"
: "${WOO_SITE_TITLE:=Shopstore Demo}"
: "${WOO_ADMIN_USER:=woo_admin}"
: "${WOO_ADMIN_PASSWORD:=change_me_in_env_file}"
: "${WOO_ADMIN_EMAIL:=admin@example.test}"
: "${WOO_BUYER_USERNAME:=retailer_demo}"
: "${WOO_BUYER_PASSWORD:=change_me_in_env_file}"
: "${WOO_BUYER_EMAIL:=retailer_demo@example.test}"
: "${WOOCOMMERCE_VERSION:=10.8.0}"

cd /var/www/html

# Wait for MySQL (defensive: compose already waits for db healthcheck).
db_ready=0
for _ in $(seq 1 60); do
  if "${WP[@]}" db check >/dev/null 2>&1; then
    db_ready=1
    break
  fi
  sleep 2
done
[ "$db_ready" -eq 1 ] || fail "database not reachable after 120s (check WP_DB_* and apps/woo/.env)"

# ---- 1) WordPress core ----
if ! "${WP[@]}" core is-installed >/dev/null 2>&1; then
  log "installing WordPress core (siteurl=$WOO_BASE_URL)"
  "${WP[@]}" core install \
    --url="$WOO_BASE_URL" \
    --title="$WOO_SITE_TITLE" \
    --admin_user="$WOO_ADMIN_USER" \
    --admin_password="$WOO_ADMIN_PASSWORD" \
    --admin_email="$WOO_ADMIN_EMAIL" \
    --skip-email
else
  log "WordPress core already installed"
fi

# Site URL is a managed option, converged every boot.
"${WP[@]}" option update home "$WOO_BASE_URL" >/dev/null
"${WP[@]}" option update siteurl "$WOO_BASE_URL" >/dev/null
"${WP[@]}" option update blogname "$WOO_SITE_TITLE" >/dev/null

# Pretty permalinks (required by WooCommerce shop/cart/checkout URLs).
"${WP[@]}" rewrite structure '/%postname%/' --hard >/dev/null 2>&1 || true

# ---- 2) WooCommerce plugin (pinned; install only on first boot) ----
if "${WP[@]}" plugin is-active woocommerce >/dev/null 2>&1; then
  log "WooCommerce is active"
else
  if "${WP[@]}" plugin is-installed woocommerce >/dev/null 2>&1; then
    log "activating WooCommerce"
    "${WP[@]}" plugin activate woocommerce >/dev/null
  else
    log "installing WooCommerce $WOOCOMMERCE_VERSION (first boot; downloads from wordpress.org)"
    "${WP[@]}" plugin install woocommerce --version="$WOOCOMMERCE_VERSION" --activate >/dev/null
  fi
fi

# Skip the onboarding wizard / first-activation redirect.
"${WP[@]}" option update woocommerce_onboarding_opt_in no >/dev/null 2>&1 || true
"${WP[@]}" option delete _wc_activation_redirect >/dev/null 2>&1 || true

# ---- 3) Store settings / pages / products (config-owned data under apps/woo/config) ----
if [ -f /woo-config/woo-options.php ]; then
  "${WP[@]}" eval-file /woo-config/woo-options.php
fi
if [ -f /woo-config/woo-pages.php ]; then
  "${WP[@]}" eval-file /woo-config/woo-pages.php
fi
if [ -f /woo-config/seed-products.php ]; then
  "${WP[@]}" eval-file /woo-config/seed-products.php
fi

# ---- 4) Test accounts: converge to .env so documented credentials always work ----
ensure_user() {
  local login="$1" email="$2" role="$3" pass="$4"
  local uid
  uid="$("${WP[@]}" user get "$login" --field=ID 2>/dev/null || true)"
  if [ -z "$uid" ]; then
    log "creating user $login (role=$role)"
    "${WP[@]}" user create "$login" "$email" --role="$role" --user_pass="$pass" >/dev/null
  else
    "${WP[@]}" user update "$login" --user_email="$email" --role="$role" --user_pass="$pass" >/dev/null
  fi
}
ensure_user "$WOO_ADMIN_USER" "$WOO_ADMIN_EMAIL" administrator "$WOO_ADMIN_PASSWORD"
ensure_user "$WOO_BUYER_USERNAME" "$WOO_BUYER_EMAIL" customer "$WOO_BUYER_PASSWORD"

# ---- 5) Flush rewrites after pages/products exist ----
"${WP[@]}" rewrite flush --hard >/dev/null 2>&1 || true

# Files created as root must be readable/writable by www-data (apache).
# Only touch paths inside the writable web-data volume (skip ro/bind mounts).
if [ "$(id -u)" = "0" ]; then
  mkdir -p /var/www/html/wp-content/uploads
  chown -R www-data:www-data \
    /var/www/html/wp-content/uploads \
    /var/www/html/wp-content/plugins/woocommerce 2>/dev/null || true
fi

log "provisioning complete"
