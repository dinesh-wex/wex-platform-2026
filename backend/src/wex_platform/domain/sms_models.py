"""SMS domain models for the buyer journey state machine."""

import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, JSON, ForeignKey
from sqlalchemy.sql import func

from wex_platform.infra.database import Base


class SMSConversationState(Base):
    __tablename__ = "sms_conversation_states"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    conversation_id = Column(String(36), ForeignKey("buyer_conversations.id"), nullable=False)
    buyer_need_id = Column(String(36), ForeignKey("buyer_needs.id"), nullable=True)
    phone = Column(String(50), nullable=False, index=True)
    phase = Column(String(30), default="INTAKE")
    turn = Column(Integer, default=0)
    criteria_readiness = Column(Float, default=0.0)
    criteria_snapshot = Column(JSON, default=dict)
    focused_match_id = Column(String(36), nullable=True)
    presented_match_ids = Column(JSON, default=list)
    renter_first_name = Column(String(100), nullable=True)
    renter_last_name = Column(String(100), nullable=True)
    name_status = Column(String(20), default="unknown")  # unknown, first_only, full
    name_requested_at_turn = Column(Integer, nullable=True)  # Turn when we asked for name (ask once only)
    buyer_email = Column(String(255), nullable=True)
    engagement_id = Column(String(36), nullable=True)
    guarantee_link_token = Column(String(64), nullable=True)
    search_session_token = Column(String(64), nullable=True)
    guarantee_signed_at = Column(DateTime(timezone=True), nullable=True)
    known_answers = Column(JSON, default=dict)
    answered_questions = Column(JSON, default=list)
    pending_escalations = Column(JSON, default=dict)
    tour_suggested_for = Column(JSON, default=list)
    last_buyer_message_at = Column(DateTime(timezone=True), nullable=True)
    last_system_message_at = Column(DateTime(timezone=True), nullable=True)
    human_escalation_offered_at = Column(DateTime(timezone=True), nullable=True)
    reengagement_count = Column(Integer, default=0)
    next_reengagement_at = Column(DateTime(timezone=True), nullable=True)
    stall_nudge_counts = Column(JSON, default=dict)
    tool_counts = Column(JSON, default=dict)
    tool_counts_reset_at = Column(DateTime(timezone=True), nullable=True)
    waitlist_offered = Column(Boolean, default=False)
    opted_out = Column(Boolean, default=False)
    opted_out_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class EscalationThread(Base):
    __tablename__ = "escalation_threads"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_state_id = Column(String(36), nullable=False)
    source_type = Column(String(20), default="sms")  # "sms" or "voice"
    property_id = Column(String(36), ForeignKey("properties.id"), nullable=False)
    question_text = Column(Text, nullable=False)
    field_key = Column(String(100), nullable=True)
    status = Column(String(30), default="pending")
    sla_deadline_at = Column(DateTime(timezone=True), nullable=False)
    buyer_nudge_sent = Column(Boolean, default=False)
    answer_raw_text = Column(Text, nullable=True)
    answer_polished_text = Column(Text, nullable=True)
    answer_sent_text = Column(Text, nullable=True)
    answer_sent_mode = Column(String(20), nullable=True)
    answered_at = Column(DateTime(timezone=True), nullable=True)
    answered_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())


class SmsSignupToken(Base):
    __tablename__ = "sms_signup_tokens"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_state_id = Column(String(36), ForeignKey("sms_conversation_states.id"), nullable=True)
    token = Column(String(64), unique=True, nullable=False, index=True)
    action = Column(String(30), nullable=False)
    buyer_phone = Column(String(50), nullable=False)
    prefilled_name = Column(String(200), nullable=True)
    prefilled_email = Column(String(255), nullable=True)
    engagement_id = Column(String(36), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False)
    used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())


class BuyerWaitlist(Base):
    __tablename__ = "buyer_waitlists"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    buyer_id = Column(String(36), ForeignKey("buyers.id"), nullable=False)
    phone = Column(String(50), nullable=False, index=True)
    city = Column(String(100), nullable=False)
    state = Column(String(50), nullable=True)
    min_sqft = Column(Integer, nullable=True)
    max_sqft = Column(Integer, nullable=True)
    use_type = Column(String(50), nullable=True)
    criteria_snapshot = Column(JSON, default=dict)
    source_channel = Column(String(10), default="sms")  # "sms" or "voice"
    status = Column(String(20), default="active")  # active, matched, expired, cancelled
    matched_property_id = Column(String(36), nullable=True)
    notified_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)  # 90-day TTL
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())
