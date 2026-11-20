"""FastAPI entry point. Each module's api.py router is included here as the module is built."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.modules.judge.api import router as guide_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AaharOS API", version="0.1.0", summary="Every gram traced. Every rupee explained.")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)

    @app.get("/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.env}

    app.include_router(guide_router)
    return app


app = create_app()
