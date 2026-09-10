<?php
/**
 * 品牌页模板（商品分类归档）。
 *
 * 阶段 1 品牌在 Woo 中以商品分类建模（见 apps/woo/config/seed-test-data.php，
 * 品牌 "Demo Brand A" = product_cat "demo-brand-a"）。本模板把分类当作品牌渲染：
 * 品牌名 + 简介 + 品牌商品列表。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

get_header();

$term = get_queried_object();
$brand_name = ( $term && ! is_wp_error( $term ) ) ? (string) $term->name : '';

do_action( 'woocommerce_before_main_content' );
?>

<header class="woocommerce-products-header ss-brand-header">
	<h1 class="woocommerce-products-header__title page-title"><?php echo esc_html( $brand_name ); ?></h1>
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
