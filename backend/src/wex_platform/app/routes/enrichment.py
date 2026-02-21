"""Post-onboarding progressive enrichment API routes.

Provides endpoints for:
- Getting the next enrichment question for a warehouse
- Submitting responses to enrichment questions
- Checking profile completeness
- Uploading photos
- Viewing enrichment history
- Scheduling follow-ups
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.infra.database import get_db
from wex_platform.domain.schemas import EnrichmentResponse, PhotoUpload, ProfileCompleteness
from wex_platform.services.enrichment_service import EnrichmentService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/enrichment", tags=["enrichment"])


@router.get("/warehouse/{warehouse_id}/next")
async def get_next_question(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get the next enrichment question for a warehouse.

    Returns the highest-priority unanswered enrichment question, or
    ``{"next_question": null}`` when all questions are answered.
    """
    svc = EnrichmentService(db)
    next_q = await svc.get_next_question(warehouse_id)
    return {"next_question": next_q}


@router.post("/warehouse/{warehouse_id}/respond")
async def submit_response(
    warehouse_id: str,
    data: EnrichmentResponse,
    db: AsyncSession = Depends(get_db),
):
    """Submit a response to an enrichment question.

    Stores the answer in ContextualMemory, optionally updates TruthCore,
    and returns confirmation with the next question (if any).
    """
    svc = EnrichmentService(db)
    try:
        result = await svc.store_response(warehouse_id, data.question_id, data.response)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/warehouse/{warehouse_id}/completeness", response_model=ProfileCompleteness)
async def get_completeness(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get profile completeness percentage for a warehouse."""
    svc = EnrichmentService(db)
    return await svc.get_profile_completeness(warehouse_id)


@router.post("/warehouse/{warehouse_id}/photos")
async def upload_photos(
    warehouse_id: str,
    data: PhotoUpload,
    db: AsyncSession = Depends(get_db),
):
    """Store photo URLs for a warehouse.

    Accepts a list of URLs (actual cloud upload is Phase 2).
    """
    svc = EnrichmentService(db)
    try:
        result = await svc.store_photos(warehouse_id, data.photo_urls)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result


@router.get("/warehouse/{warehouse_id}/history")
async def get_enrichment_history(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all past enrichment responses for a warehouse."""
    svc = EnrichmentService(db)
    history = await svc.get_enrichment_history(warehouse_id)
    return {"history": history}


@router.get("/warehouse/{warehouse_id}/schedule")
async def get_followup_schedule(
    warehouse_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Determine when to send the next enrichment follow-up.

    Returns the next question and the recommended send time, respecting
    rate-limits (3-day gap, max 2 per week).
    """
    svc = EnrichmentService(db)
    return await svc.schedule_next_followup(warehouse_id)
