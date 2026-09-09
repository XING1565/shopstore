<?php
/**
 * Phase-0 canonical marketplace test data for WooCommerce (config / ISSUE-0008).
 *
 * Owner: config. Loaded via `wp eval-file /woo-config/seed-test-data.php` by
 * docker/provision.sh. Idempotent: every record is keyed by a unique identifier
 * (username / term slug), so re-running never duplicates data.
 *
 * What it seeds (canonical set from packages/test-data/*.json):
 *   - retailer accounts: retailer_pending / retailer_approved (role customer)
 *   - brand: "Demo Brand A" as a WooCommerce product category (phase-0
 *     representation until marketplace-bridge provides a brand taxonomy)
 *   - attaches DEMO-SKU-001 / DEMO-SKU-002 to that brand
 *
 * Credentials NEVER live in the repo: passwords come from the environment
 * (WOO_RETAILER_PASSWORD, see infra/env/woo.env.example).
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

function ss_seed_log( $message, $type = 'log' ) {
	if ( defined( 'WP_CLI' ) && WP_CLI ) {
		if ( 'success' === $type ) {
			WP_CLI::success( $message );
		} elseif ( 'warning' === $type ) {
			WP_CLI::warning( $message );
		} else {
			WP_CLI::log( $message );
		}
	}
}

if ( ! function_exists( 'wc_get_product_id_by_sku' ) ) {
	ss_seed_log( 'WooCommerce not active yet; skipping marketplace test-data seed.', 'warning' );
	return;
}

// ---- 1) brand: ensure product category "Demo Brand A" ----
$brand_name = 'Demo Brand A';
$brand_slug = 'demo-brand-a';
$term       = get_term_by( 'slug', $brand_slug, 'product_cat' );
if ( ! $term ) {
	$created = wp_insert_term( $brand_name, 'product_cat', array( 'slug' => $brand_slug ) );
	if ( is_wp_error( $created ) ) {
		ss_seed_log( 'failed to create brand category: ' . $created->get_error_message(), 'warning' );
	} else {
		ss_seed_log( sprintf( 'created brand category %s (slug=%s)', $brand_name, $brand_slug ), 'success' );
		$term = get_term_by( 'slug', $brand_slug, 'product_cat' );
	}
}
$term_id = ( $term && ! is_wp_error( $term ) ) ? (int) $term->term_id : 0;

// ---- 2) attach canonical DEMO products to the brand ----
$canonical_skus = array( 'DEMO-SKU-001', 'DEMO-SKU-002' );
foreach ( $canonical_skus as $sku ) {
	$product_id = wc_get_product_id_by_sku( $sku );
	if ( ! $product_id ) {
		ss_seed_log( sprintf( 'product %s not found; skipping brand attach', $sku ) );
		continue;
	}
	if ( $term_id ) {
		wp_set_object_terms( $product_id, (int) $term_id, 'product_cat', true );
		ss_seed_log( sprintf( 'attached %s to %s (product_id=%d)', $sku, $brand_name, $product_id ), 'success' );
	}
}

// ---- 3) retailer (buyer) customer accounts ----
$retailer_password = getenv( 'WOO_RETAILER_PASSWORD' );
if ( false === $retailer_password || '' === $retailer_password ) {
	$retailer_password = 'change_me_in_env_file';
}

$retailers = array(
	array(
		'username' => 'retailer_pending',
		'email'    => 'retailer_pending@example.test',
	),
	array(
		'username' => 'retailer_approved',
		'email'    => 'retailer_approved@example.test',
	),
);

foreach ( $retailers as $retailer ) {
	$user = get_user_by( 'login', $retailer['username'] );
	if ( ! $user ) {
		$user = get_user_by( 'email', $retailer['email'] );
	}
	if ( ! $user ) {
		$user_id = wp_insert_user( array(
			'user_login' => $retailer['username'],
			'user_email' => $retailer['email'],
			'user_pass'  => $retailer_password,
			'role'       => 'customer',
			'display_name' => $retailer['username'],
		) );
		if ( is_wp_error( $user_id ) ) {
			ss_seed_log( sprintf( 'failed to create retailer %s: %s', $retailer['username'], $user_id->get_error_message() ), 'warning' );
			continue;
		}
		ss_seed_log( sprintf( 'created retailer customer %s (%s)', $retailer['username'], $retailer['email'] ), 'success' );
	} else {
		wp_update_user( array(
			'ID'         => $user->ID,
			'user_email' => $retailer['email'],
			'user_pass'  => $retailer_password,
			'role'       => 'customer',
		) );
		ss_seed_log( sprintf( 'retailer customer already exists (username=%s, id=%d); converged', $retailer['username'], $user->ID ) );
	}
}
