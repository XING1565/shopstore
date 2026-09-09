<?php
/**
 * Plugin Name: Woo No-Payment Checkout (Phase-0 baseline)
 * Description: 阶段 0 无支付下单基线占位：让结算不再依赖任何在线支付网关，订单可
 *              直接创建（配套设置见 config/woo-options.php）。所有权：config
 *              （ISSUE-0003）。后续支付/账期策略由 dev 的 marketplace-bridge 插件
 *              接管时，应先停用/移除本占位再启用真实网关。
 * Version: 0.1.0
 * Author: shopstore-config
 *
 * 本文件位于 wp-content/mu-plugins（只读挂载），随环境自动加载，属 config 管理范围。
 * 阶段 0 不实现真实支付（见父 issue 非目标），因此订单“无支付”即可进入后续流程；
 * 订单最终状态策略由后续阶段 / Core 定义，本文件只保证 checkout 不要求支付网关。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

// 购物车不要求“需要支付”，WooCommerce 会跳过支付步骤直接进入下单。
add_filter( 'woocommerce_cart_needs_payment', '__return_false' );
