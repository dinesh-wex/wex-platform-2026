"""Async database engine and session management."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from wex_platform.app.config import get_settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for all models."""
    pass


settings = get_settings()

# Auto-detect driver from DATABASE_URL
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # SQLite needs check_same_thread=False
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """FastAPI dependency: yield an async database session."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables (for local dev). Use Alembic for production migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # SQLite doesn't support ADD COLUMN IF NOT EXISTS, so we run each
    # migration and silently ignore "duplicate column" errors.
    _migrations = [
        "ALTER TABLE smoke_test_events ADD COLUMN is_test BOOLEAN DEFAULT 0",
        "ALTER TABLE page_views ADD COLUMN is_test BOOLEAN DEFAULT 0",
        "ALTER TABLE lead_captures ADD COLUMN is_test BOOLEAN DEFAULT 0",
        "ALTER TABLE lead_captures ADD COLUMN session_id VARCHAR(100)",
        "ALTER TABLE lead_captures ADD COLUMN market_rate_low FLOAT",
        "ALTER TABLE lead_captures ADD COLUMN market_rate_high FLOAT",
        "ALTER TABLE lead_captures ADD COLUMN recommended_rate FLOAT",
        "ALTER TABLE property_profiles ADD COLUMN is_test BOOLEAN DEFAULT 0",
        "ALTER TABLE property_profiles ADD COLUMN market_rate_low FLOAT",
        "ALTER TABLE property_profiles ADD COLUMN market_rate_high FLOAT",
        "ALTER TABLE property_profiles ADD COLUMN recommended_rate FLOAT",
        "ALTER TABLE property_profiles ADD COLUMN primary_image_url VARCHAR(500)",
        "ALTER TABLE property_profiles ADD COLUMN image_urls JSON",
        # --- Engagement Lifecycle v3: account_created replaces contact_captured ---
        "ALTER TABLE engagements ADD COLUMN account_created_at DATETIME",
        "UPDATE engagements SET status = 'account_created', account_created_at = updated_at WHERE status = 'contact_captured'",
    ]

    if "sqlite" in settings.database_url:
        async with engine.begin() as conn:
            for stmt in _migrations:
                try:
                    await conn.execute(text(stmt))
                except Exception:
                    pass  # Column already exists — safe to ignore
