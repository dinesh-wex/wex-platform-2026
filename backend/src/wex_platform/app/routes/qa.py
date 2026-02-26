"""Q&A flow API endpoints for engagement property questions.

Provides question submission, AI routing (confidence-based), supplier
fallback, and property knowledge base management.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.app.routes.auth import get_current_user_dep
from wex_platform.domain.enums import (
    EngagementActor,
    EngagementEventType,
    EngagementStatus,
    QuestionStatus,
)
from wex_platform.domain.models import (
    Engagement,
    EngagementEvent,
    PropertyKnowledgeEntry,
    PropertyQuestion,
    User,
)
from wex_platform.infra.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/engagements", tags=["qa"])

# AI confidence threshold — above this the AI answer is used directly
AI_CONFIDENCE_THRESHOLD = 0.70

# Supplier has 24 hours to answer a routed question
SUPPLIER_ANSWER_DEADLINE_HOURS = 24


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class QuestionSubmitRequest(BaseModel):
    question_text: str


class SupplierAnswerRequest(BaseModel):
    answer_text: str


class AdminAnswerRequest(BaseModel):
    answer_text: str


class QuestionOut(BaseModel):
    id: str
    engagement_id: str
    warehouse_id: str
    buyer_id: str
    question_text: str
    status: str
    ai_answer: Optional[str] = None
    ai_confidence: Optional[float] = None
    supplier_answer: Optional[str] = None
    final_answer: Optional[str] = None
    final_answer_source: Optional[str] = None
    routed_to_supplier_at: Optional[str] = None
    supplier_answered_at: Optional[str] = None
    supplier_deadline_at: Optional[str] = None
    timer_paused_at: Optional[str] = None
    timer_resumed_at: Optional[str] = None
    created_at: Optional[str] = None


class KnowledgeEntryOut(BaseModel):
    id: str
    warehouse_id: str
    question: str
    answer: str
    source: str
    confidence: float
    created_at: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _dt(val) -> Optional[str]:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)


def _serialize_question(q: PropertyQuestion) -> dict:
    return QuestionOut(
        id=q.id,
        engagement_id=q.engagement_id,
        warehouse_id=q.warehouse_id,
        buyer_id=q.buyer_id,
        question_text=q.question_text,
        status=q.status if isinstance(q.status, str) else q.status.value,
        ai_answer=q.ai_answer,
        ai_confidence=q.ai_confidence,
        supplier_answer=q.supplier_answer,
        final_answer=q.final_answer,
        final_answer_source=q.final_answer_source,
        routed_to_supplier_at=_dt(q.routed_to_supplier_at),
        supplier_answered_at=_dt(q.supplier_answered_at),
        supplier_deadline_at=_dt(q.supplier_deadline_at),
        timer_paused_at=_dt(q.timer_paused_at),
        timer_resumed_at=_dt(q.timer_resumed_at),
        created_at=_dt(q.created_at),
    ).model_dump()


def _serialize_knowledge(entry: PropertyKnowledgeEntry) -> dict:
    return KnowledgeEntryOut(
        id=entry.id,
        warehouse_id=entry.warehouse_id,
        question=entry.question,
        answer=entry.answer,
        source=entry.source,
        confidence=entry.confidence,
        created_at=_dt(entry.created_at),
    ).model_dump()


def _check_access(engagement: Engagement, user: User) -> None:
    """Raise 403 if user has no access to this engagement."""
    if user.role == "admin":
        return
    if user.role == "supplier" and engagement.supplier_id == user.id:
        return
    if user.role == "buyer" and engagement.buyer_id == user.id:
        return
    if user.role == "buyer" and engagement.buyer_id is None:
        return
    raise HTTPException(status_code=403, detail="Access denied")


async def _get_engagement_or_404(db: AsyncSession, engagement_id: str) -> Engagement:
    result = await db.execute(
        select(Engagement).where(Engagement.id == engagement_id)
    )
    engagement = result.scalar_one_or_none()
    if not engagement:
        raise HTTPException(status_code=404, detail="Engagement not found")
    return engagement


async def _try_ai_answer(
    warehouse_id: str, question_text: str, db: AsyncSession
) -> tuple[Optional[str], float]:
    """Attempt to answer from the property knowledge base.

    Returns (answer_text, confidence). If no match, returns (None, 0.0).
    In a production system this would call an embedding/LLM service.
    For now, we do a simple keyword match against existing knowledge entries.
    """
    result = await db.execute(
        select(PropertyKnowledgeEntry).where(
            PropertyKnowledgeEntry.warehouse_id == warehouse_id
        )
    )
    entries = result.scalars().all()

    if not entries:
        return None, 0.0

    # Simple keyword overlap scoring
    q_words = set(question_text.lower().split())
    best_entry = None
    best_score = 0.0

    for entry in entries:
        entry_words = set(entry.question.lower().split())
        if not entry_words:
            continue
        overlap = len(q_words & entry_words) / max(len(q_words), 1)
        if overlap > best_score:
            best_score = overlap
            best_entry = entry

    if best_entry and best_score >= 0.5:
        # Scale to a confidence score
        confidence = min(best_score * 1.4, 1.0)
        return best_entry.answer, confidence

    return None, 0.0


async def _save_to_knowledge_base(
    db: AsyncSession,
    warehouse_id: str,
    question: PropertyQuestion,
) -> None:
    """Save an answered question to the property knowledge base."""
    entry = PropertyKnowledgeEntry(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse_id,
        question=question.question_text,
        answer=question.final_answer,
        source=question.final_answer_source,
        source_question_id=question.id,
        confidence=question.ai_confidence or 0.9,
    )
    db.add(entry)
    logger.info(
        "Knowledge base entry created for warehouse %s from question %s",
        warehouse_id,
        question.id,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{engagement_id}/qa")
async def list_questions(
    engagement_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """List all Q&A questions for an engagement."""
    engagement = await _get_engagement_or_404(db, engagement_id)
    _check_access(engagement, user)

    result = await db.execute(
        select(PropertyQuestion)
        .where(PropertyQuestion.engagement_id == engagement_id)
        .order_by(PropertyQuestion.created_at.desc())
    )
    questions = result.scalars().all()

    return [_serialize_question(q) for q in questions]


@router.post("/{engagement_id}/qa")
async def submit_question(
    engagement_id: str,
    body: QuestionSubmitRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Buyer submits a question about the property.

    AI attempts to answer first. If confidence >= 0.70, instant answer.
    Otherwise, routes to supplier with 24hr deadline.
    Also pauses the post-tour decision timer if applicable.
    """
    engagement = await _get_engagement_or_404(db, engagement_id)

    if user.role not in ("buyer", "admin"):
        raise HTTPException(status_code=403, detail="Only buyers can submit questions")

    now = datetime.now(timezone.utc)

    # Create question record
    question = PropertyQuestion(
        id=str(uuid.uuid4()),
        engagement_id=engagement_id,
        warehouse_id=engagement.warehouse_id,
        buyer_id=user.id,
        question_text=body.question_text,
        status=QuestionStatus.AI_PROCESSING.value,
    )
    db.add(question)

    # Log event
    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement_id,
        event_type=EngagementEventType.QUESTION_SUBMITTED.value,
        actor=EngagementActor.BUYER.value,
        actor_id=user.id,
        from_status=engagement.status,
        to_status=engagement.status,
        data={"question_id": question.id, "question_text": body.question_text},
    )
    db.add(event)

    # Try AI answer from knowledge base
    ai_answer, ai_confidence = await _try_ai_answer(
        engagement.warehouse_id, body.question_text, db
    )
    question.ai_answer = ai_answer
    question.ai_confidence = ai_confidence

    if ai_confidence >= AI_CONFIDENCE_THRESHOLD and ai_answer:
        # AI can answer directly
        question.status = QuestionStatus.ANSWERED.value
        question.final_answer = ai_answer
        question.final_answer_source = "ai"
        logger.info(
            "Q&A: AI answered question %s (confidence=%.2f, engagement=%s)",
            question.id, ai_confidence, engagement_id,
        )
    else:
        # Route to supplier
        question.status = QuestionStatus.ROUTED_TO_SUPPLIER.value
        question.routed_to_supplier_at = now
        question.supplier_deadline_at = now + timedelta(hours=SUPPLIER_ANSWER_DEADLINE_HOURS)

        # Pause post-tour decision timer if engagement is in tour_completed state
        status_str = engagement.status if isinstance(engagement.status, str) else engagement.status.value
        if status_str == EngagementStatus.TOUR_COMPLETED.value:
            question.timer_paused_at = now

        logger.info(
            "Q&A: Routed question %s to supplier (confidence=%.2f, engagement=%s)",
            question.id, ai_confidence, engagement_id,
        )

    await db.commit()
    return _serialize_question(question)


