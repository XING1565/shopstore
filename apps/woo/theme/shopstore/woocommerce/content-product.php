<?php
/**
 * 商品卡片模板（商品列表 / 品牌页循环项）。
 *
 * 复用 WooCommerce 默认钩子输出缩略图 / 标题 / 价格（价格经 marketplace-bridge 的
 * woocommerce_get_price_html 投影为批发价 + MOQ），并额外展示品牌名与认证买家可见
 * 的 MOQ 标签。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

global $product;

if ( ! is_a( $product, 'WC_Product' ) ) {
	$product = wc_get_product( get_the_ID() );
}

if ( ! ( $product instanceof WC_Product ) ) {
	return;
}

$retailer = SS_Theme_Retailer::instance();
$brands   = wc_get_product_terms( $product->get_id(), 'product_cat', array( 'number' => 1 ) );
$brand    = ( ! empty( $brands ) && ! is_wp_error( $brands ) ) ? (string) $brands[0]->name : '';
?>
<li <?php wc_product_class( '', $product ); ?>>
	<?php do_action( 'woocommerce_before_shop_loop_item' ); ?>

	<div class="ss-product-card__thumb">
		<?php do_action( 'woocommerce_before_shop_loop_item_title' ); ?>
	</div>

	<?php if ( '' !== $brand ) : ?>
		<span class="ss-product-card__brand"><?php echo esc_html( $brand ); ?></span>
	<?php endif; ?>

	<?php do_action( 'woocommerce_shop_loop_item_title' ); ?>

	<?php do_action( 'woocommerce_after_shop_loop_item_title' ); ?>

	<?php if ( $retailer->current_is_approved() ) : ?>
		<?php $moq = $retailer->product_moq( $product ); ?>
		<?php if ( null !== $moq ) : ?>
			<span class="ss-product-card__moq">
				<?php esc_html_e( 'MOQ', 'shopstore' ); ?>: <?php echo esc_html( (string) $moq ); ?>
			</span>
		<?php endif; ?>
	<?php endif; ?>

	<?php do_action( 'woocommerce_after_shop_loop_item' ); ?>
</li>
