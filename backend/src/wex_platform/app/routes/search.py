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


async def _parse_location(req: SearchRequest) -> tuple[str | None, str | None, float | None, float | None]:
    """Extract city/state/lat/lng from location input using geocoding.

    Accepts: "Phoenix, AZ", "85281", "downtown LA", "123 Main St, Dallas, TX"
    Returns: (city, state, lat, lng)
    """
    if req.city and req.state:
        city, state = req.city.strip(), req.state.strip().upper()[:2]
        # Still geocode for coordinates
        try:
            from wex_platform.services.geocoding_service import geocode_location
            geo = await geocode_location(f"{city}, {state}")
            return city, state, geo.lat if geo else None, geo.lng if geo else None
        except Exception:
            return city, state, None, None

    if req.location:
        try:
            from wex_platform.services.geocoding_service import geocode_location
            geo = await geocode_location(req.location)
            if geo:
                return geo.city, geo.state, geo.lat, geo.lng
        except Exception:
            pass
        # Fallback: comma-split
        parts = [p.strip() for p in req.location.split(",")]
        if len(parts) >= 2:
            return parts[0], parts[-1].strip().upper()[:2], None, None
        return parts[0], None, None, None

    return None, None, None, None


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
    city, state, lat, lng = await _parse_location(req)
    min_sqft, max_sqft = _parse_sqft(req)

    # 1. Create an anonymous BuyerNeed (no buyer_id)
    need_id = str(uuid.uuid4())
    need = BuyerNeed(
        id=need_id,
        buyer_id=None,  # Anonymous — no account required
        city=city,
        state=state,
        lat=lat,
        lng=lng,
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
            "neighborhood": wh.get("neighborhood") or f"{wh.get('city', '')}, {wh.get('state', '')}",
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
            "distance_miles": m.get("distance_miles"),
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

    # Check expiry (handle both naive and aware datetimes from SQLite)
    if session_record.expires_at:
        expires = session_record.expires_at
        now = datetime.now(timezone.utc)
        # SQLite stores naive datetimes — make them comparable
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
    if session_record.expires_at and expires < now:
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


@router.post("/extract")
async def extract_intent(req: dict):
    """NLP extraction from freeform buyer input for smart pre-fill."""
    text = req.get("text", "")
    if not text.strip():
        return {"fields": {}, "confidence": 0}

    from wex_platform.services.intake_extractor import IntakeExtractor
    extractor = IntakeExtractor()
    result = await extractor.extract(text)

    fields = result.data if result.ok else {}

    # Geocode extracted location if present
    if fields.get("location"):
        try:
            from wex_platform.services.geocoding_service import geocode_location
            geo = await geocode_location(fields["location"])
            if geo:
                fields["lat"] = geo.lat
                fields["lng"] = geo.lng
                fields["city"] = geo.city
                fields["state"] = geo.state
        except Exception:
            pass

    confidence = min(0.95, len(fields) * 0.15) if fields else 0
    return {"fields": fields, "confidence": round(confidence, 2)}
