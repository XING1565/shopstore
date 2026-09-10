"""API v1 路由。"""

from fastapi import APIRouter

from . import brands, events, health, orders, products, retailers

router = APIRouter()
router.include_router(health.router)
router.include_router(events.router)
router.include_router(retailers.router)
router.include_router(brands.router)
router.include_router(products.router)
router.include_router(orders.router)
