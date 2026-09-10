<?php
/**
 * ShopStore 主题模板辅助函数（ISSUE-0105）。
 *
 * 供 inc/class-ss-theme-retailer.php、inc/class-ss-theme-orders.php 与前台模板共用
 * 的纯展示辅助：状态标签映射、金额 / 时间格式化、订单短 ID。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

if ( ! function_exists( 'ss_theme_retailer_status_label' ) ) {
	/**
	 * 买家认证状态 → 展示标签。
	 */
	function ss_theme_retailer_status_label( string $status ): string {
		$labels = array(
			'pending'   => __( 'Pending — your buyer account is under review.', 'shopstore' ),
			'approved'  => __( 'Approved — you can view wholesale prices and place orders.', 'shopstore' ),
			'rejected'  => __( 'Rejected — your buyer account was not approved.', 'shopstore' ),
			'suspended' => __( 'Suspended — your buyer account is currently suspended.', 'shopstore' ),
		);
		return isset( $labels[ $status ] ) ? $labels[ $status ] : $status;
	}
}

if ( ! function_exists( 'ss_theme_order_status_label' ) ) {
	/**
	 * 订单状态 → 展示标签（中文 + 英文状态码，对齐 PRD §6 状态枚举）。
	 */
	function ss_theme_order_status_label( string $status ): string {
		$labels = array(
			'draft'             => '草稿 Draft',
			'submitted'         => '已提交 Submitted',
			'sent_to_odoo'      => '已发送 Odoo',
			'odoo_confirmed'    => 'Odoo 已确认',
			'inventory_reserved' => '库存已预留',
			'picking_ready'     => '待拣货',
			'shipped'           => '已发货 Shipped',
			'completed'         => '已完成 Completed',
			'cancelled'         => '已取消 Cancelled',
			'sync_failed'       => '同步失败 SyncFailed',
		);
		return isset( $labels[ $status ] ) ? $labels[ $status ] : $status;
	}
}

if ( ! function_exists( 'ss_theme_format_money' ) ) {
	/**
	 * 金额格式化：{amount_minor, currency} → "USD 1,234.56"。
	 */
	function ss_theme_format_money( array $money ): string {
		$amount   = isset( $money['amount_minor'] ) ? (int) $money['amount_minor'] : 0;
		$currency = isset( $money['currency'] ) ? (string) $money['currency'] : 'USD';
		$exponent = ss_theme_currency_exponent( $currency );
		$factor   = 10 ** $exponent;

		$sign  = $amount < 0 ? '-' : '';
		$abs   = abs( $amount );
		$major = intdiv( $abs, $factor );
		$minor = $abs % $factor;

		$major_text = number_format( $major, 0, '.', ',' );
		$minor_text = str_pad( (string) $minor, $exponent, '0', STR_PAD_LEFT );

		return sprintf( '%s %s%s.%s', $currency, $sign, $major_text, $minor_text );
	}
}

if ( ! function_exists( 'ss_theme_currency_exponent' ) ) {
	/**
	 * ISO 4217 最小单位指数（阶段 1 仅需 USD，默认 2）。
	 */
	function ss_theme_currency_exponent( string $currency ): int {
		$map = array(
			'USD' => 2,
			'CNY' => 2,
			'EUR' => 2,
			'JPY' => 0,
			'KWD' => 3,
		);
		$currency = strtoupper( $currency );
		return isset( $map[ $currency ] ) ? $map[ $currency ] : 2;
	}
}

if ( ! function_exists( 'ss_theme_format_datetime' ) ) {
	/**
	 * RFC 3339 UTC 时间 → 本地可读时间（无法解析时原样返回）。
	 */
	function ss_theme_format_datetime( string $iso ): string {
		if ( '' === $iso ) {
			return '';
		}
		$ts = strtotime( $iso );
		if ( false === $ts ) {
			return $iso;
		}
		return wp_date( get_option( 'date_format' ) . ' ' . get_option( 'time_format' ), $ts );
	}
}

if ( ! function_exists( 'ss_theme_short_id' ) ) {
	/**
	 * UUID → 短 ID（取前 8 位，便于展示）。
	 */
	function ss_theme_short_id( string $id ): string {
		return mb_substr( $id, 0, 8 );
	}
}
