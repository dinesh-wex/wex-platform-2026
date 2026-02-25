"""Pydantic v2 schemas for API request/response validation."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class UserCreate(BaseModel):
    """Schema for creating a new user."""

    email: str
    password: str
    name: str
    role: str = "supplier"
    company: str | None = None
    phone: str | None = None


class UserLogin(BaseModel):
    """Schema for user login."""

    email: str
    password: str


class UserResponse(BaseModel):
    """Schema for user API responses."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    role: str
    company: str | None = None
    company_id: str | None = None
    company_role: str | None = None
    phone: str | None = None
    is_active: bool
    email_verified: bool


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    name: str | None = None
    company: str | None = None
    phone: str | None = None


class TokenResponse(BaseModel):
    """Schema for JWT token responses."""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    service: str


# ---------------------------------------------------------------------------
# Warehouse
# ---------------------------------------------------------------------------


class WarehouseBase(BaseModel):
    """Base warehouse fields shared across create and response."""

    owner_name: str | None = None
    owner_email: str | None = None
    owner_phone: str | None = None
    address: str
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    lat: float | None = None
    lng: float | None = None
    building_size_sqft: int | None = None
    lot_size_acres: float | None = None
    year_built: int | None = None
    construction_type: str | None = None
    zoning: str | None = None
    primary_image_url: str | None = None
    image_urls: list[str] = []
    source_url: str | None = None


class WarehouseCreate(WarehouseBase):
    """Schema for creating a new warehouse."""

    pass


class WarehouseResponse(WarehouseBase):
    """Schema for warehouse API responses."""

    id: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# TruthCore
# ---------------------------------------------------------------------------


class TruthCoreBase(BaseModel):
    """Base truth core fields."""

    warehouse_id: str
    available_from: datetime | None = None
    available_to: datetime | None = None
    min_term_months: int = 1
    max_term_months: int = 12
    min_sqft: int
    max_sqft: int
    activity_tier: str
    constraints: dict = {}
    supplier_rate_per_sqft: float
    supplier_rate_max: float | None = None
    activation_status: str = "off"
    tour_readiness: str = "48_hours"
    dock_doors_receiving: int = 0
    dock_doors_shipping: int = 0
    drive_in_bays: int = 0
    parking_spaces: int = 0
    clear_height_ft: float | None = None
    has_office_space: bool = False
    has_sprinkler: bool = False
    power_supply: str | None = None
    trust_level: int = 0


class TruthCoreCreate(TruthCoreBase):
    """Schema for creating a new truth core."""

    pass


class TruthCoreResponse(TruthCoreBase):
    """Schema for truth core API responses."""

    id: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Buyer
# ---------------------------------------------------------------------------


class BuyerBase(BaseModel):
    """Base buyer fields."""

    name: str | None = None
    company: str | None = None
    email: str | None = None
    phone: str | None = None


class BuyerCreate(BuyerBase):
    """Schema for creating a new buyer."""

    pass


class BuyerResponse(BuyerBase):
    """Schema for buyer API responses."""

    id: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# BuyerNeed
# ---------------------------------------------------------------------------


class BuyerNeedBase(BaseModel):
    """Base buyer need fields."""

    buyer_id: str
    city: str | None = None
    state: str | None = None
    lat: float | None = None
    lng: float | None = None
    radius_miles: float = 25
    min_sqft: int | None = None
    max_sqft: int | None = None
    use_type: str | None = None
    needed_from: datetime | None = None
    duration_months: int | None = None
    max_budget_per_sqft: float | None = None
    requirements: dict = {}
    status: str = "active"


class BuyerNeedCreate(BuyerNeedBase):
    """Schema for creating a new buyer need."""

    pass


class BuyerNeedResponse(BuyerNeedBase):
    """Schema for buyer need API responses."""

    id: str
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Match
# ---------------------------------------------------------------------------


class MatchResponse(BaseModel):
    """Schema for match API responses."""

    id: str
    buyer_need_id: str
    warehouse_id: str
    match_score: float | None = None
    confidence: float | None = None
    instant_book_eligible: bool = False
    reasoning: str | None = None
    scoring_breakdown: dict | None = None
    status: str = "pending"
    declined_reason: str | None = None
    presented_at: datetime | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Deal
# ---------------------------------------------------------------------------


class DealCreate(BaseModel):
    """Schema for creating a new deal."""

    match_id: str | None = None
    warehouse_id: str
    buyer_id: str
    sqft_allocated: int
    start_date: datetime
    end_date: datetime | None = None
    term_months: int | None = None
    supplier_rate: float
    buyer_rate: float
    spread_pct: float | None = None
    monthly_revenue: float | None = None
    deal_type: str = "standard"


