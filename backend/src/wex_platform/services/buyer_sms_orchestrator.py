"""Buyer SMS Orchestrator — coordinates the 6-agent pipeline.

Replaces the old BuyerSMSPipeline with a proper multi-agent flow:

1. Validate inbound (Gatekeeper)
2. Message Interpreter (deterministic regex)
3. Property Reference Resolution
4. Criteria Agent (LLM intent + action plan)
5. Tool execution (search via ClearingEngine, lookup stub)
6. Response Agent (LLM reply generation)
7. Gatekeeper -> Polisher retry loop (max 3) -> fallback
8. State update
"""

import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorResult:
    """Result from the orchestrator pipeline."""
    response: str = ""
    intent: str = "unknown"
    action: str | None = None
    criteria: dict | None = None
    phase: str = "INTAKE"
    error: str | None = None


# Facility requirement keywords — used to validate that the "requirements" field
# actually contains physical facility needs, not misclassified timing/duration text.
_FACILITY_KEYWORDS = frozenset({
    "office", "parking", "dock", "clear height", "climate", "sprinkler",
    "power", "drive-in", "loading", "hvac", "insulated", "heated",
    "cooled", "refrigerated", "freezer", "yard", "fenced", "security",
    "24/7", "rail", "ev charging", "ramp", "floor", "ceiling",
    "restroom", "bathroom", "ac ", "a/c", "air condition",
})

# Negative answers to the deal-breaker question — buyer explicitly said "no requirements"
_NO_REQUIREMENTS_PATTERNS = frozenset({
    "no", "nope", "nah", "none", "nothing", "n/a", "na", "not really",
    "no requirements", "no deal breakers", "no dealbreakers", "no deal-breakers",
    "nothing special", "i'm good", "im good", "all good", "that's it", "thats it",
    "no specifics", "no specific requirements", "no must haves", "no must-haves",
    "no thanks", "none needed",
})


def _requirements_resolved(value) -> bool:
    """Return True if requirements question has been answered (yes with specifics, or no)."""
    if not value or not isinstance(value, str):
        return False
    lower = value.lower().strip()
    # Explicit "no requirements" answer
    if lower in _NO_REQUIREMENTS_PATTERNS:
        return True
    # Actual facility keywords
    return any(kw in lower for kw in _FACILITY_KEYWORDS)


