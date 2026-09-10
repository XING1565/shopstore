<?php
/**
 * ShopStore 主题侧订单状态投影（ISSUE-0105）。
 *
 * 订单主权在 Core，Woo 前台只做「订单状态展示投影」（docs/架构方案.md §7）。
 * 本类提供 [shopstore_my_orders] shortcode 与页面模板，按当前买家身份实时查询
 * Core 订单（GET /api/v1/orders），渲染订单号 / 状态 / 行明细 / 总额 / 时间。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class SS_Theme_Orders {

	/** @var SS_Theme_Orders|null */
	private static ?SS_Theme_Orders $instance = null;

	public static function instance(): SS_Theme_Orders {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {}

	/**
	 * 注册 shortcode。
	 */
	public function hooks(): void {
		add_shortcode( 'shopstore_my_orders', array( $this, 'my_orders_shortcode' ) );
	}

	/**
	 * [shopstore_my_orders] shortcode：渲染当前买家的 Core 订单状态列表。
	 */
	public function my_orders_shortcode(): string {
		$user_id = get_current_user_id();
		if ( ! $user_id ) {
			return '<p class="ss-orders-message">' . esc_html__( 'Please log in to view your orders.', 'shopstore' ) . '</p>';
		}

		$retailer = SS_Theme_Retailer::instance();
		if ( ! $retailer->bridge_available() ) {
			return '<p class="ss-orders-message">' . esc_html__( 'Marketplace bridge is not active. Orders are unavailable.', 'shopstore' ) . '</p>';
		}

		$retailer_id = $retailer->current_retailer_id();
		if ( null === $retailer_id ) {
			return '<p class="ss-orders-message">' . esc_html__( 'No marketplace buyer profile is linked to this account yet.', 'shopstore' ) . '</p>';
		}

		$client = new SS_Theme_Core_Client();
		$result = $client->list_orders( $retailer_id );

		if ( ! $result['ok'] ) {
			return '<p class="ss-orders-message ss-orders-message--error">'
				. esc_html__( 'Order status is temporarily unavailable. Please try again later.', 'shopstore' )
				. '</p>';
		}

		$items = isset( $result['data']['items'] ) && is_array( $result['data']['items'] )
			? $result['data']['items']
			: array();

		if ( empty( $items ) ) {
			return '<p class="ss-orders-message">' . esc_html__( 'You have no orders yet.', 'shopstore' ) . '</p>';
		}

		return $this->render_order_list( $items );
	}

	/**
	 * 渲染订单列表 HTML。
	 *
	 * @param array $items Core OrderView 数组。
	 */
	private function render_order_list( array $items ): string {
		$rows = '';
		foreach ( $items as $item ) {
			if ( ! is_array( $item ) ) {
				continue;
			}
			$rows .= $this->render_order_row( $item );
		}

		$header = '<table class="ss-orders"><thead><tr>'
			. '<th>' . esc_html__( 'Order', 'shopstore' ) . '</th>'
			. '<th>' . esc_html__( 'Status', 'shopstore' ) . '</th>'
			. '<th>' . esc_html__( 'Items', 'shopstore' ) . '</th>'
			. '<th>' . esc_html__( 'Total', 'shopstore' ) . '</th>'
			. '<th>' . esc_html__( 'Placed', 'shopstore' ) . '</th>'
			. '</tr></thead><tbody>';

		return $header . $rows . '</tbody></table>';
	}

	/**
	 * 渲染单个订单行（含可展开的行明细）。
	 */
	private function render_order_row( array $item ): string {
		$order_id = isset( $item['marketplace_order_id'] ) ? (string) $item['marketplace_order_id'] : '';
		$status   = isset( $item['status'] ) ? (string) $item['status'] : '';
		$lines    = isset( $item['lines'] ) && is_array( $item['lines'] ) ? $item['lines'] : array();
		$total    = isset( $item['total'] ) && is_array( $item['total'] ) ? $item['total'] : array();
		$created  = isset( $item['created_at'] ) ? (string) $item['created_at'] : '';

		$line_summary = $this->render_lines( $lines );

		$cells = array(
			'<td data-label="' . esc_attr__( 'Order', 'shopstore' ) . '">' . esc_html( ss_theme_short_id( $order_id ) ) . '</td>',
			'<td data-label="' . esc_attr__( 'Status', 'shopstore' ) . '">' . $this->render_status_badge( $status ) . '</td>',
			'<td data-label="' . esc_attr__( 'Items', 'shopstore' ) . '">' . $line_summary . '</td>',
			'<td data-label="' . esc_attr__( 'Total', 'shopstore' ) . '">' . esc_html( ss_theme_format_money( $total ) ) . '</td>',
			'<td data-label="' . esc_attr__( 'Placed', 'shopstore' ) . '">' . esc_html( ss_theme_format_datetime( $created ) ) . '</td>',
		);

		return '<tr>' . implode( '', $cells ) . '</tr>';
	}

	/**
	 * 渲染订单行明细（SKU × 数量）。
	 */
	private function render_lines( array $lines ): string {
		if ( empty( $lines ) ) {
			return '&mdash;';
		}
		$parts = array();
		foreach ( $lines as $line ) {
			$sku      = isset( $line['sku'] ) ? (string) $line['sku'] : '';
			$quantity = isset( $line['quantity'] ) ? (int) $line['quantity'] : 0;
			$parts[]  = esc_html( $sku ) . ' &times; ' . esc_html( (string) $quantity );
		}
		return implode( '<br />', $parts );
	}

	/**
	 * 渲染订单状态徽章。
	 */
	private function render_status_badge( string $status ): string {
		return sprintf(
			'<span class="ss-order-status ss-order-status--%s">%s</span>',
			esc_attr( $status ),
			esc_html( ss_theme_order_status_label( $status ) )
		);
	}
}
