"""Clearing Engine - Orchestrates the matching pipeline.

The clearing engine is the heart of the WEx clearinghouse.  It takes a
buyer need, loads all active warehouse supply, runs a deterministic
pre-filter, hands survivors to the AI-powered Clearing Agent for
multi-dimensional scoring, enriches the top matches with buyer-facing
pricing from the Pricing Agent, persists Match and InstantBookScore
records, and returns ranked results ready for presentation.

Two-tier matching:
    Tier 1 - In-network warehouses (supplier_status='in_network') with
             active truth cores.  These are scored, priced, and returned
             as ready-to-book matches.
    Tier 2 - Off-network warehouses (supplier_status in 'third_party',
             'earncheck_only', 'interested') that pass the same pre-filter.
             When fewer than 3 Tier 1 matches exist, DLA (Demand-Led
             Activation) outreach is triggered for top Tier 2 candidates.
"""

import logging
import math
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from wex_platform.domain.models import (
    Warehouse,
    TruthCore,
    ContextualMemory,
    BuyerNeed,
    Match,
    InstantBookScore,
    DLAToken,
)

logger = logging.getLogger(__name__)

# Tier 2 supplier statuses eligible for DLA outreach
TIER2_STATUSES = ("third_party", "earncheck_only", "interested")

# Minimum Tier 1 matches before DLA is triggered for Tier 2
DLA_TRIGGER_THRESHOLD = 3

# How many Tier 2 candidates to activate via DLA
DLA_MAX_CANDIDATES = 5

