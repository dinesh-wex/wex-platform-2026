"""Demand-Led Activation routes — tokenized URL flow for off-network suppliers.

Four endpoints per the DLA spec:
- GET  /api/dla/token/{token}          — resolve token -> property + buyer req + rate
- POST /api/dla/token/{token}/rate     — accept or counter-rate
- POST /api/dla/token/{token}/confirm  — agreement signed -> status flip + buyer notification
- POST /api/dla/token/{token}/outcome  — store non-conversion outcome
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.schemas import DLAConfirm, DLAOutcome, DLARateDecision
from wex_platform.infra.database import get_db
from wex_platform.services.dla_service import DLAService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dla", tags=["dla"])


@router.get("/token/{token}")
async def resolve_token(token: str, db: AsyncSession = Depends(get_db)):
    """Resolve a DLA token to property data + anonymized buyer requirements + recommended rate.

    No authentication required — the token itself is the credential.
    This powers the DLA landing page that suppliers see when clicking
    the tokenized link from SMS/email outreach.
    """
    try:
        service = DLAService(db)
        result = await service.resolve_token(token)
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("Error resolving DLA token %s: %s", token, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve token",
        )


@router.post("/token/{token}/rate")
async def submit_rate_decision(
    token: str,
    data: DLARateDecision,
    db: AsyncSession = Depends(get_db),
):
    """Submit supplier's rate decision — accept the proposed rate or counter.

    If accepted: supplier moves directly to agreement step (fastest path).
    If counter: system responds honestly about competition and stores the counter-rate.
    """
    try:
        service = DLAService(db)
        result = await service.handle_rate_decision(
            token=token,
            accepted=data.accepted,
            proposed_rate=data.proposed_rate,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error handling rate decision for token %s: %s", token, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process rate decision",
        )


@router.post("/token/{token}/confirm")
async def confirm_agreement(
    token: str,
    data: DLAConfirm,
    db: AsyncSession = Depends(get_db),
):
    """Confirm agreement — triggers supplier_status flip to in_network + buyer notification.

    Three things happen simultaneously:
    1. supplier_status -> in_network
    2. Property enters the clearing engine as an active Tier 1 match
    3. Buyer notification fires
    """
    try:
        service = DLAService(db)
        result = await service.confirm_agreement(
            token=token,
            agreement_ref=data.agreement_ref,
            available_from=data.available_from,
            available_to=data.available_to,
            restrictions=data.restrictions,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error confirming DLA agreement for token %s: %s", token, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm agreement",
        )


@router.post("/token/{token}/outcome")
async def store_outcome(
    token: str,
    data: DLAOutcome,
    db: AsyncSession = Depends(get_db),
):
    """Store non-conversion outcome — every DLA interaction produces data.

    Outcomes: declined, no_response, dropped_off, expired.
    All data is stored to the property record regardless of outcome.
    """
    try:
        service = DLAService(db)
        result = await service.store_outcome(
            token=token,
            outcome=data.outcome,
            reason=data.reason,
            rate_floor=data.rate_floor,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error storing DLA outcome for token %s: %s", token, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to store outcome",
        )
