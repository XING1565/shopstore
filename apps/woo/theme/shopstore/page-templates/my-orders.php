<?php
/**
 * Template Name: My Orders (B2B)
 *
 * 订单状态展示页（投影 Core 状态）。直接输出 [shopstore_my_orders] shortcode，
 * 供「我的订单」页面选用。也可在任意页面正文直接使用 [shopstore_my_orders]。
 */

get_header();

while ( have_posts() ) :
	the_post();
	?>
	<article id="post-<?php the_ID(); ?>" <?php post_class(); ?>>
		<header class="entry-header">
			<h1 class="entry-title"><?php the_title(); ?></h1>
		</header>
		<div class="entry-content">
			<?php echo do_shortcode( '[shopstore_my_orders]' ); // phpcs:ignore WordPress.Security.EscapeOutput.OutputNotEscaped ?>
		</div>
	</article>
	<?php
endwhile;

get_footer();
