<?php
/**
 * 买家（Retailer）映射（ISSUE-0104）。
 *
 * Core 买家主键是 UUID（retailer_id），Woo 用户是整数 ID。桥接插件把两者关联：
 * Woo user → usermeta `_shopstore_core_retailer_id` → Core retailer_id。
 * 映射在买家注册时建立（register()），之后查询与下单以该映射身份调用 Core。
 *
 * 阶段 1 无独立 IAM：Core 通过 X-Actor-Role / X-Retailer-Id 头识别买家（见
 * apps/core/app/api/deps.py）。本类只负责「Woo 用户 → Core 买家」的映射与认证状态查询。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class ShopStore_Bridge_Retailer {

	const META_KEY = '_shopstore_core_retailer_id';

	/** @var ShopStore_Bridge_Core_Client */
	private ShopStore_Bridge_Core_Client $client;

	/** @var array<int,string|null> 单请求内 status 缓存（user_id => status）。 */
	private array $status_cache = array();

	public function __construct( ShopStore_Bridge_Core_Client $client ) {
		$this->client = $client;
	}

	/**
	 * 读取 Woo 用户对应的 Core retailer_id；未建立映射返回 null。
	 */
	public function get_retailer_id( int $user_id ): ?string {
		$value = get_user_meta( $user_id, self::META_KEY, true );
		return ( is_string( $value ) && '' !== $value ) ? $value : null;
	}

	/**
	 * 记录 Woo 用户 ↔ Core retailer_id 映射。
	 */
	public function set_retailer_id( int $user_id, string $retailer_id ): void {
		update_user_meta( $user_id, self::META_KEY, $retailer_id );
	}

	/**
	 * 当前登录用户的 Core retailer_id；未登录或未映射返回 null。
	 */
	public function current_retailer_id(): ?string {
		$user_id = get_current_user_id();
		if ( ! $user_id ) {
			return null;
		}
		return $this->get_retailer_id( $user_id );
	}

	/**
	 * 查询买家认证状态（pending / approved / rejected / suspended）。
	 * 未映射或 Core 查询失败返回 null（视为「未认证」）。
	 */
	public function status( int $user_id ): ?string {
		if ( isset( $this->status_cache[ $user_id ] ) ) {
			return $this->status_cache[ $user_id ];
		}

		$retailer_id = $this->get_retailer_id( $user_id );
		if ( null === $retailer_id ) {
			$this->status_cache[ $user_id ] = null;
			return null;
		}

		$result = $this->client->get_retailer( $retailer_id );
		$status = ( $result['ok'] && isset( $result['data']['status'] ) )
			? (string) $result['data']['status']
			: null;

		$this->status_cache[ $user_id ] = $status;
		return $status;
	}

	/**
	 * 是否已通过认证（approved）。与 Core 的 can_view_pricing / require_approved_retailer 一致。
	 */
	public function is_approved( int $user_id ): bool {
		return 'approved' === $this->status( $user_id );
	}

	/**
	 * 注册买家到 Core 并建立映射。成功后返回 retailer_id，失败返回 null。
	 *
	 * 说明：若邮箱已在 Core 注册（409 conflict），阶段 1 Core 未提供「按邮箱查询买家」的
	 * 公开接口，桥接层无法据此还原 retailer_id，此时返回 null 并交由上层提示用户联系运营
	 * （视为未建立映射，不能查看批发价 / 下单）。该限制见插件 README「已知限制」。
	 */
	public function register( int $user_id, string $email, string $company_name ): ?string {
		$result = $this->client->register_retailer( $email, $company_name );

		if ( $result['ok'] && isset( $result['data']['retailer_id'] ) ) {
			$retailer_id = (string) $result['data']['retailer_id'];
			$this->set_retailer_id( $user_id, $retailer_id );
			$this->status_cache[ $user_id ] = isset( $result['data']['status'] )
				? (string) $result['data']['status']
				: 'pending';
			return $retailer_id;
		}

		return null;
	}
}
