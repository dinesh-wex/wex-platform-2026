"""SQLAlchemy ORM models for the WEx Platform.

All models use SQLite-compatible types:
- String(36) for UUID primary keys
- JSON for structured data (no JSONB)
- DateTime for timestamps (no TIMESTAMPTZ)
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from wex_platform.infra.database import Base


# ---------------------------------------------------------------------------
# Auth / User
# ---------------------------------------------------------------------------


class User(Base):
    """Platform user for authentication."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    role = Column(String(20), nullable=False, default="supplier")  # supplier, buyer, admin, broker
    is_active = Column(Boolean, default=True)
    email_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    last_login_at = Column(DateTime, nullable=True)
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=True)
    company_role = Column(String(20), nullable=True, default="admin")

    # Relationships
    company_ref = relationship("Company", back_populates="users")


class Company(Base):
    """Organization that owns warehouses. Every user belongs to exactly one company.

    For individuals, a single-member company is auto-created at registration.
    For businesses, the company has multiple users with different roles.
    Warehouse ownership is always via company_id, never via email or user_id.
    """

    __tablename__ = "companies"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255), nullable=False)
    type = Column(String(20), nullable=False, default="individual")  # individual, business
    created_at = Column(DateTime, default=func.now())

    # Relationships
    users = relationship("User", back_populates="company_ref")
    warehouses = relationship("Warehouse", back_populates="company_ref")


# ---------------------------------------------------------------------------
# Supplier Domain
# ---------------------------------------------------------------------------


class Warehouse(Base):
    """Physical warehouse building record."""

    __tablename__ = "warehouses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_name = Column(String(255))
    owner_email = Column(String(255))
    owner_phone = Column(String(50))
    company_id = Column(String(36), ForeignKey("companies.id"), nullable=True, index=True)
    # created_by is AUDIT ONLY. Never use for access control.
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    address = Column(String(500), nullable=False)
    city = Column(String(100))
    state = Column(String(50))
    zip = Column(String(20))
    lat = Column(Float)
    lng = Column(Float)
    neighborhood = Column(String(150))
    building_size_sqft = Column(Integer)
    lot_size_acres = Column(Float)
    year_built = Column(Integer)
    construction_type = Column(String(100))
    zoning = Column(String(100))
    property_type = Column(String(50))  # warehouse, distribution, manufacturing, flex, cold_storage
    primary_image_url = Column(String(500))
    image_urls = Column(JSON, default=[])
    description = Column(Text, nullable=True)
    source_url = Column(String(500))
    supplier_status = Column(String(50), default="third_party", index=True)
    earncheck_completed_at = Column(DateTime)
    onboarded_at = Column(DateTime)
    last_outreach_at = Column(DateTime)
    outreach_count = Column(Integer, default=0)
    last_response_time_hours = Column(Float)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    company_ref = relationship("Company", back_populates="warehouses")
    truth_core = relationship("TruthCore", back_populates="warehouse", uselist=False)
    memories = relationship("ContextualMemory", back_populates="warehouse")
    supplier_agreements = relationship("SupplierAgreement", back_populates="warehouse")
    supplier_ledger_entries = relationship("SupplierLedger", back_populates="warehouse")
    matches = relationship("Match", back_populates="warehouse")
    deals = relationship("Deal", back_populates="warehouse")
    toggle_history = relationship("ToggleHistory", back_populates="warehouse")
    insurance_coverages = relationship("InsuranceCoverage", back_populates="warehouse")


