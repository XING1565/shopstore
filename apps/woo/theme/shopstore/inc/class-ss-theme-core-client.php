<?php
/**
 * ShopStore 主题侧 Core 订单查询客户端（ISSUE-0105）。
 *
 * 订单主权在 Core（见 docs/架构方案.md §6），Woo 前台只做「订单状态投影」。
 * marketplace-bridge 桥接插件（ISSUE-0104）负责批发价 / MOQ 展示与下单桥接，但
 * 其 Core 客户端未暴露订单查询；本主题为「订单状态展示页」提供轻量的 Core
 * 订单读接口（GET /api/v1/orders、GET /api/v1/orders/{id}），身份头与
 * apps/core/app/api/deps.py 的轻量身份模型一致（X-Actor-Role / X-Retailer-Id）。
 *
 * 与 bridge 的契约对齐：packages/contracts/openapi/openapi.yaml（orders 部分）、
 * packages/contracts/conventions.md（金额 / 时间 / 状态命名）。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class SS_Theme_Core_Client {

	const API_PREFIX   = '/api/v1';
	const LIST_PAGE_SIZE = 50;
	const ROLE_RETAILER = 'retailer';

	/** @var string */
	private string $base_url;

	/** @var int */
	private int $timeout;

	public function __construct( ?string $base_url = null, int $timeout = 5 ) {
		$this->base_url = rtrim( $base_url ?? self::resolve_core_url(), '/' );
		$this->timeout  = $timeout;
	}

	/**
	 * 解析 Core 地址：环境变量 MARKETPLACE_CORE_URL 优先，其次过滤钩子，最后取默认值。
	 * 与 bridge 的 resolve_core_url 保持一致，但暴露独立的过滤钩子，主题不依赖插件。
	 */
	public static function resolve_core_url(): string {
		$from_env = getenv( 'MARKETPLACE_CORE_URL' );
		$url      = $from_env ? (string) $from_env : 'http://localhost:8000';
		return apply_filters( 'shopstore_theme_core_url', $url );
	}

	/**
	 * 分页列出当前买家订单。
	 *
	 * @return array{ok:bool,status:int|null,data:array|null,code:string|null,message:string|null}
	 */
	public function list_orders( string $retailer_id, int $limit = self::LIST_PAGE_SIZE, int $offset = 0 ): array {
		return $this->request(
			'GET',
			'/orders?limit=' . $limit . '&offset=' . $offset,
			array(
				'role'        => self::ROLE_RETAILER,
				'retailer_id' => $retailer_id,
			)
		);
	}

	/**
	 * 查询单个订单。
	 *
	 * @return array{ok:bool,status:int|null,data:array|null,code:string|null,message:string|null}
	 */
	public function get_order( string $retailer_id, string $order_id ): array {
		return $this->request(
			'GET',
			'/orders/' . rawurlencode( $order_id ),
			array(
				'role'        => self::ROLE_RETAILER,
				'retailer_id' => $retailer_id,
			)
		);
	}

	/**
	 * 底层请求，返回统一结果数组（与 bridge 的 request() 形状一致）。
	 */
	private function request( string $method, string $path, array $options = array() ): array {
		$headers = array(
			'Accept'       => 'application/json',
			'Content-Type' => 'application/json',
			'X-Request-Id' => $this->new_request_id(),
		);

		if ( ! empty( $options['role'] ) ) {
			$headers['X-Actor-Role'] = $options['role'];
		}
		if ( ! empty( $options['retailer_id'] ) ) {
			$headers['X-Retailer-Id'] = $options['retailer_id'];
		}

		$args = array(
			'method'  => $method,
			'timeout' => $this->timeout,
			'headers' => $headers,
		);

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
	 * 生成 UUID v4 请求追踪 ID。
	 */
	private function new_request_id(): string {
		$data   = random_bytes( 16 );
		$data[6] = chr( ord( $data[6] ) & 0x0f | 0x40 );
		$data[8] = chr( ord( $data[8] ) & 0x3f | 0x80 );
		return vsprintf( '%s%s-%s-%s-%s-%s%s%s', str_split( bin2hex( $data ), 4 ) );
	}
}
