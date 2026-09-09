"""FastAPI 应用工厂与入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .api import health as root_health
from .api import v1
from .config import get_settings
from .errors import register_exception_handlers
from .logging import configure_logging
from .middleware import RequestContextMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(get_settings().log_level)
    yield


def create_app() -> FastAPI:
    settings = get_settings()

    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        debug=settings.app_debug,
    )

    application.add_middleware(RequestContextMiddleware)
    application.include_router(root_health.router)
    application.include_router(v1.router, prefix=settings.api_v1_prefix)
    register_exception_handlers(application)

    return application


app = create_app()
