<?php
/**
 * 后台保护：禁止在 Woo 后台手改批发价 / MOQ 覆盖 Core 数据（ISSUE-0104）。
 *
 * 批发价与 MOQ 的真相只在 Core；Woo 只持有展示投影，因此本模块在 Woo 保存商品时
 * 强制剥离任何试图写入的批发价 / MOQ 元数据，并在商品编辑页提示这些字段由 Core 管理。
 * 本插件本身不写入任何批发价 / MOQ 元数据。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class ShopStore_Bridge_Admin {

	/**
	 * 受保护的元数据键：任何插件 / 代码试图写入都会被剥离。
	 */
	const PROTECTED_META = array(
		'_wholesale_price',
		'_moq',
		'_shopstore_wholesale_price',
		'_shopstore_moq',
	);

	public function __construct() {
		add_action( 'woocommerce_process_product_meta', array( $this, 'strip_protected_meta' ), 20, 1 );
		add_action( 'admin_notices', array( $this, 'product_edit_notice' ) );
	}

	/**
	 * Woo 保存商品时强制删除受保护的批发价 / MOQ 元数据。
	 *
	 * @param int $post_id 商品 post ID。
	 */
	public function strip_protected_meta( $post_id ) {
		foreach ( self::PROTECTED_META as $key ) {
			delete_post_meta( (int) $post_id, $key );
		}
	}

	/**
	 * 商品编辑页提示：批发价 / MOQ 由 Core 管理，不在 Woo 后台维护。
	 */
	public function product_edit_notice(): void {
		global $pagenow, $post_type;
		if ( 'post.php' === $pagenow && 'product' === $post_type ) {
			echo '<div class="notice notice-info"><p>批发价与 MOQ 由 Marketplace Core 管理，本页不提供编辑，前台展示实时读取 Core。</p></div>';
		}
	}
}