class TruthCore(Base):
    """Canonical source of truth for a warehouse's availability and terms."""

    __tablename__ = "truth_cores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(
        String(36), ForeignKey("warehouses.id"), unique=True, nullable=False
    )
    available_from = Column(DateTime)
    available_to = Column(DateTime)
    min_term_months = Column(Integer, default=1)
    max_term_months = Column(Integer, default=12)
    min_sqft = Column(Integer, nullable=False)
    max_sqft = Column(Integer, nullable=False)
    activity_tier = Column(String(50), nullable=False)
    constraints = Column(JSON, default={})
    supplier_rate_per_sqft = Column(Float, nullable=False)
    supplier_rate_max = Column(Float)
    buyer_rate_per_sqft = Column(Float, nullable=True)
    activation_status = Column(String(10), default="off")
    toggled_at = Column(DateTime)
    toggle_reason = Column(Text)
    tour_readiness = Column(String(50), default="48_hours")
    dock_doors_receiving = Column(Integer, default=0)
    dock_doors_shipping = Column(Integer, default=0)
    drive_in_bays = Column(Integer, default=0)
    parking_spaces = Column(Integer, default=0)
    clear_height_ft = Column(Float)
    has_office_space = Column(Boolean, default=False)
    has_sprinkler = Column(Boolean, default=False)
    power_supply = Column(String(100))
    trust_level = Column(Integer, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    warehouse = relationship("Warehouse", back_populates="truth_core")
    supplier_agreements = relationship("SupplierAgreement", back_populates="truth_core")
    truth_core_changes = relationship("TruthCoreChange", back_populates="truth_core")


class ContextualMemory(Base):
    """AI-curated memory fragments associated with a warehouse.

    memory_type values: owner_preference, buyer_feedback, deal_outcome,
    feature_intelligence, market_context, outreach_response, enrichment_response
    """

    __tablename__ = "contextual_memories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    memory_type = Column(String(50))
    content = Column(Text, nullable=False)
    source = Column(String(50))
    confidence = Column(Float, default=1.0)
    metadata_ = Column("metadata", JSON, default={})
    created_at = Column(DateTime, default=func.now())

    # Relationships
    warehouse = relationship("Warehouse", back_populates="memories")


class SupplierAgreement(Base):
    """Legal agreement between WEx and a warehouse supplier."""

    __tablename__ = "supplier_agreements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    truth_core_id = Column(String(36), ForeignKey("truth_cores.id"), nullable=False)
    agreement_type = Column(String(50), default="network_agreement")
    agreement_version = Column(String(20), default="1.0")
    status = Column(String(20), default="draft")
    terms_json = Column(JSON, nullable=False)
    signed_at = Column(DateTime)
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    warehouse = relationship("Warehouse", back_populates="supplier_agreements")
    truth_core = relationship("TruthCore", back_populates="supplier_agreements")


class SupplierLedger(Base):
    """Financial ledger for supplier-side transactions."""

    __tablename__ = "supplier_ledger"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    deal_id = Column(String(36))
    entry_type = Column(String(50))
    amount = Column(Float, nullable=False)
    description = Column(Text)
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=func.now())

    # Relationships
    warehouse = relationship("Warehouse", back_populates="supplier_ledger_entries")


# ---------------------------------------------------------------------------
# Buyer Domain
# ---------------------------------------------------------------------------


class Buyer(Base):
    """A buyer seeking warehouse space."""

    __tablename__ = "buyers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(255))
    company = Column(String(255))
    email = Column(String(255))
    phone = Column(String(50))
    created_at = Column(DateTime, default=func.now())

    # Relationships
    needs = relationship("BuyerNeed", back_populates="buyer")
    conversations = relationship("BuyerConversation", back_populates="buyer")
    buyer_agreements = relationship("BuyerAgreement", back_populates="buyer")
    buyer_ledger_entries = relationship("BuyerLedger", back_populates="buyer")
    deals = relationship("Deal", back_populates="buyer")
    deposits = relationship("Deposit", back_populates="buyer")


class BuyerNeed(Base):
    """A buyer's specific warehouse space requirement."""

    __tablename__ = "buyer_needs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=True)
    city = Column(String(100))
    state = Column(String(50))
    lat = Column(Float)
    lng = Column(Float)
    radius_miles = Column(Float, default=25)
    min_sqft = Column(Integer)
    max_sqft = Column(Integer)
    use_type = Column(String(50))
    needed_from = Column(DateTime)
    duration_months = Column(Integer)
    max_budget_per_sqft = Column(Float)
    requirements = Column(JSON, default={})
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    buyer = relationship("Buyer", back_populates="needs")
    conversations = relationship("BuyerConversation", back_populates="buyer_need")
    matches = relationship("Match", back_populates="buyer_need")


