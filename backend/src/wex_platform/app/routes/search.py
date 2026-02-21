"""Anonymous search routes — no buyer account required.

Layer 1: POST /api/search — stateless search, runs clearing engine
Layer 2: GET  /api/search/session/{token} — retrieve cached results
Layer 3: POST /api/search/promote — promote session to real buyer need (auth required)
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.models import (
    BuyerNeed,
    SearchSession,
)
from wex_platform.domain.schemas import (
    SearchRequest,
    SearchSessionResponse,
    PromoteSessionRequest,
)
from wex_platform.infra.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/search", tags=["search"])

# Session cache lifetime
SESSION_EXPIRY_HOURS = 48


def _parse_location(req: SearchRequest) -> tuple[str | None, str | None]:
    """Extract city/state from the location string or explicit fields."""
    if req.city and req.state:
        return req.city.strip(), req.state.strip().upper()
    if req.location:
        parts = [p.strip() for p in req.location.split(",")]
        if len(parts) >= 2:
            return parts[0], parts[-1].strip().upper()[:2]
        return parts[0], None
    return None, None


def _parse_sqft(req: SearchRequest) -> tuple[int | None, int | None]:
    """Derive min/max sqft from the flat size_sqft field."""
    if not req.size_sqft:
        return None, None
    sqft = req.size_sqft
    # Allow ±20% range for matching flexibility
    return int(sqft * 0.8), int(sqft * 1.2)


@router.post("", response_model=SearchSessionResponse)
async def anonymous_search(
    req: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Run the clearing engine without requiring a buyer account.

    Creates a temporary BuyerNeed (buyer_id=NULL), runs clearing, caches
    results in a SearchSession, and returns a session token.
    """
    city, state = _parse_location(req)
    min_sqft, max_sqft = _parse_sqft(req)

    # 1. Create an anonymous BuyerNeed (no buyer_id)
    need_id = str(uuid.uuid4())
    need = BuyerNeed(
        id=need_id,
        buyer_id=None,  # Anonymous — no account required
        city=city,
        state=state,
        min_sqft=min_sqft,
        max_sqft=max_sqft,
        use_type=req.use_type,
        duration_months=req.duration_months,
        max_budget_per_sqft=req.max_budget_per_sqft,
        requirements={
            "goods_type": req.goods_type,
            "timing": req.timing,
            "deal_breakers": req.deal_breakers,
            **req.requirements,
        },
        status="anonymous",
    )
    db.add(need)
    await db.flush()  # Persist so clearing engine can find it

    # 2. Run the clearing engine
    tier1_results = []
    tier2_results = []
    try:
        from wex_platform.services.clearing_engine import ClearingEngine

        clearing = ClearingEngine()
        clearing_result = await clearing.run_clearing(
            buyer_need_id=need_id, db=db
        )
        tier1_results = clearing_result.get("tier1_matches", [])
        tier2_results = clearing_result.get("tier2_matches", [])
    except Exception as exc:
        logger.warning("Clearing engine failed for anonymous search: %s", exc)
        # Non-fatal — return empty results rather than 500

    # 3. Build buyer-safe results (strip internal fields)
    tier1_safe = []
    for m in tier1_results:
        wh = m.get("warehouse", {})
        tc = wh.get("truth_core", {})
        tier1_safe.append({
            "match_id": m.get("match_id"),
            "warehouse_id": m.get("warehouse_id"),
            "confidence": round(m.get("match_score", 0)),
            "neighborhood": f"{wh.get('city', '')}, {wh.get('state', '')}",
            "primary_image_url": wh.get("primary_image_url"),
            "address": wh.get("address", ""),
            "description": wh.get("description", ""),
            "city": wh.get("city", ""),
            "state": wh.get("state", ""),
            "available_sqft": tc.get("max_sqft", req.size_sqft),
            "building_size_sqft": wh.get("building_size_sqft"),
            "buyer_rate": m.get("buyer_rate", 0),
            "monthly_cost": round(
                m.get("buyer_rate", 0) * (req.size_sqft or tc.get("max_sqft", 0)), 2
            ),
            "term_months": req.duration_months or 6,
            "total_value": round(
                m.get("buyer_rate", 0)
                * (req.size_sqft or tc.get("max_sqft", 0))
                * (req.duration_months or 6),
                2,
            ),
            "features": {
                "activity_tier": tc.get("activity_tier"),
                "clear_height": tc.get("clear_height_ft"),
                "dock_doors": tc.get("dock_doors_receiving"),
                "has_office": tc.get("has_office_space"),
                "has_sprinkler": tc.get("has_sprinkler"),
                "parking": tc.get("parking_spaces"),
                "tour_readiness": tc.get("tour_readiness"),
            },
            "reasoning": m.get("reasoning", ""),
            "instant_book_eligible": m.get("instant_book_eligible", False),
            "tier": 1,
        })

    tier2_safe = []
    for m in tier2_results:
        tier2_safe.append({
            "match_id": f"tier2-{m.get('warehouse_id', '')}",
            "warehouse_id": m.get("warehouse_id"),
            "confidence": round(m.get("match_score", 0)),
            "neighborhood": m.get("neighborhood", ""),
            "available_sqft": m.get("sqft"),
            "building_type": m.get("building_type", "warehouse"),
            "tier": 2,
        })

    # 4. Create session token and cache results
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(hours=SESSION_EXPIRY_HOURS)

    session_record = SearchSession(
        id=str(uuid.uuid4()),
        token=token,
        requirements=req.model_dump(),
        results={"tier1": tier1_safe, "tier2": tier2_safe},
        buyer_need_id=need_id,
        status="active",
        expires_at=expires,
    )
    db.add(session_record)
    await db.commit()

    logger.info(
        "Anonymous search completed: %d tier1, %d tier2 matches (session %s)",
        len(tier1_safe),
        len(tier2_safe),
        token[:8],
    )

    return SearchSessionResponse(
        session_token=token,
        tier1=tier1_safe,
        tier2=tier2_safe,
        expires_at=expires,
    )


