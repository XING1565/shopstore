<?php
/**
 * ShopStore 主题入口（ISSUE-0105）。
 *
 * B2B 前台 storefront 主题：品牌 / 商品浏览、认证买家批发价 / MOQ 展示、无支付
 * checkout、订单状态投影。批发价 / MOQ / 下单校验 / 订单桥接由 marketplace-bridge
 * 插件（ISSUE-0104）承担，本主题负责页面模板与买家注册 / 认证状态 / 订单展示。
 *
 * 所有权：dev（apps/woo/theme/）。不修改 WooCommerce 核心代码，仅通过
 * WordPress / WooCommerce 提供的模板与钩子接入。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'SS_THEME_VERSION', '0.1.0' );
define( 'SS_THEME_DIR', get_template_directory() );
define( 'SS_THEME_URI', get_template_directory_uri() );

require_once SS_THEME_DIR . '/inc/class-ss-theme-core-client.php';
require_once SS_THEME_DIR . '/inc/class-ss-theme-retailer.php';
require_once SS_THEME_DIR . '/inc/class-ss-theme-orders.php';
require_once SS_THEME_DIR . '/inc/template-tags.php';

/**
 * 主题基础设置。
 */
function ss_theme_setup(): void {
	load_theme_textdomain( 'shopstore', SS_THEME_DIR . '/languages' );

	add_theme_support( 'automatic-feed-links' );
	add_theme_support( 'title-tag' );
	add_theme_support( 'post-thumbnails' );
	add_theme_support( 'custom-logo' );
	add_theme_support( 'html5', array( 'search-form', 'comment-form', 'comment-list', 'gallery', 'caption', 'style', 'script' ) );

	// WooCommerce 集成（商店 / 商品 / 购物车 / 结算模板）。
	add_theme_support( 'woocommerce' );
	add_theme_support( 'wc-product-gallery-zoom' );
	add_theme_support( 'wc-product-gallery-lightbox' );
	add_theme_support( 'wc-product-gallery-slider' );

	register_nav_menus(
		array(
			'primary' => __( 'Primary Menu', 'shopstore' ),
		)
	);
}
add_action( 'after_setup_theme', 'ss_theme_setup' );

/**
 * 前台脚本与样式。
 */
function ss_theme_enqueue(): void {
	wp_enqueue_style( 'ss-theme', SS_THEME_URI . '/assets/theme.css', array(), SS_THEME_VERSION );
	wp_enqueue_style( 'shopstore', get_stylesheet_uri(), array( 'ss-theme' ), SS_THEME_VERSION );
}
add_action( 'wp_enqueue_scripts', 'ss_theme_enqueue' );

/**
 * 侧边栏。
 */
function ss_theme_widgets_init(): void {
	register_sidebar(
		array(
			'name'          => __( 'Sidebar', 'shopstore' ),
			'id'            => 'sidebar-1',
			'description'   => __( 'Add widgets here.', 'shopstore' ),
			'before_widget' => '<section id="%1$s" class="widget %2$s">',
			'after_widget'  => '</section>',
			'before_title'  => '<h2 class="widget-title">',
			'after_title'   => '</h2>',
		)
	);
}
add_action( 'widgets_init', 'ss_theme_widgets_init' );

/**
 * 组装业务模块（买家注册 / 认证状态 / 订单投影）。
 */
function ss_theme_boot(): void {
	SS_Theme_Retailer::instance()->hooks();
	SS_Theme_Orders::instance()->hooks();
}
add_action( 'after_setup_theme', 'ss_theme_boot' );

/**
 * 商品单页：非认证买家的提示 + 认证买家明确展示 MOQ。
 */
function ss_theme_single_product_notice(): void {
	$product = wc_get_product( get_the_ID() );
	if ( ! ( $product instanceof WC_Product ) ) {
		return;
	}

	$retailer = SS_Theme_Retailer::instance();

	if ( ! is_user_logged_in() ) {
		echo '<div class="ss-pricing-notice">'
			. esc_html__( 'Wholesale prices and MOQ are visible to approved buyers only.', 'shopstore' )
			. ' <a href="' . esc_url( wc_get_page_permalink( 'myaccount' ) ) . '">'
			. esc_html__( 'Log in or register', 'shopstore' )
			. '</a></div>';
		return;
	}

	if ( $retailer->current_is_approved() ) {
		$moq = $retailer->product_moq( $product );
		if ( null !== $moq ) {
			echo '<div class="ss-moq">'
				. esc_html__( 'Minimum order quantity (MOQ):', 'shopstore' )
				. ' <strong>' . esc_html( (string) $moq ) . '</strong></div>';
		}
		return;
	}

	echo '<div class="ss-pricing-notice">'
		. esc_html__( 'Your buyer account is not approved yet. Wholesale prices and ordering are unavailable.', 'shopstore' )
		. '</div>';
}
add_action( 'woocommerce_single_product_summary', 'ss_theme_single_product_notice', 25 );