class BuyerConversation(Base):
    """Chat conversation with a buyer, stored as a JSON message log."""

    __tablename__ = "buyer_conversations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"))
    messages = Column(JSON, default=[])
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    buyer = relationship("Buyer", back_populates="conversations")
    buyer_need = relationship("BuyerNeed", back_populates="conversations")


class BuyerAgreement(Base):
    """Legal agreement between WEx and a buyer for a deal."""

    __tablename__ = "buyer_agreements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    deal_id = Column(String(36))
    agreement_type = Column(String(50), default="occupancy_guarantee")
    agreement_version = Column(String(20), default="1.0")
    buyer_rate_per_sqft = Column(Float, nullable=True)
    terms_json = Column(JSON, nullable=True)
    status = Column(String(20), default="draft")
    signed_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    buyer = relationship("Buyer", back_populates="buyer_agreements")


class BuyerLedger(Base):
    """Financial ledger for buyer-side transactions."""

    __tablename__ = "buyer_ledger"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    deal_id = Column(String(36))
    entry_type = Column(String(50))
    amount = Column(Float, nullable=False)
    description = Column(Text)
    period_start = Column(DateTime)
    period_end = Column(DateTime)
    status = Column(String(20), default="pending")
    created_at = Column(DateTime, default=func.now())

    # Relationships
    buyer = relationship("Buyer", back_populates="buyer_ledger_entries")


# ---------------------------------------------------------------------------
# Clearing Engine Domain
# ---------------------------------------------------------------------------


class Match(Base):
    """A scored match between a buyer need and a warehouse."""

    __tablename__ = "matches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=False)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    match_score = Column(Float)
    confidence = Column(Float)
    instant_book_eligible = Column(Boolean, default=False)
    reasoning = Column(Text)
    scoring_breakdown = Column(JSON)
    status = Column(String(20), default="pending")
    declined_reason = Column(Text)
    presented_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    buyer_need = relationship("BuyerNeed", back_populates="matches")
    warehouse = relationship("Warehouse", back_populates="matches")
    deals = relationship("Deal", back_populates="match")
    instant_book_score = relationship(
        "InstantBookScore", back_populates="match", uselist=False
    )


class Deal(Base):
    """A deal progressing through its lifecycle from terms to completion."""

    __tablename__ = "deals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(String(36), ForeignKey("matches.id"))
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    sqft_allocated = Column(Integer, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime)
    term_months = Column(Integer)
    supplier_rate = Column(Float, nullable=False)
    buyer_rate = Column(Float, nullable=False)
    spread_pct = Column(Float)
    monthly_revenue = Column(Float)
    tour_scheduled_at = Column(DateTime)
    tour_completed_at = Column(DateTime)
    tour_outcome = Column(String(50))
    tour_pass_reason = Column(Text)
    # Anti-circumvention tour flow fields
    guarantee_signed_at = Column(DateTime)
    address_revealed_at = Column(DateTime)
    tour_status = Column(String(30))  # requested / confirmed / completed / cancelled / rescheduled
    tour_preferred_date = Column(String(20))
    tour_preferred_time = Column(String(20))
    tour_notes = Column(Text)
    supplier_confirmed_at = Column(DateTime)
    supplier_proposed_date = Column(String(20))
    supplier_proposed_time = Column(String(20))
    follow_up_sent_at = Column(DateTime)
    follow_up_response = Column(Text)
    status = Column(String(30), default="terms_presented")
    deal_type = Column(String(20), default="standard")
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    match = relationship("Match", back_populates="deals")
    warehouse = relationship("Warehouse", back_populates="deals")
    buyer = relationship("Buyer", back_populates="deals")
    events = relationship("DealEvent", back_populates="deal")
    insurance_coverages = relationship("InsuranceCoverage", back_populates="deal")
    deposits = relationship("Deposit", back_populates="deal")


