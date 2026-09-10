<?php
/**
 * WooCommerce 商品归档模板（商店 / 商品列表）。
 *
 * 覆盖默认 archive-product.php：品牌页由 taxonomy-product_cat.php 单独覆盖，
 * 此处承接店铺首页与通用商品归档。批发价 / MOQ 由 marketplace-bridge 的
 * woocommerce_get_price_html 过滤钩子实时投影。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();

do_action( 'woocommerce_before_main_content' );
?>

<header class="woocommerce-products-header">
	<?php if ( apply_filters( 'woocommerce_show_page_title', true ) ) : ?>
		<h1 class="woocommerce-products-header__title page-title"><?php woocommerce_page_title(); ?></h1>
	<?php endif; ?>
	<?php do_action( 'woocommerce_archive_description' ); ?>
</header>

<?php
if ( woocommerce_product_loop() ) {
	do_action( 'woocommerce_before_shop_loop' );

	woocommerce_product_loop_start();

	if ( wc_get_loop_prop( 'total' ) ) {
		while ( have_posts() ) {
			the_post();
			do_action( 'woocommerce_shop_loop' );
			wc_get_template_part( 'content', 'product' );
		}
	}

	woocommerce_product_loop_end();

	do_action( 'woocommerce_after_shop_loop' );
} else {
	do_action( 'woocommerce_no_products_found' );
}

do_action( 'woocommerce_after_main_content' );

get_footer();