@router.get("/session/{token}")
async def get_search_session(
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve cached search results by session token."""
    result = await db.execute(
        select(SearchSession).where(SearchSession.token == token)
    )
    session_record = result.scalar_one_or_none()

    if not session_record:
        raise HTTPException(status_code=404, detail="Search session not found")

    # Check expiry
    if session_record.expires_at and session_record.expires_at < datetime.now(
        timezone.utc
    ):
        raise HTTPException(
            status_code=410,
            detail="Search session expired. Please run a new search.",
        )

    results = session_record.results or {}
    return {
        "session_token": session_record.token,
        "tier1": results.get("tier1", []),
        "tier2": results.get("tier2", []),
        "requirements": session_record.requirements,
        "status": session_record.status,
        "expires_at": session_record.expires_at.isoformat()
        if session_record.expires_at
        else None,
    }


@router.post("/promote")
async def promote_session(
    req: PromoteSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Promote an anonymous search session to a real buyer need.

    Called after the buyer creates an account and wants to take action
    (book tour, save results, rent space). Links the session's BuyerNeed
    to the authenticated buyer.

    For now this accepts buyer_id in the body; in production it should
    come from the JWT token.
    """
    # Find session
    result = await db.execute(
        select(SearchSession).where(SearchSession.token == req.session_token)
    )
    session_record = result.scalar_one_or_none()
    if not session_record:
        raise HTTPException(status_code=404, detail="Search session not found")

    if session_record.status == "promoted":
        return {
            "need_id": session_record.buyer_need_id,
            "message": "Session already promoted",
        }

    # For now, mark as promoted without requiring auth
    # In production: extract buyer_id from JWT and link the need
    session_record.status = "promoted"
    await db.commit()

    return {
        "need_id": session_record.buyer_need_id,
        "session_token": session_record.token,
        "message": "Session promoted to buyer need",
    }
