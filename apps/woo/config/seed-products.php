<?php
/**
 * Phase-0 base product test data (config / ISSUE-0003).
 *
 * Owner: config. Loaded via `wp eval-file /woo-config/seed-products.php` by
 * docker/provision.sh. Idempotent: products are keyed by SKU, so re-running
 * never duplicates them. SKU namespace per docs/命名规范.md (DEMO-SKU-###).
 * Canonical full test dataset (brands, retailer accounts, Odoo stock) lands in
 * ISSUE-0008; this file stays the minimal Woo bootstrap set.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

if ( ! function_exists( 'wc_get_product_id_by_sku' ) ) {
	if ( defined( 'WP_CLI' ) && WP_CLI ) {
		WP_CLI::warning( 'WooCommerce not active yet; skipping base product seed.' );
	}
	return;
}

$products = array(
	array(
		'sku'         => 'DEMO-SKU-001',
		'name'        => 'Demo Product A',
		'description' => 'Phase-0 基础商品（WooCommerce 演示）。完整测试数据见 ISSUE-0008。',
		'regular_price' => '199.00',
	),
	array(
		'sku'         => 'DEMO-SKU-002',
		'name'        => 'Demo Product B',
		'description' => 'Phase-0 基础商品（WooCommerce 演示）。完整测试数据见 ISSUE-0008。',
		'regular_price' => '399.00',
	),
);

foreach ( $products as $item ) {
	$existing = wc_get_product_id_by_sku( $item['sku'] );
	if ( $existing ) {
		if ( defined( 'WP_CLI' ) && WP_CLI ) {
			WP_CLI::log( sprintf( 'product already exists (sku=%s, id=%d); skip', $item['sku'], $existing ) );
		}
		continue;
	}

	$product = new WC_Product_Simple();
	$product->set_name( $item['name'] );
	$product->set_sku( $item['sku'] );
	$product->set_regular_price( $item['regular_price'] );
	$product->set_description( $item['description'] );
	$product->set_status( 'publish' );
	$product->save();

	if ( defined( 'WP_CLI' ) && WP_CLI ) {
		WP_CLI::success( sprintf( 'created product (sku=%s, id=%d)', $item['sku'], $product->get_id() ) );
	}
}
