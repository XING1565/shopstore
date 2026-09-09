# syntax=docker/dockerfile:1
# Phase-0 WordPress + WooCommerce runtime image (config / ISSUE-0003).
# Base tag comes from apps/woo/.env WORDPRESS_VERSION via compose build args
# (see apps/woo/compose.yaml). Version freeze: docs/版本清单.md (ISSUE-0002).
ARG WORDPRESS_BASE_IMAGE=wordpress:6.9-php8.3-apache
FROM ${WORDPRESS_BASE_IMAGE}

ARG WOOCOMMERCE_VERSION=10.8.0
ENV WOOCOMMERCE_VERSION=${WOOCOMMERCE_VERSION}

# wp-cli: used by provisioning and available for day-2 debugging.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl less; \
    a2enmod rewrite expires; \
    curl -fsSL -o /usr/local/bin/wp \
      https://raw.githubusercontent.com/wp-cli/builds/gh-pages/phar/wp-cli.phar; \
    chmod +x /usr/local/bin/wp; \
    rm -rf /var/lib/apt/lists/*

# Bootstrapping scripts (entrypoint wraps the stock one; provisioning is
# idempotent and converges on every start, so no manual in-container edits).
COPY entrypoint.sh /usr/local/bin/woo-entrypoint.sh
COPY provision.sh /usr/local/bin/woo-provision.sh
RUN chmod +x /usr/local/bin/woo-entrypoint.sh /usr/local/bin/woo-provision.sh

WORKDIR /var/www/html
ENTRYPOINT ["/usr/local/bin/woo-entrypoint.sh"]
