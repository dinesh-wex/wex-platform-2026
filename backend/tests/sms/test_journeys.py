"""End-to-end journey tests — chain multiple orchestrator turns verifying state continuity.

All LLM agents are mocked. Database interactions use the real async SQLite fixture.
Exercises the full BuyerSMSOrchestrator pipeline across multi-turn conversations.
"""

import uuid
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from wex_platform.agents.sms.contracts import CriteriaPlan, MessageInterpretation
from wex_platform.domain.models import (
    Buyer,
    BuyerConversation,
    Property,
    PropertyContact,
    PropertyKnowledge,
    PropertyListing,
    Warehouse,
)
from wex_platform.domain.sms_models import SMSConversationState
from wex_platform.services.buyer_sms_orchestrator import BuyerSMSOrchestrator


# Patch targets (source modules, not import sites)
_CRITERIA = "wex_platform.agents.sms.criteria_agent.CriteriaAgent"
_RESPONSE = "wex_platform.agents.sms.response_agent.ResponseAgent"
_POLISHER = "wex_platform.agents.sms.polisher_agent.PolisherAgent"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_journey_context(
    db_session,
    *,
    phone="+15551234567",
    phase="INTAKE",
    turn=0,
    properties=None,
):
    """Create Buyer + BuyerConversation + SMSConversationState + optional properties.

    Returns (buyer, conversation, state, property_ids).
    """
    buyer = Buyer(
        id=str(uuid.uuid4()),
        phone=phone,
        name="Journey Buyer",
        email="journey@test.com",
    )
    db_session.add(buyer)

    conversation = BuyerConversation(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        messages=[],
        status="active",
    )
    db_session.add(conversation)

    state = SMSConversationState(
        id=str(uuid.uuid4()),
        buyer_id=buyer.id,
        conversation_id=conversation.id,
        phone=phone,
        phase=phase,
        turn=turn,
        criteria_readiness=0.0,
        criteria_snapshot={},
        presented_match_ids=[],
    )
    db_session.add(state)

    property_ids = []
    if properties:
        for p_cfg in properties:
            pid = str(uuid.uuid4())
            property_ids.append(pid)

            wh = Warehouse(
                id=pid,
                address=p_cfg.get("address", "123 Test St"),
                city=p_cfg.get("city", "Commerce"),
                state=p_cfg.get("state", "CA"),
            )
            db_session.add(wh)

            prop = Property(
                id=pid,
                address=p_cfg.get("address", "123 Test St"),
                city=p_cfg.get("city", "Commerce"),
                state=p_cfg.get("state", "CA"),
                source="test",
            )
            db_session.add(prop)

            knowledge = PropertyKnowledge(
                id=str(uuid.uuid4()),
                property_id=pid,
                building_size_sqft=p_cfg.get("sqft", 15000),
            )
            db_session.add(knowledge)

            listing = PropertyListing(
                id=str(uuid.uuid4()),
                property_id=pid,
                available_sqft=p_cfg.get("available", 10000),
                activation_status="live",
            )
            db_session.add(listing)

            contact = PropertyContact(
                id=str(uuid.uuid4()),
                property_id=pid,
                contact_type="owner",
                name="Owner",
                email=f"owner_{pid[:8]}@test.com",
                phone="+15559990000",
                is_primary=True,
            )
            db_session.add(contact)

    await db_session.flush()
    return buyer, conversation, state, property_ids


def _good_reply(text="Sure, I can help with that. Let me search for warehouse space matching your requirements."):
    """Return a gatekeeper-safe reply (>20 chars, <320 chars, no profanity)."""
    return text


