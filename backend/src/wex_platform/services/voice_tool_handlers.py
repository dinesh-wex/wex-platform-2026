"""Vapi voice agent tool handlers.

Each handler bridges a Vapi tool-call to existing WEx services,
running a mini-pipeline: validate -> execute -> gate -> format for voice.
"""

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from wex_platform.domain.voice_models import VoiceCallState
from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    BuyerNeed,
    SearchSession,
)

logger = logging.getLogger(__name__)


class VoiceToolHandlers:
    """Handles Vapi tool-call execution by delegating to existing WEx services."""

    def __init__(self, db: AsyncSession, call_state: VoiceCallState):
        self.db = db
        self.call_state = call_state

    # ------------------------------------------------------------------
    # search_properties
    # ------------------------------------------------------------------

    async def search_properties(
        self,
        location: str,
        sqft: int,
        use_type: str | None = None,
        timing: str | None = None,
        duration: str | None = None,
        features: list[str] | None = None,
    ) -> str:
        """Search for matching warehouse properties.

        Pipeline: validate -> get/create buyer+need -> geocode -> ClearingEngine -> format
        """
        try:
            # 1. Get or create buyer + conversation
            phone = self.call_state.caller_phone

            result = await self.db.execute(
                select(Buyer).where(Buyer.phone == phone)
            )
            buyer = result.scalar_one_or_none()

            if not buyer:
                buyer = Buyer(
                    id=str(uuid.uuid4()),
                    phone=phone,
                    name=self.call_state.buyer_name or "",
                )
                self.db.add(buyer)
                await self.db.flush()

            self.call_state.buyer_id = buyer.id

            # Find or create conversation
            result = await self.db.execute(
                select(BuyerConversation)
                .where(BuyerConversation.buyer_id == buyer.id)
                .order_by(BuyerConversation.created_at.desc())
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                conversation = BuyerConversation(
                    id=str(uuid.uuid4()),
                    buyer_id=buyer.id,
                )
                self.db.add(conversation)
                await self.db.flush()

            self.call_state.conversation_id = conversation.id

            # 2. Parse location into city/state
            city, state = _parse_location(location)

            # 3. Create BuyerNeed (same pattern as buyer_sms_orchestrator._run_search)
            parsed_features = features or []
            buyer_need = BuyerNeed(
                id=str(uuid.uuid4()),
                buyer_id=buyer.id,
                city=city,
                state=state,
                min_sqft=int(sqft * 0.8) if sqft else None,
                max_sqft=int(sqft * 1.2) if sqft else None,
                use_type=use_type or "general",
                needed_from=_parse_timing(timing),
                duration_months=_parse_duration(duration),
                requirements={"features": parsed_features} if parsed_features else {},
            )
            self.db.add(buyer_need)
            await self.db.flush()

            self.call_state.buyer_need_id = buyer_need.id

            # 4. Geocode
            try:
                from wex_platform.services.geocoding_service import geocode_location

                geo_str = f"{city}, {state}" if state else city
                geo = await geocode_location(geo_str)
                if geo and geo.lat:
                    buyer_need.lat = geo.lat
                    buyer_need.lng = geo.lng
                    await self.db.flush()
            except Exception as e:
                logger.warning("Geocoding failed for '%s': %s", location, e)

            # 5. Run ClearingEngine
            from wex_platform.services.clearing_engine import ClearingEngine

            engine = ClearingEngine()
            clearing_result = await engine.run_clearing(
                buyer_need_id=buyer_need.id, db=self.db
            )

            tier1 = clearing_result.get("tier1_matches", [])

            if not tier1:
                return (
                    "I searched for warehouse space in that area but didn't find "
                    "any exact matches right now. I can keep looking and text you "
                    "when something opens up. Would you like me to do that?"
                )

            # 6. Build match summaries using shared context_builder
            from wex_platform.agents.sms.context_builder import build_match_summaries

            summaries = build_match_summaries(tier1, buyer_sqft=sqft)

            # Store presented IDs on call state
            presented_ids = [s["id"] for s in summaries if s.get("id")]
            self.call_state.presented_match_ids = presented_ids

            # 7. Create SearchSession (same pattern as SMS orchestrator)
            token = secrets.token_urlsafe(32)

            tier1_safe = []
            for m in tier1[:3]:
                wh = m.get("warehouse", {})
                tc = wh.get("truth_core", {}) if isinstance(wh, dict) else {}
                tier1_safe.append({
                    "match_id": m.get("match_id"),
                    "warehouse_id": m.get("warehouse_id"),
                    "confidence": round(m.get("match_score", 0) * 100) if m.get("match_score") else 0,
                    "neighborhood": f"{wh.get('city', '')}, {wh.get('state', '')}",
                    "city": wh.get("city", ""),
                    "state": wh.get("state", ""),
                    "address": wh.get("address", ""),
                    "available_sqft": tc.get("max_sqft"),
                    "building_size_sqft": wh.get("building_size_sqft"),
                    "buyer_rate": m.get("buyer_rate", 0),
                    "primary_image_url": wh.get("primary_image_url"),
                    "features": {
                        "clear_height": tc.get("clear_height_ft"),
                        "dock_doors": tc.get("dock_doors_receiving"),
                        "has_office": tc.get("has_office_space"),
                    },
                    "tier": 1,
                })

            session_record = SearchSession(
                id=str(uuid.uuid4()),
                token=token,
                requirements={
                    "city": city,
                    "state": state,
                    "sqft": sqft,
                    "use_type": use_type,
                },
                results={"tier1": tier1_safe, "tier2": []},
                buyer_need_id=buyer_need.id,
                buyer_id=buyer.id,
                status="active",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=48),
            )
            self.db.add(session_record)
            await self.db.flush()

            self.call_state.search_session_token = token

            # 8. Cache match summaries + IDs on call state for detail lookups
            voice_summaries = []
            for s in summaries[:3]:
                voice_summary = {
                    "id": s.get("id", ""),
                    "city": s.get("city", ""),
                    "state": s.get("state", ""),
                    "rate": s.get("rate"),
                    "monthly": s.get("monthly"),
                    "score": s.get("match_score"),
                    "features": [],
                    "instant_book": False,
                }
                # Cross-reference with tier1 data for features
                match_data = next(
                    (m for m in tier1 if m.get("warehouse_id") == s.get("id")),
                    None,
                )
                if match_data:
                    voice_summary["instant_book"] = match_data.get("instant_book_eligible", False)
                    wh = match_data.get("warehouse", {})
                    tc = wh.get("truth_core", {}) if isinstance(wh, dict) else {}
                    dock_recv = tc.get("dock_doors_receiving") or 0
                    dock_ship = tc.get("dock_doors_shipping") or 0
                    total_docks = dock_recv + dock_ship
                    if total_docks:
                        voice_summary["features"].append(f"{total_docks} dock doors")
                    if tc.get("has_office_space"):
                        voice_summary["features"].append("office space")
                    if tc.get("clear_height_ft"):
                        voice_summary["features"].append(f"{tc['clear_height_ft']}ft clear height")
                    if tc.get("has_sprinkler"):
                        voice_summary["features"].append("sprinkler system")

                voice_summaries.append(voice_summary)

            self.call_state.match_summaries = voice_summaries
            await self.db.flush()

            # 9. Format for voice and gate
            lines = [f"I found {len(voice_summaries)} options for you."]
            for i, s in enumerate(voice_summaries, 1):
                rate_str = f"{s['rate']:.2f} per square foot" if s.get("rate") else "rate to be confirmed"
                monthly_str = f", about ${s['monthly']:,} a month" if s.get("monthly") else ""
                features_str = f". {', '.join(s['features'])}" if s.get("features") else ""
                lines.append(
                    f"Option {i} is in {s['city']}"
                    f"{', ' + s['state'] if s.get('state') else ''} "
                    f"at ${rate_str}{monthly_str}{features_str}."
                )
            lines.append("Any of those sound interesting?")

            text = " ".join(lines)
            return _gate_voice_output(text)

        except Exception as e:
            logger.error("search_properties failed: %s", e, exc_info=True)
            return (
                "I ran into an issue searching right now. Let me note your "
                "requirements and follow up with you by text."
            )

    # ------------------------------------------------------------------
    # lookup_property_details
    # ------------------------------------------------------------------

    async def lookup_property_details(
        self,
        option_number: int,
        topics: list[str] | None = None,
    ) -> str:
        """Look up details about a specific property option.

        Pipeline: resolve option -> DetailFetcher -> escalation check -> format
        """
        try:
            presented = self.call_state.presented_match_ids or []
            if not presented or option_number < 1 or option_number > len(presented):
                return f"I don't have an option {option_number}. I showed you {len(presented)} options."

            property_id = presented[option_number - 1]

            # If no specific topics, return cached summary
            if not topics:
                summaries = self.call_state.match_summaries or []
                if option_number <= len(summaries):
                    s = summaries[option_number - 1]
                    rate_str = f"${s['rate']:.2f} per square foot" if s.get("rate") else "rate to be confirmed"
                    monthly_str = f", about ${s['monthly']:,} a month" if s.get("monthly") else ""
                    features_str = (
                        f". Features include: {', '.join(s['features'])}"
                        if s.get("features")
                        else ""
                    )
                    text = (
                        f"Option {option_number} is in {s.get('city', 'the area')} at "
                        f"{rate_str}{monthly_str}{features_str}."
                    )
                    return _gate_voice_output(text)
                return f"Let me pull up the details for option {option_number}."

            # Use DetailFetcher for specific topics
            from wex_platform.services.sms_detail_fetcher import DetailFetcher

            fetcher = DetailFetcher(self.db)

            fetch_results = await fetcher.fetch_by_topics(
                property_id=property_id,
                topics=topics,
                state=self.call_state,  # Uses known_answers for caching
            )

            # Separate answered from unanswered
            answered = [r for r in fetch_results if r.status in ("FOUND", "CACHE_HIT")]
            needs_escalation = [r for r in fetch_results if r.needs_escalation]

            parts = []

            # Format answered details
            if answered:
                detail_parts = []
                for r in answered:
                    label = r.label or r.field_key or "that"
                    detail_parts.append(f"{label}: {r.formatted}")
                parts.append(f"For option {option_number}: {', '.join(detail_parts)}.")

            # Handle escalations
            if needs_escalation:
                from wex_platform.services.escalation_service import EscalationService

                esc_service = EscalationService(self.db)

                escalated_labels = []
                for r in needs_escalation:
                    esc_result = await esc_service.check_and_escalate(
                        property_id=property_id,
                        question_text=f"Buyer asked about {r.field_key or 'property details'} via voice call",
                        field_key=r.field_key,
                        state=self.call_state,
                    )
                    if esc_result.get("answer"):
                        # Got answer from cache or previous escalation
                        parts.append(f"{r.label or r.field_key}: {esc_result['answer']}.")
                    elif esc_result.get("escalated"):
                        escalated_labels.append(r.label or r.field_key or "that detail")

                if escalated_labels:
                    if len(escalated_labels) == 1:
                        parts.append(
                            f"I don't have info on {escalated_labels[0]} right now. "
                            "I'll check with the warehouse owner and text you back."
                        )
                    else:
                        items = " and ".join(escalated_labels)
                        parts.append(
                            f"I don't have info on {items} right now. "
                            "I'll check with the warehouse owner and text you back."
                        )

            if not parts:
                return (
                    f"I don't have specific details on that for option {option_number} "
                    "right now. I'll look into it and text you."
                )

            text = " ".join(parts)
            return _gate_voice_output(text)

        except Exception as e:
            logger.error("lookup_property_details failed: %s", e, exc_info=True)
            return "I'm having trouble pulling up those details. I'll look into it and text you."

    # ------------------------------------------------------------------
    # send_booking_link
    # ------------------------------------------------------------------

    async def send_booking_link(
        self,
        option_number: int,
        buyer_name: str,
        buyer_email: str | None = None,
    ) -> str:
        """Create engagement + guarantee token, queue SMS for end-of-call.

        Pipeline: resolve option -> EngagementBridge -> SmsTokenService -> confirm
        """
        try:
            presented = self.call_state.presented_match_ids or []
            if not presented or option_number < 1 or option_number > len(presented):
                return "I'm not sure which property you mean. Could you clarify which option?"

            property_id = presented[option_number - 1]

            # Store buyer info on call state
            self.call_state.buyer_name = buyer_name
            if buyer_email:
                self.call_state.buyer_email = buyer_email

            # Create engagement via EngagementBridge
            from wex_platform.services.engagement_bridge import EngagementBridge

            bridge = EngagementBridge(self.db)

            booking_result = await bridge.initiate_booking(
                property_id=property_id,
                buyer_phone=self.call_state.verified_phone or self.call_state.caller_phone,
                buyer_name=buyer_name,
                buyer_email=buyer_email,
                buyer_need_id=self.call_state.buyer_need_id,
            )

            if not booking_result or booking_result.get("error"):
                return (
                    "I ran into an issue setting that up. Let me note your interest "
                    "and someone from our team will follow up with you."
                )

            self.call_state.engagement_id = booking_result.get("engagement_id")

            # Create guarantee token via SmsTokenService
            from wex_platform.services.sms_token_service import SmsTokenService

            token_service = SmsTokenService(self.db)

            token = await token_service.create_guarantee_token(
                conversation_state_id=None,  # Voice calls don't have an SMS conversation state
                buyer_phone=self.call_state.verified_phone or self.call_state.caller_phone,
                engagement_id=booking_result.get("engagement_id"),
                prefilled_name=buyer_name,
                prefilled_email=buyer_email,
            )

            self.call_state.guarantee_link_token = token.token
            await self.db.flush()

            first_name = buyer_name.split()[0] if buyer_name else ""
            return (
                f"I've set that up for you{', ' + first_name if first_name else ''}. "
                "I'll text you a link right after this call to finalize everything."
            )

        except Exception as e:
            logger.error("send_booking_link failed: %s", e, exc_info=True)
            return (
                "I ran into a technical issue. Let me note your interest and "
                "someone will follow up with you shortly."
            )


