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
