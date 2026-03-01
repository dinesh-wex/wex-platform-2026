"""Voice call domain models for the Vapi voice agent."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, JSON, ForeignKey
from sqlalchemy.sql import func

from wex_platform.infra.database import Base


class VoiceCallState(Base):
    __tablename__ = "voice_call_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vapi_call_id = Column(String(100), unique=True, nullable=False, index=True)
    caller_phone = Column(String(50), nullable=False, index=True)
    verified_phone = Column(String(50), nullable=True)
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=True)
    conversation_id = Column(String(36), ForeignKey("buyer_conversations.id"), nullable=True)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=True)

    # Collected during call
    buyer_name = Column(String(200), nullable=True)
    buyer_email = Column(String(255), nullable=True)

    # Search results (cached for detail lookups mid-call)
    presented_match_ids = Column(JSON, default=list)
    match_summaries = Column(JSON, default=list)
    search_session_token = Column(String(64), nullable=True)

    # DetailFetcher cache compat
    known_answers = Column(JSON, default=dict)

    # Escalation tracking
    answered_questions = Column(JSON, default=list)
    pending_escalations = Column(JSON, default=dict)

    # Commitment results
    engagement_id = Column(String(36), nullable=True)
    guarantee_link_token = Column(String(64), nullable=True)

    # Call metadata
    call_started_at = Column(DateTime, nullable=True)
    call_ended_at = Column(DateTime, nullable=True)
    call_duration_seconds = Column(Integer, nullable=True)
    call_summary = Column(Text, nullable=True)
    call_transcript = Column(JSON, nullable=True)  # Full conversation transcript from Vapi
    recording_url = Column(String(500), nullable=True)  # Vapi call recording URL
    sms_sent = Column(Boolean, default=False)
    follow_up_preference = Column(String(20), default="text")

    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
