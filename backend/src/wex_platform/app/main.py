"""FastAPI application entry point for the WEx Platform 2026 API."""

import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from wex_platform.app.config import get_settings
from wex_platform.infra.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database on startup."""
    await init_db()
    yield


settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.INFO if settings.debug else logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = FastAPI(
    title="WEx Platform 2026 API",
    lifespan=lifespan,
    debug=settings.debug,
)

# CORS middleware — allow all origins in debug mode for LAN/IP access
_cors_origins = settings.cors_origins_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=("*" not in _cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Route includes
# ---------------------------------------------------------------------------
from wex_platform.app.routes.auth import router as auth_router
from wex_platform.app.routes.agreements import router as agreements_router
from wex_platform.app.routes.supplier import router as supplier_router
from wex_platform.app.routes.buyer import router as buyer_router
from wex_platform.app.routes.clearing import router as clearing_router
from wex_platform.app.routes.admin import router as admin_router
from wex_platform.app.routes.dla import router as dla_router
from wex_platform.app.routes.browse import router as browse_router
from wex_platform.app.routes.sms import router as sms_router
from wex_platform.app.routes.enrichment import router as enrichment_router
from wex_platform.app.routes.search import router as search_router

app.include_router(auth_router)
app.include_router(agreements_router)
app.include_router(supplier_router)
app.include_router(buyer_router)
app.include_router(clearing_router)
app.include_router(admin_router)
app.include_router(dla_router)
app.include_router(browse_router)
app.include_router(sms_router)
app.include_router(enrichment_router)
app.include_router(search_router)


@app.get("/health", tags=["health"])
async def health_check():
    """Return service health status."""
    return {"status": "ok", "service": "wex-platform"}


def run() -> None:
    """Run the application with uvicorn (used by project.scripts entry point)."""
    uvicorn.run(
        "wex_platform.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
