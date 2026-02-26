"""Buyer-side API routes.

ECONOMIC ISOLATION: These endpoints only expose buyer-domain data.
No supplier rates, supplier identities, or WEx spread are ever returned.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.infra.database import get_db
from wex_platform.domain.models import (
    Buyer,
    BuyerNeed,
    BuyerConversation,
    Match,
    Deal,
    DealEvent,
    Warehouse,
    TruthCore,
    Engagement,
    EngagementEvent,
)
from wex_platform.domain.enums import (
    EngagementStatus,
    EngagementTier,
    EngagementEventType,
    EngagementActor,
)
from wex_platform.services.pricing_engine import PricingEngine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/buyer", tags=["buyer"])

# Instantiate pricing engine (stateless, safe as module-level singleton)
pricing_engine = PricingEngine()


# ---------------------------------------------------------------------------
# Inline request / response models
# ---------------------------------------------------------------------------


class BuyerRegisterRequest(BaseModel):
    """Request body for registering a new buyer."""

    name: str
    company: str
    email: str
    phone: Optional[str] = None


class BuyerNeedCreateRequest(BaseModel):
    """Request body for creating a buyer need."""

    buyer_id: str
    city: Optional[str] = None
    state: Optional[str] = None
    min_sqft: Optional[int] = None
    max_sqft: Optional[int] = None
    use_type: Optional[str] = None
    needed_from: Optional[datetime] = None
    duration_months: Optional[int] = None
    max_budget_per_sqft: Optional[float] = None
    requirements: dict = {}


class ChatMessageRequest(BaseModel):
    """Request body for buyer intake chat messages."""

    message: str
    conversation_history: list[dict] = []
    extracted_need: dict = {}


class AcceptMatchRequest(BaseModel):
    """Request body for accepting a match."""

    match_id: str
    deal_type: str = "standard"  # "standard" or "instant_book"


class GuaranteeSignRequest(BaseModel):
    """Request body for signing the occupancy guarantee."""

    accepted: bool = True


class TourScheduleRequest(BaseModel):
    """Request body for scheduling a tour."""

    preferred_date: str
    preferred_time: str
    notes: Optional[str] = None


class TourConfirmRequest(BaseModel):
    """Request body for supplier confirming a tour."""

    confirmed: bool
    proposed_date: Optional[str] = None
    proposed_time: Optional[str] = None


class TourOutcomeRequest(BaseModel):
    """Request body for recording a tour outcome."""

    outcome: str  # "confirmed" or "passed"
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Helper: Build buyer-safe warehouse view
# ---------------------------------------------------------------------------


def _buyer_safe_warehouse(warehouse: Warehouse, reveal_address: bool = False) -> dict:
    """Return warehouse data safe for buyer consumption.

    ISOLATION: Strips owner identity, supplier rate, and all
    supplier-only fields. Only returns physical/location attributes.

    ANTI-CIRCUMVENTION: Address is masked unless reveal_address=True
    (i.e. guarantee has been signed).
    """
    data = {
        "id": warehouse.id,
        "city": warehouse.city,
        "state": warehouse.state,
        "building_size_sqft": warehouse.building_size_sqft,
        "year_built": warehouse.year_built,
        "construction_type": warehouse.construction_type,
        "zoning": warehouse.zoning,
        "primary_image_url": warehouse.primary_image_url,
        "image_urls": warehouse.image_urls or [],
    }

    if reveal_address:
        data["address"] = warehouse.address
        data["zip"] = warehouse.zip
        data["lat"] = warehouse.lat
        data["lng"] = warehouse.lng
    else:
        # Mask: show only neighborhood-level info
        data["address"] = None
        data["zip"] = None
        data["lat"] = None
        data["lng"] = None

    return data


def _buyer_safe_deal(deal: Deal) -> dict:
    """Return deal data safe for buyer consumption.

    ISOLATION: Only returns buyer_rate. Never exposes supplier_rate,
    spread_pct, or monthly_revenue (WEx internal economics).
    """
    return {
        "id": deal.id,
        "match_id": deal.match_id,
        "warehouse_id": deal.warehouse_id,
        "buyer_id": deal.buyer_id,
        "sqft_allocated": deal.sqft_allocated,
        "start_date": deal.start_date.isoformat() if deal.start_date else None,
        "end_date": deal.end_date.isoformat() if deal.end_date else None,
        "term_months": deal.term_months,
        "rate_per_sqft": deal.buyer_rate,  # ONLY buyer rate - never supplier rate
        "monthly_payment": round(deal.buyer_rate * deal.sqft_allocated, 2),
        "tour_scheduled_at": deal.tour_scheduled_at.isoformat() if deal.tour_scheduled_at else None,
        "tour_completed_at": deal.tour_completed_at.isoformat() if deal.tour_completed_at else None,
        "tour_outcome": deal.tour_outcome,
        # Anti-circumvention tour flow fields
        "guarantee_signed_at": deal.guarantee_signed_at.isoformat() if deal.guarantee_signed_at else None,
        "address_revealed_at": deal.address_revealed_at.isoformat() if deal.address_revealed_at else None,
        "tour_status": deal.tour_status,
        "tour_preferred_date": deal.tour_preferred_date,
        "tour_preferred_time": deal.tour_preferred_time,
        "supplier_confirmed_at": deal.supplier_confirmed_at.isoformat() if deal.supplier_confirmed_at else None,
        "status": deal.status,
        "deal_type": deal.deal_type,
        "created_at": deal.created_at.isoformat() if deal.created_at else None,
        "updated_at": deal.updated_at.isoformat() if deal.updated_at else None,
    }


def _buyer_safe_match(match: Match, buyer_rate: float) -> dict:
    """Return match data safe for buyer consumption.

    ISOLATION: Only includes buyer_rate. No supplier rate, no spread,
    no owner identity.
    """
    warehouse_data = {}
    if match.warehouse:
        warehouse_data = _buyer_safe_warehouse(match.warehouse)

        # Add truth core features (physical attributes only, no rates)
        if match.warehouse.truth_core:
            tc = match.warehouse.truth_core
            warehouse_data["features"] = {
                "dock_doors_receiving": tc.dock_doors_receiving,
                "dock_doors_shipping": tc.dock_doors_shipping,
                "drive_in_bays": tc.drive_in_bays,
                "parking_spaces": tc.parking_spaces,
                "clear_height_ft": tc.clear_height_ft,
                "has_office_space": tc.has_office_space,
                "has_sprinkler": tc.has_sprinkler,
                "power_supply": tc.power_supply,
                "tour_readiness": tc.tour_readiness,
                "min_sqft": tc.min_sqft,
                "max_sqft": tc.max_sqft,
                "available_from": tc.available_from.isoformat() if tc.available_from else None,
                "available_to": tc.available_to.isoformat() if tc.available_to else None,
                "min_term_months": tc.min_term_months,
                "max_term_months": tc.max_term_months,
            }

    return {
        "id": match.id,
        "buyer_need_id": match.buyer_need_id,
        "warehouse": warehouse_data,
        "match_score": match.match_score,
        "confidence": match.confidence,
        "instant_book_eligible": match.instant_book_eligible,
        "reasoning": match.reasoning,
        "rate_per_sqft": buyer_rate,  # ONLY buyer rate
        "status": match.status,
        "presented_at": match.presented_at.isoformat() if match.presented_at else None,
        "created_at": match.created_at.isoformat() if match.created_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register")
async def register_buyer(
    body: BuyerRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """Register a new buyer profile.

    Returns the created buyer with a unique ID.
    """
    buyer = Buyer(
        id=str(uuid.uuid4()),
        name=body.name,
        company=body.company,
        email=body.email,
        phone=body.phone,
    )
    db.add(buyer)
    await db.commit()

    return {
        "id": buyer.id,
        "name": buyer.name,
        "company": buyer.company,
        "email": buyer.email,
        "phone": buyer.phone,
        "created_at": buyer.created_at.isoformat() if buyer.created_at else None,
    }


@router.get("/{buyer_id}")
async def get_buyer(
    buyer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return buyer profile with active needs and deals.

    ISOLATION: Deals only show buyer_rate, never supplier economics.
    """
    result = await db.execute(
        select(Buyer)
        .where(Buyer.id == buyer_id)
        .options(
            selectinload(Buyer.needs),
            selectinload(Buyer.deals),
        )
    )
    buyer = result.scalar_one_or_none()

    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    # Build needs list
    needs_list = []
    for need in (buyer.needs or []):
        needs_list.append({
            "id": need.id,
            "city": need.city,
            "state": need.state,
            "min_sqft": need.min_sqft,
            "max_sqft": need.max_sqft,
            "use_type": need.use_type,
            "needed_from": need.needed_from.isoformat() if need.needed_from else None,
            "duration_months": need.duration_months,
            "max_budget_per_sqft": need.max_budget_per_sqft,
            "requirements": need.requirements,
            "status": need.status,
            "created_at": need.created_at.isoformat() if need.created_at else None,
        })

    # Build deals list (buyer-safe view)
    deals_list = [_buyer_safe_deal(deal) for deal in (buyer.deals or [])]

    return {
        "id": buyer.id,
        "name": buyer.name,
        "company": buyer.company,
        "email": buyer.email,
        "phone": buyer.phone,
        "created_at": buyer.created_at.isoformat() if buyer.created_at else None,
        "needs": needs_list,
        "deals": deals_list,
    }