class DealEvent(Base):
    """Immutable event log entry for a deal."""

    __tablename__ = "deal_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False)
    event_type = Column(String(100), nullable=False)
    details = Column(JSON, default={})
    created_at = Column(DateTime, default=func.now())

    # Relationships
    deal = relationship("Deal", back_populates="events")


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class ToggleHistory(Base):
    """Audit trail for warehouse activation status changes."""

    __tablename__ = "toggle_history"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    previous_status = Column(String(10))
    new_status = Column(String(10))
    reason = Column(Text)
    in_flight_matches = Column(Integer, default=0)
    grace_period_until = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    warehouse = relationship("Warehouse", back_populates="toggle_history")


class TruthCoreChange(Base):
    """Audit trail for changes to a TruthCore record."""

    __tablename__ = "truth_core_changes"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    truth_core_id = Column(String(36), ForeignKey("truth_cores.id"), nullable=False)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    field_changed = Column(String(100), nullable=False)
    old_value = Column(Text)
    new_value = Column(Text)
    changed_by = Column(String(100))
    change_reason = Column(Text)
    toggle_was_on = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    truth_core = relationship("TruthCore", back_populates="truth_core_changes")


# ---------------------------------------------------------------------------
# Insurance & Risk
# ---------------------------------------------------------------------------


class InstantBookScore(Base):
    """Composite scoring for instant-book eligibility."""

    __tablename__ = "instant_book_scores"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    match_id = Column(String(36), ForeignKey("matches.id"), nullable=False)
    truth_core_completeness = Column(Float)
    contextual_memory_depth = Column(Float)
    supplier_trust_level = Column(Float)
    match_specificity = Column(Float)
    feature_alignment = Column(Float)
    composite_score = Column(Float)
    instant_book_eligible = Column(Boolean)
    threshold_used = Column(Integer, default=75)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    match = relationship("Match", back_populates="instant_book_score")


class InsuranceCoverage(Base):
    """Insurance coverage attached to a deal."""

    __tablename__ = "insurance_coverages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    coverage_status = Column(String(20), default="active")
    coverage_amount = Column(Float)
    monthly_premium = Column(Float)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    deal = relationship("Deal", back_populates="insurance_coverages")
    warehouse = relationship("Warehouse", back_populates="insurance_coverages")


class Deposit(Base):
    """Deposit held for a deal (security or first month)."""

    __tablename__ = "deposits"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=False)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    deposit_type = Column(String(30), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String(20), default="held")
    applied_reason = Column(Text)
    created_at = Column(DateTime, default=func.now())
    released_at = Column(DateTime)

    # Relationships
    deal = relationship("Deal", back_populates="deposits")
    buyer = relationship("Buyer", back_populates="deposits")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


class AgentLog(Base):
    """Telemetry log for AI agent actions."""

    __tablename__ = "agent_logs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    agent_name = Column(String(100), nullable=False)
    action = Column(String(200), nullable=False)
    input_summary = Column(Text)
    output_summary = Column(Text)
    tokens_used = Column(Integer)
    latency_ms = Column(Integer)
    related_warehouse_id = Column(String(36))
    related_buyer_id = Column(String(36))
    related_deal_id = Column(String(36))
    created_at = Column(DateTime, default=func.now())


