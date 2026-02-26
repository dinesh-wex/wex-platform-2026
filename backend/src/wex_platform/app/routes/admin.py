"""Admin API routes -- full visibility into both sides of the clearinghouse.

NO ECONOMIC ISOLATION: Admin endpoints expose supplier rates, buyer rates,
spreads, and all internal WEx economics. These routes are intended for the
internal admin dashboard only and must be protected by authentication in
production.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.infra.database import get_db
from wex_platform.domain.models import (
    Property,
    PropertyKnowledge,
    PropertyListing,
    Buyer,
    BuyerLedger,
    Deal,
    DealEvent,
    Match,
    AgentLog,
    SupplierLedger,
    InsuranceCoverage,
    Deposit,
)
from wex_platform.services.settlement_service import SettlementService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Inline request / response models
# ---------------------------------------------------------------------------


class AcceptDealRequest(BaseModel):
    """Request body for accepting a deal via settlement."""

    match_id: str
    deal_type: str = "standard"


class TourActionRequest(BaseModel):
    """Request body for scheduling or completing a tour."""

    deal_id: str
    action: str  # "schedule" or "complete"
    tour_datetime: Optional[str] = None
    outcome: Optional[str] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/overview")
async def get_overview(db: AsyncSession = Depends(get_db)):
    """Network overview stats for the admin dashboard.

    Returns aggregate counts and economics across the entire clearinghouse.
    """
    # Total properties
    total_wh_result = await db.execute(
        select(func.count()).select_from(Property)
    )
    total_warehouses = total_wh_result.scalar() or 0

    # Active / inactive property counts (via PropertyListing activation_status)
    active_wh_result = await db.execute(
        select(func.count())
        .select_from(PropertyListing)
        .where(PropertyListing.activation_status == "on")
    )
    active_warehouses = active_wh_result.scalar() or 0
    inactive_warehouses = total_warehouses - active_warehouses

    # Total buyers
    total_buyers_result = await db.execute(
        select(func.count()).select_from(Buyer)
    )
    total_buyers = total_buyers_result.scalar() or 0

    # Active deals
    active_deals_result = await db.execute(
        select(func.count())
        .select_from(Deal)
        .where(Deal.status.in_(["active", "confirmed"]))
    )
    total_active_deals = active_deals_result.scalar() or 0

    # Monthly GMV and spread from active deals
    gmv_result = await db.execute(
        select(
            func.coalesce(func.sum(Deal.buyer_rate * Deal.sqft_allocated), 0.0),
            func.coalesce(
                func.sum(
                    (Deal.buyer_rate - Deal.supplier_rate) * Deal.sqft_allocated
                ),
                0.0,
            ),
            func.count(),
        )
        .select_from(Deal)
        .where(Deal.status.in_(["active", "confirmed"]))
    )
    row = gmv_result.one()
    total_monthly_gmv = float(row[0])
    total_monthly_spread = float(row[1])
    active_count_for_avg = int(row[2])

    # Average spread percentage
    avg_spread_pct = 0.0
    if active_count_for_avg > 0:
        avg_spread_result = await db.execute(
            select(func.coalesce(func.avg(Deal.spread_pct), 0.0))
            .select_from(Deal)
            .where(Deal.status.in_(["active", "confirmed"]))
        )
        avg_spread_pct = float(avg_spread_result.scalar() or 0.0)

    return {
        "total_warehouses": total_warehouses,
        "active_warehouses": active_warehouses,
        "inactive_warehouses": inactive_warehouses,
        "total_buyers": total_buyers,
        "total_active_deals": total_active_deals,
        "total_monthly_gmv": round(total_monthly_gmv, 2),
        "total_monthly_spread": round(total_monthly_spread, 2),
        "avg_spread_pct": round(avg_spread_pct, 4),
    }


@router.get("/warehouses")
async def list_warehouses(db: AsyncSession = Depends(get_db)):
    """All properties with listing data, activation status, and supplier rates.

    Admin has full visibility -- no economic isolation.
    """
    result = await db.execute(
        select(Property).options(
            selectinload(Property.knowledge),
            selectinload(Property.listing),
        )
    )
    properties = result.scalars().all()

    items = []
    for prop in properties:
        activation_status = None
        supplier_rate = None
        available_sqft = None
        building_size_sqft = None

        pk = prop.knowledge
        pl = prop.listing

        if pl:
            activation_status = pl.activation_status
            supplier_rate = pl.supplier_rate_per_sqft
            available_sqft = pl.max_sqft

        if pk:
            building_size_sqft = pk.building_size_sqft

        # Count current active placements via Deal table
        deal_count_result = await db.execute(
            select(func.count())
            .select_from(Deal)
            .where(Deal.warehouse_id == prop.id)
            .where(Deal.status.in_(("active", "confirmed")))
        )
        active_placements = deal_count_result.scalar() or 0

        items.append({
            "id": prop.id,
            "address": prop.address,
            "city": prop.city,
            "state": prop.state,
            "building_size_sqft": building_size_sqft,
            "activation_status": activation_status,
            "supplier_rate": supplier_rate,
            "available_sqft": available_sqft,
            "current_placements": active_placements,
        })

    return items


@router.get("/deals")
async def list_deals(
    status: Optional[str] = Query(None, description="Filter by deal status"),
    db: AsyncSession = Depends(get_db),
):
    """All deals with full economics visible to admin.

    Includes supplier_rate, buyer_rate, spread, and monthly WEx revenue.
    """
    query = (
        select(Deal)
        .options(
            selectinload(Deal.warehouse),
            selectinload(Deal.buyer),
        )
        .order_by(Deal.created_at.desc())
    )

    if status:
        query = query.where(Deal.status == status)

    result = await db.execute(query)
    deals = result.scalars().all()

    items = []
    for deal in deals:
        warehouse_address = deal.warehouse.address if deal.warehouse else None
        buyer_company = deal.buyer.company if deal.buyer else None

        spread = (deal.buyer_rate - deal.supplier_rate) if deal.buyer_rate and deal.supplier_rate else 0.0
        spread_pct = deal.spread_pct or 0.0
        monthly_revenue = spread * deal.sqft_allocated if spread else 0.0

        items.append({
            "id": deal.id,
            "warehouse_address": warehouse_address,
            "buyer_company": buyer_company,
            "sqft": deal.sqft_allocated,
            "supplier_rate": deal.supplier_rate,
            "buyer_rate": deal.buyer_rate,
            "spread": round(spread, 4),
            "spread_pct": round(spread_pct, 4),
            "monthly_revenue": round(monthly_revenue, 2),
            "status": deal.status,
            "deal_type": deal.deal_type,
            "created_at": deal.created_at.isoformat() if deal.created_at else None,
        })

    return items


@router.get("/deals/{deal_id}")
async def get_deal_detail(
    deal_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Single deal detail with full economics, ledger entries, insurance, and deposits."""
    result = await db.execute(
        select(Deal)
        .where(Deal.id == deal_id)
        .options(
            selectinload(Deal.warehouse),
            selectinload(Deal.buyer),
            selectinload(Deal.events),
            selectinload(Deal.insurance_coverages),
            selectinload(Deal.deposits),
        )
    )
    deal = result.scalar_one_or_none()

    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found")

    warehouse_address = deal.warehouse.address if deal.warehouse else None
    buyer_company = deal.buyer.company if deal.buyer else None

    spread = (deal.buyer_rate - deal.supplier_rate) if deal.buyer_rate and deal.supplier_rate else 0.0
    monthly_revenue = spread * deal.sqft_allocated if spread else 0.0

    # Build events list
    events_list = []
    for ev in (deal.events or []):
        events_list.append({
            "id": ev.id,
            "event_type": ev.event_type,
            "details": ev.details,
            "created_at": ev.created_at.isoformat() if ev.created_at else None,
        })

    # Build insurance list
    insurance_list = []
    for ic in (deal.insurance_coverages or []):
        insurance_list.append({
            "id": ic.id,
            "coverage_status": ic.coverage_status,
            "coverage_amount": ic.coverage_amount,
            "monthly_premium": ic.monthly_premium,
            "created_at": ic.created_at.isoformat() if ic.created_at else None,
        })

    # Build deposits list
    deposits_list = []
    for dep in (deal.deposits or []):
        deposits_list.append({
            "id": dep.id,
            "deposit_type": dep.deposit_type,
            "amount": dep.amount,
            "status": dep.status,
            "applied_reason": dep.applied_reason,
            "created_at": dep.created_at.isoformat() if dep.created_at else None,
            "released_at": dep.released_at.isoformat() if dep.released_at else None,
        })

    # Fetch supplier ledger entries for this deal
    supplier_ledger_result = await db.execute(
        select(SupplierLedger)
        .where(SupplierLedger.deal_id == deal_id)
        .order_by(SupplierLedger.created_at.desc())
    )
    supplier_ledger_entries = supplier_ledger_result.scalars().all()

    supplier_ledger_list = []
    for le in supplier_ledger_entries:
        supplier_ledger_list.append({
            "id": le.id,
            "entry_type": le.entry_type,
            "amount": le.amount,
            "description": le.description,
            "period_start": le.period_start.isoformat() if le.period_start else None,
            "period_end": le.period_end.isoformat() if le.period_end else None,
            "status": le.status,
            "created_at": le.created_at.isoformat() if le.created_at else None,
        })

    # Fetch buyer ledger entries for this deal
    buyer_ledger_result = await db.execute(
        select(BuyerLedger)
        .where(BuyerLedger.deal_id == deal_id)
        .order_by(BuyerLedger.created_at.desc())
    )
    buyer_ledger_entries = buyer_ledger_result.scalars().all()

    buyer_ledger_list = []
    for le in buyer_ledger_entries:
        buyer_ledger_list.append({
            "id": le.id,
            "entry_type": le.entry_type,
            "amount": le.amount,
            "description": le.description,
            "period_start": le.period_start.isoformat() if le.period_start else None,
            "period_end": le.period_end.isoformat() if le.period_end else None,
            "status": le.status,
            "created_at": le.created_at.isoformat() if le.created_at else None,
        })

    return {
        "id": deal.id,
        "match_id": deal.match_id,
        "warehouse_id": deal.warehouse_id,
        "warehouse_address": warehouse_address,
        "buyer_id": deal.buyer_id,
        "buyer_company": buyer_company,
        "sqft_allocated": deal.sqft_allocated,
        "start_date": deal.start_date.isoformat() if deal.start_date else None,
        "end_date": deal.end_date.isoformat() if deal.end_date else None,
        "term_months": deal.term_months,
        "supplier_rate": deal.supplier_rate,
        "buyer_rate": deal.buyer_rate,
        "spread": round(spread, 4),
        "spread_pct": deal.spread_pct,
        "monthly_revenue": round(monthly_revenue, 2),
        "tour_scheduled_at": deal.tour_scheduled_at.isoformat() if deal.tour_scheduled_at else None,
        "tour_completed_at": deal.tour_completed_at.isoformat() if deal.tour_completed_at else None,
        "tour_outcome": deal.tour_outcome,
        "status": deal.status,
        "deal_type": deal.deal_type,
        "created_at": deal.created_at.isoformat() if deal.created_at else None,
        "updated_at": deal.updated_at.isoformat() if deal.updated_at else None,
        "events": events_list,
        "insurance_coverages": insurance_list,
        "deposits": deposits_list,
        "supplier_ledger": supplier_ledger_list,
        "buyer_ledger": buyer_ledger_list,
    }


