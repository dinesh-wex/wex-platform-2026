"""Clearing Engine - Orchestrates the matching pipeline.

The clearing engine is the heart of the WEx clearinghouse.  It takes a
buyer need, loads all active property supply, runs a deterministic
pre-filter, hands survivors to the AI-powered Clearing Agent for
multi-dimensional scoring, enriches the top matches with buyer-facing
pricing from the Pricing Agent, persists Match and InstantBookScore
records, and returns ranked results ready for presentation.

Two-tier matching:
    Tier 1 - In-network properties (relationship_status='active') with
             active listings.  These are scored, priced, and returned
             as ready-to-book matches.
    Tier 2 - Off-network properties (relationship_status in 'prospect',
             'contacted', 'interested', 'earncheck_only') that pass the
             same pre-filter.  When fewer than 3 Tier 1 matches exist,
             DLA (Demand-Led Activation) outreach is triggered for top
             Tier 2 candidates.
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
    Property,
    PropertyKnowledge,
    PropertyListing,
    PropertyEvent,
    ContextualMemory,
    BuyerNeed,
    Match,
    InstantBookScore,
    DLAToken,
    PropertyProfile,  # Keep for now — may be referenced in edge cases
)

logger = logging.getLogger(__name__)

# Tier 2 relationship statuses eligible for DLA outreach
TIER2_STATUSES = ("prospect", "contacted", "interested", "earncheck_only")

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
            2. Tier 1: Load in-network properties, pre-filter, AI-score,
               price, and persist Match records
            3. Tier 2: Load off-network properties, pre-filter, AI-score
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
        # Tier 1: In-network properties
        # ------------------------------------------------------------------
        tier1_matches = await self._run_tier1(
            buyer_need_id, buyer_need, need_dict, session
        )

        # ------------------------------------------------------------------
        # Tier 2: Off-network properties
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
        """Tier 1: score and price in-network properties."""

        result = await session.execute(
            select(Property)
            .join(PropertyListing)
            .join(PropertyKnowledge)
            .where(
                Property.relationship_status == "active",
                PropertyListing.activation_status == "on",
            )
            .options(
                selectinload(Property.listing),
                selectinload(Property.knowledge),
                selectinload(Property.memories),
            )
        )
        properties = result.unique().scalars().all()

        if not properties:
            logger.info(
                "No in-network properties found for buyer need %s",
                buyer_need_id,
            )
            return []

        candidates = self._pre_filter(buyer_need, properties)
        if not candidates:
            logger.info(
                "No in-network properties passed pre-filter for buyer need %s "
                "(checked %d)",
                buyer_need_id,
                len(properties),
            )
            return []

        logger.info(
            "Tier 1 pre-filter passed %d of %d in-network properties for %s",
            len(candidates),
            len(properties),
            buyer_need_id,
        )

        property_dicts = self._format_properties(candidates)

        # Layer 1: Deterministic MCDA scoring
        from wex_platform.services.match_scorer import (
            compute_composite_score,
            recompute_with_feature_score,
            apply_budget_context,
        )

        deterministic_scores = {}
        for prop_dict in property_dicts:
            scores = compute_composite_score(
                need_dict, prop_dict, prop_dict.get("truth_core", {})
            )
            deterministic_scores[prop_dict["id"]] = scores

        # Sort by base composite, take top candidates for LLM evaluation
        sorted_candidates = sorted(
            property_dicts,
            key=lambda p: deterministic_scores[p["id"]]["composite_score"],
            reverse=True,
        )[:6]  # Send top 6 to LLM, return top 3

        # Layer 2: LLM evaluates features + generates reasoning
        from wex_platform.agents.clearing_agent import ClearingAgent

        clearing_agent = ClearingAgent()

        try:
            agent_result = await clearing_agent.evaluate_features(
                need_dict, sorted_candidates, deterministic_scores,
            )
            if agent_result.ok:
                for match_data in agent_result.data:
                    prop_id = match_data.get("warehouse_id")
                    if prop_id in deterministic_scores:
                        deterministic_scores[prop_id] = recompute_with_feature_score(
                            deterministic_scores[prop_id],
                            match_data["feature_score"],
                        )
                        deterministic_scores[prop_id]["reasoning"] = match_data.get("reasoning", "")
                        deterministic_scores[prop_id]["instant_book_eligible"] = match_data.get("instant_book_eligible", False)
            else:
                logger.warning("LLM feature eval failed, using base scores: %s", agent_result.error)
        except Exception as exc:
            logger.warning("LLM feature eval exception, using base scores: %s", exc)

        # Deterministic instant_book_eligible based on PropertyListing.
        # Properties with pricing_mode="auto" and tour_required=False are eligible.
        candidate_ids = [p["id"] for p in sorted_candidates]
        pl_result = await session.execute(
            select(PropertyListing.property_id, PropertyListing.pricing_mode, PropertyListing.tour_required)
            .where(PropertyListing.property_id.in_(candidate_ids))
        )
        pl_data = {row.property_id: row for row in pl_result}

        for prop_cand in sorted_candidates:
            prop_id = prop_cand["id"]
            scores = deterministic_scores.get(prop_id)
            if scores:
                listing_row = pl_data.get(prop_id)
                # auto pricing + no tour required = instant book OK
                scores["instant_book_eligible"] = (
                    listing_row is not None
                    and listing_row.pricing_mode == "auto"
                    and not listing_row.tour_required
                )

        # Re-sort by final composite and take top 3
        final_sorted = sorted(
            sorted_candidates,
            key=lambda p: deterministic_scores[p["id"]]["composite_score"],
            reverse=True,
        )[:3]

        # Pricing (pure formula -- no AI needed) + persistence
        results: list[dict] = []
        for prop_dict_match in final_sorted:
            prop_id = prop_dict_match["id"]
            scores = deterministic_scores[prop_id]

            tc_data = prop_dict_match["truth_core"]
            supplier_rate = tc_data.get("supplier_rate_per_sqft", 0)

            # WEx formula: supplier x 1.20 (margin) x 1.06 (guarantee), round UP
            buyer_rate = math.ceil((supplier_rate * 1.20 * 1.06) * 100) / 100

            spread = buyer_rate - supplier_rate
            spread_pct = (spread / buyer_rate) * 100 if buyer_rate > 0 else 0

            match_id = str(uuid.uuid4())
            match = Match(
                id=match_id,
                buyer_need_id=buyer_need_id,
                warehouse_id=prop_id,
                match_score=scores["composite_score"],
                confidence=scores["composite_score"],
                instant_book_eligible=scores.get("instant_book_eligible", False),
                reasoning=scores.get("reasoning", ""),
                scoring_breakdown={
                    "location_score": scores["location_score"],
                    "size_score": scores["size_score"],
                    "use_type_score": scores["use_type_score"],
                    "feature_score": scores["feature_score"],
                    "timing_score": scores["timing_score"],
                    "budget_score": scores["budget_score"],
                },
                status="pending",
            )
            session.add(match)

            ib_score = self._build_instant_book_score(
                match_id=match_id,
                match_data={
                    "composite_score": scores["composite_score"],
                    "scoring_breakdown": {
                        "use_type": scores["use_type_score"],
                    },
                    "instant_book_eligible": scores.get("instant_book_eligible", False),
                },
                tc_data=tc_data,
                memory_count=len(prop_dict_match.get("memories", [])),
            )
            session.add(ib_score)

            results.append({
                "match_id": match_id,
                "warehouse_id": prop_id,
                "warehouse": prop_dict_match,
                "match_score": scores["composite_score"],
                "scoring_breakdown": {
                    "location_score": scores["location_score"],
                    "size_score": scores["size_score"],
                    "use_type_score": scores["use_type_score"],
                    "feature_score": scores["feature_score"],
                    "timing_score": scores["timing_score"],
                    "budget_score": scores["budget_score"],
                },
                "reasoning": scores.get("reasoning", ""),
                "instant_book_eligible": scores.get("instant_book_eligible", False),
                "buyer_rate": round(buyer_rate, 2),
                "supplier_rate": round(supplier_rate, 2),  # Admin only
                "spread_pct": round(spread_pct, 1),  # Admin only
                "confidence": scores["composite_score"],
                "distance_miles": scores.get("distance_miles"),
                "within_budget": scores.get("within_budget", True),
                "budget_stretch_pct": scores.get("budget_stretch_pct", 0.0),
                "use_type_callouts": scores.get("use_type_callouts", []),
            })

        apply_budget_context(results, buyer_need.max_budget_per_sqft)

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
            select(Property)
            .outerjoin(PropertyListing)
            .outerjoin(PropertyKnowledge)
            .where(
                Property.relationship_status.in_(TIER2_STATUSES),
            )
            .options(
                selectinload(Property.knowledge),
                selectinload(Property.listing),
                selectinload(Property.memories),
            )
        )
        properties = result.unique().scalars().all()

        if not properties:
            logger.info(
                "No off-network properties found for tier2 (buyer need %s)",
                buyer_need.id if hasattr(buyer_need, "id") else "?",
            )
            return []

        candidates = self._pre_filter(buyer_need, properties)
        if not candidates:
            return []

        logger.info(
            "Tier 2 pre-filter passed %d of %d off-network properties",
            len(candidates),
            len(properties),
        )

        # Use the same AI scoring pipeline for tier 2 candidates
        property_dicts = self._format_properties(candidates)

        from wex_platform.agents.clearing_agent import ClearingAgent

        clearing_agent = ClearingAgent()
        agent_result = await clearing_agent.find_matches(need_dict, property_dicts)

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
            prop_id = match_data.get("warehouse_id")
            prop_dict = next(
                (p for p in property_dicts if p["id"] == prop_id), None
            )
            if not prop_dict:
                continue

            tier2_results.append({
                "warehouse_id": prop_id,
                "neighborhood": prop_dict.get("neighborhood") or prop_dict.get("city", "Unknown"),
                "match_score": match_data.get("composite_score", 0),
                "sqft": prop_dict.get("building_size_sqft"),
                "building_type": prop_dict.get("property_type", "warehouse"),
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
            property_id = candidate["warehouse_id"]

            # Avoid duplicate tokens for the same property + buyer need
            existing = await session.execute(
                select(DLAToken).where(
                    DLAToken.warehouse_id == property_id,
                    DLAToken.buyer_need_id == buyer_need_id,
                    DLAToken.status.in_(("pending", "interested")),
                )
            )
            if existing.scalar_one_or_none():
                logger.debug(
                    "DLA token already exists for property %s / need %s",
                    property_id,
                    buyer_need_id,
                )
                continue

            token = DLAToken(
                id=str(uuid.uuid4()),
                token=secrets.token_urlsafe(32),
                warehouse_id=property_id,
                buyer_need_id=buyer_need_id,
                status="pending",
                expires_at=expires,
                outreach_channel="sms",
            )
            session.add(token)

            # Upgrade prospect -> interested
            prop_result = await session.execute(
                select(Property).where(Property.id == property_id)
            )
            prop = prop_result.scalar_one_or_none()
            if prop and prop.relationship_status == "prospect":
                prop.relationship_status = "interested"
                session.add(PropertyEvent(
                    property_id=property_id,
                    event_type="outreach_sent",
                    actor="system",
                    metadata_={"buyer_need_id": str(buyer_need_id), "source": "dla"},
                ))

            created += 1
            logger.info(
                "DLA token created for property %s (buyer need %s)",
                property_id,
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
        """Fast count of in-network properties matching basic criteria.

        Used by the buyer wizard size-slider to show a live count badge.

        Args:
            location: City or state string to match against.
            min_sqft: Minimum required sqft.
            max_sqft: Maximum required sqft.
            use_type: Optional property use type filter.
            session: Active DB session.

        Returns:
            Dict with ``count`` (int) and ``approximate`` (bool).
        """
        query = (
            select(sa_func.count(Property.id))
            .join(PropertyListing)
            .where(
                Property.relationship_status == "active",
                PropertyListing.activation_status == "on",
            )
        )

        # Location filter: match city or state (case-insensitive)
        if location:
            loc_upper = location.strip().upper()
            query = query.where(
                sa_func.upper(Property.city).contains(loc_upper)
                | sa_func.upper(Property.state).contains(loc_upper)
            )

        # Size filters against listing
        if min_sqft > 0:
            query = query.where(
                (PropertyListing.max_sqft >= min_sqft) | (PropertyListing.max_sqft.is_(None))
            )
        if max_sqft < 100_000:
            query = query.where(
                (PropertyListing.min_sqft <= max_sqft) | (PropertyListing.min_sqft.is_(None))
            )

        # Use type / activity tier filter
        if use_type:
            query = query.join(PropertyKnowledge).where(
                PropertyKnowledge.activity_tier == use_type
            )

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
            "lat": buyer_need.lat,
            "lng": buyer_need.lng,
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
        properties: list[Property],
    ) -> list[Property]:
        """Co-primary gate: BOTH geo AND requirements must pass."""
        candidates = []
        buyer_radius = buyer_need.radius_miles or 25
        max_radius = min(buyer_radius, 50)

        buyer_has_coords = buyer_need.lat is not None and buyer_need.lng is not None

        for prop in properties:
            pl = prop.listing
            pk = prop.knowledge

            # ---- REQUIREMENTS GATE ----
            if not self._passes_requirements_gate(prop, buyer_need):
                continue

            # ---- GEO GATE ----
            prop_has_coords = prop.lat is not None and prop.lng is not None

            if buyer_has_coords and prop_has_coords:
                # Best path: coordinate-based distance check
                dist = _haversine_miles(buyer_need.lat, buyer_need.lng, prop.lat, prop.lng)
                if dist > max_radius:
                    continue
            elif buyer_has_coords and not prop_has_coords:
                # Buyer has coords but property doesn't -- fall back to state match
                if buyer_need.state and prop.state:
                    if buyer_need.state.upper() != prop.state.upper():
                        continue
                else:
                    # Can't verify geo at all -- skip this property
                    continue
            elif buyer_need.state and prop.state:
                # No buyer coords -- state-level fallback
                if buyer_need.state.upper() != prop.state.upper():
                    continue
            else:
                # No geo info on either side -- skip
                continue

            candidates.append(prop)

        # If strict filter yields nothing, try KNN fallback
        if not candidates and buyer_need.lat and buyer_need.lng:
            candidates = self._knn_fallback(buyer_need, properties, k=5, max_distance=100)

        return candidates

    def _passes_requirements_gate(self, prop: Property, buyer_need: BuyerNeed) -> bool:
        """Check size overlap and use type compatibility."""
        pl = prop.listing
        pk = prop.knowledge

        # For Tier 2, listing may not exist -- use knowledge if available
        if pl:
            min_sqft = pl.min_sqft
            max_sqft = pl.max_sqft
        else:
            # No listing -- cannot verify size constraints, allow through
            min_sqft = None
            max_sqft = None

        # Size overlap
        if buyer_need.min_sqft and max_sqft and max_sqft < buyer_need.min_sqft:
            return False
        if buyer_need.max_sqft and min_sqft and min_sqft > buyer_need.max_sqft:
            return False

        # Use type compatibility (replaces flat activity_tier match)
        if buyer_need.use_type:
            activity_tier = pk.activity_tier if pk else None
            has_office = pk.has_office if pk else False
            from wex_platform.services.use_type_compat import compute_use_type_score
            score, _ = compute_use_type_score(
                activity_tier or "storage_only",
                buyer_need.use_type,
                has_office_space=has_office or False,
            )
            if score == 0:
                return False

        return True

    def _knn_fallback(self, buyer_need, all_properties, k=5, max_distance=100):
        """Find k nearest properties that pass requirements gate, regardless of radius."""
        scored = []
        for prop in all_properties:
            if not self._passes_requirements_gate(prop, buyer_need):
                continue
            if not (prop.lat and prop.lng):
                continue
            dist = _haversine_miles(buyer_need.lat, buyer_need.lng, prop.lat, prop.lng)
            if dist <= max_distance:
                scored.append((dist, prop))
        scored.sort(key=lambda x: x[0])
        return [prop for _, prop in scored[:k]]

    # ------------------------------------------------------------------
    # Property formatting
    # ------------------------------------------------------------------

    def _format_properties(
        self,
        properties: list,
    ) -> list[dict]:
        """Convert Property ORM objects to dicts for the scoring pipeline.
        No merge logic needed -- each field has exactly one authoritative home.
        """
        result = []
        for prop in properties:
            pk = prop.knowledge  # PropertyKnowledge (1:1, may be None)
            pl = prop.listing    # PropertyListing (1:1, may be None)

            entry = {
                "id": prop.id,
                "address": prop.address,
                "city": prop.city,
                "state": prop.state,
                "zip": prop.zip,
                "building_size_sqft": pk.building_size_sqft if pk else None,
                "property_type": prop.property_type,
                "primary_image_url": prop.primary_image_url,
                "lat": prop.lat,
                "lng": prop.lng,
                "image_urls": prop.image_urls or [],
                "description": pk.additional_notes if pk else None,
                "neighborhood": prop.neighborhood,
                # Preserve "truth_core" sub-key for downstream compat (match_scorer, clearing_agent)
                "truth_core": {
                    "min_sqft": pl.min_sqft if pl else None,
                    "max_sqft": pl.max_sqft if pl else None,
                    "activity_tier": pk.activity_tier if pk else None,
                    "constraints": pl.constraints if pl else {},
                    "clear_height_ft": pk.clear_height_ft if pk else None,
                    "dock_doors_receiving": pk.dock_doors_receiving if pk else 0,
                    "dock_doors_shipping": pk.dock_doors_shipping if pk else 0,
                    "drive_in_bays": pk.drive_in_bays if pk else 0,
                    "has_office_space": pk.has_office if pk else False,
                    "has_sprinkler": pk.has_sprinkler if pk else False,
                    "parking_spaces": pk.parking_spaces if pk else 0,
                    "power_supply": pk.power_supply if pk else None,
                    "trust_level": pl.trust_level if pl else 0,
                    "min_term_months": pl.min_term_months if pl else 1,
                    "max_term_months": pl.max_term_months if pl else 12,
                    "tour_readiness": pl.tour_readiness if pl else "48_hours",
                    "supplier_rate_per_sqft": pl.supplier_rate_per_sqft if pl else None,
                },
                "memories": [
                    {"content": m.content, "memory_type": m.memory_type}
                    for m in (prop.memories or [])
                ],
            }
            result.append(entry)
        return result

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
        agent's scoring breakdown plus property metadata quality
        signals (listing completeness, memory depth, trust).

        Args:
            match_id: The Match record UUID this score belongs to.
            match_data: The match dict from the clearing agent.
            tc_data: The truth_core sub-dict for the property.
            memory_count: Number of contextual memory entries.

        Returns:
            An InstantBookScore ORM instance (not yet added to session).
        """
        scoring = match_data.get("scoring_breakdown", {})
        composite = match_data.get("composite_score", 0)

        # Listing completeness: how many key fields are populated
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
