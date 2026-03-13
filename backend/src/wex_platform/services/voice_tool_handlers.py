"""Vapi voice agent tool handlers.

Each handler bridges a Vapi tool-call to existing WEx services,
running a mini-pipeline: validate -> execute -> gate -> format for voice.
"""

import asyncio
import logging
import os
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

VOICE_TOOL_LIMITS = {
    "search": int(os.environ.get("VOICE_SEARCH_LIMIT", "9")),
    "detail": int(os.environ.get("VOICE_DETAIL_LIMIT", "15")),
    "address": int(os.environ.get("VOICE_ADDRESS_LIMIT", "6")),
}

VOICE_LIMIT_RESPONSE = (
    "I've shown you quite a few options. Want to narrow down what we've looked at, "
    "or I can have our team email you a full summary?"
)


class VoiceToolHandlers:
    """Handles Vapi tool-call execution by delegating to existing WEx services."""

    def __init__(self, db: AsyncSession, call_state: VoiceCallState):
        self.db = db
        self.call_state = call_state

    async def _check_and_increment(self, tool_key: str) -> str | None:
        """Check tool limit, increment counter. Returns redirect message if limit hit, None if OK."""
        counts = self.call_state.tool_counts or {}
        current = counts.get(tool_key, 0)
        if current >= VOICE_TOOL_LIMITS.get(tool_key, 99):
            logger.warning("TOOL_LIMIT | voice %s hit limit %d for %s",
                           self.call_state.vapi_call_id, current, tool_key)
            from wex_platform.services.email_service import send_tool_limit_email
            await send_tool_limit_email({
                "phone": self.call_state.caller_phone,
                "channel": "voice",
                "tool_key": tool_key,
                "count": current,
                "limits": VOICE_TOOL_LIMITS,
                "call_id": self.call_state.vapi_call_id,
            })
            return VOICE_LIMIT_RESPONSE
        counts[tool_key] = current + 1
        self.call_state.tool_counts = counts
        return None

    # ------------------------------------------------------------------
    # search_properties
    # ------------------------------------------------------------------

    async def search_properties(
        self,
        location: str,
        sqft: int | None = None,
        use_type: str | None = None,
        timing: str | None = None,
        duration: str | None = None,
        features: list[str] | None = None,
        budget_monthly: int | None = None,
    ) -> str:
        """Search for matching warehouse properties.

        Pipeline: validate -> get/create buyer+need -> geocode -> ClearingEngine -> format
        """
        limit_msg = await self._check_and_increment("search")
        if limit_msg:
            return limit_msg

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

            # 2b. Budget-to-sqft conversion
            if budget_monthly and not sqft:
                try:
                    from wex_platform.services.buyer_sms_orchestrator import _get_market_rates
                    nnn_low, nnn_high = await _get_market_rates(city, state)
                    if nnn_low and nnn_high:
                        avg_rate = (nnn_low + nnn_high) / 2
                        sqft = int(budget_monthly / avg_rate)
                        logger.info("Voice budget conversion: $%d/mo -> %d sqft (rate=%.2f)", budget_monthly, sqft, avg_rate)
                except Exception:
                    logger.exception("Voice budget-to-sqft conversion failed")

            if not sqft:
                return (
                    "I need to know how much space you're looking for. "
                    "Can you give me a rough square footage or a monthly budget?"
                )

            # 3. Get or reuse BuyerNeed — reuse if seeded from SMS and criteria still match
            parsed_features = features or []
            reuse_existing = False

            if self.call_state.buyer_need_id:
                # VoiceCallState was seeded from an SMS conversation.
                # NOTE: VoiceCallState is seeded from SMS once at call start and updated
                # independently. SMSConversationState is NEVER written to by voice handlers.
                # If criteria diverge (different city/sqft), we create a voice-only BuyerNeed.
                need_result = await self.db.execute(
                    select(BuyerNeed).where(BuyerNeed.id == self.call_state.buyer_need_id)
                )
                existing_need = need_result.scalar_one_or_none()

                if existing_need:
                    city_match = (existing_need.city or "").lower() == city.lower()
                    sqft_in_range = (
                        existing_need.min_sqft is not None
                        and existing_need.max_sqft is not None
                        and existing_need.min_sqft <= sqft <= existing_need.max_sqft
                    )
                    if city_match and sqft_in_range:
                        reuse_existing = True
                        buyer_need = existing_need
                        logger.info(
                            "Reusing SMS-seeded BuyerNeed %s for voice call (city=%s, sqft=%d)",
                            existing_need.id, city, sqft,
                        )

            if not reuse_existing:
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

            # 5a. Early return: if we're reusing an existing BuyerNeed and already have
            # cached match summaries from the SMS conversation, skip the ClearingEngine.
            if reuse_existing and self.call_state.match_summaries:
                voice_summaries = self.call_state.match_summaries
                self.call_state.presented_match_ids = [s["id"] for s in voice_summaries if s.get("id")]
                await self.db.flush()

                lines = [
                    f"Based on what we found for you earlier, I have "
                    f"{len(voice_summaries)} option{'s' if len(voice_summaries) != 1 else ''}."
                ]
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
            from wex_platform.agents.voice.gatekeeper import sanitize_match_summary
            summaries = [sanitize_match_summary(s) for s in summaries]

            # Store presented IDs on call state
            presented_ids = [s["id"] for s in summaries if s.get("id")]
            self.call_state.presented_match_ids = presented_ids

            # 7. Create SearchSession (same pattern as SMS orchestrator)
            token = secrets.token_urlsafe(32)

            # Build buyer-safe results matching web format (must match search.py shape)
            req_sqft = sqft or 0
            req_term = buyer_need.duration_months or 6
            tier1_safe = []
            for m in tier1[:3]:
                wh = m.get("warehouse", {})
                tc = wh.get("truth_core", {}) if isinstance(wh, dict) else {}
                rate = m.get("buyer_rate", 0)
                alloc_sqft = req_sqft or tc.get("max_sqft", 0)
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
                    "buyer_rate": rate,
                    "monthly_cost": round(rate * alloc_sqft, 2),
                    "term_months": req_term,
                    "total_value": round(rate * alloc_sqft * req_term, 2),
                    "primary_image_url": wh.get("primary_image_url"),
                    "description": wh.get("description", ""),
                    "features": {
                        "activity_tier": tc.get("activity_tier"),
                        "clear_height": tc.get("clear_height_ft"),
                        "dock_doors": tc.get("dock_doors_receiving"),
                        "has_office": tc.get("has_office_space"),
                        "has_sprinkler": tc.get("has_sprinkler"),
                        "parking": tc.get("parking_spaces"),
                    },
                    "instant_book_eligible": m.get("instant_book_eligible", False),
                    "distance_miles": m.get("distance_miles"),
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
        limit_msg = await self._check_and_increment("detail")
        if limit_msg:
            return limit_msg

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

            # Sanitize: strip voice-restricted fields from results
            from wex_platform.agents.voice.gatekeeper import sanitize_detail_response
            for r in fetch_results:
                if hasattr(r, "property_data") and isinstance(r.property_data, dict):
                    r.property_data = sanitize_detail_response(r.property_data)

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
                waiting_labels = []
                for r in needs_escalation:
                    # Use the AI-interpreted field label (from Vapi's topic mapping),
                    # not the raw speech transcription which has STT artifacts.
                    question_text = r.label or (r.field_key or "").replace("_", " ") or "property details"
                    esc_result = await esc_service.check_and_escalate(
                        property_id=property_id,
                        question_text=question_text,
                        field_key=r.field_key,
                        state=self.call_state,
                        source_type="voice",
                    )
                    if esc_result.get("answer"):
                        # Got answer from cache or previous escalation
                        parts.append(f"{r.label or r.field_key}: {esc_result['answer']}.")
                    elif esc_result.get("escalated"):
                        escalated_labels.append(r.label or r.field_key or "that detail")
                    elif esc_result.get("waiting"):
                        # Already escalated via another channel — pending
                        waiting_labels.append(r.label or r.field_key or "that detail")

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

                if waiting_labels:
                    if len(waiting_labels) == 1:
                        parts.append(
                            f"We're still waiting to hear back on {waiting_labels[0]} from the warehouse owner."
                        )
                    else:
                        items = " and ".join(waiting_labels)
                        parts.append(
                            f"We're still waiting to hear back on {items} from the warehouse owner."
                        )

            # Handle fully unmapped topics (topics were provided but none matched topic_catalog)
            # fetch_by_topics returned empty list — no mapped fields, no escalation yet.
            if not fetch_results and topics:
                # Use the AI-interpreted topic names (from Vapi's LLM tool call),
                # not the raw speech transcription which has STT artifacts.
                topic_labels = ', '.join(t.replace('_', ' ') for t in topics)
                question_text = topic_labels

                # Try PropertyInsight first (4-second timeout for voice)
                insight_found = False
                try:
                    from wex_platform.services.property_insight_service import PropertyInsightService
                    insight_service = PropertyInsightService(self.db)
                    insight = await asyncio.wait_for(
                        insight_service.search(property_id, question_text, channel="voice"),
                        timeout=4.0,
                    )
                    if insight.found and insight.answer:
                        from wex_platform.agents.voice.gatekeeper import scrub_narrative_for_voice
                        parts.append(scrub_narrative_for_voice(insight.answer))
                        insight_found = True
                except asyncio.TimeoutError:
                    logger.warning(
                        "PropertyInsight timed out (4s) for property %s, falling through to escalation",
                        property_id,
                    )
                except Exception:
                    logger.exception("PropertyInsight error for property %s", property_id)

                if not insight_found:
                    # Fall through to escalation (existing code)
                    from wex_platform.services.escalation_service import EscalationService
                    esc_service = EscalationService(self.db)
                    esc_result = await esc_service.check_and_escalate(
                        property_id=property_id,
                        question_text=question_text,
                        field_key=None,
                        state=self.call_state,
                        source_type="voice",
                    )
                    if esc_result.get("answer"):
                        parts.append(esc_result["answer"])
                    elif esc_result.get("waiting"):
                        parts.append("We're still checking on that with the warehouse owner. Should hear back soon.")
                    elif esc_result.get("escalated"):
                        parts.append(
                            "I don't have that right now. I'll check with the warehouse owner and text you back."
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
    # lookup_by_address
    # ------------------------------------------------------------------

    async def lookup_by_address(self, address: str) -> str:
        """Look up a specific property by street address.

        Pipeline: address_lookup service -> tier check -> format for voice
        """
        limit_msg = await self._check_and_increment("address")
        if limit_msg:
            return limit_msg

        try:
            from wex_platform.services.address_lookup import lookup_by_address as _lookup

            result = await _lookup(address_text=address, db=self.db, include_tier2=True)

            if not result.found or not result.property_data:
                return (
                    "I couldn't find that specific address in our system. "
                    "Want me to search for available space in that area instead?"
                )

            from wex_platform.agents.voice.gatekeeper import sanitize_detail_response
            data = sanitize_detail_response(result.property_data or {})
            city = data.get("city", "the area")
            state = data.get("state", "")
            location_str = f"{city}, {state}" if state else city

            if result.tier == 1:
                # Tier 1: active property — present details and track
                self.call_state.presented_match_ids = self.call_state.presented_match_ids or []
                self.call_state.presented_match_ids.append(result.property_id)

                rate = data.get("rate")
                rate_str = f"at ${rate:.2f} per square foot" if rate else "with rate to be confirmed"
                features_parts = []
                feats = data.get("features", {})
                if feats.get("dock_doors"):
                    features_parts.append(f"{feats['dock_doors']} dock doors")
                if feats.get("has_office"):
                    features_parts.append("office space")
                if feats.get("clear_height_ft"):
                    features_parts.append(f"{feats['clear_height_ft']}ft clear height")
                features_str = f", with {', '.join(features_parts)}" if features_parts else ""

                text = (
                    f"I found that property in {location_str} {rate_str}{features_str}. "
                    "Would you like more details, or should I send you the info by text?"
                )
                return _gate_voice_output(text)

            elif result.tier == 2:
                # Tier 2: not yet active — offer to check with owner
                return (
                    f"I found that property in {location_str}, but we don't have it "
                    "listed for instant availability yet. I can check with the owner "
                    "to see if space is available — want me to do that?"
                )

            else:
                return (
                    "I found a property at that address, but I don't have availability "
                    "info right now. Want me to search for other options in that area?"
                )

        except Exception as e:
            logger.error("lookup_by_address failed: %s", e, exc_info=True)
            return (
                "I had trouble looking up that address. "
                "Want me to search for available space in that area instead?"
            )

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

    # ------------------------------------------------------------------
    # add_to_waitlist
    # ------------------------------------------------------------------

    async def handle_add_to_waitlist(self, params: dict) -> str:
        """Add caller to waitlist for a city with no current inventory."""
        city = params.get("city")
        if not city:
            return "I need to know which city to add you to the waitlist for."

        sqft_needed = params.get("sqft_needed")
        use_type = params.get("use_type")

        from wex_platform.services.waitlist_service import WaitlistService
        waitlist = WaitlistService(self.db)

        criteria = {}
        if sqft_needed:
            criteria["sqft"] = sqft_needed
        if use_type:
            criteria["use_type"] = use_type
        criteria["location"] = city

        # Use call_state phone and buyer_id
        phone = self.call_state.caller_phone
        buyer_id = self.call_state.buyer_id

        # Ensure we have a buyer_id — create buyer record if needed
        if not buyer_id:
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
            buyer_id = buyer.id
            self.call_state.buyer_id = buyer_id

        try:
            await waitlist.add_to_waitlist(
                phone=phone,
                buyer_id=buyer_id,
                criteria=criteria,
                source_channel="voice",
            )
        except Exception as e:
            logger.error("add_to_waitlist failed: %s", e, exc_info=True)
            return "I had trouble adding you to the waitlist. I'll note your interest and follow up by text."

        return f"Done — added to the waitlist for {city}. They'll get a text when something opens up."

    # ------------------------------------------------------------------
    # check_booking_status
    # ------------------------------------------------------------------

    async def check_booking_status(self) -> str:
        """Check the caller's most recent engagement status."""
        try:
            from wex_platform.agents.sms.status_messages import (
                STATUS_MESSAGES, DEFAULT_STATUS_MESSAGE, TOUR_CONFIRMED_NO_DATE, TERMINAL_STATUSES,
            )
            from wex_platform.domain.models import Engagement, Buyer
            from datetime import datetime, timezone, timedelta

            engagement = None

            # Try by engagement_id on call state first
            if self.call_state.engagement_id:
                result = await self.db.execute(
                    select(Engagement).where(Engagement.id == self.call_state.engagement_id)
                )
                engagement = result.scalar_one_or_none()

            # Fall back to phone lookup
            if not engagement:
                phone = self.call_state.caller_phone
                cutoff = datetime.now(timezone.utc) - timedelta(days=30)
                result = await self.db.execute(
                    select(Engagement)
                    .join(Buyer, Engagement.buyer_id == Buyer.id)
                    .where(
                        Buyer.phone == phone,
                        Engagement.created_at >= cutoff,
                        Engagement.status.notin_(TERMINAL_STATUSES),
                    )
                    .order_by(Engagement.updated_at.desc())
                )
                engagement = result.scalar_one_or_none()

            if not engagement:
                return "I don't see an active booking for your number. Want to start a new search?"

            status = engagement.status
            template = STATUS_MESSAGES.get(status)

            if not template:
                logger.warning("Unmapped engagement status (voice): %s", status)
                return DEFAULT_STATUS_MESSAGE

            if status == "tour_confirmed":
                if engagement.tour_scheduled_date:
                    date_str = engagement.tour_scheduled_date.strftime("%A %B %d at %I:%M %p")
                    return template.format(date=date_str)
                else:
                    return TOUR_CONFIRMED_NO_DATE

            return template

        except Exception as e:
            logger.error("check_booking_status failed: %s", e, exc_info=True)
            return "I'm having trouble looking that up right now. I'll check and text you the update."


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
