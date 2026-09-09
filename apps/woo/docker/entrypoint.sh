#!/usr/bin/env bash
#
# Phase-0 bootstrap entrypoint (config / ISSUE-0003).
#
# The stock WordPress docker-entrypoint.sh only lays down WP core + wp-config.php
# when it is asked to start the server, so we run it in the background (it execs
# apache2-foreground and keeps running), then run our idempotent provisioning
# once the site files are present. Container start therefore requires no manual
# file edits inside the container.
set -euo pipefail

/usr/local/bin/docker-entrypoint.sh apache2-foreground &
wp_pid=$!

forward_term() {
  kill -TERM "$wp_pid" 2>/dev/null || true
}
trap forward_term TERM INT

# Wait for the stock entrypoint to materialise WP (copy + wp-config.php).
for _ in $(seq 1 90); do
  if [ -f wp-config.php ] && [ -f index.php ]; then
    break
  fi
  sleep 1
done

# Idempotent provisioning; failures must not take down the web server, but they
# are logged loudly so a misconfiguration is visible in `docker compose logs`.
if [ -x /usr/local/bin/woo-provision.sh ]; then
  /usr/local/bin/woo-provision.sh \
    || echo "[woo-entrypoint] provisioning FAILED (see logs above); keeping web running" >&2
fi

# Keep the container alive with apache as long as apache lives.
set +e
wait "$wp_pid"
status=$?
exit $status
