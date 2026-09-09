<?php
/**
 * Phase-0 WooCommerce store settings baseline (config / ISSUE-0003).
 *
 * Owner: config. Loaded via `wp eval-file /woo-config/woo-options.php` by
 * docker/provision.sh. Idempotent: re-running just re-applies the same values.
 * Overridable through apps/woo/.env (WOO_*), see infra/env/woo.env.example.
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

$env = static function ( string $key, string $default ): string {
	$value = getenv( $key );
	return ( false === $value || '' === $value ) ? $default : $value;
};

// 基础货币与地区 + 无支付 checkout 配套（真实下单无需支付由 mu-plugin
// woo-no-payment-checkout.php 保证，这里只做配套设置）。
$settings = array(
	// 货币与地区
	'woocommerce_currency'                          => $env( 'WOO_CURRENCY', 'CNY' ),
	'woocommerce_currency_pos'                      => 'left',
	'woocommerce_price_thousand_sep'                => ',',
	'woocommerce_price_decimal_sep'                 => '.',
	'woocommerce_price_num_decimals'                => 2,
	'woocommerce_default_country'                   => $env( 'WOO_DEFAULT_COUNTRY', 'CN' ),
	'woocommerce_allowed_countries'                 => 'all',
	'woocommerce_store_address'                     => $env( 'WOO_STORE_ADDRESS', '1 Demo Road' ),
	'woocommerce_store_city'                        => $env( 'WOO_STORE_CITY', 'Shanghai' ),
	'woocommerce_store_postcode'                    => $env( 'WOO_STORE_POSTCODE', '200000' ),
	// 计量 / 税务基线
	'woocommerce_calc_taxes'                        => 'no',
	'woocommerce_weight_unit'                       => 'kg',
	'woocommerce_dimension_unit'                    => 'cm',
	// checkout：B2B 需登录下单，不做游客结账
	'woocommerce_enable_guest_checkout'             => 'no',
	'woocommerce_enable_signup_and_login_from_checkout' => 'yes',
	'woocommerce_enable_checkout_login_reminder'    => 'yes',
);

foreach ( $settings as $key => $value ) {
	update_option( $key, $value );
}

if ( defined( 'WP_CLI' ) && WP_CLI ) {
	WP_CLI::success( sprintf( 'WooCommerce settings applied (%d options)', count( $settings ) ) );
}