class BuyerSMSOrchestrator:
    """Orchestrates the full buyer SMS pipeline.

    Flow:
    1. Load SMSConversationState
    2. Run Message Interpreter (deterministic)
    3. Property Reference Resolution
    4. Compute criteria_readiness
    5. Run Criteria Agent (LLM)
    6. Tool execution (search, lookup stub)
    7. Run Response Agent (LLM)
    8. Gatekeeper -> Polisher retry loop (max 3) -> fallback
    9. Update state
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def process_message(
        self,
        phone: str,
        message: str,
        state,  # SMSConversationState
        conversation: object,  # BuyerConversation
        buyer: object,  # Buyer
        conversation_history: list[dict] | None = None,
        existing_criteria: dict | None = None,
    ) -> OrchestratorResult:
        """Run the full pipeline on an inbound buyer SMS."""
        from wex_platform.agents.sms.message_interpreter import interpret_message
        from wex_platform.agents.sms.criteria_agent import CriteriaAgent
        from wex_platform.agents.sms.response_agent import ResponseAgent
        from wex_platform.agents.sms.gatekeeper import validate_outbound, validate_inbound, trim_to_limit
        from wex_platform.agents.sms.polisher_agent import PolisherAgent
        from wex_platform.agents.sms.fallback_templates import get_fallback
        from wex_platform.agents.sms.context_builder import build_match_summaries

        phase = state.phase or "INTAKE"

        # == Validate inbound ==
        gate = validate_inbound(message)
        if not gate.ok:
            logger.warning("Inbound rejected from %s: %s", phone, gate.violation)
            return OrchestratorResult(error=f"Inbound rejected: {gate.violation}")

        # == 1. Message Interpreter (deterministic) ==
        interpretation = interpret_message(message)

        # == 2. Property Reference Resolution ==
        resolved_property_id = None
        presented_ids = state.presented_match_ids or []

        if interpretation.positional_references and presented_ids:
            try:
                ref_num = int(interpretation.positional_references[0])
                if 1 <= ref_num <= len(presented_ids):
                    resolved_property_id = presented_ids[ref_num - 1]
            except (ValueError, IndexError):
                pass

        # If already focused on a property, keep it unless new reference
        if not resolved_property_id and state.focused_match_id:
            resolved_property_id = state.focused_match_id

        # ── Re-present check ──
        re_present_pattern = re.compile(r'\b(?:other|options|what else|show me|back|alternatives|list|all)\b', re.IGNORECASE)
        if re_present_pattern.search(message) and phase in ("PROPERTY_FOCUSED", "PRESENTING") and presented_ids:
            # Buyer wants to re-see options
            match_summaries_check = state.criteria_snapshot.get("match_summaries") if state.criteria_snapshot else None
            if match_summaries_check:
                from wex_platform.agents.sms.contracts import CriteriaPlan
                plan = CriteriaPlan(
                    intent="facility_info",
                    action=None,
                    response_hint="Here are the matches again. Summarize the top options briefly (city and rate only, never mention property sqft).",
                )
                phase = "PRESENTING"
                state.focused_match_id = None  # Unfocus

                # Skip criteria agent + tool execution, jump to response agent
                # Store match summaries and proceed
                presented_match_summaries = match_summaries_check

                # == Response Agent (LLM) ==
                response_agent = ResponseAgent()
                is_first = (state.turn or 0) <= 1

                response_text = await response_agent.generate_reply(
                    message=message,
                    intent=plan.intent,
                    phase=phase,
                    criteria=None,
                    property_data=None,
                    match_summaries=presented_match_summaries,
                    conversation_history=conversation_history,
                    response_hint=plan.response_hint,
                    is_first_message=is_first,
                )

                # == Gatekeeper -> Polisher retry loop ==
                polisher = PolisherAgent()
                max_len = 800 if is_first else 480

                for attempt in range(3):
                    gate = validate_outbound(response_text, is_first_message=is_first)
                    if gate.ok:
                        break
                    if attempt < 2:
                        polish_result = await polisher.polish(response_text, gate.hint, is_first_message=is_first)
                        response_text = polish_result.polished_text if polish_result.ok else response_text
                    else:
                        response_text = get_fallback(plan.intent, count=len(presented_match_summaries))
                        response_text = trim_to_limit(response_text, is_first_message=is_first)

                # == Update state ==
                state.phase = phase
                return OrchestratorResult(
                    response=response_text,
                    intent=plan.intent,
                    action=plan.action,
                    criteria=None,
                    phase=phase,
                )

        # == 3. Build match summaries from state ==
        presented_match_summaries = None
        if state.criteria_snapshot and state.criteria_snapshot.get("match_summaries"):
            presented_match_summaries = state.criteria_snapshot["match_summaries"]

        # == 4. Criteria Agent (LLM) ==
        criteria_agent = CriteriaAgent()
        plan = await criteria_agent.plan(
            message=message,
            interpretation=interpretation,
            conversation_history=conversation_history,
            phase=phase,
            existing_criteria=existing_criteria,
            resolved_property_id=resolved_property_id,
            presented_match_summaries=presented_match_summaries,
        )

        # == Deterministic override: if interpreter found search data, it's not a greeting ==
        has_search_data = (
            interpretation.cities or interpretation.states
            or interpretation.sqft or interpretation.features
            or interpretation.action_keywords
        )
        if plan.intent == "greeting" and has_search_data:
            logger.info("Override: criteria agent said greeting but interpreter found search data")
            plan.intent = "new_search"
            if not plan.action and (interpretation.cities or interpretation.sqft):
                plan.action = "search"
            # Ensure criteria includes interpreter findings
            if not plan.criteria:
                plan.criteria = {}
            if interpretation.cities and not plan.criteria.get("location"):
                loc = interpretation.cities[0]
                if interpretation.states:
                    loc = f"{loc}, {interpretation.states[0]}"
                plan.criteria["location"] = loc
            if interpretation.sqft and not plan.criteria.get("sqft"):
                plan.criteria["sqft"] = interpretation.sqft

        # == 5. Compute criteria readiness ==
        merged_criteria = {**(existing_criteria or {}), **(plan.criteria or {})}
        # Remove None values
        merged_criteria = {k: v for k, v in merged_criteria.items() if v is not None}

        # Deterministic: if buyer says "no" to deal-breakers, mark requirements as answered
        msg_lower = message.strip().lower().rstrip(".!?")
        if msg_lower in _NO_REQUIREMENTS_PATTERNS and not _requirements_resolved(merged_criteria.get("requirements")):
            merged_criteria["requirements"] = "none"

        logger.info(
            "ORCHESTRATOR DEBUG | turn=%s phone=%s | existing_criteria=%s | plan.criteria=%s | merged_criteria=%s | plan.intent=%s plan.action=%s plan.response_hint=%s",
            state.turn, phone, existing_criteria, plan.criteria, merged_criteria,
            plan.intent, plan.action, plan.response_hint,
        )

        readiness = 0.0
        if merged_criteria.get("location"):
            readiness += 0.3
        if merged_criteria.get("sqft"):
            readiness += 0.25
        if merged_criteria.get("use_type"):
            readiness += 0.25
        extras = {"features", "goods_type", "timing", "duration", "requirements"}
        for key in extras:
            if key == "requirements":
                # Only count if it has actual facility keywords, not misclassified timing
                if _requirements_resolved(merged_criteria.get(key)):
                    readiness += 0.1
            elif merged_criteria.get(key):
                readiness += 0.1
        readiness = min(readiness, 1.0)
        state.criteria_readiness = readiness

        # Determine what qualifying questions remain
        missing_fields = []
        if not merged_criteria.get("location"):
            missing_fields.append("city")
        if not merged_criteria.get("sqft"):
            missing_fields.append("size")
        if not merged_criteria.get("use_type"):
            missing_fields.append("what they'll use it for (storage, fulfillment, etc.)")

        # Extra qualifying questions — REQUIRED before presenting matches.
        # Only count fields the buyer explicitly provided (existing_criteria from prior turns),
        # not what the LLM inferred this turn, to ensure we always ask.
        prior = existing_criteria or {}
        extra_missing = []
        if not _requirements_resolved(prior.get("requirements")) and not _requirements_resolved(merged_criteria.get("requirements")):
            extra_missing.append("deal-breakers — ask specifically: 'Do you need office space or parking? Any other must-haves like dock doors, climate control, or 24/7 access?'")
        if not prior.get("timing") and not merged_criteria.get("timing"):
            extra_missing.append("when they need it")
        if not prior.get("duration") and not merged_criteria.get("duration"):
            extra_missing.append("how many months they need the space")

        logger.info(
            "ORCHESTRATOR DEBUG | readiness=%.2f has_core=%s | missing_fields=%s | extra_missing=%s | criteria_snapshot=%s",
            readiness, readiness >= 0.8, missing_fields, extra_missing, state.criteria_snapshot,
        )

        # Build response_hint for missing core fields
        if plan.intent in ("new_search", "refine_search") and missing_fields:
            if not plan.response_hint:
                plan.response_hint = f"Still need: {', '.join(missing_fields)}. Ask naturally in one message."

        # Forward clarification from criteria agent
        if plan.clarification_needed and not plan.response_hint:
            plan.response_hint = plan.clarification_needed

        # ── Backward phase movement ──
        # If buyer is in PRESENTING/PROPERTY_FOCUSED but gives new criteria → re-search
        if plan.intent == "refine_search" and phase in ("PRESENTING", "PROPERTY_FOCUSED"):
            if readiness >= 0.8:
                plan.action = "search"  # Force a re-search with updated criteria

        # == 6. Tool execution ==
        match_summaries = presented_match_summaries
        property_data = None

        # Search strategy: only search once ALL qualifying fields are collected
        # (location + sqft + use_type + timing + duration)
        has_core_fields = readiness >= 0.8
        all_qualifying_done = has_core_fields and not extra_missing

        # If we already searched and have cached matches, and buyer just answered
        # the last qualifying question, present the cached matches
        if (
            phase == "QUALIFYING"
            and presented_match_summaries
            and all_qualifying_done
            and plan.intent in ("provide_info", "new_search", "refine_search")
            and plan.action != "search"
        ):
            match_summaries = presented_match_summaries
            phase = "PRESENTING"
            plan.response_hint = f"All qualifying info collected. Found {len(match_summaries)} matches. Tell the buyer how many you found and briefly summarize the top options (city, rate, and monthly estimate — never mention property sqft)."

        elif plan.action == "search" and all_qualifying_done:
            # All questions answered — trigger ClearingEngine search
            match_summaries = await self._run_search(
                merged_criteria, phone, conversation, state
            )

            if match_summaries:
                phase = "PRESENTING"
                plan.response_hint = f"Found {len(match_summaries)} options. Tell the buyer how many you found and briefly summarize the top options (city, rate, and monthly estimate — never mention property sqft)."
            else:
                phase = "QUALIFYING"
                plan.response_hint = "Search ran but found no matches. Tell the buyer nothing exact right now, but you're expanding the search and will text them when something opens up."

        elif plan.action == "search" and has_core_fields and not all_qualifying_done:
            # Have core fields but still missing qualifying questions — don't search yet
            plan.action = None
            plan.response_hint = (
                f"Good, got the basics. Still need to know: {', '.join(extra_missing)}. "
                f"Ask the remaining questions naturally in one message."
            )

        elif plan.action == "lookup" and resolved_property_id:
            # Real detail fetcher (Phase 3)
            from wex_platform.services.sms_detail_fetcher import DetailFetcher

            detail_fetcher = DetailFetcher(self.db)

            topics_to_fetch = list(interpretation.topics) if interpretation.topics else []
            if plan.asked_fields:
                for af in plan.asked_fields:
                    if af not in topics_to_fetch:
                        topics_to_fetch.append(af)
            if topics_to_fetch:
                fetch_results = await detail_fetcher.fetch_by_topics(
                    property_id=resolved_property_id,
                    topics=topics_to_fetch,
                    state=state,
                )

                # Check if any need escalation
                needs_escalation = any(r.needs_escalation for r in fetch_results)
                answered = [r for r in fetch_results if r.status in ("FOUND", "CACHE_HIT")]

                if answered:
                    # Build property_data from answered results
                    property_data = {
                        "id": resolved_property_id,
                        "answers": {r.field_key: r.formatted for r in answered if r.formatted},
                        "source": "detail_fetcher",
                    }

                if needs_escalation:
                    # Escalate unanswered questions
                    from wex_platform.services.escalation_service import EscalationService
                    esc_service = EscalationService(self.db)

                    unanswered = [r for r in fetch_results if r.needs_escalation]
                    for result in unanswered:
                        esc_result = await esc_service.check_and_escalate(
                            property_id=resolved_property_id,
                            question_text=message,
                            field_key=result.field_key,
                            state=state,
                        )
                        if esc_result.get("escalated"):
                            phase = "AWAITING_ANSWER"
                        elif esc_result.get("answer"):
                            if not property_data:
                                property_data = {"id": resolved_property_id, "answers": {}, "source": "escalation_cache"}
                            if result.field_key:
                                property_data["answers"][result.field_key] = esc_result["answer"]
            else:
                # No specific topics detected, use stub for general lookup
                property_data = self._stub_lookup(resolved_property_id, presented_match_summaries)

            if resolved_property_id != state.focused_match_id:
                state.focused_match_id = resolved_property_id
            if phase != "AWAITING_ANSWER":
                phase = "PROPERTY_FOCUSED"

        elif plan.intent == "greeting":
            pass  # Stay in current phase

        elif plan.intent in ("new_search", "refine_search") and readiness < 0.6:
            phase = "QUALIFYING"

        # Deterministic override: when core fields are present but extras are missing,
        # ALWAYS tell the response agent to ask — overrides whatever the criteria agent LLM said
        logger.info(
            "ORCHESTRATOR DEBUG | SAFETY NET CHECK: has_core_fields=%s extra_missing=%s → fires=%s",
            has_core_fields, extra_missing, bool(has_core_fields and extra_missing),
        )
        if has_core_fields and extra_missing:
            phase = "QUALIFYING"
            plan.response_hint = (
                f"Got the basics. Still need: {', '.join(extra_missing)}. "
                f"Ask naturally in one short message."
            )

        # ── Phase-specific handling ──

        # COLLECTING_INFO: collect name/email for commitment flow
        # Only enter when buyer explicitly wants to commit OR we're already collecting.
        # Do NOT enter just because buyer provided their name in PRESENTING phase
        # (that's handled by the name-link block below).
        _in_commitment_flow = (
            phase == "COLLECTING_INFO"
            or (plan.action == "collect_info" and phase not in ("PRESENTING", "QUALIFYING"))
            or plan.action == "commitment_handoff"
        )
        if _in_commitment_flow:
            if interpretation.emails:
                state.buyer_email = interpretation.emails[0]

            # Determine what we still need
            if not state.renter_first_name:
                phase = "COLLECTING_INFO"
                plan.response_hint = "Ask for the buyer's name to proceed with booking"
            elif not state.buyer_email:
                phase = "COLLECTING_INFO"
                plan.response_hint = "Got their name, now ask for email to send over the details"
            else:
                # We have name + email -> proceed to commitment
                phase = "COMMITMENT"

        # COMMITMENT: create engagement + generate guarantee link
        if plan.action == "commitment_handoff" or (phase == "COMMITMENT" and state.renter_first_name and state.buyer_email):
            if resolved_property_id and not state.engagement_id:
                from wex_platform.services.engagement_bridge import EngagementBridge
                from wex_platform.services.sms_token_service import SmsTokenService

                bridge = EngagementBridge(self.db)
                booking_result = await bridge.initiate_booking(
                    property_id=resolved_property_id,
                    buyer_phone=phone,
                    buyer_name=f"{state.renter_first_name or ''} {state.renter_last_name or ''}".strip(),
                    buyer_email=state.buyer_email,
                    buyer_need_id=state.buyer_need_id,
                )

                if booking_result.get("engagement_id"):
                    state.engagement_id = booking_result["engagement_id"]

                    # Generate guarantee token
                    token_service = SmsTokenService(self.db)
                    token = await token_service.create_guarantee_token(
                        conversation_state_id=state.id,
                        buyer_phone=phone,
                        engagement_id=booking_result["engagement_id"],
                        prefilled_name=f"{state.renter_first_name or ''} {state.renter_last_name or ''}".strip(),
                        prefilled_email=state.buyer_email,
                    )
                    state.guarantee_link_token = token.token
                    phase = "GUARANTEE_PENDING"

                    from wex_platform.app.config import get_settings
                    settings = get_settings()
                    plan.response_hint = f"Send guarantee link: {settings.frontend_url}/sms/guarantee/{token.token}"

        # TOUR_SCHEDULING: extract date/time, request tour
        if plan.action == "schedule_tour" and state.engagement_id:
            from wex_platform.services.engagement_bridge import EngagementBridge
            bridge = EngagementBridge(self.db)

            tour_result = await bridge.request_tour(
                engagement_id=state.engagement_id,
                notes=message,
            )

            if tour_result.get("ok"):
                phase = "TOUR_SCHEDULING"
                plan.response_hint = "Tour request sent to supplier. Confirm with buyer."

        # == Name extraction (opportunistic — always extract if present) ==
        if plan.extracted_name and plan.extracted_name.get("first_name"):
            state.renter_first_name = plan.extracted_name["first_name"]
            state.renter_last_name = plan.extracted_name.get("last_name")
            state.name_status = "full" if state.renter_last_name else "first_only"

        # Also try interpreter names as fallback
        if not state.renter_first_name and interpretation.names:
            parts = interpretation.names[0].split(None, 1)
            state.renter_first_name = parts[0]
            state.renter_last_name = parts[1] if len(parts) > 1 else None
            state.name_status = "full" if state.renter_last_name else "first_only"

        # == Name capture decision (ask once, never re-ask) ==
        name_capture_prompt = None
        if (
            state.name_status in ("unknown", None, "")
            and state.name_requested_at_turn is None
            and phase == "PRESENTING"
        ):
            # Ask for name when presenting matches — natural moment
            state.name_requested_at_turn = state.turn
            name_capture_prompt = "What's your name by the way?"

        # == Name just captured → send search link with best match highlight ==
        # Only fires on the EXACT turn after name was requested (one-shot)
        if (
            state.renter_first_name
            and state.name_requested_at_turn is not None
            and (state.turn or 0) == state.name_requested_at_turn + 1
            and state.search_session_token
        ):
            from wex_platform.app.config import get_settings
            settings = get_settings()
            search_link = f"{settings.frontend_url}/buyer/options?session={state.search_session_token}"

            # Build best match context — pass raw data, let response agent handle tone
            # (the normal gatekeeper→polisher pipeline enforces limits at 800 for URL messages)
            best_match_ctx = ""
            if match_summaries:
                best = match_summaries[0]
                city = best.get("city", "")
                rate = best.get("rate", "")
                monthly = best.get("monthly")
                reasoning = best.get("reasoning", "")
                description = best.get("description", "")
                highlight = reasoning[:200] or description[:200] or ""
                if city:
                    rate_str = f"${rate}/sqft" if rate else ""
                    monthly_str = f", about ${monthly:,}/mo" if monthly else ""
                    best_match_ctx = f" Best match is in {city} at {rate_str}{monthly_str}."
                    if highlight:
                        best_match_ctx += f" Why it's a good fit: {highlight}"

            plan.response_hint = (
                f"Buyer just gave their name. Acknowledge warmly using their name."
                f"{best_match_ctx} "
                f"Then share this link to review all options: {search_link} . "
                f"Weave the best match info into a brief natural sentence in your broker voice. "
                f"Do NOT copy the 'why it's a good fit' text verbatim, paraphrase it naturally. "
                f"Do NOT list all matches again. Do NOT push for tours or commitment."
            )

        # == 7. Response Agent (LLM) ==
        response_agent = ResponseAgent()
        is_first = (state.turn or 0) <= 1

        response_text = await response_agent.generate_reply(
            message=message,
            intent=plan.intent,
            phase=phase,
            criteria=merged_criteria if merged_criteria else None,
            property_data=property_data,
            match_summaries=match_summaries,
            conversation_history=conversation_history,
            response_hint=plan.response_hint,
            is_first_message=is_first,
            name_capture_prompt=name_capture_prompt,
            renter_name=state.renter_first_name,
        )

        # == 8. Gatekeeper -> Polisher retry loop ==
        polisher = PolisherAgent()
        has_url = "http://" in response_text or "https://" in response_text
        max_len = 800 if (is_first or has_url) else 480
        context = None
        if plan.intent == "commitment":
            context = "commitment"
        elif plan.intent == "tour_request":
            context = "tour"
        elif phase == "AWAITING_ANSWER":
            context = "awaiting_answer"

        for attempt in range(3):
            gate = validate_outbound(response_text, is_first_message=is_first, context=context)
            if gate.ok:
                break

            logger.warning("Gatekeeper rejected (attempt %d): %s", attempt + 1, gate.hint)

            if attempt < 2:
                polish_result = await polisher.polish(response_text, gate.hint, is_first_message=is_first)
                response_text = polish_result.polished_text if polish_result.ok else response_text
            else:
                # Fallback template
                location = merged_criteria.get("location") if merged_criteria else None
                response_text = get_fallback(
                    plan.intent,
                    location=location,
                    count=len(match_summaries) if match_summaries else 0,
                )
                response_text = trim_to_limit(response_text, is_first_message=is_first)
                logger.warning("Using fallback template after 3 gatekeeper rejections")

        # == 9. Update state ==
        state.phase = phase
        if merged_criteria:
            snapshot = dict(state.criteria_snapshot or {})
            snapshot.update(merged_criteria)
            if match_summaries:
                snapshot["match_summaries"] = match_summaries
            state.criteria_snapshot = snapshot

        # ── Compute next re-engagement time ──
        from wex_platform.services.buyer_notification_service import STALL_RULES
        tiers = STALL_RULES.get(phase)
        if tiers:
            delay_hours, _ = tiers[0]  # Use the first tier's delay
            state.next_reengagement_at = datetime.now(timezone.utc) + timedelta(hours=delay_hours)

        return OrchestratorResult(
            response=response_text,
            intent=plan.intent,
            action=plan.action,
            criteria=merged_criteria if merged_criteria else None,
            phase=phase,
        )

    async def _run_search(
        self, criteria: dict, phone: str, conversation, state
    ) -> list[dict] | None:
        """Run ClearingEngine search and return match summaries."""
        try:
            from wex_platform.services.buyer_conversation_service import BuyerConversationService
            from wex_platform.services.clearing_engine import ClearingEngine

            conv_service = BuyerConversationService(self.db)
            buyer_need = await conv_service.create_buyer_need_from_criteria(
                criteria=criteria,
                phone=phone,
                conversation_id=conversation.id,
            )

            if not buyer_need:
                return None

            # Geocode city/state to lat/lng for better pre-filter matching
            if buyer_need.city and not buyer_need.lat:
                try:
                    from wex_platform.services.geocoding_service import geocode_location
                    location_str = f"{buyer_need.city}, {buyer_need.state}" if buyer_need.state else buyer_need.city
                    geo_result = await geocode_location(location_str)
                    if geo_result and geo_result.lat and geo_result.lng:
                        buyer_need.lat = geo_result.lat
                        buyer_need.lng = geo_result.lng
                        await self.db.flush()
                except Exception as geo_err:
                    logger.warning("Geocoding failed for SMS search: %s", geo_err)

            state.buyer_need_id = buyer_need.id

            clearing_engine = ClearingEngine()
            result = await clearing_engine.run_clearing(
                buyer_need_id=buyer_need.id, db=self.db
            )

            # run_clearing returns {"tier1_matches": [...], "tier2_matches": [...], ...}
            tier1 = result.get("tier1_matches", []) if isinstance(result, dict) else result
            if not tier1:
                return None

            # Build summaries with buyer's requested sqft for monthly estimate
            from wex_platform.agents.sms.context_builder import build_match_summaries
            buyer_sqft = criteria.get("sqft") if criteria else None
            summaries = build_match_summaries(tier1, buyer_sqft=buyer_sqft)

            # Store presented IDs
            state.presented_match_ids = [s["id"] for s in summaries if s.get("id")]

            # Create a SearchSession so buyer can view matches on web
            import uuid as _uuid
            from wex_platform.domain.models import SearchSession
            from wex_platform.app.config import get_settings

            settings = get_settings()
            token = secrets.token_urlsafe(32)
            expires = datetime.now(timezone.utc) + timedelta(hours=48)

            # Build buyer-safe results matching web format
            tier1_safe = []
            for m in tier1:
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
                id=str(_uuid.uuid4()),
                token=token,
                requirements=criteria,
                results={"tier1": tier1_safe, "tier2": []},
                buyer_need_id=buyer_need.id,
                status="active",
                expires_at=expires,
            )
            self.db.add(session_record)
            state.search_session_token = token

            return summaries

        except Exception as e:
            logger.error("Search failed: %s", e, exc_info=True)
            return None

    def _stub_lookup(
        self, property_id: str, match_summaries: list[dict] | None
    ) -> dict | None:
        """Phase 2 stub: look up property from match summaries."""
        if not match_summaries:
            return None
        for summary in match_summaries:
            if summary.get("id") == property_id:
                return {
                    "id": property_id,
                    "city": summary.get("city", ""),
                    "sqft": summary.get("sqft"),
                    "rate": summary.get("rate"),
                    "address": summary.get("address", ""),
                    "source": "match_summary",
                }
        return None
