<?php
/**
 * 下单校验与 Woo 订单 → Core 下单桥接（ISSUE-0104 / ISSUE-0117）。
 *
 * 1) 下单前拦截：强制走 Core 校验，未登录 / 未认证（非 approved）或数量低于 MOQ
 *    时在桥接层拒绝并提示原因。classic checkout 走 woocommerce_after_checkout_validation，
 *    block checkout（Store API）走 woocommerce_store_api_checkout_update_customer_from_request
 *    （ISSUE-0117：补齐 block checkout 下单前 MOQ 校验）。
 * 2) Woo 订单创建后（classic 的 woocommerce_checkout_order_processed，或 block checkout
 *    的 woocommerce_store_api_checkout_order_processed）：以买家身份把订单行提交到
 *    Core（POST /api/v1/orders），并把 marketplace_order_id 写回 Woo 订单元数据。
 *    幂等键 `woo.order.create.{woo_order_id}`，重试不重复创建。
 *    block checkout 路径下 Core 仍拒绝时抛出 RouteException 中止结账，防止
 *    process_without_payment 把 failed 状态覆盖回 processing（ISSUE-0117）。
 *
 * Core 拥有订单主权：Woo 订单只是前台投影，最终状态以 Core 为准。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class ShopStore_Bridge_Checkout {

	/** Woo 订单上记录 marketplace_order_id 的元数据键。 */
	const WOO_ORDER_META = '_shopstore_marketplace_order_id';

	/** @var ShopStore_Bridge_Core_Client */
	private ShopStore_Bridge_Core_Client $client;

	/** @var ShopStore_Bridge_Retailer */
	private ShopStore_Bridge_Retailer $retailer;

	public function __construct( ShopStore_Bridge_Core_Client $client, ShopStore_Bridge_Retailer $retailer ) {
		$this->client   = $client;
		$this->retailer = $retailer;

		add_action( 'woocommerce_after_checkout_validation', array( $this, 'validate_checkout' ), 10, 2 );
		add_action( 'woocommerce_store_api_checkout_update_customer_from_request', array( $this, 'validate_store_api_checkout' ), 10, 2 );
		add_action( 'woocommerce_checkout_order_processed', array( $this, 'after_order_processed' ), 20, 3 );
		add_action( 'woocommerce_store_api_checkout_order_processed', array( $this, 'after_store_api_order_processed' ), 20, 1 );
	}

	/**
	 * 下单前拦截（classic checkout）：认证 + MOQ 校验，失败时向 WC_Checkout 写入错误并阻止提交。
	 *
	 * @param array    $data   结账提交数据。
	 * @param WP_Error $errors WC_Checkout 的错误收集器。
	 * @return array 原样返回 $data。
	 */
	public function validate_checkout( $data, $errors ) {
		foreach ( $this->checkout_validation_errors() as $error ) {
			$errors->add( $error['code'], $error['message'] );
		}
		return $data;
	}

	/**
	 * 下单前拦截（block checkout / Store API）：认证 + MOQ 校验。
	 *
	 * `woocommerce_after_checkout_validation` 属 classic checkout 钩子，block checkout
	 * 不触发；此处用 Store API 的 `woocommerce_store_api_checkout_update_customer_from_request`
	 * 在订单创建前做同样的校验。校验失败时抛出 RouteException，Checkout 路由会捕获并以
	 * 错误响应返回，前台据此渲染错误且不再创建订单（不会落 processing）。
	 *
	 * @param WC_Customer     $customer 当前结账客户对象。
	 * @param WP_REST_Request $request  Store API 结账请求。
	 */
	public function validate_store_api_checkout( $customer, $request ) {
		$errors = $this->checkout_validation_errors();
		if ( empty( $errors ) ) {
			return;
		}

		if ( ! class_exists( '\Automattic\WooCommerce\StoreApi\Exceptions\RouteException' ) ) {
			return;
		}

		$first = reset( $errors );
		throw new \Automattic\WooCommerce\StoreApi\Exceptions\RouteException(
			$first['code'],
			$first['message'],
			400
		);
	}

	/**
	 * 汇总下单前的认证 / MOQ 校验错误（classic 与 block checkout 共用）。
	 *
	 * @return array<int,array{code:string,message:string}> 校验错误列表；空数组表示通过。
	 */
	private function checkout_validation_errors(): array {
		$errors = array();

		$user_id = get_current_user_id();
		if ( ! $user_id ) {
			$errors[] = array(
				'code'    => 'shopstore_auth',
				'message' => __( '请先登录后再下单。', 'shopstore-bridge' ),
			);
			return $errors;
		}

		if ( ! $this->retailer->is_approved( $user_id ) ) {
			$errors[] = array(
				'code'    => 'shopstore_auth',
				'message' => __( '您的买家账号尚未通过认证，暂不能下单。', 'shopstore-bridge' ),
			);
			return $errors;
		}

		$retailer_id = $this->retailer->get_retailer_id( $user_id );

		foreach ( WC()->cart->get_cart() as $cart_item ) {
			$product = isset( $cart_item['data'] ) && $cart_item['data'] instanceof WC_Product
				? $cart_item['data']
				: null;
			if ( null === $product ) {
				continue;
			}
			$sku = (string) $product->get_sku();
			if ( '' === $sku ) {
				continue;
			}

			$result = $this->client->find_product_by_sku( $sku, $retailer_id );
			// Core 不可用：拦截，避免绕过 MOQ 校验直接下单。
			if ( ! $result['ok'] ) {
				$errors[] = array(
					'code'    => 'shopstore_core',
					'message' => __( '批发价与下单校验服务暂不可用，请稍后重试。', 'shopstore-bridge' ),
				);
				continue;
			}
			$product_view = isset( $result['product'] ) ? $result['product'] : null;
			// 非 Core 商品：跳过 MOQ 校验，交由 Woo 原生流程。
			if ( null === $product_view ) {
				continue;
			}

			$moq  = isset( $product_view['moq'] ) ? (int) $product_view['moq'] : 1;
			$qty  = isset( $cart_item['quantity'] ) ? (int) $cart_item['quantity'] : 0;
			if ( $qty < $moq ) {
				$errors[] = array(
					'code'    => 'shopstore_moq',
					'message' => sprintf(
						/* translators: 1: SKU, 2: 下单数量, 3: MOQ */
						__( '商品 %1$s 下单数量 %2$d 低于最小起订量 %3$d。', 'shopstore-bridge' ),
						$sku,
						$qty,
						$moq
					),
				);
			}
		}

		return $errors;
	}

	/**
	 * Woo 订单创建后（classic checkout 短代码路径）：把订单行提交到 Core，写回 marketplace_order_id。
	 *
	 * @param int       $order_id    Woo 订单 ID。
	 * @param array     $posted_data 结账提交数据。
	 * @param WC_Order  $order       订单对象。
	 */
	public function after_order_processed( $order_id, $posted_data, $order ) {
		$this->handle_order_processed( $order );
	}

	/**
	 * Woo 订单创建后（Store API / block checkout 路径）：把订单行提交到 Core，写回 marketplace_order_id。
	 *
	 * Store API 钩子传入的是 WC_Order 对象（单参数），与 classic 钩子的签名不同。
	 * Core 拒绝时（含低于 MOQ 被 Core 二次拦截），在标记 failed 后抛出 RouteException 中止
	 * 结账，防止 Store API 后续 process_without_payment 把状态覆盖回 processing。
	 *
	 * @param WC_Order $order 订单对象。
	 */
	public function after_store_api_order_processed( $order ) {
		$this->handle_order_processed( $order, true );
	}

	/**
	 * 两个 checkout 路径（classic / block）共用的下单桥接：把订单行提交到 Core，写回 marketplace_order_id。
	 *
	 * @param WC_Order|mixed $order              订单对象；非 WC_Order 时直接忽略。
	 * @param bool           $abort_on_failure   为 true（block checkout）时，Core 拒绝后抛 RouteException 中止结账。
	 */
	private function handle_order_processed( $order, bool $abort_on_failure = false ) {
		$user_id = get_current_user_id();
		if ( ! $user_id || ! ( $order instanceof WC_Order ) ) {
			return;
		}

		$lines = $this->order_lines( $order );
		if ( empty( $lines ) ) {
			return;
		}

		$result = $this->place_core_order( $order, $user_id );

		if ( isset( $result['ok'] ) && $result['ok'] && ! empty( $result['marketplace_order_id'] ) ) {
			$order->add_order_note(
				sprintf(
					/* translators: %s: Core marketplace_order_id */
					__( '已在 Core 创建订单（marketplace_order_id=%s）。', 'shopstore-bridge' ),
					$result['marketplace_order_id']
				)
			);
			return;
		}

		$message = isset( $result['message'] ) && $result['message'] ? $result['message'] : __( '未知错误', 'shopstore-bridge' );
		$order->add_order_note(
			sprintf(
				/* translators: %s: Core 错误信息 */
				__( 'Core 下单失败：%s', 'shopstore-bridge' ),
				$message
			)
		);
		$order->update_status( 'failed', $message );

		if ( $abort_on_failure && class_exists( '\Automattic\WooCommerce\StoreApi\Exceptions\RouteException' ) ) {
			throw new \Automattic\WooCommerce\StoreApi\Exceptions\RouteException(
				'shopstore_core_rejected',
				$message,
				400
			);
		}
	}

	/**
	 * 桥接接口：把已存在的 Woo 订单提交到 Core（供 ISSUE-0105 前台 / 重试逻辑调用）。
	 *
	 * 返回数组：
	 *   ok                  bool
	 *   marketplace_order_id string|null  Core 订单主键
	 *   message             string|null   错误描述
	 */
	public function place_core_order( WC_Order $order, int $user_id ): array {
		$retailer_id = $this->retailer->get_retailer_id( $user_id );
		if ( null === $retailer_id ) {
			return array(
				'ok'                   => false,
				'marketplace_order_id' => null,
				'message'              => __( '未找到 Core 买家映射。', 'shopstore-bridge' ),
			);
		}

		$lines = $this->order_lines( $order );
		if ( empty( $lines ) ) {
			return array(
				'ok'                   => false,
				'marketplace_order_id' => null,
				'message'              => __( '订单无可提交的 Core 商品行。', 'shopstore-bridge' ),
			);
		}

		$woo_order_id    = (int) $order->get_id();
		$idempotency_key = 'woo.order.create.' . $woo_order_id;
		$result          = $this->client->place_order( $retailer_id, $lines, $idempotency_key, $woo_order_id );

		if ( $result['ok'] && isset( $result['data']['marketplace_order_id'] ) ) {
			$marketplace_order_id = (string) $result['data']['marketplace_order_id'];
			$order->update_meta_data( self::WOO_ORDER_META, $marketplace_order_id );
			$order->save();
			return array(
				'ok'                   => true,
				'marketplace_order_id' => $marketplace_order_id,
				'message'              => null,
			);
		}

		return array(
			'ok'                   => false,
			'marketplace_order_id' => null,
			'message'              => $result['message'],
		);
	}

	/**
	 * 提取 Woo 订单中带 SKU 的商品行 → Core 订单行（sku + quantity）。
	 *
	 * @return array<int,array{sku:string,quantity:int}>
	 */
	private function order_lines( WC_Order $order ): array {
		$lines = array();
		foreach ( $order->get_items() as $item ) {
			$product = $item->get_product();
			$sku     = ( $product instanceof WC_Product ) ? (string) $product->get_sku() : '';
			if ( '' === $sku ) {
				continue;
			}
			$lines[] = array(
				'sku'      => $sku,
				'quantity' => (int) $item->get_quantity(),
			);
		}
		return $lines;
	}
}
