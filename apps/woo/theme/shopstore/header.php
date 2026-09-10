<?php
/**
 * 页头模板。
 */
?>
<!doctype html>
<html <?php language_attributes(); ?>>
<head>
	<meta charset="<?php bloginfo( 'charset' ); ?>" />
	<meta name="viewport" content="width=device-width, initial-scale=1" />
	<?php wp_head(); ?>
</head>
<body <?php body_class(); ?>>
<?php wp_body_open(); ?>

<header class="site-header">
	<div class="container">
		<div class="site-branding">
			<?php if ( has_custom_logo() ) : ?>
				<?php the_custom_logo(); ?>
			<?php else : ?>
				<a class="site-title" href="<?php echo esc_url( home_url( '/' ) ); ?>">
					<?php bloginfo( 'name' ); ?>
				</a>
			<?php endif; ?>
		</div>

		<nav class="site-nav" aria-label="<?php esc_attr_e( 'Primary', 'shopstore' ); ?>">
			<?php
			wp_nav_menu(
				array(
					'theme_location' => 'primary',
					'container'      => false,
					'fallback_cb'    => false,
				)
			);
			?>
		</nav>

		<div class="site-account">
			<?php
			$account_url = function_exists( 'wc_get_page_permalink' )
				? wc_get_page_permalink( 'myaccount' )
				: wp_login_url();
			?>
			<a href="<?php echo esc_url( $account_url ); ?>">
				<?php echo is_user_logged_in() ? esc_html__( 'My account', 'shopstore' ) : esc_html__( 'Log in', 'shopstore' ); ?>
			</a>
		</div>
	</div>
</header>

<main class="site-main">
	<div class="container">