class DealResponse(BaseModel):
    """Schema for deal API responses."""

    id: str
    match_id: str | None = None
    warehouse_id: str
    buyer_id: str
    sqft_allocated: int
    start_date: datetime
    end_date: datetime | None = None
    term_months: int | None = None
    supplier_rate: float
    buyer_rate: float
    spread_pct: float | None = None
    monthly_revenue: float | None = None
    tour_scheduled_at: datetime | None = None
    tour_completed_at: datetime | None = None
    tour_outcome: str | None = None
    tour_pass_reason: str | None = None
    status: str = "terms_presented"
    deal_type: str = "standard"
    created_at: datetime
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# AgentLog
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tour
# ---------------------------------------------------------------------------


class TourSchedule(BaseModel):
    """Schema for scheduling a tour."""

    preferred_date: str
    preferred_time: str
    notes: str | None = None


class TourConfirm(BaseModel):
    """Schema for supplier confirming/proposing alternative tour time."""

    confirmed: bool
    proposed_date: str | None = None
    proposed_time: str | None = None
    notes: str | None = None


class TourOutcome(BaseModel):
    """Schema for recording tour outcome."""

    outcome: str  # confirmed, passed, rescheduled, cancelled
    reason: str | None = None
    follow_up_notes: str | None = None


# ---------------------------------------------------------------------------
# Agreements
# ---------------------------------------------------------------------------


class AgreementSign(BaseModel):
    """Schema for signing an agreement."""

    type: str  # 'occupancy_guarantee' or 'network_agreement'
    deal_id: str | None = None
    warehouse_id: str | None = None


class AgreementStatus(BaseModel):
    """Schema for agreement status response."""

    signed: bool
    signed_at: str | None = None


# ---------------------------------------------------------------------------
# AgentLog
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DLA (Demand-Led Activation)
# ---------------------------------------------------------------------------


class DLARateDecision(BaseModel):
    """Schema for supplier rate accept/counter."""

    accepted: bool
    proposed_rate: float | None = None


class DLAConfirm(BaseModel):
    """Schema for supplier agreement confirmation."""

    agreement_ref: str | None = None
    stripe_setup: bool = False
    available_from: str | None = None
    available_to: str | None = None
    restrictions: str | None = None


class DLAOutcome(BaseModel):
    """Schema for non-conversion outcome storage."""

    outcome: str  # declined, no_response, dropped_off, expired
    reason: str | None = None
    rate_floor: float | None = None


class DLATokenResponse(BaseModel):
    """Schema for resolved DLA token data."""

    token: str
    status: str
    property_data: dict
    buyer_requirement: dict
    suggested_rate: float
    market_range: dict
    expires_at: datetime


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


class EnrichmentResponse(BaseModel):
    """Schema for submitting an enrichment question response."""

    question_id: str
    response: str


class PhotoUpload(BaseModel):
    """Schema for uploading photo URLs to a warehouse."""

    photo_urls: list[str]


class ProfileCompleteness(BaseModel):
    """Schema for profile completeness response."""

    total_questions: int
    answered: int
    percentage: float
    missing: list[str]


# ---------------------------------------------------------------------------
# Anonymous Search
# ---------------------------------------------------------------------------


class SearchRequest(BaseModel):
    """Anonymous search — no buyer account required."""

    location: str | None = None         # e.g. "Phoenix, AZ"
    city: str | None = None
    state: str | None = None
    use_type: str | None = None         # storage_only, storage_light_assembly, etc.
    goods_type: str | None = None       # general, food_grade, hazmat, etc.
    size_sqft: int | None = None
    timing: str | None = None           # immediately, 1_month, 3_months
    duration_months: int | None = None
    max_budget_per_sqft: float | None = None
    deal_breakers: list[str] = []
    requirements: dict = {}


class SearchSessionResponse(BaseModel):
    """Response from anonymous search."""

    session_token: str
    tier1: list[dict]
    tier2: list[dict]
    expires_at: datetime


class PromoteSessionRequest(BaseModel):
    """Promote an anonymous search session to a real buyer need."""

    session_token: str


class AgentLogResponse(BaseModel):
    """Schema for agent log API responses."""

    id: str
    agent_name: str
    action: str
    input_summary: str | None = None
    output_summary: str | None = None
    tokens_used: int | None = None
    latency_ms: int | None = None
    related_warehouse_id: str | None = None
    related_buyer_id: str | None = None
    related_deal_id: str | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# LLM Layer 2 — Feature Evaluation
# ---------------------------------------------------------------------------


class FeatureEvalMatch(BaseModel):
    """Single warehouse feature evaluation from LLM Layer 2."""
    warehouse_id: str
    feature_score: int = Field(ge=0, le=100, description="Feature alignment score 0-100")
    instant_book_eligible: bool
    reasoning: str = Field(max_length=500, description="2-3 sentence buyer-facing explanation")


class FeatureEvalResponse(BaseModel):
    """LLM Layer 2 response — feature evaluation + reasoning for all candidates."""
    matches: list[FeatureEvalMatch]
