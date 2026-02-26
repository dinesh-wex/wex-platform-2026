"""Domain enumerations for the WEx Clearing House.

All enums use the (str, Enum) pattern to ensure JSON serialization compatibility.
"""

from enum import Enum


class ActivationStatus(str, Enum):
    """Whether a warehouse listing is active on the platform."""

    ON = "on"
    OFF = "off"


class ActivityTier(str, Enum):
    """Permitted activity level within a warehouse space."""

    STORAGE_ONLY = "storage_only"
    STORAGE_OFFICE = "storage_office"
    STORAGE_LIGHT_ASSEMBLY = "storage_light_assembly"
    COLD_STORAGE = "cold_storage"


class TourReadiness(str, Enum):
    """How quickly a warehouse can accommodate a tour."""

    SAME_DAY = "same_day"
    FORTY_EIGHT_HOURS = "48_hours"
    BY_APPOINTMENT = "by_appointment"


class AgreementStatus(str, Enum):
    """Status of a supplier or buyer agreement."""

    DRAFT = "draft"
    ACTIVE = "active"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class LedgerEntryType(str, Enum):
    """Types of financial ledger entries."""

    PAYMENT = "payment"
    DEPOSIT_HELD = "deposit_held"
    ADJUSTMENT = "adjustment"
    DEPOSIT = "deposit"
    REFUND = "refund"


class BuyerNeedStatus(str, Enum):
    """Status of a buyer's warehouse need request."""

    ACTIVE = "active"
    MATCHED = "matched"
    CLOSED = "closed"
    EXPIRED = "expired"


class MatchStatus(str, Enum):
    """Status of a match between a buyer need and a warehouse."""

    PENDING = "pending"
    PRESENTED = "presented"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"


class DealStatus(str, Enum):
    """Status of a deal through its lifecycle."""

    TERMS_PRESENTED = "terms_presented"
    TERMS_ACCEPTED = "terms_accepted"
    TOUR_SCHEDULED = "tour_scheduled"
    TOUR_COMPLETED = "tour_completed"
    CONFIRMED = "confirmed"
    ACTIVE = "active"
    COMPLETED = "completed"
    DECLINED = "declined"
    DEFAULTED = "defaulted"
    TERMINATED = "terminated"


class DealType(str, Enum):
    """Type of deal execution."""

    STANDARD = "standard"
    INSTANT_BOOK = "instant_book"


class DepositType(str, Enum):
    """Type of deposit held."""

    SECURITY_DEPOSIT = "security_deposit"
    FIRST_MONTH = "first_month"


class DepositStatus(str, Enum):
    """Status of a deposit."""

    HELD = "held"
    APPLIED = "applied"
    REFUNDED = "refunded"
    CLAIMED = "claimed"


class CoverageStatus(str, Enum):
    """Status of insurance coverage."""

    ACTIVE = "active"
    CLAIMED = "claimed"
    EXPIRED = "expired"


class ConversationStatus(str, Enum):
    """Status of a buyer conversation."""

    ACTIVE = "active"
    CLOSED = "closed"


class MemoryType(str, Enum):
    """Type of contextual memory stored for a warehouse."""

    OWNER_PREFERENCE = "owner_preference"
    BUYER_FEEDBACK = "buyer_feedback"
    DEAL_OUTCOME = "deal_outcome"
    FEATURE_INTELLIGENCE = "feature_intelligence"
    MARKET_CONTEXT = "market_context"
    OUTREACH_RESPONSE = "outreach_response"
    ENRICHMENT_RESPONSE = "enrichment_response"


class MemorySource(str, Enum):
    """Source of a contextual memory entry."""

    ACTIVATION_CHAT = "activation_chat"
    BUYER_QUESTION = "buyer_question"
    TOUR_FEEDBACK = "tour_feedback"
    DEAL_HISTORY = "deal_history"
    BUILDING_DATA = "building_data"


class NearMissOutcome(str, Enum):
    """Outcome when a property nearly matched a buyer need."""

    EXCLUDED = "excluded"
    LOW_RANKED = "low_ranked"
    SHOWN_NOT_SELECTED = "shown_not_selected"


class SupplierResponseEventType(str, Enum):
    """Type of event that triggered a supplier response."""

    DEAL_PING = "deal_ping"
    DLA_OUTREACH = "dla_outreach"
    TOUR_REQUEST = "tour_request"
    AGREEMENT_REQUEST = "agreement_request"


