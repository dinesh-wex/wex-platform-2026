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
_is_sqlite = "sqlite" in settings.database_url
_connect_args = {}
if _is_sqlite:
    _connect_args["check_same_thread"] = False
    _connect_args["timeout"] = 30  # Wait up to 30s for write lock (default 5s)

_engine_kwargs = {
    "echo": False,  # Set True only when debugging SQL queries — very verbose
    "connect_args": _connect_args,
}
if not _is_sqlite:
    _engine_kwargs["pool_size"] = 5
    _engine_kwargs["max_overflow"] = 10

engine = create_async_engine(settings.database_url, **_engine_kwargs)

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
    # Ensure SMS models are registered with Base.metadata
    import wex_platform.domain.sms_models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Enable WAL mode for SQLite — allows concurrent reads + single writer
    # without "database is locked" errors from background tasks.
    if _is_sqlite:
        async with engine.begin() as conn:
            await conn.execute(text("PRAGMA journal_mode=WAL"))
            await conn.execute(text("PRAGMA busy_timeout=30000"))

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
        # --- Hold mechanic columns ---
        "ALTER TABLE engagements ADD COLUMN hold_expires_at DATETIME",
        "ALTER TABLE engagements ADD COLUMN hold_extended BOOLEAN DEFAULT 0",
        "ALTER TABLE engagements ADD COLUMN hold_extended_at DATETIME",
        "ALTER TABLE engagements ADD COLUMN hold_extended_until DATETIME",
        "ALTER TABLE engagements ADD COLUMN tour_notes TEXT",
        "ALTER TABLE warehouses ADD COLUMN available_sqft INTEGER",
        "UPDATE warehouses SET available_sqft = (SELECT tc.max_sqft FROM truth_cores tc WHERE tc.warehouse_id = warehouses.id) WHERE available_sqft IS NULL",
        # --- Property pipeline v2: add property_id FK to contextual_memories ---
        "ALTER TABLE contextual_memories ADD COLUMN property_id VARCHAR(36)",
        "ALTER TABLE engagements ADD COLUMN source_channel VARCHAR(10) DEFAULT 'web'",
        "ALTER TABLE sms_conversation_states ADD COLUMN search_session_token VARCHAR(64)",
        "ALTER TABLE sms_conversation_states ADD COLUMN name_requested_at_turn INTEGER",
    ]

    if "sqlite" in settings.database_url:
        async with engine.begin() as conn:
            for stmt in _migrations:
                try:
                    await conn.execute(text(stmt))
                except Exception:
                    pass  # Column already exists — safe to ignore

        # Backfill new property tables from legacy data
        from wex_platform.services.backfill_properties import backfill_properties
        async with async_session() as session:
            stats = await backfill_properties(session)
            if any(v > 0 for v in stats.values()):
                print(f"[init_db] Property backfill: {stats}")
