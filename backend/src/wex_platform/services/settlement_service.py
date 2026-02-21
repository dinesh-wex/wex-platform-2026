"""Settlement Service - Handles deal lifecycle operations.

This is NOT an AI agent. It is business logic that orchestrates the
creation and progression of deals through their lifecycle: acceptance,
tour scheduling, confirmation, ledger entries, and summaries.

ECONOMIC ISOLATION: Internal methods see both sides of the economics
(supplier rate, buyer rate, spread). External-facing methods must be
careful about what they expose -- see the clearing engine for patterns.
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.domain.models import (
    Deal,
    DealEvent,
    Match,
    Warehouse,
    TruthCore,
    Buyer,
    BuyerNeed,
    BuyerLedger,
    SupplierLedger,
    InsuranceCoverage,
    Deposit,
)
from wex_platform.domain.enums import (
    DealStatus,
    DealType,
    MatchStatus,
    LedgerEntryType,
    DepositType,
    DepositStatus,
    CoverageStatus,
)
from wex_platform.services.pricing_engine import PricingEngine

logger = logging.getLogger(__name__)


class SettlementService:
    """Orchestrates deal lifecycle from acceptance through active management.

    All methods are async and accept a SQLAlchemy AsyncSession.  The
    caller is responsible for committing or rolling back the session
    after each operation.
    """

    def __init__(self):
        self.pricing_engine = PricingEngine()

    # ------------------------------------------------------------------
    # Deal Acceptance
    # ------------------------------------------------------------------

    async def accept_deal(
        self,
        db: AsyncSession,
        match_id: str,
        deal_type: str = "standard",
    ) -> dict:
        """Accept a match and create a full deal with all financial records.

        Steps:
            1. Load the match record with related buyer need and warehouse
            2. Load warehouse truth_core to get supplier_rate
            3. Use pricing engine to calculate buyer_rate
            4. Create Deal record with both rates, sqft, term, spread
            5. Create DealEvent (type='created')
            6. Create InsuranceCoverage (active, coverage = 3x monthly)
            7. Create Deposit records (security_deposit + first_month)
            8. Create dual ledger entries (BuyerLedger + SupplierLedger)
            9. Update match status to 'accepted'
            10. Return deal summary dict

        Args:
            db: Active async SQLAlchemy session.
            match_id: UUID of the Match to accept.
            deal_type: 'standard' or 'instant_book'.

        Returns:
            Dict with deal details and related record IDs.

        Raises:
            ValueError: If match or related records are not found.
        """
        # 1. Load match with relationships
        result = await db.execute(
            select(Match)
            .where(Match.id == match_id)
            .options(
                selectinload(Match.buyer_need),
                selectinload(Match.warehouse),
            )
        )
        match = result.scalar_one_or_none()
        if not match:
            raise ValueError(f"Match {match_id} not found")

        buyer_need = match.buyer_need
        if not buyer_need:
            raise ValueError(f"BuyerNeed not found for match {match_id}")

        warehouse = match.warehouse
        if not warehouse:
            raise ValueError(f"Warehouse not found for match {match_id}")

        # 2. Load truth_core for supplier rate
        tc_result = await db.execute(
            select(TruthCore).where(TruthCore.warehouse_id == warehouse.id)
        )
        truth_core = tc_result.scalar_one_or_none()
        if not truth_core:
            raise ValueError(f"TruthCore not found for warehouse {warehouse.id}")

        supplier_rate = truth_core.supplier_rate_per_sqft

        # 3. Calculate buyer rate via pricing engine
        warehouse_features = {
            "has_office_space": truth_core.has_office_space,
            "has_sprinkler": truth_core.has_sprinkler,
            "clear_height_ft": truth_core.clear_height_ft,
            "dock_doors_receiving": truth_core.dock_doors_receiving,
            "parking_spaces": truth_core.parking_spaces,
        }
        pricing = self.pricing_engine.calculate_buyer_rate(
            supplier_rate=supplier_rate,
            state=warehouse.state or "",
            warehouse_features=warehouse_features,
        )
        buyer_rate = pricing["buyer_rate"]

        # Deal parameters
        sqft = buyer_need.max_sqft or buyer_need.min_sqft or truth_core.min_sqft
        term_months = buyer_need.duration_months or 6
        start_date = buyer_need.needed_from or datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=term_months * 30)

        # Economics
        monthly_buyer = buyer_rate * sqft
        monthly_supplier = supplier_rate * sqft
        monthly_spread = monthly_buyer - monthly_supplier
        spread_pct = (monthly_spread / monthly_buyer * 100) if monthly_buyer > 0 else 0

        # 4. Create Deal record
        deal_id = str(uuid.uuid4())
        deal = Deal(
            id=deal_id,
            match_id=match_id,
            warehouse_id=warehouse.id,
            buyer_id=buyer_need.buyer_id,
            sqft_allocated=sqft,
            start_date=start_date,
            end_date=end_date,
            term_months=term_months,
            supplier_rate=supplier_rate,
            buyer_rate=buyer_rate,
            spread_pct=round(spread_pct, 1),
            monthly_revenue=round(monthly_spread, 2),
            status=DealStatus.TERMS_ACCEPTED.value,
            deal_type=deal_type,
        )
        db.add(deal)

        # 5. Create DealEvent
        event_id = str(uuid.uuid4())
        deal_event = DealEvent(
            id=event_id,
            deal_id=deal_id,
            event_type="created",
            details={
                "match_id": match_id,
                "deal_type": deal_type,
                "sqft_allocated": sqft,
                "buyer_rate": buyer_rate,
                "supplier_rate": supplier_rate,
                "spread_pct": round(spread_pct, 1),
            },
        )
        db.add(deal_event)

        # 6. Create InsuranceCoverage (3x monthly supplier payment)
        insurance_id = str(uuid.uuid4())
        coverage_amount = round(monthly_supplier * 3, 2)
        insurance = InsuranceCoverage(
            id=insurance_id,
            deal_id=deal_id,
            warehouse_id=warehouse.id,
            coverage_status=CoverageStatus.ACTIVE.value,
            coverage_amount=coverage_amount,
            monthly_premium=round(coverage_amount * 0.02, 2),  # 2% monthly premium
        )
        db.add(insurance)

        # 7. Create Deposit records
        security_deposit_id = str(uuid.uuid4())
        security_deposit = Deposit(
            id=security_deposit_id,
            deal_id=deal_id,
            buyer_id=buyer_need.buyer_id,
            deposit_type=DepositType.SECURITY_DEPOSIT.value,
            amount=round(monthly_buyer, 2),
            status=DepositStatus.HELD.value,
        )
        db.add(security_deposit)

        first_month_id = str(uuid.uuid4())
        first_month_deposit = Deposit(
            id=first_month_id,
            deal_id=deal_id,
            buyer_id=buyer_need.buyer_id,
            deposit_type=DepositType.FIRST_MONTH.value,
            amount=round(monthly_buyer, 2),
            status=DepositStatus.HELD.value,
        )
        db.add(first_month_deposit)

        # 8. Create dual ledger entries
        # Buyer ledger: first month debit
        buyer_ledger_id = str(uuid.uuid4())
        buyer_ledger = BuyerLedger(
            id=buyer_ledger_id,
            buyer_id=buyer_need.buyer_id,
            deal_id=deal_id,
            entry_type=LedgerEntryType.PAYMENT.value,
            amount=round(monthly_buyer, 2),
            description=f"First month payment - {sqft:,} sqft at ${buyer_rate}/sqft",
            period_start=start_date,
            period_end=start_date + timedelta(days=30),
            status="pending",
        )
        db.add(buyer_ledger)

        # Supplier ledger: first payment credit
        supplier_ledger_id = str(uuid.uuid4())
        supplier_ledger = SupplierLedger(
            id=supplier_ledger_id,
            warehouse_id=warehouse.id,
            deal_id=deal_id,
            entry_type=LedgerEntryType.PAYMENT.value,
            amount=round(monthly_supplier, 2),
            description=f"First month supplier payment - {sqft:,} sqft at ${supplier_rate}/sqft",
            period_start=start_date,
            period_end=start_date + timedelta(days=30),
            status="pending",
        )
        db.add(supplier_ledger)

        # 9. Update match status
        match.status = MatchStatus.ACCEPTED.value

        await db.commit()

        logger.info(
            "Deal %s created from match %s: %d sqft, %d months, buyer_rate=$%.2f, supplier_rate=$%.2f",
            deal_id,
            match_id,
            sqft,
            term_months,
            buyer_rate,
            supplier_rate,
        )

        return {
            "deal_id": deal_id,
            "match_id": match_id,
            "warehouse_id": warehouse.id,
            "buyer_id": buyer_need.buyer_id,
            "sqft_allocated": sqft,
            "term_months": term_months,
            "start_date": str(start_date),
            "end_date": str(end_date),
            "buyer_rate": buyer_rate,
            "supplier_rate": supplier_rate,
            "spread_pct": round(spread_pct, 1),
            "monthly_buyer_payment": round(monthly_buyer, 2),
            "monthly_supplier_payment": round(monthly_supplier, 2),
            "monthly_wex_revenue": round(monthly_spread, 2),
            "insurance_id": insurance_id,
            "insurance_coverage": coverage_amount,
            "security_deposit": round(monthly_buyer, 2),
            "first_month_payment": round(monthly_buyer, 2),
            "status": DealStatus.TERMS_ACCEPTED.value,
            "deal_type": deal_type,
        }

    # ------------------------------------------------------------------
    # Tour Scheduling
    # ------------------------------------------------------------------

    async def schedule_tour(
        self,
        db: AsyncSession,
        deal_id: str,
        tour_datetime: str,
    ) -> dict:
        """Schedule a warehouse tour for a deal.

        Args:
            db: Active async SQLAlchemy session.
            deal_id: UUID of the Deal.
            tour_datetime: ISO-format datetime string for the tour.

        Returns:
            Dict with updated deal fields.

        Raises:
            ValueError: If deal is not found.
        """
        deal = await db.get(Deal, deal_id)
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        tour_dt = datetime.fromisoformat(tour_datetime)
        deal.tour_scheduled_at = tour_dt
        deal.status = DealStatus.TOUR_SCHEDULED.value
        deal.updated_at = datetime.now(timezone.utc)

        event = DealEvent(
            id=str(uuid.uuid4()),
            deal_id=deal_id,
            event_type="tour_scheduled",
            details={
                "tour_datetime": tour_datetime,
                "previous_status": deal.status,
            },
        )
        db.add(event)

        await db.commit()

        logger.info("Tour scheduled for deal %s at %s", deal_id, tour_datetime)

        return {
            "deal_id": deal_id,
            "status": DealStatus.TOUR_SCHEDULED.value,
            "tour_scheduled_at": tour_datetime,
        }

    # ------------------------------------------------------------------
    # Tour Completion
    # ------------------------------------------------------------------

    async def complete_tour(
        self,
        db: AsyncSession,
        deal_id: str,
        outcome: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Record the outcome of a warehouse tour.

        Args:
            db: Active async SQLAlchemy session.
            deal_id: UUID of the Deal.
            outcome: 'confirmed' or 'passed'.
            reason: Optional reason if the buyer passed.

        Returns:
            Dict with updated deal fields.

        Raises:
            ValueError: If deal is not found or outcome is invalid.
        """
        if outcome not in ("confirmed", "passed"):
            raise ValueError(f"Invalid tour outcome: {outcome}. Must be 'confirmed' or 'passed'.")

        deal = await db.get(Deal, deal_id)
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        deal.tour_completed_at = datetime.now(timezone.utc)
        deal.tour_outcome = outcome
        deal.updated_at = datetime.now(timezone.utc)

        if outcome == "confirmed":
            deal.status = DealStatus.CONFIRMED.value
        elif outcome == "passed":
            deal.status = DealStatus.DECLINED.value
            deal.tour_pass_reason = reason

        event = DealEvent(
            id=str(uuid.uuid4()),
            deal_id=deal_id,
            event_type=f"tour_{outcome}",
            details={
                "outcome": outcome,
                "reason": reason,
            },
        )
        db.add(event)

        await db.commit()

        logger.info("Tour completed for deal %s: outcome=%s", deal_id, outcome)

        return {
            "deal_id": deal_id,
            "status": deal.status,
            "tour_outcome": outcome,
            "tour_completed_at": str(deal.tour_completed_at),
            "tour_pass_reason": reason,
        }

    # ------------------------------------------------------------------
    # Deal Confirmation
    # ------------------------------------------------------------------

    async def confirm_deal(
        self,
        db: AsyncSession,
        deal_id: str,
    ) -> dict:
        """Confirm a deal and set it to active status.

        Args:
            db: Active async SQLAlchemy session.
            deal_id: UUID of the Deal.

        Returns:
            Dict with updated deal fields.

        Raises:
            ValueError: If deal is not found.
        """
        deal = await db.get(Deal, deal_id)
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        deal.status = DealStatus.ACTIVE.value
        deal.updated_at = datetime.now(timezone.utc)

        event = DealEvent(
            id=str(uuid.uuid4()),
            deal_id=deal_id,
            event_type="confirmed",
            details={
                "previous_status": deal.status,
                "confirmed_at": str(datetime.now(timezone.utc)),
            },
        )
        db.add(event)

        await db.commit()

        logger.info("Deal %s confirmed and now active", deal_id)

        return {
            "deal_id": deal_id,
            "status": DealStatus.ACTIVE.value,
            "confirmed_at": str(datetime.now(timezone.utc)),
        }

    # ------------------------------------------------------------------
    # Monthly Ledger Generation
    # ------------------------------------------------------------------

    async def generate_monthly_ledger_entries(
        self,
        db: AsyncSession,
        deal_id: str,
    ) -> dict:
        """Generate a new pair of monthly ledger entries for a deal.

        Creates one BuyerLedger entry (buyer pays WEx at buyer_rate * sqft)
        and one SupplierLedger entry (WEx pays supplier at supplier_rate * sqft).

        Args:
            db: Active async SQLAlchemy session.
            deal_id: UUID of the Deal.

        Returns:
            Dict with entry details and spread calculation.

        Raises:
            ValueError: If deal is not found.
        """
        deal = await db.get(Deal, deal_id)
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        monthly_buyer = deal.buyer_rate * deal.sqft_allocated
        monthly_supplier = deal.supplier_rate * deal.sqft_allocated
        monthly_spread = monthly_buyer - monthly_supplier

        # Determine the period for this entry
        # Find the latest buyer ledger entry to calculate next period
        existing_result = await db.execute(
            select(BuyerLedger)
            .where(BuyerLedger.deal_id == deal_id)
            .order_by(BuyerLedger.period_end.desc())
        )
        latest_entry = existing_result.scalars().first()

        if latest_entry and latest_entry.period_end:
            period_start = latest_entry.period_end
        else:
            period_start = deal.start_date

        period_end = period_start + timedelta(days=30)

        # Buyer ledger entry
        buyer_entry_id = str(uuid.uuid4())
        buyer_entry = BuyerLedger(
            id=buyer_entry_id,
            buyer_id=deal.buyer_id,
            deal_id=deal_id,
            entry_type=LedgerEntryType.PAYMENT.value,
            amount=round(monthly_buyer, 2),
            description=f"Monthly payment - {deal.sqft_allocated:,} sqft at ${deal.buyer_rate}/sqft",
            period_start=period_start,
            period_end=period_end,
            status="pending",
        )
        db.add(buyer_entry)

        # Supplier ledger entry
        supplier_entry_id = str(uuid.uuid4())
        supplier_entry = SupplierLedger(
            id=supplier_entry_id,
            warehouse_id=deal.warehouse_id,
            deal_id=deal_id,
            entry_type=LedgerEntryType.PAYMENT.value,
            amount=round(monthly_supplier, 2),
            description=f"Monthly supplier payment - {deal.sqft_allocated:,} sqft at ${deal.supplier_rate}/sqft",
            period_start=period_start,
            period_end=period_end,
            status="pending",
        )
        db.add(supplier_entry)

        await db.commit()

        logger.info(
            "Monthly ledger entries created for deal %s: buyer=$%.2f, supplier=$%.2f, spread=$%.2f",
            deal_id,
            monthly_buyer,
            monthly_supplier,
            monthly_spread,
        )

        return {
            "deal_id": deal_id,
            "period_start": str(period_start),
            "period_end": str(period_end),
            "buyer_entry_id": buyer_entry_id,
            "buyer_amount": round(monthly_buyer, 2),
            "supplier_entry_id": supplier_entry_id,
            "supplier_amount": round(monthly_supplier, 2),
            "wex_spread": round(monthly_spread, 2),
            "spread_pct": round(
                (monthly_spread / monthly_buyer * 100) if monthly_buyer > 0 else 0, 1
            ),
        }

    # ------------------------------------------------------------------
    # Deal Summary
    # ------------------------------------------------------------------

    async def get_deal_summary(
        self,
        db: AsyncSession,
        deal_id: str,
    ) -> dict:
        """Load a comprehensive deal summary with all related records.

        Args:
            db: Active async SQLAlchemy session.
            deal_id: UUID of the Deal.

        Returns:
            Dict with deal details, rates, schedule, ledger entries,
            insurance status, deposit status, and event history.

        Raises:
            ValueError: If deal is not found.
        """
        # Load deal with relationships
        result = await db.execute(
            select(Deal)
            .where(Deal.id == deal_id)
            .options(
                selectinload(Deal.match),
                selectinload(Deal.warehouse),
                selectinload(Deal.buyer),
                selectinload(Deal.events),
                selectinload(Deal.insurance_coverages),
                selectinload(Deal.deposits),
            )
        )
        deal = result.scalar_one_or_none()
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        # Load ledger entries
        buyer_ledger_result = await db.execute(
            select(BuyerLedger)
            .where(BuyerLedger.deal_id == deal_id)
            .order_by(BuyerLedger.period_start)
        )
        buyer_entries = buyer_ledger_result.scalars().all()

        supplier_ledger_result = await db.execute(
            select(SupplierLedger)
            .where(SupplierLedger.deal_id == deal_id)
            .order_by(SupplierLedger.period_start)
        )
        supplier_entries = supplier_ledger_result.scalars().all()

        # Calculate economics
        monthly_buyer = deal.buyer_rate * deal.sqft_allocated
        monthly_supplier = deal.supplier_rate * deal.sqft_allocated
        monthly_spread = monthly_buyer - monthly_supplier

        return {
            "deal": {
                "id": deal.id,
                "status": deal.status,
                "deal_type": deal.deal_type,
                "sqft_allocated": deal.sqft_allocated,
                "term_months": deal.term_months,
                "start_date": str(deal.start_date) if deal.start_date else None,
                "end_date": str(deal.end_date) if deal.end_date else None,
                "created_at": str(deal.created_at) if deal.created_at else None,
            },
            "rates": {
                "buyer_rate": deal.buyer_rate,
                "supplier_rate": deal.supplier_rate,
                "spread_pct": deal.spread_pct,
                "monthly_buyer_payment": round(monthly_buyer, 2),
                "monthly_supplier_payment": round(monthly_supplier, 2),
                "monthly_wex_revenue": round(monthly_spread, 2),
                "total_contract_value": round(monthly_buyer * (deal.term_months or 1), 2),
                "total_wex_revenue": round(monthly_spread * (deal.term_months or 1), 2),
            },
            "warehouse": {
                "id": deal.warehouse.id if deal.warehouse else None,
                "address": deal.warehouse.address if deal.warehouse else None,
                "city": deal.warehouse.city if deal.warehouse else None,
                "state": deal.warehouse.state if deal.warehouse else None,
            },
            "buyer": {
                "id": deal.buyer.id if deal.buyer else None,
                "name": deal.buyer.name if deal.buyer else None,
                "company": deal.buyer.company if deal.buyer else None,
            },
            "match": {
                "id": deal.match.id if deal.match else None,
                "match_score": deal.match.match_score if deal.match else None,
                "instant_book_eligible": (
                    deal.match.instant_book_eligible if deal.match else None
                ),
            },
            "tour": {
                "scheduled_at": str(deal.tour_scheduled_at) if deal.tour_scheduled_at else None,
                "completed_at": str(deal.tour_completed_at) if deal.tour_completed_at else None,
                "outcome": deal.tour_outcome,
                "pass_reason": deal.tour_pass_reason,
            },
            "insurance": [
                {
                    "id": ic.id,
                    "status": ic.coverage_status,
                    "coverage_amount": ic.coverage_amount,
                    "monthly_premium": ic.monthly_premium,
                }
                for ic in (deal.insurance_coverages or [])
            ],
            "deposits": [
                {
                    "id": dep.id,
                    "type": dep.deposit_type,
                    "amount": dep.amount,
                    "status": dep.status,
                }
                for dep in (deal.deposits or [])
            ],
            "buyer_ledger": [
                {
                    "id": entry.id,
                    "entry_type": entry.entry_type,
                    "amount": entry.amount,
                    "description": entry.description,
                    "period_start": str(entry.period_start) if entry.period_start else None,
                    "period_end": str(entry.period_end) if entry.period_end else None,
                    "status": entry.status,
                }
                for entry in buyer_entries
            ],
            "supplier_ledger": [
                {
                    "id": entry.id,
                    "entry_type": entry.entry_type,
                    "amount": entry.amount,
                    "description": entry.description,
                    "period_start": str(entry.period_start) if entry.period_start else None,
                    "period_end": str(entry.period_end) if entry.period_end else None,
                    "status": entry.status,
                }
                for entry in supplier_entries
            ],
            "events": [
                {
                    "id": ev.id,
                    "event_type": ev.event_type,
                    "details": ev.details,
                    "created_at": str(ev.created_at) if ev.created_at else None,
                }
                for ev in sorted(
                    (deal.events or []),
                    key=lambda e: e.created_at or datetime.min,
                )
            ],
        }
