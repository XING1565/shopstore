<?php
/**
 * 页脚模板。
 */
?>
	</div>
</main>

<footer class="site-footer">
	<div class="container">
		<p class="site-footer__copyright">
			&copy; <?php echo esc_html( gmdate( 'Y' ) ); ?>
			<?php bloginfo( 'name' ); ?>
		</p>
	</div>
</footer>

<?php wp_footer(); ?>
</body>
</html>