# ======================================================================
# Private helpers
# ======================================================================


def _gate_voice_output(text: str) -> str:
    """Run VoiceGatekeeper on tool output; return sanitized text on violations."""
    from wex_platform.agents.voice.gatekeeper import validate_tool_result

    gate = validate_tool_result(text)
    if not gate.ok:
        logger.warning("Voice gatekeeper violations: %s", gate.violations)
        return gate.sanitized_text or text
    return text


def _parse_location(location: str) -> tuple[str, str | None]:
    """Parse a location string into (city, state).

    Handles: "Dallas, TX", "Dallas Texas", "Dallas, Texas", "Dallas"
    """
    parts = [p.strip() for p in location.split(",")]
    if len(parts) >= 2:
        city = parts[0]
        state = parts[1].strip()
        return city, state

    # Try to find state abbreviation at end
    words = location.strip().split()
    if len(words) >= 2 and len(words[-1]) == 2 and words[-1].isalpha():
        state = words[-1].upper()
        city = " ".join(words[:-1])
        return city, state

    return location.strip(), None


def _parse_timing(timing: str | None) -> datetime | None:
    """Parse a timing string into a datetime (needed_from is DateTime on BuyerNeed)."""
    if not timing:
        return None

    timing_lower = timing.lower().strip()

    if timing_lower in ("asap", "immediately", "now", "right away"):
        return datetime.now(timezone.utc)

    # Try common patterns: "next month", "in 2 weeks", "March", "March 2026"
    month_names = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "jun": 6, "jul": 7, "aug": 8, "sep": 9,
        "oct": 10, "nov": 11, "dec": 12,
    }

    for name, month_num in month_names.items():
        if name in timing_lower:
            now = datetime.now(timezone.utc)
            year = now.year
            # If the month is in the past this year, assume next year
            if month_num <= now.month:
                year += 1
            return datetime(year, month_num, 1, tzinfo=timezone.utc)

    if "next month" in timing_lower:
        now = datetime.now(timezone.utc)
        if now.month == 12:
            return datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        return datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)

    # Try extracting weeks/days
    weeks_match = re.search(r"(\d+)\s*week", timing_lower)
    if weeks_match:
        return datetime.now(timezone.utc) + timedelta(weeks=int(weeks_match.group(1)))

    days_match = re.search(r"(\d+)\s*day", timing_lower)
    if days_match:
        return datetime.now(timezone.utc) + timedelta(days=int(days_match.group(1)))

    return None


def _parse_duration(duration: str | None) -> int | None:
    """Parse a duration string into months."""
    if not duration:
        return None

    duration_lower = duration.lower().replace(" ", "").replace("-", "_")

    duration_map = {
        "1_3": 3,
        "3_6": 6,
        "6_12": 12,
        "12_24": 24,
        "24+": 36,
        "1_month": 1,
        "3_months": 3,
        "6_months": 6,
        "12_months": 12,
        "1_year": 12,
        "2_years": 24,
    }

    for key, months in duration_map.items():
        if key in duration_lower:
            return months

    # Try to extract a number
    match = re.search(r"(\d+)", duration)
    if match:
        num = int(match.group(1))
        if "year" in duration.lower():
            return num * 12
        return num

    return None
