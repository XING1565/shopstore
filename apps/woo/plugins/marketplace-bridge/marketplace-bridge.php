<?php
/**
 * Plugin Name: ShopStore Marketplace Bridge
 * Plugin URI: https://github.com/XING1565/shopstore
 * Description: WooCommerce 与 Marketplace Core 的轻量桥接插件（ISSUE-0104）。前台批发价 / MOQ 展示与下单校验均实时读取 Core 投影，Woo 不落真相；下单钩子回 Core 校验认证与 MOQ；禁止 Woo 后台手改批发价 / MOQ 覆盖 Core 数据；提供 Woo 订单 → Core 下单桥接接口。
 * Version: 0.1.0
 * Author: shopstore-dev
 * Requires at least: 6.5
 * Requires PHP: 8.1
 * WC requires at least: 8.0
 * WC tested up to: 10.8
 * Text Domain: shopstore-bridge
 *
 * 所有权：dev（apps/woo/plugins/marketplace-bridge/）。本插件不修改 WooCommerce 核心代码，
 * 只通过 WordPress / WooCommerce 提供的 filter / action 钩子做投影与拦截。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

define( 'SS_BRIDGE_VERSION', '0.1.0' );
define( 'SS_BRIDGE_PLUGIN_FILE', __FILE__ );
define( 'SS_BRIDGE_PLUGIN_DIR', plugin_dir_path( __FILE__ ) );

require_once SS_BRIDGE_PLUGIN_DIR . 'src/class-ss-bridge-core-client.php';
require_once SS_BRIDGE_PLUGIN_DIR . 'src/class-ss-bridge-retailer.php';
require_once SS_BRIDGE_PLUGIN_DIR . 'src/class-ss-bridge-display.php';
require_once SS_BRIDGE_PLUGIN_DIR . 'src/class-ss-bridge-checkout.php';
require_once SS_BRIDGE_PLUGIN_DIR . 'src/class-ss-bridge-admin.php';

/**
 * 插件引导：在 plugins_loaded 时校验 WooCommerce 并装配各模块。
 */
final class ShopStore_Bridge {

	/**
	 * 启动桥接插件。所有模块通过各自的钩子注册，互不依赖 Core 可用性。
	 */
	public function boot(): void {
		if ( ! class_exists( 'WooCommerce' ) ) {
			add_action( 'admin_notices', array( $this, 'missing_woocommerce_notice' ) );
			return;
		}

		$client   = new ShopStore_Bridge_Core_Client( ShopStore_Bridge_Core_Client::resolve_core_url() );
		$retailer = new ShopStore_Bridge_Retailer( $client );

		new ShopStore_Bridge_Display( $client, $retailer );
		new ShopStore_Bridge_Checkout( $client, $retailer );
		new ShopStore_Bridge_Admin();
	}

	/**
	 * WooCommerce 未激活时的后台提示。
	 */
	public function missing_woocommerce_notice(): void {
		echo '<div class="notice notice-warning"><p>ShopStore Marketplace Bridge 需要 WooCommerce 处于激活状态。</p></div>';
	}
}

/**
 * 激活钩子：仅做环境校验，不做数据变更。
 */
function ss_bridge_activate(): void {
	if ( ! class_exists( 'WooCommerce' ) ) {
		deactivate_plugins( plugin_basename( SS_BRIDGE_PLUGIN_FILE ) );
		wp_die(
			'ShopStore Marketplace Bridge 需要先安装并激活 WooCommerce。',
			'激活失败',
			array( 'back_link' => true )
		);
	}
}
register_activation_hook( SS_BRIDGE_PLUGIN_FILE, 'ss_bridge_activate' );

$ss_bridge = new ShopStore_Bridge();
add_action( 'plugins_loaded', array( $ss_bridge, 'boot' ) );
