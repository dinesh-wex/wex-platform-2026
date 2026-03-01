"""FastAPI application entry point for the WEx Platform 2026 API."""

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from wex_platform.app.config import get_settings
from wex_platform.infra.database import async_session, init_db
from wex_platform.services.hold_monitor import check_hold_expiry_warnings, expire_holds
from wex_platform.services.vapi_assistant_config import register_vapi_phone_number

logger = logging.getLogger(__name__)


async def hold_monitor_loop():
    """Run hold monitoring jobs every 15 minutes."""
    while True:
        try:
            async with async_session() as db:
                await check_hold_expiry_warnings(db)
                expired_count = await expire_holds(db)
                if expired_count:
                    logger.info("Hold monitor: expired %d holds", expired_count)
        except Exception as e:
            logger.error("Hold monitor error: %s", e)
        await asyncio.sleep(15 * 60)  # 15 minutes


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize database on startup."""
    await init_db()

    # Register Vapi phone number (non-blocking: don't crash app if it fails)
    settings = get_settings()
    if settings.vapi_api_key:
        try:
            await register_vapi_phone_number(f"{settings.frontend_url}/api/voice/webhook")
        except Exception as e:
            logger.warning("Failed to register Vapi phone number: %s", e)

    asyncio.create_task(hold_monitor_loop())
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
from wex_platform.app.routes.buyer_sms import router as buyer_sms_router
from wex_platform.app.routes.enrichment import router as enrichment_router
from wex_platform.app.routes.search import router as search_router
from wex_platform.app.routes.supplier_dashboard import router as supplier_dashboard_router, upload_router
from wex_platform.app.routes.engagement import router as engagement_router, buyer_payments_router
from wex_platform.app.routes.qa import router as qa_router, knowledge_router, admin_knowledge_router, anonymous_qa_router
from wex_platform.app.routes.admin_engagements import router as admin_engagements_router, payment_admin_router
from wex_platform.app.routes.seed_engagements import router as seed_router
from wex_platform.app.routes.sms_reply_tool import router as sms_reply_router
from wex_platform.app.routes.sms_guarantee import router as sms_guarantee_router
from wex_platform.app.routes.sms_scheduler import router as sms_scheduler_router
from wex_platform.app.routes.sms_optin import router as sms_optin_router
from wex_platform.app.routes.vapi_webhook import router as vapi_webhook_router

app.include_router(auth_router)
app.include_router(agreements_router)
app.include_router(supplier_router)
app.include_router(buyer_router)
app.include_router(clearing_router)
app.include_router(admin_router)
app.include_router(dla_router)
app.include_router(browse_router)
app.include_router(sms_router)
app.include_router(buyer_sms_router)
app.include_router(enrichment_router)
app.include_router(search_router)
app.include_router(supplier_dashboard_router)
app.include_router(upload_router)
app.include_router(engagement_router)
app.include_router(buyer_payments_router)
app.include_router(qa_router)
app.include_router(knowledge_router)
app.include_router(admin_knowledge_router)
app.include_router(anonymous_qa_router)
app.include_router(admin_engagements_router)
app.include_router(payment_admin_router)
app.include_router(seed_router)
app.include_router(sms_reply_router)
app.include_router(sms_guarantee_router)
app.include_router(sms_scheduler_router)
app.include_router(sms_optin_router)
app.include_router(vapi_webhook_router)

# Static file mount for uploaded photos
_uploads_dir = Path(__file__).resolve().parents[3] / "uploads"
_uploads_dir.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_uploads_dir)), name="uploads")


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