class SmokeTestEvent(Base):
    """Tracks supplier funnel events for the smoke test."""
    __tablename__ = "smoke_test_events"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    event = Column(String, nullable=False, index=True)
    properties = Column(JSON, default={})
    session_id = Column(String, nullable=False, index=True)
    # Denormalized columns for fast querying (also stored in properties JSON)
    email = Column(String, index=True)
    address = Column(String)
    city = Column(String, index=True)
    state = Column(String, index=True)
    zip = Column(String, index=True)
    is_test = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class LeadCapture(Base):
    """Captured lead from the verify-lead form (email CTA click)."""
    __tablename__ = "lead_captures"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String, nullable=False, index=True)
    address = Column(String)
    full_name = Column(String)
    phone = Column(String)
    company = Column(String)
    sqft = Column(Integer)
    revenue = Column(Float)
    rate = Column(Float)
    market_rate_low = Column(Float)
    market_rate_high = Column(Float)
    recommended_rate = Column(Float)
    pricing_path = Column(String)
    source = Column(String, default="earncheck_email")
    session_id = Column(String, index=True)
    is_test = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class PageView(Base):
    """Lightweight page-view tracker — replaces external analytics for simple metrics."""
    __tablename__ = "page_views"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    path = Column(String, nullable=False, index=True)
    referrer = Column(String)
    utm_source = Column(String)
    utm_medium = Column(String)
    utm_campaign = Column(String)
    user_agent = Column(String)
    ip = Column(String)
    session_id = Column(String, index=True)
    is_test = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class MarketRateCache(Base):
    """Caches Gemini Search grounded NNN lease rates by zipcode (30-day TTL)."""
    __tablename__ = "market_rate_cache"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    zipcode = Column(String, nullable=False, unique=True, index=True)
    nnn_low = Column(Float, nullable=False)
    nnn_high = Column(Float, nullable=False)
    source_context = Column(String, default="")
    fetched_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class DLAToken(Base):
    """Demand-Led Activation token for off-network supplier outreach."""

    __tablename__ = "dla_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(64), unique=True, index=True, nullable=False)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=False)
    suggested_rate = Column(Float)
    supplier_rate = Column(Float)  # counter-rate if proposed
    rate_accepted = Column(Boolean)
    status = Column(
        String(30), default="pending"
    )  # pending, interested, rate_decided, confirmed, declined, expired
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=func.now())
    responded_at = Column(DateTime)
    outreach_channel = Column(String(20), default="sms")  # sms, email
    agreement_ref = Column(String(255))  # signed agreement reference
    decline_reason = Column(Text)
    last_step_reached = Column(String(50))  # property_confirm, deal, rate_decision, agreement

    # Relationships
    warehouse = relationship("Warehouse", backref="dla_tokens")
    buyer_need = relationship("BuyerNeed", backref="dla_tokens")


class PropertyProfile(Base):
    """Living AI-enriched property dossier linking address -> person.

    Progressively built across the EarnCheck funnel:
      Trigger 1: Gemini search completes -> building specs + AI summary v1
      Trigger 2: Configurator completed -> user preferences + AI summary v2
      Trigger 3: Email submitted -> pricing + email + AI summary v3
    """
    __tablename__ = "property_profiles"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)
    warehouse_id = Column(String, index=True)
    email = Column(String, index=True)
    address = Column(String, index=True)
    city = Column(String)
    state = Column(String)
    zip = Column(String)

    # --- Structured fields (from configurator) ---
    sqft = Column(Integer)
    min_rentable = Column(Integer)
    activity_tier = Column(String)          # storage_only | storage_light_assembly
    has_office = Column(Boolean)
    weekend_access = Column(Boolean)
    min_term_months = Column(Integer)
    availability_start = Column(String)
    pricing_path = Column(String)           # set_rate | commission
    rate_per_sqft = Column(Float)
    market_rate_low = Column(Float)
    market_rate_high = Column(Float)
    recommended_rate = Column(Float)
    is_test = Column(Boolean, default=False)

    # --- Building specs (from Gemini search) ---
    building_size_sqft = Column(Integer)
    clear_height_ft = Column(Float)
    dock_doors = Column(Integer)
    drive_in_bays = Column(Integer)
    parking_spaces = Column(Integer)
    year_built = Column(Integer)
    construction_type = Column(String)
    has_sprinkler = Column(Boolean)
    power_supply = Column(String)
    zoning = Column(String)

    # --- Extended building specs (from Gemini, currently JSON-only) ---
    building_class = Column(String)         # A | B | C
    trailer_parking = Column(Integer)
    rail_served = Column(Boolean)
    fenced_yard = Column(Boolean)
    column_spacing_ft = Column(String)
    number_of_stories = Column(Integer)
    warehouse_heated = Column(Boolean)
    year_renovated = Column(Integer)
    available_sqft = Column(Integer)
    lot_size_acres = Column(Float)

    # --- Images (copied from Warehouse on activation) ---
    primary_image_url = Column(String(500))
    image_urls = Column(JSON, default=[])

    # --- AI fields ---
    additional_notes = Column(Text)         # Raw user free-text from "Tell us more"
    ai_profile_summary = Column(Text)       # AI-generated structured summary (living doc)
    profile_version = Column(Integer, default=0)

    # --- Timestamps ---
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Search Sessions (anonymous buyer search - no account required)
# ---------------------------------------------------------------------------