class SupplierResponseOutcome(str, Enum):
    """Outcome of a supplier's response to an event."""

    ACCEPTED = "accepted"
    DECLINED = "declined"
    COUNTER = "counter"
    EXPIRED = "expired"
    CONFIRMED = "confirmed"
    RESCHEDULED = "rescheduled"


class BuyerEngagementAction(str, Enum):
    """Action a buyer took when viewing a property in search results."""

    ACCEPTED = "accepted"
    QUESTION_ASKED = "question_asked"
    EMAIL_LIST = "email_list"
    SKIPPED = "skipped"
    BOUNCED = "bounced"


class ResultTier(str, Enum):
    """Tier ranking for a property in search results."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"


class CompanyRole(str, Enum):
    """Role of a user within their company."""

    ADMIN = "admin"
    MEMBER = "member"


# ---------------------------------------------------------------------------
# Engagement Lifecycle Enums
# ---------------------------------------------------------------------------


class EngagementStatus(str, Enum):
    """Status of an engagement through its full lifecycle."""

    DEAL_PING_SENT = "deal_ping_sent"
    DEAL_PING_ACCEPTED = "deal_ping_accepted"
    DEAL_PING_EXPIRED = "deal_ping_expired"
    DEAL_PING_DECLINED = "deal_ping_declined"
    MATCHED = "matched"
    BUYER_REVIEWING = "buyer_reviewing"
    BUYER_ACCEPTED = "buyer_accepted"
    ACCOUNT_CREATED = "account_created"
    GUARANTEE_SIGNED = "guarantee_signed"
    ADDRESS_REVEALED = "address_revealed"
    TOUR_REQUESTED = "tour_requested"
    TOUR_CONFIRMED = "tour_confirmed"
    TOUR_RESCHEDULED = "tour_rescheduled"
    INSTANT_BOOK_REQUESTED = "instant_book_requested"
    TOUR_COMPLETED = "tour_completed"
    BUYER_CONFIRMED = "buyer_confirmed"
    AGREEMENT_SENT = "agreement_sent"
    AGREEMENT_SIGNED = "agreement_signed"
    ONBOARDING = "onboarding"
    ACTIVE = "active"
    COMPLETED = "completed"
    DECLINED_BY_BUYER = "declined_by_buyer"
    DECLINED_BY_SUPPLIER = "declined_by_supplier"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class EngagementTier(str, Enum):
    """Tier classification for an engagement."""

    TIER_1 = "tier_1"
    TIER_2 = "tier_2"


class EngagementPath(str, Enum):
    """Path a buyer chooses for an engagement."""

    TOUR = "tour"
    INSTANT_BOOK = "instant_book"


class TourOutcome(str, Enum):
    """Outcome of a completed tour."""

    CONFIRMED = "confirmed"
    PASSED = "passed"
    ADJUSTMENT_NEEDED = "adjustment_needed"


class EngagementEventType(str, Enum):
    """Type of event in the engagement audit trail."""

    DEAL_PING_SENT = "deal_ping_sent"
    DEAL_PING_ACCEPTED = "deal_ping_accepted"
    DEAL_PING_DECLINED = "deal_ping_declined"
    DEAL_PING_EXPIRED = "deal_ping_expired"
    MATCHED = "matched"
    BUYER_REVIEWING = "buyer_reviewing"
    BUYER_ACCEPTED = "buyer_accepted"
    ACCOUNT_CREATED = "account_created"
    GUARANTEE_SIGNED = "guarantee_signed"
    ADDRESS_REVEALED = "address_revealed"
    TOUR_REQUESTED = "tour_requested"
    TOUR_CONFIRMED = "tour_confirmed"
    TOUR_RESCHEDULED = "tour_rescheduled"
    TOUR_CANCELLED = "tour_cancelled"
    INSTANT_BOOK_REQUESTED = "instant_book_requested"
    INSTANT_BOOK_UNAVAILABLE = "instant_book_unavailable"
    TOUR_COMPLETED = "tour_completed"
    BUYER_CONFIRMED = "buyer_confirmed"
    BUYER_PASSED = "buyer_passed"
    AGREEMENT_SENT = "agreement_sent"
    AGREEMENT_BUYER_SIGNED = "agreement_buyer_signed"
    AGREEMENT_SUPPLIER_SIGNED = "agreement_supplier_signed"
    AGREEMENT_SIGNED = "agreement_signed"
    AGREEMENT_EXPIRED = "agreement_expired"
    ONBOARDING_STARTED = "onboarding_started"
    INSURANCE_UPLOADED = "insurance_uploaded"
    COMPANY_DOCS_UPLOADED = "company_docs_uploaded"
    PAYMENT_METHOD_ADDED = "payment_method_added"
    ONBOARDING_COMPLETED = "onboarding_completed"
    LEASE_ACTIVATED = "lease_activated"
    LEASE_COMPLETED = "lease_completed"
    DECLINED_BY_BUYER = "declined_by_buyer"
    DECLINED_BY_SUPPLIER = "declined_by_supplier"
    EXPIRED = "expired"
    QUESTION_SUBMITTED = "question_submitted"
    QUESTION_ANSWERED = "question_answered"
    ADMIN_OVERRIDE = "admin_override"
    ADMIN_NOTE = "admin_note"
    DEADLINE_EXTENDED = "deadline_extended"
    PAYMENT_RECORDED = "payment_recorded"
    PAYMENT_OVERDUE = "payment_overdue"
    CANCELLED = "cancelled"
    REMINDER_SENT = "reminder_sent"
    NOTE_ADDED = "note_added"
    HOLD_EXTENDED = "hold_extended"
    HOLD_EXPIRED = "hold_expired"
    HOLD_WARNING_24H = "hold_warning_24h"
    HOLD_WARNING_4H = "hold_warning_4h"


class EngagementActor(str, Enum):
    """Actor performing an engagement action."""

    BUYER = "buyer"
    SUPPLIER = "supplier"
    ADMIN = "admin"
    SYSTEM = "system"


class CancelledBy(str, Enum):
    """Party that cancelled an engagement."""

    BUYER = "buyer"
    SUPPLIER = "supplier"
    ADMIN = "admin"
    SYSTEM = "system"


class DeclineParty(str, Enum):
    """Party that declined an engagement."""

    BUYER = "buyer"
    SUPPLIER = "supplier"


class QuestionStatus(str, Enum):
    """Status of a property question in the Q&A flow."""

    SUBMITTED = "submitted"
    AI_PROCESSING = "ai_processing"
    ROUTED_TO_SUPPLIER = "routed_to_supplier"
    ANSWERED = "answered"
    EXPIRED = "expired"


class AgreementSignStatus(str, Enum):
    """Signing status of an engagement agreement."""

    PENDING = "pending"
    BUYER_SIGNED = "buyer_signed"
    SUPPLIER_SIGNED = "supplier_signed"
    FULLY_SIGNED = "fully_signed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class BuyerPaymentStatus(str, Enum):
    """Status of a buyer payment."""

    UPCOMING = "upcoming"
    INVOICED = "invoiced"
    PAID = "paid"
    OVERDUE = "overdue"


class SupplierPaymentStatus(str, Enum):
    """Status of a supplier payout."""

    UPCOMING = "upcoming"
    SCHEDULED = "scheduled"
    DEPOSITED = "deposited"


# ---------------------------------------------------------------------------
# Property Pipeline Enums (v2 schema)
# ---------------------------------------------------------------------------


class RelationshipStatus(str, Enum):
    """Supplier relationship status in the property pipeline."""

    PROSPECT = "prospect"
    CONTACTED = "contacted"
    INTERESTED = "interested"
    EARNCHECK_ONLY = "earncheck_only"
    ACTIVE = "active"
    DECLINED = "declined"
    UNRESPONSIVE = "unresponsive"
    CHURNED = "churned"


class PropertySource(str, Enum):
    """How a property was originally discovered."""

    EARNCHECK = "earncheck"
    COSTAR = "costar"
    MANUAL = "manual"
    PUBLIC_RECORDS = "public_records"
    BROKER = "broker"


class PropertyEventType(str, Enum):
    """Type of event in the property lifecycle audit trail."""

    DISCOVERED = "discovered"
    OUTREACH_SENT = "outreach_sent"
    RESPONSE_RECEIVED = "response_received"
    EARNCHECK_STARTED = "earncheck_started"
    EARNCHECK_COMPLETED = "earncheck_completed"
    ACTIVATED = "activated"
    PAUSED = "paused"
    DEACTIVATED = "deactivated"
    DECLINED = "declined"
    PRICE_CHANGED = "price_changed"
    DATA_ENRICHED = "data_enriched"


class ContactRole(str, Enum):
    """Role of a contact associated with a property."""

    OWNER = "owner"
    MANAGER = "manager"
    BROKER = "broker"
    EMERGENCY = "emergency"


class PricingMode(str, Enum):
    """How a property's listing price is determined."""

    AUTO = "auto"
    MANUAL = "manual"


class EnrichmentSource(str, Enum):
    """Source of data enrichment for property knowledge fields."""

    AI = "ai"
    SUPPLIER = "supplier"
    MANUAL = "manual"
    THIRD_PARTY = "third_party"
