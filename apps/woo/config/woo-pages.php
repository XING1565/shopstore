<?php
/**
 * Phase-0 WooCommerce core pages (config / ISSUE-0003).
 *
 * Owner: config. Loaded via `wp eval-file /woo-config/woo-pages.php`.
 * Ensures shop / cart / checkout / my-account pages exist and are wired to the
 * matching `woocommerce_*_page_id` options. Idempotent.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$pages = array(
	'woocommerce_shop_page_id'      => array( 'shop',       'Shop',       '' ),
	'woocommerce_cart_page_id'      => array( 'cart',       'Cart',       '[woocommerce_cart]' ),
	'woocommerce_checkout_page_id'  => array( 'checkout',   'Checkout',   '[woocommerce_checkout]' ),
	'woocommerce_myaccount_page_id' => array( 'my-account', 'My Account', '[woocommerce_my_account]' ),
);

foreach ( $pages as $option_key => $def ) {
	list( $slug, $title, $shortcode ) = $def;

	$page_id = (int) get_option( $option_key, 0 );
	$post    = $page_id ? get_post( $page_id ) : null;

	// Existing option but page missing/trashed -> fall through and recreate.
	if ( $post && 'trash' !== $post->post_status ) {
		continue;
	}

	$found = get_posts(
		array(
			'post_type'   => 'page',
			'name'        => $slug,
			'post_status' => array( 'publish', 'draft', 'trash' ),
			'numberposts' => 1,
			'fields'      => 'ids',
		)
	);

	if ( ! empty( $found ) ) {
		$page_id = (int) $found[0];
		wp_update_post(
			array(
				'ID'          => $page_id,
				'post_status' => 'publish',
			)
		);
	} else {
		$page_id = (int) wp_insert_post(
			array(
				'post_type'    => 'page',
				'post_status'  => 'publish',
				'post_title'   => $title,
				'post_name'    => $slug,
				'post_content' => $shortcode,
			)
		);
	}

	if ( $page_id && $shortcode ) {
		$current = get_post_field( 'post_content', $page_id );
		if ( false === strpos( (string) $current, $shortcode ) ) {
			wp_update_post(
				array(
					'ID'           => $page_id,
					'post_content' => $current . "\n" . $shortcode,
				)
			);
		}
	}

	update_option( $option_key, $page_id );
	if ( defined( 'WP_CLI' ) && WP_CLI ) {
		WP_CLI::log( sprintf( 'WooCommerce page %s -> id %d', $slug, $page_id ) );
	}
}