# DLA token validity period
DLA_TOKEN_EXPIRY_DAYS = 7


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in miles between two lat/lng points."""
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ClearingEngine:
    """Orchestrates the clearing pipeline: filter -> score -> price-check -> rank."""

    async def run_clearing(
        self,
        buyer_need_id: str,
        session: AsyncSession = None,
        *,
        db: AsyncSession = None,
    ) -> dict:
        """Run the full two-tier clearing pipeline for a buyer need.

        Steps:
            1. Load the buyer need
            2. Tier 1: Load in-network warehouses, pre-filter, AI-score,
               price, and persist Match records
            3. Tier 2: Load off-network warehouses, pre-filter, AI-score
               (limited fields only)
            4. If Tier 1 < 3 matches, trigger DLA for top Tier 2 candidates
            5. Return structured result with both tiers

        Args:
            buyer_need_id: UUID of the BuyerNeed to match against.
            session: An active async SQLAlchemy session.
            db: Alias for *session* (accepted for caller compatibility).

        Returns:
            A dict with keys:
                tier1_matches  - list of fully scored/priced match dicts
                tier2_matches  - list of limited candidate dicts (being sourced)
                dla_triggered  - whether DLA outreach was initiated
                total_matches  - combined count of both tiers

        Raises:
            ValueError: If the buyer need is not found.
        """
        # Accept both 'session' and 'db' for caller compatibility
        session = session or db
        if session is None:
            raise ValueError("A database session is required (pass session= or db=)")

        # 1. Load buyer need
        buyer_need = await session.get(BuyerNeed, buyer_need_id)
        if not buyer_need:
            raise ValueError(f"Buyer need {buyer_need_id} not found")

        need_dict = self._build_need_dict(buyer_need)

        # ------------------------------------------------------------------
        # Tier 1: In-network warehouses
        # ------------------------------------------------------------------
        tier1_matches = await self._run_tier1(
            buyer_need_id, buyer_need, need_dict, session
        )

        # ------------------------------------------------------------------
        # Tier 2: Off-network warehouses
        # ------------------------------------------------------------------
        tier2_matches = await self._run_tier2(buyer_need, need_dict, session)

        # ------------------------------------------------------------------
        # DLA trigger: activate Tier 2 candidates when Tier 1 is thin
        # ------------------------------------------------------------------
        dla_triggered = False
        if len(tier1_matches) < DLA_TRIGGER_THRESHOLD and tier2_matches:
            dla_triggered = await self._trigger_dla(
                buyer_need_id, tier2_matches, session
            )

        await session.commit()

        total = len(tier1_matches) + len(tier2_matches)
        logger.info(
            "Clearing complete for buyer need %s: %d tier1, %d tier2, DLA=%s",
            buyer_need_id,
            len(tier1_matches),
            len(tier2_matches),
            dla_triggered,
        )

        return {
            "tier1_matches": tier1_matches,
            "tier2_matches": tier2_matches,
            "dla_triggered": dla_triggered,
            "total_matches": total,
        }

    # ------------------------------------------------------------------
    # Tier 1 pipeline (in-network, full scoring + pricing)
    # ------------------------------------------------------------------

    async def _run_tier1(
        self,
        buyer_need_id: str,
        buyer_need: BuyerNeed,
        need_dict: dict,
        session: AsyncSession,
    ) -> list[dict]:
        """Tier 1: score and price in-network warehouses."""

        result = await session.execute(
            select(Warehouse)
            .join(TruthCore)
            .where(
                TruthCore.activation_status == "on",
                Warehouse.supplier_status == "in_network",
            )
            .options(
                selectinload(Warehouse.truth_core),
                selectinload(Warehouse.memories),
            )
        )
        warehouses = result.scalars().all()

        if not warehouses:
            logger.info(
                "No in-network warehouses found for buyer need %s",
                buyer_need_id,
            )
            return []

        candidates = self._pre_filter(buyer_need, warehouses)
        if not candidates:
            logger.info(
                "No in-network warehouses passed pre-filter for buyer need %s "
                "(checked %d)",
                buyer_need_id,
                len(warehouses),
            )
            return []

        logger.info(
            "Tier 1 pre-filter passed %d of %d in-network warehouses for %s",
            len(candidates),
            len(warehouses),
            buyer_need_id,
        )

        warehouse_dicts = self._format_warehouses(candidates)

        # AI-powered scoring
        from wex_platform.agents.clearing_agent import ClearingAgent

        clearing_agent = ClearingAgent()
        agent_result = await clearing_agent.find_matches(need_dict, warehouse_dicts)

        if not agent_result.ok:
            logger.error(
                "Clearing agent failed (tier1) for buyer need %s: %s",
                buyer_need_id,
                agent_result.error,
            )
            return []

        matches_data = agent_result.data.get("matches", [])
        if not matches_data:
            return []

        # Pricing (pure formula — no AI needed) + persistence
        results: list[dict] = []
        for match_data in matches_data[:3]:  # Top 3 matches
            wh_id = match_data.get("warehouse_id")
            wh_dict_match = next(
                (w for w in warehouse_dicts if w["id"] == wh_id), None
            )
            if not wh_dict_match:
                logger.warning(
                    "Clearing agent returned unknown warehouse_id %s", wh_id
                )
                continue

            tc_data = wh_dict_match["truth_core"]
            supplier_rate = tc_data.get("supplier_rate_per_sqft", 0)

            # WEx formula: supplier × 1.20 (margin) × 1.06 (guarantee), round UP
            buyer_rate = math.ceil((supplier_rate * 1.20 * 1.06) * 100) / 100

            spread = buyer_rate - supplier_rate
            spread_pct = (spread / buyer_rate) * 100 if buyer_rate > 0 else 0

            match_id = str(uuid.uuid4())
            match = Match(
                id=match_id,
                buyer_need_id=buyer_need_id,
                warehouse_id=wh_id,
                match_score=match_data.get("composite_score", 0),
                confidence=match_data.get("confidence", 0),
                instant_book_eligible=match_data.get(
                    "instant_book_eligible", False
                ),
                reasoning=match_data.get("reasoning", ""),
                scoring_breakdown=match_data.get("scoring_breakdown", {}),
                status="pending",
            )
            session.add(match)

            ib_score = self._build_instant_book_score(
                match_id=match_id,
                match_data=match_data,
                tc_data=tc_data,
                memory_count=len(wh_dict_match.get("memories", [])),
            )
            session.add(ib_score)

            # Calculate distance from buyer's requested location
            wh_lat = wh_dict_match.get("lat")
            wh_lng = wh_dict_match.get("lng")
            distance_miles = None
            if buyer_need.lat and buyer_need.lng and wh_lat and wh_lng:
                distance_miles = round(
                    _haversine_miles(buyer_need.lat, buyer_need.lng, wh_lat, wh_lng), 1
                )

            results.append({
                "match_id": match_id,
                "warehouse_id": wh_id,
                "warehouse": wh_dict_match,
                "match_score": match_data.get("composite_score", 0),
                "scoring_breakdown": match_data.get("scoring_breakdown", {}),
                "reasoning": match_data.get("reasoning", ""),
                "instant_book_eligible": match_data.get(
                    "instant_book_eligible", False
                ),
                "buyer_rate": round(buyer_rate, 2),
                "supplier_rate": round(supplier_rate, 2),  # Admin only
                "spread_pct": round(spread_pct, 1),  # Admin only
                "confidence": match_data.get("confidence", 0),
                "distance_miles": distance_miles,
            })

        return results

    # ------------------------------------------------------------------
    # Tier 2 pipeline (off-network, limited info)
    # ------------------------------------------------------------------

    async def _run_tier2(
        self,
        buyer_need: BuyerNeed,
        need_dict: dict,
        session: AsyncSession,
    ) -> list[dict]:
        """Tier 2: identify off-network candidates with limited disclosure.

        Returns candidate dicts containing only: warehouse_id, city
        (as neighbourhood proxy), match_score, building_size_sqft,
        property_type.  No exact address, rate, or owner info.
        """
        result = await session.execute(
            select(Warehouse)
            .join(TruthCore)
            .where(
                TruthCore.activation_status == "on",
                Warehouse.supplier_status.in_(TIER2_STATUSES),
            )
            .options(
                selectinload(Warehouse.truth_core),
                selectinload(Warehouse.memories),
            )
        )
        warehouses = result.scalars().all()

        if not warehouses:
            logger.info(
                "No off-network warehouses found for tier2 (buyer need %s)",
                buyer_need.id if hasattr(buyer_need, "id") else "?",
            )
            return []

        candidates = self._pre_filter(buyer_need, warehouses)
        if not candidates:
            return []

        logger.info(
            "Tier 2 pre-filter passed %d of %d off-network warehouses",
            len(candidates),
            len(warehouses),
        )

        # Use the same AI scoring pipeline for tier 2 candidates
        warehouse_dicts = self._format_warehouses(candidates)

        from wex_platform.agents.clearing_agent import ClearingAgent

        clearing_agent = ClearingAgent()
        agent_result = await clearing_agent.find_matches(need_dict, warehouse_dicts)

        if not agent_result.ok:
            logger.warning(
                "Clearing agent failed (tier2): %s", agent_result.error
            )
            return []

        matches_data = agent_result.data.get("matches", [])
        if not matches_data:
            return []

        # Build limited-disclosure dicts for tier 2
        tier2_results: list[dict] = []
        for match_data in matches_data[:DLA_MAX_CANDIDATES]:
            wh_id = match_data.get("warehouse_id")
            wh_dict = next(
                (w for w in warehouse_dicts if w["id"] == wh_id), None
            )
            if not wh_dict:
                continue

            tier2_results.append({
                "warehouse_id": wh_id,
                "neighborhood": wh_dict.get("city", "Unknown"),
                "match_score": match_data.get("composite_score", 0),
                "sqft": wh_dict.get("building_size_sqft"),
                "building_type": wh_dict.get("property_type", "warehouse"),
            })

        return tier2_results

    # ------------------------------------------------------------------
    # DLA (Demand-Led Activation) trigger
    # ------------------------------------------------------------------

    async def _trigger_dla(
        self,
        buyer_need_id: str,
        tier2_matches: list[dict],
        session: AsyncSession,
    ) -> bool:
        """Create DLAToken records and mark candidates as 'interested'.

        Args:
            buyer_need_id: The buyer need driving this activation.
            tier2_matches: Tier 2 candidate dicts (from _run_tier2).
            session: Active DB session (not yet committed).

        Returns:
            True if at least one DLA token was created.
        """
        created = 0
        now = datetime.now(timezone.utc)
        expires = now + timedelta(days=DLA_TOKEN_EXPIRY_DAYS)

        for candidate in tier2_matches[:DLA_MAX_CANDIDATES]:
            wh_id = candidate["warehouse_id"]

            # Avoid duplicate tokens for the same warehouse + buyer need
            existing = await session.execute(
                select(DLAToken).where(
                    DLAToken.warehouse_id == wh_id,
                    DLAToken.buyer_need_id == buyer_need_id,
                    DLAToken.status.in_(("pending", "interested")),
                )
            )
            if existing.scalar_one_or_none():
                logger.debug(
                    "DLA token already exists for warehouse %s / need %s",
                    wh_id,
                    buyer_need_id,
                )
                continue

            token = DLAToken(
                id=str(uuid.uuid4()),
                token=secrets.token_urlsafe(32),
                warehouse_id=wh_id,
                buyer_need_id=buyer_need_id,
                status="pending",
                expires_at=expires,
                outreach_channel="sms",
            )
            session.add(token)

            # Upgrade third_party -> interested
            wh_result = await session.execute(
                select(Warehouse).where(Warehouse.id == wh_id)
            )
            warehouse = wh_result.scalar_one_or_none()
            if warehouse and warehouse.supplier_status == "third_party":
                warehouse.supplier_status = "interested"
                warehouse.last_outreach_at = now
                warehouse.outreach_count = (warehouse.outreach_count or 0) + 1

            created += 1
            logger.info(
                "DLA token created for warehouse %s (buyer need %s)",
                wh_id,
                buyer_need_id,
            )

        if created:
            logger.info(
                "DLA triggered: %d tokens created for buyer need %s",
                created,
                buyer_need_id,
            )

        return created > 0

    # ------------------------------------------------------------------
    # Quick match count (for buyer wizard live badge)
    # ------------------------------------------------------------------

    async def get_match_count(
        self,
        location: str,
        min_sqft: int,
        max_sqft: int,
        use_type: str | None,
        session: AsyncSession,
    ) -> dict:
        """Fast count of in-network warehouses matching basic criteria.

        Used by the buyer wizard size-slider to show a live count badge.

        Args:
            location: City or state string to match against.
            min_sqft: Minimum required sqft.
            max_sqft: Maximum required sqft.
            use_type: Optional warehouse use type filter.
            session: Active DB session.

        Returns:
            Dict with ``count`` (int) and ``approximate`` (bool).
        """
        query = (
            select(sa_func.count(Warehouse.id))
            .join(TruthCore)
            .where(
                Warehouse.supplier_status == "in_network",
                TruthCore.activation_status == "on",
            )
        )

        # Location filter: match city or state (case-insensitive)
        if location:
            loc_upper = location.strip().upper()
            query = query.where(
                sa_func.upper(Warehouse.city).contains(loc_upper)
                | sa_func.upper(Warehouse.state).contains(loc_upper)
            )

        # Size filters against truth core
        if min_sqft > 0:
            query = query.where(
                (TruthCore.max_sqft >= min_sqft) | (TruthCore.max_sqft.is_(None))
            )
        if max_sqft < 100_000:
            query = query.where(
                (TruthCore.min_sqft <= max_sqft) | (TruthCore.min_sqft.is_(None))
            )

        # Use type / activity tier filter
        if use_type:
            query = query.where(TruthCore.activity_tier == use_type)

        result = await session.execute(query)
        count = result.scalar() or 0

        return {"count": count, "approximate": count > 50}

    # ------------------------------------------------------------------
    # Helper: build need_dict from BuyerNeed
    # ------------------------------------------------------------------

    @staticmethod
    def _build_need_dict(buyer_need: BuyerNeed) -> dict:
        """Convert a BuyerNeed ORM instance to a plain dict for agents."""
        return {
            "city": buyer_need.city,
            "state": buyer_need.state,
            "radius_miles": buyer_need.radius_miles,
            "min_sqft": buyer_need.min_sqft,
            "max_sqft": buyer_need.max_sqft,
            "use_type": buyer_need.use_type,
            "needed_from": (
                str(buyer_need.needed_from)
                if buyer_need.needed_from
                else "ASAP"
            ),
            "duration_months": buyer_need.duration_months,
            "max_budget_per_sqft": buyer_need.max_budget_per_sqft,
            "requirements": buyer_need.requirements or {},
        }

    # ------------------------------------------------------------------
    # Deterministic pre-filter
    # ------------------------------------------------------------------

    def _pre_filter(
        self,
        buyer_need: BuyerNeed,
        warehouses: list[Warehouse],
    ) -> list[Warehouse]:
        """Deterministic pre-filter before AI scoring.

        Removes warehouses that cannot possibly satisfy the buyer
        need based on hard constraints: available sqft range and
        geographic state.  This keeps the AI scoring prompt small
        and focused on plausible candidates.

        Args:
            buyer_need: The buyer's structured need.
            warehouses: All active warehouses.

        Returns:
            The subset of warehouses that pass hard-constraint checks.
        """
        candidates = []
        for wh in warehouses:
            tc = wh.truth_core
            if not tc:
                continue

            # Size filter - warehouse must have enough space
            if buyer_need.min_sqft and tc.max_sqft and tc.max_sqft < buyer_need.min_sqft:
                continue
            if buyer_need.max_sqft and tc.min_sqft and tc.min_sqft > buyer_need.max_sqft:
                continue

            # State filter — hard constraint, never return out-of-state
            if buyer_need.state and wh.state:
                if buyer_need.state.upper() != wh.state.upper():
                    continue

            # Distance filter — max 50 miles when coordinates are available
            if buyer_need.lat and buyer_need.lng and wh.lat and wh.lng:
                dist = _haversine_miles(buyer_need.lat, buyer_need.lng, wh.lat, wh.lng)
                if dist > 50:
                    continue

            candidates.append(wh)

        # Never relax the state filter — out-of-state results confuse buyers
        if not candidates and buyer_need.state:
            logger.info(
                "No warehouses in state %s — returning empty set",
                buyer_need.state,
            )

        return candidates

    # ------------------------------------------------------------------
    # Warehouse formatting
    # ------------------------------------------------------------------

    def _format_warehouses(
        self,
        warehouses: list[Warehouse],
    ) -> list[dict]:
        """Convert ORM warehouse objects into plain dicts for agent consumption.

        Args:
            warehouses: List of Warehouse ORM instances with
                truth_core and memories eager-loaded.

        Returns:
            List of plain dicts suitable for JSON serialization and
            prompt injection.
        """
        warehouse_dicts = []
        for wh in warehouses:
            tc = wh.truth_core
            wh_dict = {
                "id": wh.id,
                "address": wh.address,
                "city": wh.city,
                "state": wh.state,
                "building_size_sqft": wh.building_size_sqft,
                "property_type": wh.property_type,
                "primary_image_url": wh.primary_image_url,
                "lat": wh.lat,
                "lng": wh.lng,
                "image_urls": wh.image_urls or [],
                "truth_core": {
                    "min_sqft": tc.min_sqft,
                    "max_sqft": tc.max_sqft,
                    "activity_tier": tc.activity_tier,
                    "constraints": tc.constraints or {},
                    "clear_height_ft": tc.clear_height_ft,
                    "dock_doors_receiving": tc.dock_doors_receiving,
                    "dock_doors_shipping": tc.dock_doors_shipping,
                    "drive_in_bays": tc.drive_in_bays,
                    "has_office_space": tc.has_office_space,
                    "has_sprinkler": tc.has_sprinkler,
                    "parking_spaces": tc.parking_spaces,
                    "power_supply": tc.power_supply,
                    "trust_level": tc.trust_level,
                    "available_from": (
                        str(tc.available_from) if tc.available_from else "Now"
                    ),
                    "available_to": (
                        str(tc.available_to) if tc.available_to else None
                    ),
                    "min_term_months": tc.min_term_months,
                    "max_term_months": tc.max_term_months,
                    "tour_readiness": tc.tour_readiness,
                    "supplier_rate_per_sqft": tc.supplier_rate_per_sqft,
                },
                "memories": [
                    {"content": m.content, "memory_type": m.memory_type}
                    for m in (wh.memories or [])
                ],
            }
            warehouse_dicts.append(wh_dict)
        return warehouse_dicts

    # ------------------------------------------------------------------
    # InstantBookScore construction
    # ------------------------------------------------------------------

    def _build_instant_book_score(
        self,
        match_id: str,
        match_data: dict,
        tc_data: dict,
        memory_count: int,
    ) -> InstantBookScore:
        """Build an InstantBookScore record from match data.

        The composite sub-scores are derived from the clearing
        agent's scoring breakdown plus warehouse metadata quality
        signals (truth core completeness, memory depth, trust).

        Args:
            match_id: The Match record UUID this score belongs to.
            match_data: The match dict from the clearing agent.
            tc_data: The truth_core sub-dict for the warehouse.
            memory_count: Number of contextual memory entries.

        Returns:
            An InstantBookScore ORM instance (not yet added to session).
        """
        scoring = match_data.get("scoring_breakdown", {})
        composite = match_data.get("composite_score", 0)

        # Truth core completeness: how many key fields are populated
        key_fields = [
            "min_sqft", "max_sqft", "activity_tier", "clear_height_ft",
            "dock_doors_receiving", "supplier_rate_per_sqft", "tour_readiness",
            "trust_level",
        ]
        populated = sum(
            1 for f in key_fields
            if tc_data.get(f) is not None and tc_data.get(f) != 0
        )
        truth_core_completeness = min(100, int((populated / len(key_fields)) * 100))

        # Memory depth: more memories = more context = better scoring
        contextual_memory_depth = min(100, memory_count * 25)

        return InstantBookScore(
            id=str(uuid.uuid4()),
            match_id=match_id,
            truth_core_completeness=truth_core_completeness,
            contextual_memory_depth=contextual_memory_depth,
            supplier_trust_level=tc_data.get("trust_level", 0),
            match_specificity=int(composite),
            feature_alignment=int(scoring.get("use_type", 70)),
            composite_score=int(composite),
            instant_book_eligible=match_data.get("instant_book_eligible", False),
        )