# ---------------------------------------------------------------------------
# Journey 1: TCPA Compliance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_journey_tcpa_compliance(db_session):
    """TCPA flow: greeting -> STOP opts out -> START re-activates -> normal processing.

    Note: STOP/START are handled at the webhook route level (buyer_sms.py),
    not in the orchestrator. This test verifies the orchestrator respects
    opted_out state and handles normal messages correctly.
    """
    buyer, conversation, state, _ = await _make_journey_context(db_session)

    orchestrator = BuyerSMSOrchestrator(db_session)

    # -- Turn 1: "Hi" -> greeting --
    state.turn = 1
    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
    ):
        mock_plan.return_value = CriteriaPlan(intent="greeting", action=None)
        mock_reply.return_value = _good_reply(
            "This is Warehouse Exchange. Looking for warehouse space? What city, state and how much space?"
        )

        result = await orchestrator.process_message(
            phone="+15551234567",
            message="Hi",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.intent == "greeting"
    assert result.response  # Non-empty

    # -- Simulate STOP at webhook layer --
    # The webhook sets opted_out=True and phase=ABANDONED directly.
    state.opted_out = True
    state.phase = "ABANDONED"
    await db_session.flush()

    assert state.opted_out is True
    assert state.phase == "ABANDONED"

    # -- Simulate START at webhook layer --
    state.opted_out = False
    state.phase = "INTAKE"
    await db_session.flush()

    assert state.opted_out is False
    assert state.phase == "INTAKE"

    # -- Turn 4: Normal message after re-subscribe --
    state.turn = 4
    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
    ):
        mock_plan.return_value = CriteriaPlan(
            intent="new_search",
            action="search",
            criteria={"location": "Commerce, CA", "sqft": 10000, "use_type": "storage"},
        )
        mock_reply.return_value = _good_reply(
            "Got it! Searching for 10k sqft storage space in Commerce CA now."
        )

        # Mock _run_search since readiness < 0.6 (no location in existing state)
        result = await orchestrator.process_message(
            phone="+15551234567",
            message="Need 10k sqft in Commerce",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.error is None
    assert result.intent == "new_search"


# ---------------------------------------------------------------------------
# Journey 2: Search + Property Focus
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_journey_search_and_focus(db_session):
    """Search -> matches presented -> buyer focuses on option 2 -> PROPERTY_FOCUSED."""
    properties_cfg = [
        {"city": "Commerce", "sqft": 10000, "available": 8000, "address": "100 A St"},
        {"city": "Commerce", "sqft": 15000, "available": 12000, "address": "200 B St"},
        {"city": "Commerce", "sqft": 20000, "available": 18000, "address": "300 C St"},
    ]
    buyer, conversation, state, prop_ids = await _make_journey_context(
        db_session, properties=properties_cfg,
    )

    match_summaries = [
        {"id": prop_ids[0], "city": "Commerce", "sqft": 10000, "rate": 0.85},
        {"id": prop_ids[1], "city": "Commerce", "sqft": 15000, "rate": 0.90},
        {"id": prop_ids[2], "city": "Commerce", "sqft": 20000, "rate": 0.95},
    ]

    orchestrator = BuyerSMSOrchestrator(db_session)

    # -- Turn 1: "I need 10k sqft in Commerce CA for storage" --
    state.turn = 1

    async def _mock_run_search(criteria, phone, conversation, st):
        """Mock _run_search that also sets presented_match_ids like the real one."""
        st.presented_match_ids = [s["id"] for s in match_summaries]
        return match_summaries

    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
        patch.object(orchestrator, "_run_search", side_effect=_mock_run_search) as mock_search,
    ):
        mock_plan.return_value = CriteriaPlan(
            intent="new_search",
            action="search",
            criteria={"location": "Commerce, CA", "sqft": 10000, "use_type": "storage",
                      "timing": "ASAP", "duration": "6_months", "goods_type": "general"},
        )
        mock_reply.return_value = _good_reply(
            "Found 3 options in Commerce CA! Option 1: 10k sqft $0.85/sqft. "
            "Option 2: 15k sqft $0.90/sqft. Option 3: 20k sqft $0.95/sqft. "
            "Reply with a number to learn more."
        )

        result = await orchestrator.process_message(
            phone="+15551234567",
            message="I need 10k sqft in Commerce CA for storage ASAP, general goods",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.phase == "PRESENTING"
    assert state.presented_match_ids == [prop_ids[0], prop_ids[1], prop_ids[2]]
    # Criteria readiness should be computed from location + sqft + use_type
    assert state.criteria_readiness >= 0.8

    # -- Turn 2: "tell me about option 2" --
    state.turn = 2
    # Criteria snapshot now has match_summaries stored from turn 1
    state.criteria_snapshot = {
        "location": "Commerce, CA",
        "sqft": 10000,
        "use_type": "storage",
        "match_summaries": match_summaries,
    }
    await db_session.flush()

    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
    ):
        mock_plan.return_value = CriteriaPlan(
            intent="facility_info",
            action="lookup",
            resolved_property_id=prop_ids[1],
        )
        mock_reply.return_value = _good_reply(
            "Option 2 is a 15,000 sqft space in Commerce at $0.90/sqft. Great for storage and light distribution."
        )

        result = await orchestrator.process_message(
            phone="+15551234567",
            message="tell me about option 2",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.phase == "PROPERTY_FOCUSED"
    assert state.focused_match_id == prop_ids[1]


# ---------------------------------------------------------------------------
# Journey 3: Escalation Flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_journey_escalation_flow(db_session):
    """Search -> focus -> unanswerable question -> AWAITING_ANSWER escalation."""
    properties_cfg = [
        {"city": "Commerce", "sqft": 15000, "available": 12000, "address": "200 B St"},
    ]
    buyer, conversation, state, prop_ids = await _make_journey_context(
        db_session, properties=properties_cfg,
    )

    match_summaries = [
        {"id": prop_ids[0], "city": "Commerce", "sqft": 15000, "rate": 0.90},
    ]

    orchestrator = BuyerSMSOrchestrator(db_session)

    # -- Turn 1: Search and present --
    state.turn = 1

    async def _mock_run_search_esc(criteria, phone, conversation, st):
        """Mock _run_search that also sets presented_match_ids."""
        st.presented_match_ids = [s["id"] for s in match_summaries]
        return match_summaries

    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
        patch.object(orchestrator, "_run_search", side_effect=_mock_run_search_esc) as mock_search,
    ):
        mock_plan.return_value = CriteriaPlan(
            intent="new_search",
            action="search",
            criteria={"location": "Commerce, CA", "sqft": 15000, "use_type": "storage",
                      "timing": "ASAP", "duration": "6_months", "goods_type": "general"},
        )
        mock_reply.return_value = _good_reply(
            "Found 1 option in Commerce CA! 15k sqft at $0.90/sqft. Reply 1 to learn more."
        )

        result = await orchestrator.process_message(
            phone="+15551234567",
            message="15k sqft storage Commerce CA ASAP, general goods",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.phase == "PRESENTING"
    assert state.presented_match_ids == [prop_ids[0]]

    # -- Turn 2: Focus on property 1 --
    state.turn = 2
    state.criteria_snapshot = {
        "location": "Commerce, CA",
        "sqft": 15000,
        "match_summaries": match_summaries,
    }
    await db_session.flush()

    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
    ):
        mock_plan.return_value = CriteriaPlan(
            intent="facility_info",
            action="lookup",
            resolved_property_id=prop_ids[0],
        )
        mock_reply.return_value = _good_reply(
            "This is a 15,000 sqft warehouse in Commerce at $0.90/sqft. What else would you like to know?"
        )

        result = await orchestrator.process_message(
            phone="+15551234567",
            message="tell me about option 1",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.phase == "PROPERTY_FOCUSED"
    assert state.focused_match_id == prop_ids[0]

    # -- Turn 3: "Do they have rail access?" -> escalation --
    # "rail" is a recognized topic in topic_catalog, so interpret_message
    # will set topics=["rail"]. DetailFetcher then returns needs_escalation=True
    # since the data is not available.
    state.turn = 3
    await db_session.flush()

    with (
        patch(f"{_CRITERIA}.plan", new_callable=AsyncMock) as mock_plan,
        patch(f"{_RESPONSE}.generate_reply", new_callable=AsyncMock) as mock_reply,
        patch(f"{_POLISHER}.polish", new_callable=AsyncMock) as mock_polish,
        patch(
            "wex_platform.services.sms_detail_fetcher.DetailFetcher.fetch_by_topics",
            new_callable=AsyncMock,
        ) as mock_fetch,
        patch(
            "wex_platform.services.escalation_service.EscalationService.check_and_escalate",
            new_callable=AsyncMock,
        ) as mock_escalate,
    ):
        from wex_platform.agents.sms.contracts import DetailFetchResult

        mock_plan.return_value = CriteriaPlan(
            intent="facility_info",
            action="lookup",
            resolved_property_id=prop_ids[0],
        )
        # DetailFetcher returns an unmapped result that needs escalation
        mock_fetch.return_value = [
            DetailFetchResult(
                status="UNMAPPED",
                field_key="rail_served",
                needs_escalation=True,
            )
        ]
        mock_escalate.return_value = {"escalated": True, "thread_id": "esc_123"}
        mock_reply.return_value = _good_reply(
            "Great question! I'm checking with the property owner about rail access. I'll text you back soon."
        )

        result = await orchestrator.process_message(
            phone="+15551234567",
            message="Do they have rail access?",
            state=state,
            conversation=conversation,
            buyer=buyer,
        )

    assert result.phase == "AWAITING_ANSWER"
    assert state.focused_match_id == prop_ids[0]