@router.get("/agents")
async def get_agent_logs(db: AsyncSession = Depends(get_db)):
    """Agent activity log -- most recent 50 entries.

    Shows AI agent telemetry including tokens used and latency.
    """
    result = await db.execute(
        select(AgentLog)
        .order_by(AgentLog.created_at.desc())
        .limit(50)
    )
    entries = result.scalars().all()

    return [
        {
            "id": entry.id,
            "agent_name": entry.agent_name,
            "action": entry.action,
            "input_summary": entry.input_summary,
            "output_summary": entry.output_summary,
            "tokens_used": entry.tokens_used,
            "latency_ms": entry.latency_ms,
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
        }
        for entry in entries
    ]


@router.get("/ledger")
async def get_principal_ledger(db: AsyncSession = Depends(get_db)):
    """Principal ledger view -- buyer payments in, supplier payments out, net WEx revenue.

    Aggregates both sides of the ledger with recent entries.
    """
    # Sum of buyer payments in
    buyer_total_result = await db.execute(
        select(func.coalesce(func.sum(BuyerLedger.amount), 0.0))
        .select_from(BuyerLedger)
    )
    buyer_payments_in = float(buyer_total_result.scalar() or 0.0)

    # Sum of supplier payments out
    supplier_total_result = await db.execute(
        select(func.coalesce(func.sum(SupplierLedger.amount), 0.0))
        .select_from(SupplierLedger)
    )
    supplier_payments_out = float(supplier_total_result.scalar() or 0.0)

    # Net WEx revenue
    net_wex_revenue = buyer_payments_in - supplier_payments_out

    # Recent buyer ledger entries (last 20)
    buyer_entries_result = await db.execute(
        select(BuyerLedger)
        .order_by(BuyerLedger.created_at.desc())
        .limit(20)
    )
    buyer_entries = buyer_entries_result.scalars().all()

    recent_buyer_entries = [
        {
            "id": e.id,
            "buyer_id": e.buyer_id,
            "deal_id": e.deal_id,
            "entry_type": e.entry_type,
            "amount": e.amount,
            "description": e.description,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in buyer_entries
    ]

    # Recent supplier ledger entries (last 20)
    supplier_entries_result = await db.execute(
        select(SupplierLedger)
        .order_by(SupplierLedger.created_at.desc())
        .limit(20)
    )
    supplier_entries = supplier_entries_result.scalars().all()

    recent_supplier_entries = [
        {
            "id": e.id,
            "warehouse_id": e.warehouse_id,
            "deal_id": e.deal_id,
            "entry_type": e.entry_type,
            "amount": e.amount,
            "description": e.description,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in supplier_entries
    ]

    return {
        "buyer_payments_in": round(buyer_payments_in, 2),
        "supplier_payments_out": round(supplier_payments_out, 2),
        "net_wex_revenue": round(net_wex_revenue, 2),
        "recent_buyer_entries": recent_buyer_entries,
        "recent_supplier_entries": recent_supplier_entries,
    }


@router.get("/clearing/stats")
async def get_clearing_stats(db: AsyncSession = Depends(get_db)):
    """Clearing engine statistics.

    Aggregate metrics on match creation, acceptance, scoring, and
    instant book rates.
    """
    # Total matches by status
    total_matches_result = await db.execute(
        select(func.count()).select_from(Match)
    )
    total_matches = total_matches_result.scalar() or 0

    # Accepted matches (status = 'accepted')
    accepted_result = await db.execute(
        select(func.count())
        .select_from(Match)
        .where(Match.status == "accepted")
    )
    accepted_matches = accepted_result.scalar() or 0

    # Declined matches (status = 'declined')
    declined_result = await db.execute(
        select(func.count())
        .select_from(Match)
        .where(Match.status == "declined")
    )
    declined_matches = declined_result.scalar() or 0

    # Average match score
    avg_score_result = await db.execute(
        select(func.coalesce(func.avg(Match.match_score), 0.0))
        .select_from(Match)
    )
    avg_match_score = float(avg_score_result.scalar() or 0.0)

    # Instant book rate
    total_deals_result = await db.execute(
        select(func.count()).select_from(Deal)
    )
    total_deals = total_deals_result.scalar() or 0

    instant_book_result = await db.execute(
        select(func.count())
        .select_from(Deal)
        .where(Deal.deal_type == "instant_book")
    )
    instant_book_deals = instant_book_result.scalar() or 0

    instant_book_rate = 0.0
    if total_deals > 0:
        instant_book_rate = (instant_book_deals / total_deals) * 100

    return {
        "total_matches": total_matches,
        "accepted_matches": accepted_matches,
        "declined_matches": declined_matches,
        "avg_match_score": round(avg_match_score, 4),
        "total_deals": total_deals,
        "instant_book_deals": instant_book_deals,
        "instant_book_rate": round(instant_book_rate, 2),
    }


# ---------------------------------------------------------------------------
# Settlement endpoints
# ---------------------------------------------------------------------------


@router.post("/settlement/accept")
async def accept_deal(
    body: AcceptDealRequest,
    db: AsyncSession = Depends(get_db),
):
    """Accept a deal via the settlement service.

    Creates the deal from a match, calculates economics, and initiates
    the settlement flow.
    """
    settlement = SettlementService(db)

    try:
        result = await settlement.accept_deal(
            match_id=body.match_id,
            deal_type=body.deal_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Settlement accept_deal error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Settlement service error: {str(e)}",
        )

    return result


@router.post("/settlement/tour")
async def settlement_tour(
    body: TourActionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Schedule or complete a tour via the settlement service.

    Actions:
    - "schedule": sets tour_datetime on the deal
    - "complete": records the tour outcome
    """
    settlement = SettlementService(db)

    try:
        if body.action == "schedule":
            if not body.tour_datetime:
                raise HTTPException(
                    status_code=400,
                    detail="tour_datetime is required when action is 'schedule'",
                )
            result = await settlement.schedule_tour(
                deal_id=body.deal_id,
                tour_datetime=body.tour_datetime,
            )
        elif body.action == "complete":
            if not body.outcome:
                raise HTTPException(
                    status_code=400,
                    detail="outcome is required when action is 'complete'",
                )
            result = await settlement.complete_tour(
                deal_id=body.deal_id,
                outcome=body.outcome,
                reason=body.reason,
            )
        else:
            raise HTTPException(
                status_code=400,
                detail="action must be 'schedule' or 'complete'",
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Settlement tour error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Settlement service error: {str(e)}",
        )

    return result


@router.get("/settlement/deal/{deal_id}/summary")
async def get_deal_summary(
    deal_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Full deal summary via the settlement service.

    Returns comprehensive deal information including economics,
    timeline, and current state.
    """
    settlement = SettlementService(db)

    try:
        result = await settlement.get_deal_summary(deal_id=deal_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Settlement get_deal_summary error: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Settlement service error: {str(e)}",
        )

    return result
