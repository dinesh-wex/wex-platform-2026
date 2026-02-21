"""Demand-Led Activation service — tokenized URL flow for off-network suppliers.

Triggered by the Clearing Engine when a buyer search produces insufficient
Tier 1 (in-network) matches. DLA generates deal-specific tokenized URLs,
resolves them to pre-loaded property + anonymized buyer data, manages the
rate negotiation flow, and flips supplier status on agreement confirmation.
"""

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.app.config import get_settings
from wex_platform.domain.models import (
    Warehouse,
    TruthCore,
    BuyerNeed,
    Buyer,
    ContextualMemory,
    MarketRateCache,
    DLAToken,
    Match,
)

logger = logging.getLogger(__name__)

# Default response window in hours (Product-owned, configurable)
DEFAULT_RESPONSE_WINDOW_HOURS = 48


class DLAService:
    """Orchestrates the Demand-Led Activation flow end-to-end."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

    # ------------------------------------------------------------------
    # Token generation
    # ------------------------------------------------------------------

    async def generate_token(self, warehouse_id: str, buyer_need_id: str) -> str:
        """Generate a unique, expiry-based token for DLA outreach.

        The token encodes warehouse + buyer need context and is stored
        with an expiration window (default 48h, configurable by Product).

        Returns:
            The 32-character hex token string.
        """
        # Verify warehouse and buyer need exist
        warehouse = await self.db.get(Warehouse, warehouse_id)
        if not warehouse:
            raise ValueError(f"Warehouse {warehouse_id} not found")

        buyer_need = await self.db.get(BuyerNeed, buyer_need_id)
        if not buyer_need:
            raise ValueError(f"Buyer need {buyer_need_id} not found")

        # Generate token
        raw = f"{warehouse_id}:{buyer_need_id}:{secrets.token_hex(8)}"
        token = hashlib.sha256(raw.encode()).hexdigest()[:32]

        # Calculate suggested rate before storing
        rate_data = await self.calculate_suggested_rate(warehouse_id, buyer_need_id)

        # Create DLAToken record
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=DEFAULT_RESPONSE_WINDOW_HOURS
        )
        dla_token = DLAToken(
            id=str(uuid.uuid4()),
            token=token,
            warehouse_id=warehouse_id,
            buyer_need_id=buyer_need_id,
            suggested_rate=rate_data.get("suggested_rate"),
            status="pending",
            expires_at=expires_at,
        )
        self.db.add(dla_token)

        # Update warehouse outreach tracking
        warehouse.last_outreach_at = datetime.now(timezone.utc)
        warehouse.outreach_count = (warehouse.outreach_count or 0) + 1

        await self.db.commit()

        logger.info(
            "DLA token generated for warehouse %s / buyer need %s (expires %s)",
            warehouse_id,
            buyer_need_id,
            expires_at.isoformat(),
        )
        return token

    # ------------------------------------------------------------------
    # Token resolution
    # ------------------------------------------------------------------

    async def resolve_token(self, token: str) -> dict:
        """Resolve token to property data + anonymized buyer requirements + recommended rate.

        This is what powers the DLA landing page. No auth required — the
        token itself is the credential.

        Returns:
            Dict with property_data, buyer_requirement, suggested_rate,
            market_range, status, and expires_at.

        Raises:
            ValueError: If token is invalid, expired, or already confirmed.
        """
        dla_token = await self._get_valid_token(token)

        # Load warehouse with truth core
        result = await self.db.execute(
            select(Warehouse)
            .options(selectinload(Warehouse.truth_core))
            .where(Warehouse.id == dla_token.warehouse_id)
        )
        warehouse = result.scalar_one_or_none()
        if not warehouse:
            raise ValueError("Property not found")

        # Load buyer need (anonymized)
        buyer_need = await self.db.get(BuyerNeed, dla_token.buyer_need_id)
        if not buyer_need:
            raise ValueError("Buyer requirement no longer active")

        # Build property data (full — supplier sees their own property)
        tc = warehouse.truth_core
        property_data = {
            "warehouse_id": warehouse.id,
            "address": warehouse.address,
            "city": warehouse.city,
            "state": warehouse.state,
            "zip": warehouse.zip,
            "building_size_sqft": warehouse.building_size_sqft,
            "year_built": warehouse.year_built,
            "construction_type": warehouse.construction_type,
            "property_type": warehouse.property_type,
            "primary_image_url": warehouse.primary_image_url,
            "owner_name": warehouse.owner_name,
        }

        if tc:
            property_data.update({
                "clear_height_ft": tc.clear_height_ft,
                "dock_doors_receiving": tc.dock_doors_receiving,
                "dock_doors_shipping": tc.dock_doors_shipping,
                "drive_in_bays": tc.drive_in_bays,
                "parking_spaces": tc.parking_spaces,
                "has_office_space": tc.has_office_space,
                "has_sprinkler": tc.has_sprinkler,
                "power_supply": tc.power_supply,
            })

        # Build anonymized buyer requirement (no name, company, email)
        buyer_requirement = {
            "sqft_needed": buyer_need.max_sqft or buyer_need.min_sqft,
            "min_sqft": buyer_need.min_sqft,
            "max_sqft": buyer_need.max_sqft,
            "use_type": buyer_need.use_type,
            "needed_from": (
                buyer_need.needed_from.strftime("%B %Y")
                if buyer_need.needed_from
                else "ASAP"
            ),
            "duration_months": buyer_need.duration_months,
            "city": buyer_need.city,
            "state": buyer_need.state,
        }

        # Get market rate range
        market_range = await self._get_market_range(warehouse.zip or "")

        # Track that supplier opened the link
        if dla_token.status == "pending":
            dla_token.status = "interested"
            dla_token.last_step_reached = "property_confirm"
            warehouse.supplier_status = "interested"
            await self.db.commit()

        return {
            "token": token,
            "status": dla_token.status,
            "property_data": property_data,
            "buyer_requirement": buyer_requirement,
            "suggested_rate": dla_token.suggested_rate or 0,
            "market_range": market_range,
            "expires_at": dla_token.expires_at.isoformat() if dla_token.expires_at else None,
        }

    # ------------------------------------------------------------------
    # Rate calculation
    # ------------------------------------------------------------------

    async def calculate_suggested_rate(
        self, warehouse_id: str, buyer_need_id: str
    ) -> dict:
        """Calculate suggested rate from live market data.

        Based on:
        - Tier 1 confirmed rates in the same area
        - Buyer's budget ceiling
        - Market rate cache (Gemini-grounded NNN lease rates)

        Returns:
            Dict with suggested_rate, market_low, market_high, and
            competing_spaces count.
        """
        warehouse = await self.db.get(Warehouse, warehouse_id)
        buyer_need = await self.db.get(BuyerNeed, buyer_need_id)

        if not warehouse or not buyer_need:
            return {"suggested_rate": 0, "market_low": 0, "market_high": 0, "competing_spaces": 0}

        # 1. Get market rates from cache
        market_range = await self._get_market_range(warehouse.zip or "")

        # 2. Get Tier 1 rates in the same area (confirmed in-network rates)
        tier1_result = await self.db.execute(
            select(TruthCore.supplier_rate_per_sqft)
            .join(Warehouse, Warehouse.id == TruthCore.warehouse_id)
            .where(
                and_(
                    Warehouse.supplier_status == "in_network",
                    TruthCore.activation_status == "on",
                    Warehouse.state == warehouse.state,
                )
            )
        )
        tier1_rates = [r[0] for r in tier1_result.all() if r[0] is not None]

        # 3. Count competing spaces within buyer budget
        competing_query = await self.db.execute(
            select(func.count())
            .select_from(TruthCore)
            .join(Warehouse, Warehouse.id == TruthCore.warehouse_id)
            .where(
                and_(
                    Warehouse.supplier_status == "in_network",
                    TruthCore.activation_status == "on",
                    Warehouse.state == warehouse.state,
                    TruthCore.supplier_rate_per_sqft <= (buyer_need.max_budget_per_sqft or 999),
                )
            )
        )
        competing_spaces = competing_query.scalar() or 0

        # 4. Calculate suggested rate
        # Priority: buyer budget ceiling > market median > tier 1 average
        market_low = market_range.get("low", 0)
        market_high = market_range.get("high", 0)

        if tier1_rates:
            tier1_avg = sum(tier1_rates) / len(tier1_rates)
        else:
            tier1_avg = (market_low + market_high) / 2 if market_high > 0 else 0

        buyer_ceiling = buyer_need.max_budget_per_sqft or 0

        # Suggested rate: anchor to the buyer's budget but within market range
        if buyer_ceiling > 0 and tier1_avg > 0:
            # Weight toward buyer budget (60%) with market anchor (40%)
            suggested = (buyer_ceiling * 0.6) + (tier1_avg * 0.4)
        elif buyer_ceiling > 0:
            suggested = buyer_ceiling * 0.9  # Slight discount from ceiling
        elif tier1_avg > 0:
            suggested = tier1_avg
        elif market_high > 0:
            suggested = (market_low + market_high) / 2
        else:
            suggested = 0

        # Clamp to market range if available
        if market_low > 0 and suggested < market_low:
            suggested = market_low
        if market_high > 0 and suggested > market_high:
            suggested = market_high * 0.95  # Stay just under market ceiling

        return {
            "suggested_rate": round(suggested, 2),
            "market_low": market_low,
            "market_high": market_high,
            "tier1_avg": round(tier1_avg, 2) if tier1_avg else None,
            "competing_spaces": competing_spaces,
            "buyer_budget_ceiling": buyer_ceiling,
        }

    # ------------------------------------------------------------------
    # Rate decision handling
    # ------------------------------------------------------------------

    async def handle_rate_decision(
        self, token: str, accepted: bool, proposed_rate: float | None = None
    ) -> dict:
        """Process supplier's rate decision (accept or counter).

        If accepted: move to agreement step.
        If counter: store the counter-rate, inform about competition.

        Returns:
            Dict with next_step, message, and status.
        """
        dla_token = await self._get_valid_token(token)

        # Load buyer need for budget context
        buyer_need = await self.db.get(BuyerNeed, dla_token.buyer_need_id)
        warehouse = await self.db.get(Warehouse, dla_token.warehouse_id)

        dla_token.rate_accepted = accepted
        dla_token.responded_at = datetime.now(timezone.utc)
        dla_token.last_step_reached = "rate_decision"

        if accepted:
            dla_token.supplier_rate = dla_token.suggested_rate
            dla_token.status = "rate_decided"
            await self.db.commit()

            return {
                "status": "rate_decided",
                "next_step": "agreement",
                "message": "Rate accepted. Proceed to agreement.",
                "rate": dla_token.suggested_rate,
            }
        else:
            # Counter-rate flow
            if proposed_rate is None:
                raise ValueError("proposed_rate is required when not accepting")

            dla_token.supplier_rate = proposed_rate
            dla_token.status = "rate_decided"

            # Calculate how many competing spaces are within buyer budget
            buyer_budget = buyer_need.max_budget_per_sqft if buyer_need else 0
            competing = 0
            if buyer_budget and warehouse:
                competing_result = await self.db.execute(
                    select(func.count())
                    .select_from(TruthCore)
                    .join(Warehouse, Warehouse.id == TruthCore.warehouse_id)
                    .where(
                        and_(
                            Warehouse.supplier_status == "in_network",
                            TruthCore.activation_status == "on",
                            Warehouse.state == warehouse.state,
                            TruthCore.supplier_rate_per_sqft <= buyer_budget,
                        )
                    )
                )
                competing = competing_result.scalar() or 0

            await self.db.commit()

            # Build honest response about competition
            if proposed_rate > (buyer_budget or 0) and buyer_budget > 0:
                message = (
                    f"Got it — we've noted your rate of ${proposed_rate:.2f}/sqft. "
                    f"The buyer's current budget is closer to ${buyer_budget:.2f}, "
                    f"so we'll present your space but want to be upfront — "
                    f"there are already {competing} spaces within their budget range. "
                    f"We'll let you know what they decide."
                )
            else:
                message = (
                    f"Your rate of ${proposed_rate:.2f}/sqft has been noted. "
                    f"We'll present your space to the buyer."
                )

            return {
                "status": "rate_decided",
                "next_step": "agreement",
                "message": message,
                "rate": proposed_rate,
                "competing_spaces": competing,
                "within_budget": proposed_rate <= (buyer_budget or 0),
            }

    # ------------------------------------------------------------------
    # Agreement confirmation
    # ------------------------------------------------------------------

    async def confirm_agreement(self, token: str, agreement_ref: str | None = None,
                                 available_from: str | None = None,
                                 available_to: str | None = None,
                                 restrictions: str | None = None) -> dict:
        """Agreement signed -> flip status to in_network + notify buyer.

        Three things happen simultaneously:
        1. supplier_status -> in_network
        2. Property enters clearing engine as active Tier 1 match
        3. Buyer notification fires

        Returns:
            Dict with confirmation details.
        """
        dla_token = await self._get_valid_token(token, allow_statuses=["rate_decided"])

        warehouse = await self.db.execute(
            select(Warehouse)
            .options(selectinload(Warehouse.truth_core))
            .where(Warehouse.id == dla_token.warehouse_id)
        )
        warehouse = warehouse.scalar_one_or_none()
        if not warehouse:
            raise ValueError("Property not found")

        buyer_need = await self.db.get(BuyerNeed, dla_token.buyer_need_id)

        # 1. Flip supplier status to in_network
        warehouse.supplier_status = "in_network"
        warehouse.onboarded_at = datetime.now(timezone.utc)

        # 2. Activate truth core if exists
        tc = warehouse.truth_core
        if tc:
            tc.activation_status = "on"
            tc.toggled_at = datetime.now(timezone.utc)
            tc.toggle_reason = "DLA agreement confirmed"
            # Update rate to the agreed rate
            if dla_token.supplier_rate:
                tc.supplier_rate_per_sqft = dla_token.supplier_rate

        # 3. Update DLA token
        dla_token.status = "confirmed"
        dla_token.agreement_ref = agreement_ref
        dla_token.last_step_reached = "agreement"
        dla_token.responded_at = datetime.now(timezone.utc)

        # 4. Create a Match record linking this warehouse to the buyer need
        if buyer_need:
            match = Match(
                id=str(uuid.uuid4()),
                buyer_need_id=dla_token.buyer_need_id,
                warehouse_id=dla_token.warehouse_id,
                match_score=85.0,  # DLA matches are pre-qualified
                confidence=0.9,
                instant_book_eligible=False,
                reasoning="Activated via Demand-Led Activation flow",
                scoring_breakdown={"source": "dla", "rate_accepted": dla_token.rate_accepted},
                status="pending",
            )
            self.db.add(match)

        # 5. Store contextual memory about the DLA conversion
        memory = ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse.id,
            memory_type="deal_outcome",
            content=(
                f"Supplier converted via DLA. Agreed rate: ${dla_token.supplier_rate:.2f}/sqft. "
                f"Rate {'accepted as suggested' if dla_token.rate_accepted else 'counter-proposed'}. "
                f"Buyer need: {buyer_need.use_type or 'general'} in {buyer_need.city or 'area'}."
            ),
            source="dla_flow",
            confidence=1.0,
        )
        self.db.add(memory)

        await self.db.commit()

        logger.info(
            "DLA confirmed: warehouse %s now in_network (token %s)",
            warehouse.id,
            token,
        )

        # 6. Buyer notification (async — fire and forget)
        buyer_notification = None
        if buyer_need:
            buyer = await self.db.get(Buyer, buyer_need.buyer_id)
            if buyer:
                buyer_notification = {
                    "buyer_id": buyer.id,
                    "buyer_email": buyer.email,
                    "buyer_phone": buyer.phone,
                    "message": (
                        f"Good news — a new space just confirmed availability for your "
                        f"requirements. {warehouse.city or ''}, "
                        f"{warehouse.building_size_sqft or 'N/A'} sqft, "
                        f"${dla_token.supplier_rate:.2f}/sqft."
                    ),
                }

        return {
            "status": "confirmed",
            "warehouse_id": warehouse.id,
            "supplier_status": "in_network",
            "rate_agreed": dla_token.supplier_rate,
            "buyer_notification": buyer_notification,
        }

    # ------------------------------------------------------------------
    # Non-conversion outcome storage
    # ------------------------------------------------------------------

    async def store_outcome(
        self,
        token: str,
        outcome: str,
        reason: str | None = None,
        rate_floor: float | None = None,
    ) -> dict:
        """Store non-conversion outcome (decline, no response, etc.).

        Every DLA outcome produces data stored to the property record.
        Nothing is wasted.

        Returns:
            Dict with acknowledgment details.
        """
        result = await self.db.execute(
            select(DLAToken).where(DLAToken.token == token)
        )
        dla_token = result.scalar_one_or_none()
        if not dla_token:
            raise ValueError("Invalid token")

        warehouse = await self.db.get(Warehouse, dla_token.warehouse_id)

        # Map outcome to supplier_status
        status_map = {
            "declined": "declined",
            "no_response": "unresponsive",
            "dropped_off": "interested",  # Keep as interested — they showed some intent
            "expired": "unresponsive",
        }

        dla_token.status = outcome
        dla_token.decline_reason = reason

        if warehouse:
            new_status = status_map.get(outcome, warehouse.supplier_status)
            warehouse.supplier_status = new_status

            # Store outcome as contextual memory
            memory_content = f"DLA outcome: {outcome}."
            if reason:
                memory_content += f" Reason: {reason}."
            if rate_floor:
                memory_content += f" Rate floor indicated: ${rate_floor:.2f}/sqft."
            if dla_token.last_step_reached:
                memory_content += f" Last step reached: {dla_token.last_step_reached}."

            memory = ContextualMemory(
                id=str(uuid.uuid4()),
                warehouse_id=warehouse.id,
                memory_type="outreach_response",
                content=memory_content,
                source="dla_flow",
                confidence=1.0,
                metadata_={
                    "outcome": outcome,
                    "reason": reason,
                    "rate_floor": rate_floor,
                    "token": token,
                    "buyer_need_id": dla_token.buyer_need_id,
                },
            )
            self.db.add(memory)

        await self.db.commit()

        logger.info(
            "DLA outcome stored: warehouse %s -> %s (token %s)",
            dla_token.warehouse_id,
            outcome,
            token,
        )

        return {
            "status": outcome,
            "warehouse_id": dla_token.warehouse_id,
            "acknowledged": True,
        }

    # ------------------------------------------------------------------
    # DLA candidate finding (called by clearing engine)
    # ------------------------------------------------------------------

    async def find_dla_candidates(
        self, buyer_need_id: str, limit: int = 5
    ) -> list[dict]:
        """Find off-network candidates for a buyer need.

        Called by the clearing engine when < 3 Tier 1 matches are found.
        Queries suppliers with status in (third_party, earncheck_only, interested)
        and scores them by match quality.

        Returns:
            Ranked list of candidate dicts with warehouse data and score.
        """
        buyer_need = await self.db.get(BuyerNeed, buyer_need_id)
        if not buyer_need:
            raise ValueError(f"Buyer need {buyer_need_id} not found")

        # Query off-network candidates
        result = await self.db.execute(
            select(Warehouse)
            .options(
                selectinload(Warehouse.truth_core),
                selectinload(Warehouse.memories),
            )
            .where(
                and_(
                    Warehouse.supplier_status.in_(
                        ["third_party", "earncheck_only", "interested"]
                    ),
                    # Exclude recently outreached (max 1 outreach per 30 days)
                    # This is enforced via outreach_count and last_outreach_at
                )
            )
        )
        warehouses = result.scalars().all()

        # Score and filter candidates
        scored = []
        now = datetime.now(timezone.utc)

        for wh in warehouses:
            # Skip if outreached in last 30 days
            if wh.last_outreach_at:
                days_since = (now - wh.last_outreach_at).days
                if days_since < 30:
                    continue

            # Skip if no phone for SMS outreach
            if not wh.owner_phone:
                continue

            score = self._score_candidate(wh, buyer_need)
            if score > 0:
                scored.append({
                    "warehouse_id": wh.id,
                    "owner_name": wh.owner_name,
                    "owner_phone": wh.owner_phone,
                    "owner_email": wh.owner_email,
                    "address": wh.address,
                    "city": wh.city,
                    "state": wh.state,
                    "zip": wh.zip,
                    "building_size_sqft": wh.building_size_sqft,
                    "property_type": wh.property_type,
                    "supplier_status": wh.supplier_status,
                    "score": score,
                    "outreach_count": wh.outreach_count or 0,
                })

        # Sort by score descending, return top N
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _score_candidate(self, warehouse: Warehouse, buyer_need: BuyerNeed) -> float:
        """Score an off-network candidate against a buyer need.

        Scoring factors:
        - Size match (0-40 points)
        - Location match (0-30 points)
        - Previous engagement bonus (0-20 points)
        - Data completeness (0-10 points)
        """
        score = 0.0
        tc = warehouse.truth_core

        # Size match (up to 40 points)
        wh_sqft = warehouse.building_size_sqft or (tc.max_sqft if tc else 0)
        need_sqft = buyer_need.max_sqft or buyer_need.min_sqft or 0

        if wh_sqft and need_sqft:
            ratio = min(wh_sqft, need_sqft) / max(wh_sqft, need_sqft)
            score += ratio * 40

        # Location match (up to 30 points)
        if buyer_need.state and warehouse.state:
            if buyer_need.state.upper() == warehouse.state.upper():
                score += 15
                if buyer_need.city and warehouse.city:
                    if buyer_need.city.lower() == warehouse.city.lower():
                        score += 15
                    elif buyer_need.city.lower() in (warehouse.city or "").lower():
                        score += 10

        # Previous engagement bonus (up to 20 points)
        if warehouse.supplier_status == "earncheck_only":
            score += 20  # Already used EarnCheck — warm lead
        elif warehouse.supplier_status == "interested":
            score += 15  # Previously expressed interest
        elif warehouse.supplier_status == "third_party":
            score += 5  # Cold — minimal bonus

        # Data completeness (up to 10 points)
        data_fields = [
            warehouse.building_size_sqft,
            warehouse.year_built,
            warehouse.construction_type,
            warehouse.property_type,
            warehouse.owner_name,
            warehouse.owner_phone,
        ]
        populated = sum(1 for f in data_fields if f)
        score += (populated / len(data_fields)) * 10

        return round(score, 1)

    async def _get_market_range(self, zipcode: str) -> dict:
        """Look up cached market rate range for a zipcode."""
        if not zipcode:
            return {"low": 0, "high": 0, "source": "none"}

        result = await self.db.execute(
            select(MarketRateCache).where(MarketRateCache.zipcode == zipcode)
        )
        cache = result.scalar_one_or_none()

        if cache:
            return {
                "low": cache.nnn_low,
                "high": cache.nnn_high,
                "source": "market_rate_cache",
            }

        return {"low": 0, "high": 0, "source": "none"}

    async def _get_valid_token(
        self, token: str, allow_statuses: list[str] | None = None
    ) -> DLAToken:
        """Look up and validate a DLA token.

        Checks: exists, not expired, status is valid.

        Raises:
            ValueError: If token is invalid, expired, or wrong status.
        """
        result = await self.db.execute(
            select(DLAToken).where(DLAToken.token == token)
        )
        dla_token = result.scalar_one_or_none()

        if not dla_token:
            raise ValueError("Invalid token")

        # Check expiration
        now = datetime.now(timezone.utc)
        if dla_token.expires_at and dla_token.expires_at.replace(tzinfo=timezone.utc) < now:
            if dla_token.status not in ("confirmed", "declined", "expired"):
                dla_token.status = "expired"
                await self.db.commit()
            raise ValueError("Token has expired")

        # Check status if specific statuses are required
        if allow_statuses and dla_token.status not in allow_statuses:
            raise ValueError(
                f"Token status is '{dla_token.status}', expected one of {allow_statuses}"
            )

        # For general access, block only terminal states
        if not allow_statuses and dla_token.status in ("confirmed", "expired"):
            raise ValueError(f"Token is already {dla_token.status}")

        return dla_token
