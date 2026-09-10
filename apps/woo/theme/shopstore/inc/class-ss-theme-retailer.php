<?php
/**
 * ShopStore 主题侧买家（Retailer）注册 / 认证状态粘合层（ISSUE-0105）。
 *
 * 买家注册是 WooCommerce 原生能力（my-account 注册 / checkout 注册），本类在注册
 * 完成后把 Woo 用户映射到 Core 买家（调用 marketplace-bridge 的
 * ShopStore_Bridge_Retailer::register()），并向前台提供认证状态展示
 * （Pending / Approved 等）。
 *
 * 依赖 ISSUE-0104（marketplace-bridge）已激活。若插件缺失，本类所有入口优雅降级：
 * 不建立 Core 映射、状态展示提示「桥接插件未启用」，不产生致命错误。
 */

if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

final class SS_Theme_Retailer {

	/** @var SS_Theme_Retailer|null */
	private static ?SS_Theme_Retailer $instance = null;

	/** @var ShopStore_Bridge_Core_Client|null */
	private $client = null;

	/** @var ShopStore_Bridge_Retailer|null */
	private $retailer = null;

	public static function instance(): SS_Theme_Retailer {
		if ( null === self::$instance ) {
			self::$instance = new self();
		}
		return self::$instance;
	}

	private function __construct() {}

	/**
	 * 注册全部钩子（after_setup_theme 时调用一次）。
	 */
	public function hooks(): void {
		// 注册表单增加「公司名」字段（Core 买家必填 company_name）。
		add_action( 'woocommerce_register_form', array( $this, 'render_company_field' ) );
		add_filter( 'woocommerce_register_post', array( $this, 'validate_company_field' ), 10, 3 );
		add_action( 'woocommerce_created_customer', array( $this, 'on_customer_created' ), 20, 3 );

		// 认证状态提示：my-account 仪表盘 + 独立 shortcode。
		add_action( 'woocommerce_account_dashboard', array( $this, 'render_status_notice' ) );
		add_shortcode( 'shopstore_account_status', array( $this, 'status_shortcode' ) );

		// B2B 前台需要登录注册：切换主题时确保 my-account 注册开启。
		add_action( 'after_switch_theme', array( $this, 'ensure_registration_enabled' ) );
	}

	/**
	 * 是否具备可用的 bridge 桥接层。
	 */
	public function bridge_available(): bool {
		return class_exists( 'ShopStore_Bridge_Core_Client' ) && class_exists( 'ShopStore_Bridge_Retailer' );
	}

	/**
	 * 惰性构建 bridge 实例（主题自身持有的 client/retailer，映射 usermeta 与插件共享）。
	 */
	private function ensure_bridge(): void {
		if ( $this->bridge_available() ) {
			if ( null === $this->client ) {
				$this->client = new ShopStore_Bridge_Core_Client( ShopStore_Bridge_Core_Client::resolve_core_url() );
			}
			if ( null === $this->retailer ) {
				$this->retailer = new ShopStore_Bridge_Retailer( $this->client );
			}
		}
	}

	/**
	 * 当前登录用户的 Core retailer_id（未登录 / 未映射返回 null）。
	 */
	public function current_retailer_id(): ?string {
		$this->ensure_bridge();
		if ( null !== $this->retailer ) {
			$retailer_id = $this->retailer->current_retailer_id();
			if ( null !== $retailer_id ) {
				return $retailer_id;
			}
		}
		return null;
	}

	/**
	 * 当前登录用户认证状态（pending / approved / rejected / suspended），
	 * 无法确定时返回 null。
	 */
	public function current_status(): ?string {
		$user_id = get_current_user_id();
		if ( ! $user_id ) {
			return null;
		}
		$this->ensure_bridge();
		if ( null !== $this->retailer ) {
			return $this->retailer->status( $user_id );
		}
		return null;
	}

	/**
	 * 当前登录用户是否已通过认证（approved）。
	 */
	public function current_is_approved(): bool {
		return 'approved' === $this->current_status();
	}

	/**
	 * 商品 MOQ（认证买家可见）；不可见 / 无法确定返回 null。
	 */
	public function product_moq( WC_Product $product ): ?int {
		$sku = (string) $product->get_sku();
		if ( '' === $sku ) {
			return null;
		}
		$this->ensure_bridge();
		if ( null === $this->client ) {
			return null;
		}
		$retailer_id = $this->current_retailer_id();
		$result      = $this->client->find_product_by_sku( $sku, $retailer_id );
		if ( ! $result['ok'] || null === ( $result['product'] ?? null ) ) {
			return null;
		}
		return isset( $result['product']['moq'] ) ? (int) $result['product']['moq'] : null;
	}

