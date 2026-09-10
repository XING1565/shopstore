<?php
/**
 * Core HTTP 客户端（ISSUE-0104）。
 *
 * 封装对 Marketplace Core 的 HTTP 调用：拼接 base_url 与版本前缀、注入请求追踪头
 * （X-Request-Id）、身份头（X-Actor-Role / X-Retailer-Id / X-Operator-Name）与幂等键
 * （Idempotency-Key），并把统一错误体 {"error": {code, message, ...}} 归一化为
 * 结果数组，供 display / checkout 模块消费。
 *
 * 契约见 packages/contracts/openapi/openapi.yaml 与 packages/contracts/conventions.md。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class ShopStore_Bridge_Core_Client {

	const ROLE_RETAILER = 'retailer';
	const ROLE_OPERATOR = 'operator';

	const DEFAULT_CORE_URL = 'http://localhost:8000';
	const API_PREFIX       = '/api/v1';
	const LIST_PAGE_SIZE   = 100;
	const LIST_MAX_PAGES   = 10;

	/** @var string Core base URL（不含尾部斜杠）。 */
	private string $base_url;

	/** @var int HTTP 超时秒数。 */
	private int $timeout;

	public function __construct( string $base_url, int $timeout = 5 ) {
		$this->base_url = rtrim( $base_url, '/' );
		$this->timeout  = $timeout;
	}

	/**
	 * 解析 Core 地址：环境变量 MARKETPLACE_CORE_URL 优先，其次过滤钩子，最后取默认值。
	 */
	public static function resolve_core_url(): string {
		$from_env = getenv( 'MARKETPLACE_CORE_URL' );
		$url      = $from_env ? (string) $from_env : self::DEFAULT_CORE_URL;
		return apply_filters( 'shopstore_bridge_core_url', $url );
	}

	/**
	 * 生成 UUID v4 请求追踪 ID。
	 */
	private function new_request_id(): string {
		$data   = random_bytes( 16 );
		$data[6] = chr( ord( $data[6] ) & 0x0f | 0x40 );
		$data[8] = chr( ord( $data[8] ) & 0x3f | 0x80 );
		return vsprintf( '%s%s-%s-%s-%s-%s%s%s', str_split( bin2hex( $data ), 4 ) );
	}

	/**
	 * 底层请求。返回统一结果数组：
	 *   ok      bool   2xx
	 *   status  int|null
	 *   data    array|null 解码后的 JSON 体（关联数组）
	 *   code    string|null Core 错误码（error.code）或 "network" / "http_error"
	 *   message string|null 错误描述
	 */
	private function request( string $method, string $path, array $options = array() ): array {
		$headers = array(
			'Accept'        => 'application/json',
			'Content-Type'  => 'application/json',
			'X-Request-Id'  => $this->new_request_id(),
		);

		if ( ! empty( $options['role'] ) ) {
			$headers['X-Actor-Role'] = $options['role'];
		}
		if ( ! empty( $options['retailer_id'] ) ) {
			$headers['X-Retailer-Id'] = $options['retailer_id'];
		}
		if ( ! empty( $options['operator_name'] ) ) {
			$headers['X-Operator-Name'] = $options['operator_name'];
		}
		if ( ! empty( $options['idempotency_key'] ) ) {
			$headers['Idempotency-Key'] = $options['idempotency_key'];
		}

		$args = array(
			'method'  => $method,
			'timeout' => $this->timeout,
			'headers' => $headers,
		);
		if ( isset( $options['body'] ) ) {
			$args['body'] = wp_json_encode( $options['body'] );
		}

		$url      = $this->base_url . self::API_PREFIX . $path;
		$response = wp_remote_request( $url, $args );

		if ( is_wp_error( $response ) ) {
			return array(
				'ok'      => false,
				'status'  => null,
				'data'    => null,
				'code'    => 'network',
				'message' => $response->get_error_message(),
			);
		}

		$status = (int) wp_remote_retrieve_response_code( $response );
		$raw    = wp_remote_retrieve_body( $response );
		$data   = $raw ? json_decode( $raw, true ) : null;

		if ( $status >= 200 && $status < 300 ) {
			return array(
				'ok'      => true,
				'status'  => $status,
				'data'    => is_array( $data ) ? $data : null,
				'code'    => null,
				'message' => null,
			);
		}

		$code    = 'http_error';
		$message = 'Core 请求失败（HTTP ' . $status . '）';
		if ( is_array( $data ) && isset( $data['error'] ) && is_array( $data['error'] ) ) {
			$code    = isset( $data['error']['code'] ) ? (string) $data['error']['code'] : $code;
			$message = isset( $data['error']['message'] ) ? (string) $data['error']['message'] : $message;
		}

		return array(
			'ok'      => false,
			'status'  => $status,
			'data'    => is_array( $data ) ? $data : null,
			'code'    => $code,
			'message' => $message,
		);
	}

	/**
	 * 分页列出商品。返回统一结果数组；data 为 ProductList 形状（见 openapi.yaml）。
	 */
	public function list_products( ?string $retailer_id = null ): array {
		$options = array();
		if ( null !== $retailer_id && '' !== $retailer_id ) {
			$options['role']        = self::ROLE_RETAILER;
			$options['retailer_id'] = $retailer_id;
		}
		return $this->request( 'GET', '/products?limit=' . self::LIST_PAGE_SIZE, $options );
	}

	/**
	 * 按 SKU 查找商品（SKU 为三系统稳定业务关联键）。
	 *
	 * 返回：
	 *   ok=true  且 product=null  → SKU 不属于 Core 商品（无此 SKU）
	 *   ok=true  且 product=array → 找到，product 为 ProductView（批发价/MOQ 是否可见由 Core 鉴权决定）
	 *   ok=false                  → Core 不可用或出错，调用方应「遮罩」而非回退到 Woo 本地价格
	 */
	public function find_product_by_sku( string $sku, ?string $retailer_id = null ): array {
		$offset = 0;
		for ( $page = 0; $page < self::LIST_MAX_PAGES; $page++ ) {
			$options = array();
			if ( null !== $retailer_id && '' !== $retailer_id ) {
				$options['role']        = self::ROLE_RETAILER;
				$options['retailer_id'] = $retailer_id;
			}
			$result = $this->request(
				'GET',
				'/products?limit=' . self::LIST_PAGE_SIZE . '&offset=' . $offset,
				$options
			);

			if ( ! $result['ok'] ) {
				return $result;
			}

			$items = isset( $result['data']['items'] ) && is_array( $result['data']['items'] )
				? $result['data']['items']
				: array();
			foreach ( $items as $item ) {
				if ( is_array( $item ) && isset( $item['sku'] ) && $item['sku'] === $sku ) {
					$result['product'] = $item;
					return $result;
				}
			}

			$total = isset( $result['data']['total'] ) ? (int) $result['data']['total'] : count( $items );
			$offset += self::LIST_PAGE_SIZE;
			if ( $offset >= $total ) {
				break;
			}
		}

		return array(
			'ok'      => true,
			'status'  => 200,
			'data'    => null,
			'code'    => null,
			'message' => null,
			'product' => null,
		);
	}

	/**
	 * 注册买家（默认 pending）。返回统一结果数组，data 为 RetailerView。
	 */
	public function register_retailer( string $email, string $company_name ): array {
		return $this->request(
			'POST',
			'/retailers',
			array(
				'body' => array(
					'email'        => $email,
					'company_name' => $company_name,
				),
			)
		);
	}

	/**
	 * 查询单个买家（以买家身份调用）。返回统一结果数组，data 为 RetailerView。
	 */
	public function get_retailer( string $retailer_id ): array {
		return $this->request(
			'GET',
			'/retailers/' . rawurlencode( $retailer_id ),
			array(
				'role'        => self::ROLE_RETAILER,
				'retailer_id' => $retailer_id,
			)
		);
	}

	/**
	 * 无支付下单（以买家身份调用，Core 做 MOQ 校验）。data 为 OrderView。
	 *
	 * @param string   $retailer_id     买家主键。
	 * @param array    $lines           Core 订单行（sku + quantity）。
	 * @param string   $idempotency_key 幂等键。
	 * @param int|null $woo_order_id    Woo 订单号，随请求发送供 Core 记录回写。
	 */
	public function place_order( string $retailer_id, array $lines, string $idempotency_key, ?int $woo_order_id = null ): array {
		$body = array( 'lines' => $lines );
		if ( null !== $woo_order_id ) {
			$body['woo_order_id'] = $woo_order_id;
		}
		return $this->request(
			'POST',
			'/orders',
			array(
				'role'            => self::ROLE_RETAILER,
				'retailer_id'     => $retailer_id,
				'idempotency_key' => $idempotency_key,
				'body'            => $body,
			)
		);
	}
}