@router.post("/{engagement_id}/qa/{question_id}/answer")
async def supplier_answer_question(
    engagement_id: str,
    question_id: str,
    body: SupplierAnswerRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Supplier answers a routed question."""
    engagement = await _get_engagement_or_404(db, engagement_id)

    if user.role not in ("supplier", "admin"):
        raise HTTPException(status_code=403, detail="Only suppliers can answer questions")

    # Supplier must own the engagement's warehouse
    if user.role == "supplier" and engagement.supplier_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(PropertyQuestion).where(PropertyQuestion.id == question_id)
    )
    question = result.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")

    if question.engagement_id != engagement_id:
        raise HTTPException(status_code=400, detail="Question does not belong to this engagement")

    now = datetime.now(timezone.utc)
    question.supplier_answer = body.answer_text
    question.supplier_answered_at = now
    question.final_answer = body.answer_text
    question.final_answer_source = "supplier"
    question.status = QuestionStatus.ANSWERED.value

    # Resume post-tour decision timer if it was paused
    if question.timer_paused_at and not question.timer_resumed_at:
        question.timer_resumed_at = now

    # Log event
    event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement_id,
        event_type=EngagementEventType.QUESTION_ANSWERED.value,
        actor=EngagementActor.SUPPLIER.value,
        actor_id=user.id,
        from_status=engagement.status,
        to_status=engagement.status,
        data={
            "question_id": question.id,
            "answer_source": "supplier",
        },
    )
    db.add(event)

    # Save to property knowledge base
    await _save_to_knowledge_base(db, engagement.warehouse_id, question)

    await db.commit()
    logger.info(
        "Q&A: Supplier answered question %s (engagement=%s)",
        question.id, engagement_id,
    )
    return _serialize_question(question)


# ---------------------------------------------------------------------------
# Anonymous Property Questions (no auth required)
# ---------------------------------------------------------------------------

anonymous_qa_router = APIRouter(prefix="/api", tags=["anonymous-qa"])


class AnonymousQuestionRequest(BaseModel):
    question_text: str
    session_token: Optional[str] = None
    email: Optional[str] = None


@anonymous_qa_router.post("/properties/{warehouse_id}/questions/anonymous")
async def submit_anonymous_question(
    warehouse_id: str,
    body: AnonymousQuestionRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Anonymous buyer asks a question about a property. No auth required."""
    question = PropertyQuestion(
        id=str(uuid.uuid4()),
        engagement_id=None,  # No engagement yet
        warehouse_id=warehouse_id,
        buyer_id=None,  # Anonymous
        question_text=body.question_text,
        status=QuestionStatus.SUBMITTED.value,
    )
    db.add(question)
    await db.commit()
    return {"ok": True, "message": "Your question has been sent. WEx will follow up via email."}


# ---------------------------------------------------------------------------
# Property Knowledge Base (admin-managed)
# ---------------------------------------------------------------------------

knowledge_router = APIRouter(prefix="/api", tags=["knowledge"])


@knowledge_router.get("/properties/{warehouse_id}/knowledge")
async def get_property_knowledge(
    warehouse_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Get property knowledge base entries."""
    result = await db.execute(
        select(PropertyKnowledgeEntry)
        .where(PropertyKnowledgeEntry.warehouse_id == warehouse_id)
        .order_by(PropertyKnowledgeEntry.created_at.desc())
    )
    entries = result.scalars().all()
    return [_serialize_knowledge(e) for e in entries]


admin_knowledge_router = APIRouter(prefix="/api/admin", tags=["admin-knowledge"])


class KnowledgeEntryCreate(BaseModel):
    question: str
    answer: str


@admin_knowledge_router.post("/properties/{warehouse_id}/knowledge")
async def admin_create_knowledge(
    warehouse_id: str,
    body: KnowledgeEntryCreate,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Admin creates a knowledge base entry for a property."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin only")

    entry = PropertyKnowledgeEntry(
        id=str(uuid.uuid4()),
        warehouse_id=warehouse_id,
        question=body.question,
        answer=body.answer,
        source="admin",
        confidence=1.0,
    )
    db.add(entry)
    await db.commit()

    logger.info("Admin created knowledge entry for warehouse %s", warehouse_id)
    return _serialize_knowledge(entry)