	/**
	 * 注册表单追加公司名字段。
	 */
	public function render_company_field(): void {
		$company = isset( $_POST['company_name'] ) // phpcs:ignore WordPress.Security.NonceVerification.Missing
			? sanitize_text_field( wp_unslash( $_POST['company_name'] ) ) // phpcs:ignore WordPress.Security.NonceVerification.Missing
			: '';
		?>
		<p class="woocommerce-form-row woocommerce-form-row--wide form-row form-row-wide">
			<label for="reg_company_name">
				<?php esc_html_e( 'Company name', 'shopstore' ); ?>&nbsp;
				<span class="required">*</span>
			</label>
			<input type="text" class="woocommerce-Input woocommerce-Input--text input-text"
				name="company_name" id="reg_company_name" autocomplete="organization"
				value="<?php echo esc_attr( $company ); ?>" />
		</p>
		<?php
	}

	/**
	 * 校验公司名必填。
	 *
	 * @param string   $username 用户名。
	 * @param string   $email    邮箱。
	 * @param WP_Error $errors   校验错误收集器。
	 * @return WP_Error
	 */
	public function validate_company_field( $username, $email, $errors ) {
		$company = isset( $_POST['company_name'] ) // phpcs:ignore WordPress.Security.NonceVerification.Missing
			? trim( sanitize_text_field( wp_unslash( $_POST['company_name'] ) ) ) // phpcs:ignore WordPress.Security.NonceVerification.Missing
			: '';
		if ( '' === $company ) {
			$errors->add( 'company_name_error', __( 'Please enter your company name.', 'shopstore' ) );
		}
		return $errors;
	}

	/**
	 * Woo 用户创建成功后，映射到 Core 买家（pending）。
	 *
	 * @param int    $customer_id        新用户 ID。
	 * @param array  $new_customer_data  新用户数据。
	 * @param bool   $password_generated 密码是否自动生成。
	 */
	public function on_customer_created( $customer_id, $new_customer_data, $password_generated ) {
		$company = isset( $_POST['company_name'] ) // phpcs:ignore WordPress.Security.NonceVerification.Missing
			? trim( sanitize_text_field( wp_unslash( $_POST['company_name'] ) ) ) // phpcs:ignore WordPress.Security.NonceVerification.Missing
			: '';
		$user = get_userdata( (int) $customer_id );
		if ( ! $user || '' === $company ) {
			return;
		}

		$this->ensure_bridge();
		if ( null === $this->retailer ) {
			return;
		}

		$this->retailer->register( (int) $customer_id, $user->user_email, $company );
	}

	/**
	 * 认证状态提示（HTML），可复用于仪表盘 / shortcode。
	 */
	public function render_status_notice(): void {
		echo wp_kses_post( $this->status_notice_html() ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped
	}

	/**
	 * [shopstore_account_status] shortcode。
	 *
	 * @return string
	 */
	public function status_shortcode(): string {
		return $this->status_notice_html();
	}

	/**
	 * 生成认证状态提示 HTML。
	 */
	private function status_notice_html(): string {
		$user_id = get_current_user_id();
		if ( ! $user_id ) {
			return sprintf(
				'<div class="ss-status ss-status--guest">%s</div>',
				esc_html__( 'Please log in to view your buyer status.', 'shopstore' )
			);
		}

		if ( ! $this->bridge_available() ) {
			return sprintf(
				'<div class="ss-status ss-status--muted">%s</div>',
				esc_html__( 'Marketplace bridge is not active. Buyer status is unavailable.', 'shopstore' )
			);
		}

		$retailer_id = $this->current_retailer_id();
		if ( null === $retailer_id ) {
			return sprintf(
				'<div class="ss-status ss-status--muted">%s</div>',
				esc_html__( 'No marketplace buyer profile is linked to this account yet. Please contact support.', 'shopstore' )
			);
		}

		$status = $this->current_status();
		if ( null === $status ) {
			return sprintf(
				'<div class="ss-status ss-status--muted">%s</div>',
				esc_html__( 'Buyer status is temporarily unavailable.', 'shopstore' )
			);
		}

		return sprintf(
			'<div class="ss-status ss-status--%s">%s</div>',
			esc_attr( $status ),
			esc_html( ss_theme_retailer_status_label( $status ) )
		);
	}

	/**
	 * 切换主题时确保 my-account 允许注册（B2B 前台注册买家的前提）。
	 */
	public function ensure_registration_enabled(): void {
		update_option( 'woocommerce_enable_myaccount_registration', 'yes' );
	}
}
