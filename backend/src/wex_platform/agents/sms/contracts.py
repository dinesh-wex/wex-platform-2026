"""Typed dataclasses for SMS agent I/O contracts."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MessageInterpretation:
    """Output of the deterministic Message Interpreter."""
    cities: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    sqft: int | None = None
    min_sqft: int | None = None
    max_sqft: int | None = None
    topics: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    positional_references: list[str] = field(default_factory=list)
    action_keywords: list[str] = field(default_factory=list)
    emails: list[str] = field(default_factory=list)
    names: list[str] = field(default_factory=list)
    raw_text: str = ""
    query_type: str = "general"
    original_message: str = ""
    address_text: str | None = None

    def __post_init__(self):
        # Sync sqft <-> min_sqft for backward compatibility.
        # If sqft is set but min_sqft is not, copy sqft to min_sqft.
        # If min_sqft is set but sqft is not, copy min_sqft to sqft.
        if self.sqft is not None and self.min_sqft is None:
            self.min_sqft = self.sqft
        elif self.min_sqft is not None and self.sqft is None:
            self.sqft = self.min_sqft


@dataclass
class CriteriaPlan:
    """Output of the Criteria Agent (LLM)."""
    intent: str = "unknown"  # new_search, refine_search, facility_info, tour_request, commitment, provide_info, greeting, unknown
    action: str | None = None  # search, lookup, schedule_tour, commitment_handoff, collect_info, None
    criteria: dict = field(default_factory=dict)  # {location, sqft, use_type, ...}
    resolved_property_id: str | None = None
    response_hint: str | None = None  # hint for response agent
    confidence: float = 0.0
    extracted_name: dict | None = None  # {"first_name": "...", "last_name": "..."} or None
    asked_fields: list[str] | None = None
    clarification_needed: str | None = None


@dataclass
class DetailFetchResult:
    """Output of Detail Fetcher (Phase 3 stub for now)."""
    status: str = "NOT_IMPLEMENTED"  # FOUND, CACHE_HIT, MAPPED, UNMAPPED, NOT_IMPLEMENTED
    field_key: str | None = None
    value: str | None = None
    formatted: str | None = None
    needs_escalation: bool = False
    source: str = ""
    label: str = ""


@dataclass
class PolishResult:
    """Output of the SMS polish/rewrite step."""
    ok: bool = True
    polished_text: str = ""
    original_length: int = 0
    polished_length: int = 0
    error_code: str | None = None


@dataclass
class GatekeeperResult:
    """Result of SMS validation."""
    ok: bool = True
    hint: str | None = None
    violation: str | None = None
