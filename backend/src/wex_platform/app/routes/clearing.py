"""Clearing engine API routes.

These endpoints trigger and query the matching/clearing process
that connects buyer needs to available warehouse inventory.
Supports two-tier matching: Tier 1 (in-network) and Tier 2 (off-network
with DLA activation).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.infra.database import get_db
from wex_platform.domain.models import (
    BuyerNeed,
    Match,
    Warehouse,
    TruthCore,
)
from wex_platform.services.pricing_engine import PricingEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clearing", tags=["clearing"])

# Instantiate pricing engine
pricing_engine = PricingEngine()


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class ClearingMatchRequest(BaseModel):
    """Request body for triggering clearing."""

    buyer_need_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/match")
async def trigger_clearing(
    body: ClearingMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger two-tier clearing (matching) for a buyer need.

    Calls ClearingEngine.run_clearing() which returns Tier 1 (in-network,
    ready-to-book) matches and Tier 2 (off-network, being sourced)
    candidates.  If fewer than 3 Tier 1 matches exist, DLA outreach is
    triggered automatically for top Tier 2 candidates.
    """
    # Verify buyer need exists
    need_result = await db.execute(
        select(BuyerNeed).where(BuyerNeed.id == body.buyer_need_id)
    )
    need = need_result.scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Buyer need not found")

    try:
        from wex_platform.services.clearing_engine import ClearingEngine

        clearing = ClearingEngine()
        result = await clearing.run_clearing(
            buyer_need_id=body.buyer_need_id,
            db=db,
        )

        # result is now a dict with tier1_matches, tier2_matches, etc.
        tier1 = result.get("tier1_matches", [])
        tier2 = result.get("tier2_matches", [])
        dla_triggered = result.get("dla_triggered", False)

        # Re-fetch persisted Tier 1 Match records for canonical DB state
        matches_result = await db.execute(
            select(Match)
            .where(Match.buyer_need_id == body.buyer_need_id)
            .options(
                selectinload(Match.warehouse).selectinload(Warehouse.truth_core),
            )
            .order_by(Match.match_score.desc())
        )
        matches = matches_result.scalars().all()

        return {
            "buyer_need_id": body.buyer_need_id,
            "tier1_matches": [
                {
                    "id": m.id,
                    "warehouse_id": m.warehouse_id,
                    "match_score": m.match_score,
                    "confidence": m.confidence,
                    "instant_book_eligible": m.instant_book_eligible,
                    "reasoning": m.reasoning,
                    "scoring_breakdown": m.scoring_breakdown,
                    "status": m.status,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in matches
            ],
            "tier2_matches": tier2,
            "dla_triggered": dla_triggered,
            "total_matches": len(matches) + len(tier2),
        }

    except ImportError:
        logger.warning("ClearingEngine not available yet")
        return {
            "buyer_need_id": body.buyer_need_id,
            "tier1_matches": [],
            "tier2_matches": [],
            "dla_triggered": False,
            "total_matches": 0,
            "message": "Clearing engine not yet available",
        }
    except Exception as e:
        logger.error("Clearing engine error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Clearing engine error: {str(e)}",
        )


@router.get("/match-count")
async def get_match_count(
    location: str = Query(..., description="City or state to search in"),
    min_sqft: int = Query(0, ge=0),
    max_sqft: int = Query(100_000, ge=0),
    use_type: str | None = Query(None, description="Activity tier / use type filter"),
    db: AsyncSession = Depends(get_db),
):
    """Quick count of matching warehouses for the buyer wizard live count badge.

    Returns the number of in-network warehouses that match basic criteria
    (location, size range, optional use type).  Used by the buyer wizard
    Step 4 (Size slider) to provide real-time feedback.
    """
    try:
        from wex_platform.services.clearing_engine import ClearingEngine

        clearing = ClearingEngine()
        result = await clearing.get_match_count(
            location=location,
            min_sqft=min_sqft,
            max_sqft=max_sqft,
            use_type=use_type,
            session=db,
        )
        return result

    except ImportError:
        logger.warning("ClearingEngine not available for match-count")
        return {"count": 0, "approximate": False}
    except Exception as e:
        logger.error("Match count error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Match count error: {str(e)}",
        )


@router.get("/match/{match_id}")
async def get_match_detail(
    match_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get detailed match information with scoring breakdown.

    Returns the full match record including the scoring breakdown
    that explains how the match score was calculated.
    """
    result = await db.execute(
        select(Match)
        .where(Match.id == match_id)
        .options(
            selectinload(Match.warehouse).selectinload(Warehouse.truth_core),
            selectinload(Match.buyer_need),
            selectinload(Match.instant_book_score),
        )
    )
    match = result.scalar_one_or_none()

    if not match:
        raise HTTPException(status_code=404, detail="Match not found")

    # Build warehouse summary
    warehouse_summary = None
    if match.warehouse:
        wh = match.warehouse
        warehouse_summary = {
            "id": wh.id,
            "address": wh.address,
            "city": wh.city,
            "state": wh.state,
            "building_size_sqft": wh.building_size_sqft,
            "primary_image_url": wh.primary_image_url,
        }

        if wh.truth_core:
            tc = wh.truth_core
            warehouse_summary["features"] = {
                "min_sqft": tc.min_sqft,
                "max_sqft": tc.max_sqft,
                "activity_tier": tc.activity_tier,
                "dock_doors_receiving": tc.dock_doors_receiving,
                "dock_doors_shipping": tc.dock_doors_shipping,
                "clear_height_ft": tc.clear_height_ft,
                "has_office_space": tc.has_office_space,
                "has_sprinkler": tc.has_sprinkler,
                "tour_readiness": tc.tour_readiness,
                "activation_status": tc.activation_status,
            }

    # Build need summary
    need_summary = None
    if match.buyer_need:
        bn = match.buyer_need
        need_summary = {
            "id": bn.id,
            "city": bn.city,
            "state": bn.state,
            "min_sqft": bn.min_sqft,
            "max_sqft": bn.max_sqft,
            "use_type": bn.use_type,
            "duration_months": bn.duration_months,
            "max_budget_per_sqft": bn.max_budget_per_sqft,
        }

    # Build instant book score details
    ib_details = None
    if match.instant_book_score:
        ibs = match.instant_book_score
        ib_details = {
            "truth_core_completeness": ibs.truth_core_completeness,
            "contextual_memory_depth": ibs.contextual_memory_depth,
            "supplier_trust_level": ibs.supplier_trust_level,
            "match_specificity": ibs.match_specificity,
            "feature_alignment": ibs.feature_alignment,
            "composite_score": ibs.composite_score,
            "instant_book_eligible": ibs.instant_book_eligible,
            "threshold_used": ibs.threshold_used,
        }

    return {
        "id": match.id,
        "buyer_need_id": match.buyer_need_id,
        "warehouse_id": match.warehouse_id,
        "match_score": match.match_score,
        "confidence": match.confidence,
        "instant_book_eligible": match.instant_book_eligible,
        "reasoning": match.reasoning,
        "scoring_breakdown": match.scoring_breakdown,
        "status": match.status,
        "declined_reason": match.declined_reason,
        "presented_at": match.presented_at.isoformat() if match.presented_at else None,
        "created_at": match.created_at.isoformat() if match.created_at else None,
        "warehouse": warehouse_summary,
        "buyer_need": need_summary,
        "instant_book_details": ib_details,
    }