class SearchSession(Base):
    """Anonymous search session — stores requirements + results before buyer registers."""

    __tablename__ = "search_sessions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    token = Column(String(64), unique=True, nullable=False, index=True)
    requirements = Column(JSON, nullable=False)       # The buyer requirements dict
    results = Column(JSON, default={})                 # Cached tier1/tier2 results
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=True)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=True)
    status = Column(String(20), default="active")      # active, promoted, expired
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=func.now())

    buyer_need = relationship("BuyerNeed")


# ---------------------------------------------------------------------------
# Supplier Dashboard Domain
# ---------------------------------------------------------------------------


class NearMiss(Base):
    """A property that nearly matched a buyer need but was excluded or not selected."""

    __tablename__ = "near_misses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=False)
    match_score = Column(Float, nullable=True)
    outcome = Column(String(50))  # NearMissOutcome
    reasons = Column(JSON)  # array of {field, detail, fix}
    evaluated_at = Column(DateTime)

    # Relationships
    warehouse = relationship("Warehouse", backref="near_misses")
    buyer_need = relationship("BuyerNeed", backref="near_misses")


class SupplierResponse(Base):
    """Tracks supplier responses to deal pings, DLA outreach, tour requests, etc."""

    __tablename__ = "supplier_responses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    supplier_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    deal_id = Column(String(36), ForeignKey("deals.id"), nullable=True)
    dla_token = Column(String(64), nullable=True)
    event_type = Column(String(50))  # SupplierResponseEventType
    sent_at = Column(DateTime)
    deadline_at = Column(DateTime)
    responded_at = Column(DateTime, nullable=True)
    response_time_hours = Column(Float, nullable=True)
    outcome = Column(String(50), nullable=True)  # SupplierResponseOutcome
    decline_reason = Column(String(255), nullable=True)
    counter_rate = Column(Float, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    warehouse = relationship("Warehouse", backref="supplier_responses")
    supplier = relationship("User", backref="supplier_responses")
    deal = relationship("Deal", backref="supplier_responses")


class BuyerEngagement(Base):
    """Tracks how buyers engage with a property in search results."""

    __tablename__ = "buyer_engagements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    property_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=False)
    shown_at = Column(DateTime)
    position_in_results = Column(Integer)
    tier = Column(String(20))  # ResultTier
    action_taken = Column(String(50), nullable=True)  # BuyerEngagementAction
    action_at = Column(DateTime, nullable=True)
    time_on_page_seconds = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    warehouse = relationship("Warehouse", backref="buyer_engagements")
    buyer_need = relationship("BuyerNeed", backref="buyer_engagements")


class UploadToken(Base):
    """Tokenized upload access for property photos (no auth required)."""

    __tablename__ = "upload_tokens"

    token = Column(String(64), primary_key=True)
    property_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    is_used = Column(Boolean, default=False)

    # Relationships
    warehouse = relationship("Warehouse", backref="upload_tokens")


# ---------------------------------------------------------------------------
# Engagement Lifecycle Domain
# ---------------------------------------------------------------------------


class Engagement(Base):
    """Central engagement tracking object from match through active lease."""

    __tablename__ = "engagements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=False)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=True)
    # supplier_id is AUDIT ONLY — records who actioned the deal ping.
    # Never use for authorization. Use company_id via the property FK instead.
    supplier_id = Column(String(36), ForeignKey("users.id"), nullable=False)

    # Status
    status = Column(String(50), nullable=False, default="deal_ping_sent", index=True)
    tier = Column(String(20), nullable=False)  # EngagementTier
    path = Column(String(20), nullable=True)  # EngagementPath — set when buyer chooses

    # Matching
    match_score = Column(Float)
    match_rank = Column(Integer)

    # Pricing
    supplier_rate_sqft = Column(Numeric(10, 4))
    buyer_rate_sqft = Column(Numeric(10, 4))
    monthly_supplier_payout = Column(Numeric(12, 2))
    monthly_buyer_total = Column(Numeric(12, 2))
    sqft = Column(Integer)

    # Deal ping
    deal_ping_sent_at = Column(DateTime, nullable=True)
    deal_ping_expires_at = Column(DateTime, nullable=True)
    deal_ping_responded_at = Column(DateTime, nullable=True)

    # Supplier terms (Tier 2)
    supplier_terms_accepted = Column(Boolean, default=False)
    supplier_terms_version = Column(String(100), nullable=True)

    # Buyer contact
    buyer_email = Column(String(255), nullable=True)
    buyer_phone = Column(String(50), nullable=True)
    buyer_company_name = Column(String(255), nullable=True)

    # Guarantee
    guarantee_signed_at = Column(DateTime, nullable=True)
    guarantee_ip_address = Column(String(45), nullable=True)
    guarantee_terms_version = Column(String(100), nullable=True)

    # Tour
    tour_requested_at = Column(DateTime, nullable=True)
    tour_requested_date = Column(Date, nullable=True)
    tour_requested_time = Column(String(20), nullable=True)  # e.g. "10:00 AM"
    tour_confirmed_at = Column(DateTime, nullable=True)
    tour_scheduled_date = Column(DateTime, nullable=True)
    tour_completed_at = Column(DateTime, nullable=True)
    tour_reschedule_count = Column(Integer, default=0)
    tour_rescheduled_date = Column(Date, nullable=True)
    tour_rescheduled_time = Column(String(20), nullable=True)
    tour_rescheduled_by = Column(String(20), nullable=True)  # EngagementActor value
    tour_outcome = Column(String(30), nullable=True)  # TourOutcome

    # Instant book
    instant_book_requested_at = Column(DateTime, nullable=True)
    instant_book_confirmed_at = Column(DateTime, nullable=True)

    # Agreement
    agreement_sent_at = Column(DateTime, nullable=True)
    agreement_signed_at = Column(DateTime, nullable=True)

    # Onboarding
    onboarding_started_at = Column(DateTime, nullable=True)
    onboarding_completed_at = Column(DateTime, nullable=True)
    insurance_uploaded = Column(Boolean, default=False)
    company_docs_uploaded = Column(Boolean, default=False)
    payment_method_added = Column(Boolean, default=False)

    # Lease
    term_months = Column(Integer, nullable=True)  # Snapshotted from BuyerNeed.duration_months at creation
    lease_start_date = Column(Date, nullable=True)
    lease_end_date = Column(Date, nullable=True)

    # Decline
    declined_by = Column(String(20), nullable=True)  # DeclineParty
    decline_reason = Column(String(500), nullable=True)
    declined_at = Column(DateTime, nullable=True)

    # Cancellation
    cancelled_by = Column(String(20), nullable=True)  # CancelledBy
    cancel_reason = Column(String(500), nullable=True)
    cancelled_at = Column(DateTime, nullable=True)

    # Admin
    admin_notes = Column(Text, nullable=True)
    admin_flagged = Column(Boolean, default=False)
    admin_flag_reason = Column(String(500), nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    events = relationship("EngagementEvent", back_populates="engagement")
    warehouse = relationship("Warehouse", backref="engagements")
    buyer_need = relationship("BuyerNeed", backref="engagements")
    buyer = relationship("Buyer", backref="engagements")
    supplier = relationship("User", backref="engagements")


class EngagementEvent(Base):
    """Immutable audit trail entry for engagement state transitions."""

    __tablename__ = "engagement_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String(36), ForeignKey("engagements.id"), nullable=False)
    event_type = Column(String(100), nullable=False)  # EngagementEventType
    actor = Column(String(20), nullable=False)  # EngagementActor
    actor_id = Column(String(36), nullable=True)
    from_status = Column(String(50), nullable=True)  # EngagementStatus
    to_status = Column(String(50), nullable=True)  # EngagementStatus
    data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=func.now())

    # Relationships
    engagement = relationship("Engagement", back_populates="events")


class EngagementAgreement(Base):
    """Per-engagement lease agreement with dual-sign workflow."""

    __tablename__ = "engagement_agreements"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String(36), ForeignKey("engagements.id"), nullable=False)
    version = Column(Integer, default=1)
    status = Column(String(30), nullable=False, default="pending")  # AgreementSignStatus
    terms_text = Column(Text, nullable=False)

    # Pricing snapshot
    buyer_rate_sqft = Column(Numeric(10, 4))
    supplier_rate_sqft = Column(Numeric(10, 4))
    monthly_buyer_total = Column(Numeric(12, 2))
    monthly_supplier_payout = Column(Numeric(12, 2))

    # Signing timestamps
    sent_at = Column(DateTime, nullable=False)
    buyer_signed_at = Column(DateTime, nullable=True)
    supplier_signed_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=False)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    engagement = relationship("Engagement", backref="agreements")