@router.post("/need")
async def create_buyer_need(
    body: BuyerNeedCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Create a new buyer need (warehouse space requirement).

    Returns the created need record.
    """
    # Verify buyer exists
    buyer_result = await db.execute(
        select(Buyer).where(Buyer.id == body.buyer_id)
    )
    buyer = buyer_result.scalar_one_or_none()
    if not buyer:
        raise HTTPException(status_code=404, detail="Buyer not found")

    need = BuyerNeed(
        id=str(uuid.uuid4()),
        buyer_id=body.buyer_id,
        city=body.city,
        state=body.state,
        min_sqft=body.min_sqft,
        max_sqft=body.max_sqft,
        use_type=body.use_type,
        needed_from=body.needed_from,
        duration_months=body.duration_months,
        max_budget_per_sqft=body.max_budget_per_sqft,
        requirements=body.requirements,
        status="active",
    )
    db.add(need)
    await db.commit()

    return {
        "id": need.id,
        "buyer_id": need.buyer_id,
        "city": need.city,
        "state": need.state,
        "min_sqft": need.min_sqft,
        "max_sqft": need.max_sqft,
        "use_type": need.use_type,
        "needed_from": need.needed_from.isoformat() if need.needed_from else None,
        "duration_months": need.duration_months,
        "max_budget_per_sqft": need.max_budget_per_sqft,
        "requirements": need.requirements,
        "status": need.status,
        "created_at": need.created_at.isoformat() if need.created_at else None,
    }


@router.get("/{buyer_id}/needs")
async def get_buyer_needs(
    buyer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all needs for a buyer."""
    # Verify buyer exists
    buyer_result = await db.execute(
        select(Buyer).where(Buyer.id == buyer_id)
    )
    if not buyer_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Buyer not found")

    result = await db.execute(
        select(BuyerNeed)
        .where(BuyerNeed.buyer_id == buyer_id)
        .order_by(BuyerNeed.created_at.desc())
    )
    needs = result.scalars().all()

    return [
        {
            "id": need.id,
            "buyer_id": need.buyer_id,
            "city": need.city,
            "state": need.state,
            "min_sqft": need.min_sqft,
            "max_sqft": need.max_sqft,
            "use_type": need.use_type,
            "needed_from": need.needed_from.isoformat() if need.needed_from else None,
            "duration_months": need.duration_months,
            "max_budget_per_sqft": need.max_budget_per_sqft,
            "requirements": need.requirements,
            "status": need.status,
            "created_at": need.created_at.isoformat() if need.created_at else None,
            "updated_at": need.updated_at.isoformat() if need.updated_at else None,
        }
        for need in needs
    ]


@router.post("/need/{need_id}/chat")
async def buyer_need_chat(
    need_id: str,
    body: ChatMessageRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a message in the buyer intake conversation.

    Calls BuyerAgent.process_message() to generate an AI response
    that helps the buyer articulate their warehouse needs.
    """
    # Verify need exists
    need_result = await db.execute(
        select(BuyerNeed)
        .where(BuyerNeed.id == need_id)
        .options(selectinload(BuyerNeed.buyer))
    )
    need = need_result.scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Buyer need not found")

    try:
        from wex_platform.agents.buyer_agent import BuyerAgent

        agent = BuyerAgent()
        result = await agent.process_message(
            need_id=need_id,
            user_message=body.message,
            conversation_history=body.conversation_history,
            extracted_need=body.extracted_need,
        )

        if not result.ok:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Buyer agent processing failed",
            )

        # Store conversation in database
        conversation_result = await db.execute(
            select(BuyerConversation).where(
                BuyerConversation.buyer_need_id == need_id,
                BuyerConversation.status == "active",
            )
        )
        conversation = conversation_result.scalar_one_or_none()

        # Build updated messages list
        updated_messages = list(body.conversation_history)
        updated_messages.append({"role": "user", "content": body.message})
        updated_messages.append({"role": "assistant", "content": result.data})

        if conversation:
            conversation.messages = updated_messages
        else:
            conversation = BuyerConversation(
                id=str(uuid.uuid4()),
                buyer_id=need.buyer_id,
                buyer_need_id=need_id,
                messages=updated_messages,
                status="active",
            )
            db.add(conversation)

        return {
            "agent_response": result.data,
            "need_id": need_id,
        }

    except ImportError:
        # BuyerAgent not yet implemented - return a helpful fallback
        logger.warning("BuyerAgent not available, returning fallback response")
        return {
            "agent_response": (
                "Thank you for your message. I'm processing your warehouse "
                "requirements. Could you tell me more about the specific "
                "features you need?"
            ),
            "need_id": need_id,
            "fallback": True,
        }


@router.post("/need/{need_id}/chat/start")
async def buyer_need_chat_start(
    need_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Start a new buyer intake conversation.

    Calls BuyerAgent.generate_initial_message() to create a welcoming
    first message that kicks off the needs discovery flow.
    """
    # Verify need exists
    need_result = await db.execute(
        select(BuyerNeed)
        .where(BuyerNeed.id == need_id)
        .options(selectinload(BuyerNeed.buyer))
    )
    need = need_result.scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Buyer need not found")

    try:
        from wex_platform.agents.buyer_agent import BuyerAgent

        agent = BuyerAgent()
        result = await agent.generate_initial_message(
            need_data={
                "city": need.city,
                "state": need.state,
                "min_sqft": need.min_sqft,
                "max_sqft": need.max_sqft,
                "use_type": need.use_type,
                "duration_months": need.duration_months,
                "max_budget_per_sqft": need.max_budget_per_sqft,
                "requirements": need.requirements,
            }
        )

        if not result.ok:
            raise HTTPException(
                status_code=500,
                detail=result.error or "Failed to generate initial message",
            )

        # Create a conversation record
        conversation = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=need.buyer_id,
            buyer_need_id=need_id,
            messages=[{"role": "assistant", "content": result.data}],
            status="active",
        )
        db.add(conversation)

        return {
            "initial_message": result.data,
            "need_id": need_id,
            "conversation_id": conversation.id,
        }

    except ImportError:
        # BuyerAgent not yet implemented - return a helpful fallback
        logger.warning("BuyerAgent not available, returning fallback response")

        initial_msg = (
            "Welcome to WEx! I'm here to help you find the perfect warehouse "
            "space. Let's start by understanding your needs. What type of "
            "operations will you be running in the space?"
        )

        conversation = BuyerConversation(
            id=str(uuid.uuid4()),
            buyer_id=need.buyer_id,
            buyer_need_id=need_id,
            messages=[{"role": "assistant", "content": initial_msg}],
            status="active",
        )
        db.add(conversation)

        return {
            "initial_message": initial_msg,
            "need_id": need_id,
            "conversation_id": conversation.id,
            "fallback": True,
        }


@router.get("/need/{need_id}/options")
async def get_buyer_options(
    need_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get cleared options (matches) for a buyer need.

    If no matches exist yet, triggers the ClearingEngine to run matching.
    Returns matches with BUYER-VISIBLE data only.

    ISOLATION: Only buyer_rate is returned. No supplier_rate, spread,
    owner identity, or WEx economics are exposed.
    """
    # Verify need exists
    need_result = await db.execute(
        select(BuyerNeed).where(BuyerNeed.id == need_id)
    )
    need = need_result.scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Buyer need not found")

    # Check for existing matches
    matches_result = await db.execute(
        select(Match)
        .where(Match.buyer_need_id == need_id)
        .options(
            selectinload(Match.warehouse).selectinload(Warehouse.truth_core),
        )
        .order_by(Match.match_score.desc())
    )
    matches = matches_result.scalars().all()

    # If no matches exist, try to run clearing
    if not matches:
        try:
            from wex_platform.services.clearing_engine import ClearingEngine

            clearing = ClearingEngine()
            clearing_result = await clearing.run_clearing(
                buyer_need_id=need_id, db=db
            )

            if clearing_result and clearing_result.get("tier1_matches"):
                # Re-fetch matches after clearing
                matches_result = await db.execute(
                    select(Match)
                    .where(Match.buyer_need_id == need_id)
                    .options(
                        selectinload(Match.warehouse).selectinload(
                            Warehouse.truth_core
                        ),
                    )
                    .order_by(Match.match_score.desc())
                )
                matches = matches_result.scalars().all()
        except ImportError:
            logger.warning("ClearingEngine not available yet")
        except Exception as e:
            logger.error("Clearing engine error: %s", e)

    # Build buyer-safe response
    options = []
    for match in matches:
        # Calculate buyer rate from supplier rate + spread
        buyer_rate = None
        if match.warehouse and match.warehouse.truth_core:
            tc = match.warehouse.truth_core
            pricing = pricing_engine.calculate_buyer_rate(
                supplier_rate=tc.supplier_rate_per_sqft,
                state=match.warehouse.state or "",
                warehouse_features={
                    "has_office_space": tc.has_office_space,
                    "has_sprinkler": tc.has_sprinkler,
                    "clear_height_ft": tc.clear_height_ft,
                    "dock_doors_receiving": tc.dock_doors_receiving,
                    "parking_spaces": tc.parking_spaces,
                },
            )
            buyer_rate = pricing["buyer_rate"]

        if buyer_rate is not None:
            options.append(_buyer_safe_match(match, buyer_rate))

    # Mark matches as presented
    now = datetime.now(timezone.utc)
    for match in matches:
        if match.status == "pending":
            match.status = "presented"
            match.presented_at = now

    return {
        "need_id": need_id,
        "options_count": len(options),
        "options": options,
    }


@router.post("/need/{need_id}/accept")
async def accept_match(
    need_id: str,
    body: AcceptMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Buyer accepts a match/deal terms.

    Creates a Deal record. For standard deals, status is 'terms_accepted'.
    For instant_book deals, status is 'confirmed' immediately.

    ISOLATION: Response only contains buyer_rate and buyer-facing economics.
    """
    # Verify need exists
    need_result = await db.execute(
        select(BuyerNeed).where(BuyerNeed.id == need_id)
    )
    need = need_result.scalar_one_or_none()
    if not need:
        raise HTTPException(status_code=404, detail="Buyer need not found")

    # Verify match exists and belongs to this need
    match_result = await db.execute(
        select(Match)
        .where(Match.id == body.match_id, Match.buyer_need_id == need_id)
        .options(
            selectinload(Match.warehouse).selectinload(Warehouse.truth_core),
        )
    )
    match = match_result.scalar_one_or_none()
    if not match:
        raise HTTPException(
            status_code=404,
            detail="Match not found or does not belong to this need",
        )

    if not match.warehouse or not match.warehouse.truth_core:
        raise HTTPException(
            status_code=400,
            detail="Warehouse data incomplete for this match",
        )

    # Validate deal_type
    if body.deal_type not in ("standard", "instant_book"):
        raise HTTPException(
            status_code=400,
            detail="deal_type must be 'standard' or 'instant_book'",
        )

    # For instant_book, verify eligibility
    if body.deal_type == "instant_book" and not match.instant_book_eligible:
        raise HTTPException(
            status_code=400,
            detail="This match is not eligible for instant booking",
        )

    tc = match.warehouse.truth_core
    now = datetime.now(timezone.utc)

    # Calculate buyer rate
    pricing = pricing_engine.calculate_buyer_rate(
        supplier_rate=tc.supplier_rate_per_sqft,
        state=match.warehouse.state or "",
        warehouse_features={
            "has_office_space": tc.has_office_space,
            "has_sprinkler": tc.has_sprinkler,
            "clear_height_ft": tc.clear_height_ft,
            "dock_doors_receiving": tc.dock_doors_receiving,
            "parking_spaces": tc.parking_spaces,
        },
    )

    # Determine sqft (use need's max_sqft or warehouse's max_sqft)
    sqft = need.max_sqft or tc.max_sqft
    term_months = need.duration_months or tc.min_term_months or 1
    start_date = need.needed_from or now

    # Determine initial status based on deal type
    initial_status = "confirmed" if body.deal_type == "instant_book" else "terms_accepted"

    # Calculate deal economics (internal, not exposed to buyer)
    economics = pricing_engine.calculate_deal_economics(
        supplier_rate=tc.supplier_rate_per_sqft,
        buyer_rate=pricing["buyer_rate"],
        sqft=sqft,
        term_months=term_months,
    )

    # Create the deal
    deal = Deal(
        id=str(uuid.uuid4()),
        match_id=match.id,
        warehouse_id=match.warehouse_id,
        buyer_id=need.buyer_id,
        sqft_allocated=sqft,
        start_date=start_date,
        term_months=term_months,
        supplier_rate=tc.supplier_rate_per_sqft,  # Stored internally, never exposed
        buyer_rate=pricing["buyer_rate"],  # Locked buyer rate
        spread_pct=pricing["spread_pct"],  # Internal economics
        monthly_revenue=economics["monthly_wex_revenue"],  # Internal economics
        status=initial_status,
        deal_type=body.deal_type,
    )
    db.add(deal)

    # Also create Engagement record for the new lifecycle system
    engagement = Engagement(
        id=str(uuid.uuid4()),
        warehouse_id=match.warehouse_id,
        buyer_need_id=need_id,
        buyer_id=need.buyer_id,
        supplier_id=match.warehouse.created_by or "",
        status=EngagementStatus.BUYER_ACCEPTED.value,
        tier=EngagementTier.TIER_1.value,
        match_score=match.match_score,
        match_rank=None,
        supplier_rate_sqft=tc.supplier_rate_per_sqft,
        buyer_rate_sqft=pricing["buyer_rate"],
        monthly_supplier_payout=economics["monthly_supplier_payment"],
        monthly_buyer_total=economics["monthly_buyer_payment"],
        sqft=sqft,
    )
    db.add(engagement)

    # Create engagement event
    eng_event = EngagementEvent(
        id=str(uuid.uuid4()),
        engagement_id=engagement.id,
        event_type=EngagementEventType.BUYER_ACCEPTED.value,
        actor=EngagementActor.BUYER.value,
        actor_id=need.buyer_id,
        from_status=None,
        to_status=EngagementStatus.BUYER_ACCEPTED.value,
        data={"deal_id": deal.id, "path": body.deal_type},
    )
    db.add(eng_event)

    # Update match status
    match.status = "accepted"

    # Create deal event
    event = DealEvent(
        id=str(uuid.uuid4()),
        deal_id=deal.id,
        event_type="deal_created",
        details={
            "deal_type": body.deal_type,
            "initial_status": initial_status,
            "buyer_rate": pricing["buyer_rate"],
            "sqft": sqft,
            "term_months": term_months,
        },
    )
    db.add(event)

    await db.commit()

    # Return buyer-safe deal view
    return {
        "deal": _buyer_safe_deal(deal),
        "deal_id": deal.id,
        "engagement_id": engagement.id,
        "economics": {
            # ONLY buyer-facing economics - no supplier rate, no spread, no WEx revenue
            "monthly_payment": economics["monthly_buyer_payment"],
            "total_contract_value": economics["total_contract_value"],
            "security_deposit": economics["security_deposit"],
            "first_month_payment": economics["first_month_payment"],
            "upfront_total": economics["upfront_total"],
        },
    }


@router.post("/deal/{deal_id}/guarantee")
async def sign_guarantee(
    deal_id: str,
    body: GuaranteeSignRequest,
    db: AsyncSession = Depends(get_db),
):
    """Sign the WEx Occupancy Guarantee for a deal.

    ANTI-CIRCUMVENTION: This is the leverage point. The buyer must sign
    the guarantee BEFORE the property address is revealed. Once signed,
    the full address is returned in the response.

    Updates deal status to 'guarantee_signed' and records timestamps.
    """
    if not body.accepted:
        raise HTTPException(
            status_code=400,
            detail="You must accept the occupancy guarantee to proceed.",
        )

    result = await db.execute(
        select(Deal)
        .where(Deal.id == deal_id)
        .options(
            selectinload(Deal.warehouse),
        )
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.guarantee_signed_at:
        # Already signed — just return the deal with address
        warehouse_data = {}
        if deal.warehouse:
            warehouse_data = _buyer_safe_warehouse(deal.warehouse, reveal_address=True)
        return {
            "deal": _buyer_safe_deal(deal),
            "warehouse": warehouse_data,
            "already_signed": True,
        }

    if deal.status not in ("terms_accepted", "terms_presented"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot sign guarantee for deal with status '{deal.status}'",
        )

    now = datetime.now(timezone.utc)

    deal.guarantee_signed_at = now
    deal.address_revealed_at = now
    deal.status = "guarantee_signed"

    # Create deal event
    event = DealEvent(
        id=str(uuid.uuid4()),
        deal_id=deal.id,
        event_type="guarantee_signed",
        details={
            "signed_at": now.isoformat(),
            "address_revealed": True,
        },
    )
    db.add(event)

    await db.commit()

    # Return the deal WITH the full address now revealed
    warehouse_data = {}
    if deal.warehouse:
        warehouse_data = _buyer_safe_warehouse(deal.warehouse, reveal_address=True)

    return {
        "deal": _buyer_safe_deal(deal),
        "warehouse": warehouse_data,
    }


@router.post("/deal/{deal_id}/tour")
async def schedule_tour(
    deal_id: str,
    body: TourScheduleRequest,
    db: AsyncSession = Depends(get_db),
):
    """Schedule a tour for a deal.

    ANTI-CIRCUMVENTION: Guarantee must be signed first.
    Updates the deal with tour details and notifies the supplier.
    Sets tour_status to 'requested' pending supplier confirmation.
    """
    result = await db.execute(
        select(Deal)
        .where(Deal.id == deal_id)
        .options(selectinload(Deal.warehouse))
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    # Guarantee must be signed before scheduling
    if not deal.guarantee_signed_at:
        raise HTTPException(
            status_code=400,
            detail="Occupancy guarantee must be signed before scheduling a tour.",
        )

    if deal.status not in ("guarantee_signed", "terms_accepted", "terms_presented"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot schedule tour for deal with status '{deal.status}'",
        )

    now = datetime.now(timezone.utc)

    # Parse the preferred date and time into a datetime
    try:
        tour_datetime = datetime.fromisoformat(
            f"{body.preferred_date}T{body.preferred_time}"
        )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date or time format. Use YYYY-MM-DD and HH:MM",
        )

    deal.tour_scheduled_at = tour_datetime
    deal.tour_preferred_date = body.preferred_date
    deal.tour_preferred_time = body.preferred_time
    deal.tour_notes = body.notes
    deal.tour_status = "requested"
    deal.status = "tour_requested"

    # Create deal event
    event = DealEvent(
        id=str(uuid.uuid4()),
        deal_id=deal.id,
        event_type="tour_scheduled",
        details={
            "preferred_date": body.preferred_date,
            "preferred_time": body.preferred_time,
            "notes": body.notes,
            "scheduled_at": tour_datetime.isoformat(),
        },
    )
    db.add(event)

    # Trigger supplier notification (best-effort)
    try:
        from wex_platform.services.email_service import send_tour_notification
        if deal.warehouse and deal.warehouse.owner_email:
            import asyncio
            asyncio.ensure_future(send_tour_notification(
                supplier_email=deal.warehouse.owner_email,
                deal_id=deal.id,
                warehouse_address=deal.warehouse.address,
                tour_date=body.preferred_date,
                tour_time=body.preferred_time,
                notes=body.notes,
            ))
    except ImportError:
        logger.warning("Email service not available for tour notification")
    except Exception as e:
        logger.warning("Tour notification failed (non-blocking): %s", e)

    return {
        "deal_id": deal.id,
        "status": deal.status,
        "tour_status": deal.tour_status,
        "tour_scheduled_at": tour_datetime.isoformat(),
        "preferred_date": body.preferred_date,
        "preferred_time": body.preferred_time,
        "message": "Tour requested! The supplier will confirm within 12 hours.",
    }


@router.post("/deal/{deal_id}/tour-outcome")
async def record_tour_outcome(
    deal_id: str,
    body: TourOutcomeRequest,
    db: AsyncSession = Depends(get_db),
):
    """Record the outcome of a warehouse tour.

    If confirmed, the deal moves to 'confirmed' status.
    If passed, the deal moves to 'declined' status with reason captured
    for the learning loop.
    """
    result = await db.execute(
        select(Deal).where(Deal.id == deal_id)
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    if deal.status not in ("tour_scheduled", "tour_requested", "tour_confirmed"):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot record tour outcome for deal with status '{deal.status}'",
        )

    if body.outcome not in ("confirmed", "passed"):
        raise HTTPException(
            status_code=400,
            detail="Outcome must be 'confirmed' or 'passed'",
        )

    now = datetime.now(timezone.utc)
    deal.tour_completed_at = now
    deal.tour_outcome = body.outcome
    deal.tour_status = "completed"

    if body.outcome == "confirmed":
        deal.status = "confirmed"
    else:
        deal.status = "declined"
        deal.tour_pass_reason = body.reason

    # Create deal event
    event = DealEvent(
        id=str(uuid.uuid4()),
        deal_id=deal.id,
        event_type="tour_outcome",
        details={
            "outcome": body.outcome,
            "reason": body.reason,
            "new_status": deal.status,
        },
    )
    db.add(event)

    # Trigger 24hr follow-up (best-effort)
    try:
        from wex_platform.services.email_service import schedule_tour_followup
        import asyncio
        asyncio.ensure_future(schedule_tour_followup(deal_id=deal.id))
    except ImportError:
        logger.warning("Email service not available for tour follow-up")
    except Exception as e:
        logger.warning("Tour follow-up scheduling failed: %s", e)

    return {
        "deal_id": deal.id,
        "status": deal.status,
        "tour_status": deal.tour_status,
        "tour_outcome": body.outcome,
        "tour_completed_at": now.isoformat(),
        "reason": body.reason,
    }


@router.get("/{buyer_id}/deals")
async def get_buyer_deals(
    buyer_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all deals for a buyer (buyer view - no supplier rates).

    ISOLATION: Only buyer_rate and buyer-facing economics are returned.
    No supplier_rate, spread_pct, monthly_revenue, or owner identity.
    """
    # Verify buyer exists
    buyer_result = await db.execute(
        select(Buyer).where(Buyer.id == buyer_id)
    )
    if not buyer_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Buyer not found")

    result = await db.execute(
        select(Deal)
        .where(Deal.buyer_id == buyer_id)
        .order_by(Deal.created_at.desc())
    )
    deals = result.scalars().all()

    return [_buyer_safe_deal(deal) for deal in deals]
