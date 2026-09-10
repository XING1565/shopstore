<?php
/**
 * 前台批发价 / MOQ 展示投影（ISSUE-0104）。
 *
 * 批发价与 MOQ 的真相只在 Core（见 packages/contracts/schemas/product.schema.json 与
 * 商品创建链路与三系统投影契约.md）。本模块在 Woo 前台渲染价格时实时向 Core 读取投影，
 * Woo 不落批发价 / MOQ：
 *
 *   - 已认证（approved）买家 → 展示 Core 批发价 + MOQ
 *   - 未登录 / 未认证 / 未映射买家 → 遮罩（与 Core「未认证不可见批发价」语义一致）
 *   - SKU 不属于 Core（无此商品）→ 保持 Woo 原生价格展示，不干预
 *   - Core 不可用 → 遮罩并记录日志，不回退到 Woo 本地价格（避免把占位价当真相）
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class ShopStore_Bridge_Display {

	/** @var ShopStore_Bridge_Core_Client */
	private ShopStore_Bridge_Core_Client $client;

	/** @var ShopStore_Bridge_Retailer */
	private ShopStore_Bridge_Retailer $retailer;

	/** @var array<string,array> 单请求内按 SKU+上下文缓存 Core 商品查找结果。 */
	private array $product_cache = array();

	public function __construct( ShopStore_Bridge_Core_Client $client, ShopStore_Bridge_Retailer $retailer ) {
		$this->client   = $client;
		$this->retailer = $retailer;

		add_filter( 'woocommerce_get_price_html', array( $this, 'filter_price_html' ), 20, 2 );
	}

	/**
	 * 替换前台价格 HTML。仅作用于前端（不干预后台），且仅当商品带 SKU 时介入。
	 *
	 * @param string      $price_html WooCommerce 原生价格 HTML。
	 * @param WC_Product  $product    商品对象。
	 */
	public function filter_price_html( $price_html, $product ) {
		if ( is_admin() ) {
			return $price_html;
		}
		if ( ! ( $product instanceof WC_Product ) ) {
			return $price_html;
		}

		$sku = (string) $product->get_sku();
		if ( '' === $sku ) {
			return $price_html;
		}

		$retailer_id = $this->resolve_context();
		$result      = $this->find_product( $sku, $retailer_id );

		// Core 不可用：遮罩，不回退到 Woo 本地价格。
		if ( ! $result['ok'] ) {
			$this->log( sprintf( 'Core 商品查询失败，价格已遮罩 sku=%s：%s', $sku, $result['message'] ) );
			return $this->masked_html( 'unavailable' );
		}

		$product_view = isset( $result['product'] ) ? $result['product'] : null;
		// SKU 不属于 Core 商品：保持 Woo 原生展示。
		if ( null === $product_view ) {
			return $price_html;
		}

		// Core 商品，但批发价 / MOQ 对当前身份不可见（未认证 / 未登录）。
		if ( ! isset( $product_view['wholesale_price'] ) || ! isset( $product_view['moq'] ) ) {
			return $this->masked_html( 'unauthorized' );
		}

		return $this->wholesale_html( $product_view );
	}

	/**
	 * 供 ISSUE-0105 前台模板调用的公开接口：返回指定商品的 MOQ（未认证返回 null）。
	 */
	public function get_moq( WC_Product $product ): ?int {
		$sku = (string) $product->get_sku();
		if ( '' === $sku ) {
			return null;
		}
		$retailer_id = $this->resolve_context();
		$result      = $this->find_product( $sku, $retailer_id );
		if ( ! $result['ok'] || null === ( $result['product'] ?? null ) ) {
			return null;
		}
		return isset( $result['product']['moq'] ) ? (int) $result['product']['moq'] : null;
	}

	/**
	 * 解析当前请求的买家上下文：返回当前 Woo 用户映射到的 Core retailer_id；
	 * 未登录或未建立映射返回 null。批发价 / MOQ 是否可见由 Core 鉴权决定。
	 */
	private function resolve_context(): ?string {
		$user_id = get_current_user_id();
		if ( ! $user_id ) {
			return null;
		}
		return $this->retailer->get_retailer_id( $user_id );
	}

	/**
	 * 按 SKU 查找 Core 商品（带单请求缓存）。
	 */
	private function find_product( string $sku, ?string $retailer_id ): array {
		$key = $sku . '|' . (string) $retailer_id;
		if ( array_key_exists( $key, $this->product_cache ) ) {
			return $this->product_cache[ $key ];
		}
		$result                    = $this->client->find_product_by_sku( $sku, $retailer_id );
		$this->product_cache[ $key ] = $result;
		return $result;
	}

	/**
	 * 已认证买家的批发价 + MOQ 展示 HTML。
	 */
	private function wholesale_html( array $product_view ): string {
		$money = isset( $product_view['wholesale_price'] ) && is_array( $product_view['wholesale_price'] )
			? $product_view['wholesale_price']
			: null;
		$moq   = isset( $product_view['moq'] ) ? (int) $product_view['moq'] : 0;

		$price_text = $money ? $this->format_money( $money ) : '';
		$moq_text   = $moq > 0 ? sprintf( '起订量 %d 件', $moq ) : '';

		$parts = array_filter( array( $price_text, $moq_text ) );
		return '<span class="ss-bridge-wholesale">' . esc_html( implode( ' · ', $parts ) ) . '</span>';
	}

	/**
	 * 遮罩 HTML（未认证 / Core 不可用）。
	 */
	private function masked_html( string $reason ): string {
		$text = 'unavailable' === $reason
			? '批发价暂不可用'
			: '批发价仅对认证买家可见';
		return '<span class="ss-bridge-masked">' . esc_html( $text ) . '</span>';
	}

	/**
	 * 金额格式化：amount_minor / 10^exponent，带货币代码。禁止浮点截断。
	 */
	private function format_money( array $money ): string {
		$amount   = isset( $money['amount_minor'] ) ? (int) $money['amount_minor'] : 0;
		$currency = isset( $money['currency'] ) ? (string) $money['currency'] : 'USD';
		$exponent = self::currency_exponent( $currency );
		$factor   = 10 ** $exponent;

		$sign       = $amount < 0 ? '-' : '';
		$abs        = abs( $amount );
		$major      = intdiv( $abs, $factor );
		$minor      = $abs % $factor;

		$major_text = number_format( $major, 0, '.', ',' );
		$minor_text = str_pad( (string) $minor, $exponent, '0', STR_PAD_LEFT );

		return sprintf( '%s %s%s.%s', $currency, $sign, $major_text, $minor_text );
	}

	/**
	 * ISO 4217 最小单位指数（阶段 1 仅需 USD，默认 2）。
	 */
	private static function currency_exponent( string $currency ): int {
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

	/**
	 * 记录调试日志（仅 WP_DEBUG 开启时）。
	 */
	private function log( string $message ): void {
		if ( defined( 'WP_DEBUG' ) && WP_DEBUG ) {
			// phpcs:ignore WordPress.PHP.DevelopmentFunctions.error_log_error_log
			error_log( '[shopstore-bridge] ' . $message );
		}
	}
}