class PropertyQuestion(Base):
    """Q&A question with AI routing for a property engagement."""

    __tablename__ = "property_questions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String(36), ForeignKey("engagements.id"), nullable=False)
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    question_text = Column(Text, nullable=False)

    # Status
    status = Column(String(30), nullable=False, default="submitted")  # QuestionStatus

    # AI routing
    ai_answer = Column(Text, nullable=True)
    ai_confidence = Column(Float, nullable=True)

    # Supplier routing
    supplier_answer = Column(Text, nullable=True)

    # Final answer
    final_answer = Column(Text, nullable=True)
    final_answer_source = Column(String(20), nullable=True)  # 'ai', 'supplier', 'admin'

    # Supplier deadline tracking
    routed_to_supplier_at = Column(DateTime, nullable=True)
    supplier_answered_at = Column(DateTime, nullable=True)
    supplier_deadline_at = Column(DateTime, nullable=True)

    # Timer pause (post-tour deadline pause while Q&A open)
    timer_paused_at = Column(DateTime, nullable=True)
    timer_resumed_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())

    # Relationships
    engagement = relationship("Engagement", backref="questions")
    warehouse = relationship("Warehouse", backref="property_questions")
    buyer = relationship("Buyer", backref="property_questions")


class PropertyKnowledgeEntry(Base):
    """Property knowledge base entry built from Q&A answers."""

    __tablename__ = "property_knowledge_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    warehouse_id = Column(String(36), ForeignKey("warehouses.id"), nullable=False)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source = Column(String(20), nullable=False)  # 'ai', 'supplier', 'admin'
    source_question_id = Column(String(36), ForeignKey("property_questions.id"), nullable=True)
    confidence = Column(Float, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    warehouse = relationship("Warehouse", backref="knowledge_entries")
    source_question = relationship("PropertyQuestion", backref="knowledge_entries")


class PaymentRecord(Base):
    """Buyer/supplier payment tracking for an engagement period."""

    __tablename__ = "payment_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    engagement_id = Column(String(36), ForeignKey("engagements.id"), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)

    # Amounts
    buyer_amount = Column(Numeric(12, 2), nullable=False)
    supplier_amount = Column(Numeric(12, 2), nullable=False)
    wex_amount = Column(Numeric(12, 2), nullable=False)

    # Statuses
    buyer_status = Column(String(20), nullable=False, default="upcoming")  # BuyerPaymentStatus
    supplier_status = Column(String(20), nullable=False, default="upcoming")  # SupplierPaymentStatus

    # Payment timestamps
    buyer_invoiced_at = Column(DateTime, nullable=True)
    buyer_paid_at = Column(DateTime, nullable=True)
    supplier_scheduled_at = Column(DateTime, nullable=True)
    supplier_deposited_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationships
    engagement = relationship("Engagement", backref="payment_records")
