"""End-to-end test: SMS buyer journey through the orchestrator.

Simulates 5 turns of conversation:
1. "Hey" -> greeting
2. "Looking for warehouse in Carson CA" -> qualifying questions
3. "2000 sqft for furniture storage" -> asks timing/duration
4. "ASAP and 8 months" -> runs search, presents matches, asks name
5. "James" -> sends search link with best match highlight

Uses real DB (SQLite) and real LLM calls (Gemini).
Mocks only Aircall SMS sending.

Usage:
    conda run -n wex python test_sms_flow.py
"""

import asyncio
import os
import sys
import logging
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

# -- Path setup (same pattern as clear_sms_data.py) --
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

logging.basicConfig(
    level=logging.WARNING,  # Keep noise down; we print our own output
    format="%(levelname)s %(name)s: %(message)s",
)
# Bump orchestrator + agents to INFO so we can see what's happening
logging.getLogger("wex_platform.services.buyer_sms_orchestrator").setLevel(logging.INFO)
logging.getLogger("wex_platform.agents.sms").setLevel(logging.INFO)

TEST_PHONE = "+15551234567"

TURNS = [
    ("Hey", "greeting response"),
    ("Carson, CA", "city and state — should ask sqft/use_type"),
    ("5000 sqft for distribution", "sqft + use_type — should ask timing/duration/requirements"),
    ("July 1, about 12 months", "timing + duration — should ask requirements"),
    ("Need dock doors and an office", "requirements — should run search and present matches"),
    ("Peter", "name capture — should send search link"),
]


async def clear_test_data():
    """Delete any existing SMS data for the test phone number."""
    from sqlalchemy import text as sql_text
    from wex_platform.infra.database import async_session

    async with async_session() as db:
        # Find buyer
        row = await db.execute(
            sql_text("SELECT id FROM buyers WHERE phone = :p"), {"p": TEST_PHONE}
        )
        buyer = row.first()
        if not buyer:
            print("[cleanup] No existing data for test phone.\n")
            return

        bid = buyer[0]
        print(f"[cleanup] Found buyer {bid} -- clearing data...")

        # Get conversation IDs
        rows = await db.execute(
            sql_text("SELECT id FROM buyer_conversations WHERE buyer_id = :b"), {"b": bid}
        )
        conv_ids = [r[0] for r in rows.all()]

        # Get state IDs
        state_ids = []
        if conv_ids:
            ph = ",".join(f"'{c}'" for c in conv_ids)
            rows = await db.execute(sql_text(
                f"SELECT id FROM sms_conversation_states WHERE conversation_id IN ({ph})"
            ))
            state_ids = [r[0] for r in rows.all()]

        # Delete in FK order
        if state_ids:
            ph = ",".join(f"'{s}'" for s in state_ids)
            await db.execute(sql_text(f"DELETE FROM escalation_threads WHERE conversation_state_id IN ({ph})"))
            await db.execute(sql_text(f"DELETE FROM sms_signup_tokens WHERE conversation_state_id IN ({ph})"))

        if conv_ids:
            ph = ",".join(f"'{c}'" for c in conv_ids)
            await db.execute(sql_text(f"DELETE FROM sms_conversation_states WHERE conversation_id IN ({ph})"))

        # Search sessions via buyer_needs
        rows = await db.execute(
            sql_text("SELECT id FROM buyer_needs WHERE buyer_id = :b"), {"b": bid}
        )
        need_ids = [r[0] for r in rows.all()]
        if need_ids:
            ph = ",".join(f"'{n}'" for n in need_ids)
            await db.execute(sql_text(f"DELETE FROM search_sessions WHERE buyer_need_id IN ({ph})"))

        if conv_ids:
            ph = ",".join(f"'{c}'" for c in conv_ids)
            await db.execute(sql_text(f"DELETE FROM buyer_conversations WHERE id IN ({ph})"))

        await db.execute(sql_text("DELETE FROM buyer_needs WHERE buyer_id = :b"), {"b": bid})
        await db.execute(sql_text("DELETE FROM buyers WHERE id = :b"), {"b": bid})
        await db.commit()
        print("[cleanup] Done.\n")


async def simulate_turn(turn_num: int, message: str, description: str):
    """Simulate one inbound SMS turn, mimicking the webhook background task logic."""
    from wex_platform.infra.database import async_session
    from wex_platform.services.buyer_conversation_service import BuyerConversationService
    from wex_platform.services.buyer_sms_orchestrator import BuyerSMSOrchestrator
    from wex_platform.domain.models import BuyerNeed

    async with async_session() as db:
        conv_service = BuyerConversationService(db)
        conversation, buyer = await conv_service.get_or_create_conversation(TEST_PHONE)
        state = await conv_service.get_or_create_sms_state(
            buyer_id=buyer.id,
            conversation_id=conversation.id,
            phone=TEST_PHONE,
        )

        # Increment turn + timestamp (same as webhook does inline)
        state.turn = (state.turn or 0) + 1
        state.last_buyer_message_at = datetime.now(timezone.utc)

        # Record inbound
        await conv_service.add_message(conversation.id, "buyer", message)
        await db.flush()

        # Build conversation history
        conversation_history = conversation.messages or []

        # Reconstruct existing_criteria from linked BuyerNeed (same as webhook bg task)
        existing_criteria = None
        if conversation.buyer_need_id:
            existing_need = await db.get(BuyerNeed, conversation.buyer_need_id)
            if existing_need:
                existing_criteria = {
                    "location": f"{existing_need.city or ''}, {existing_need.state or ''}".strip(", "),
                    "sqft": existing_need.min_sqft,
                    "use_type": existing_need.use_type,
                }
                if existing_need.requirements:
                    existing_criteria.update({
                        k: v for k, v in existing_need.requirements.items()
                        if k in ("goods_type", "timing", "duration")
                    })

        # Also pull timing/duration from criteria_snapshot if present
        if state.criteria_snapshot:
            if not existing_criteria:
                existing_criteria = {}
            for key in ("timing", "duration"):
                if state.criteria_snapshot.get(key) and not existing_criteria.get(key):
                    existing_criteria[key] = state.criteria_snapshot[key]

        # Run orchestrator
        orchestrator = BuyerSMSOrchestrator(db)
        result = await orchestrator.process_message(
            phone=TEST_PHONE,
            message=message,
            state=state,
            conversation=conversation,
            buyer=buyer,
            conversation_history=conversation_history,
            existing_criteria=existing_criteria,
        )

        # Record outbound
        if result.response:
            await conv_service.add_message(conversation.id, "assistant", result.response)

        await db.commit()

    return result, state


async def main():
    # Ensure tables exist
    from wex_platform.infra.database import init_db
    await init_db()

    # Clean slate
    await clear_test_data()

    print("=" * 70)
    print("SMS BUYER JOURNEY -- END-TO-END TEST")
    print("=" * 70)

    results = []

    for i, (msg, desc) in enumerate(TURNS, start=1):
        print(f"\n{'─' * 70}")
        print(f"TURN {i}: {desc}")
        print(f"{'─' * 70}")
        print(f"  Buyer says: \"{msg}\"")
        print(f"  (calling orchestrator...)")

        result, state = await simulate_turn(i, msg, desc)

        if result.error:
            print(f"  ERROR: {result.error}")
            results.append((result, state))
            continue

        print(f"  Response:  {result.response}")
        print(f"  Intent:    {result.intent}")
        print(f"  Phase:     {result.phase}")
        print(f"  Action:    {result.action}")

        results.append((result, state))

    # ── Final turn verification (name-capture -> search-link) ──
    print(f"\n{'=' * 70}")
    print("FINAL TURN VERIFICATION (name-capture -> search-link)")
    print(f"{'=' * 70}")

    if len(results) >= 6:
        r_final, s_final = results[5]
        response = r_final.response

        # Check for tunnel / frontend URL in the response
        from wex_platform.app.config import get_settings
        settings = get_settings()
        has_link = settings.frontend_url in response or "/buyer/options" in response
        print(f"  Contains search link:       {'YES' if has_link else 'NO'}")

        # Check if response re-lists all options (look for numbered list pattern like "1.", "2.", "3.")
        import re
        numbered_items = re.findall(r'(?:^|\n)\s*\d+[.)]\s', response)
        re_lists_options = len(numbered_items) >= 3
        print(f"  Re-lists all options:       {'YES (BAD!)' if re_lists_options else 'NO (GOOD)'}")

        # Check name acknowledgment
        acknowledges_name = "peter" in response.lower()
        print(f"  Acknowledges name 'Peter':  {'YES' if acknowledges_name else 'NO'}")

        # Check phase
        phase_ok = r_final.phase == "PRESENTING"
        print(f"  Phase is PRESENTING:        {'YES' if phase_ok else f'NO ({r_final.phase})'}")

        # Summary
        print(f"\n  {'PASS' if (has_link and not re_lists_options and acknowledges_name and phase_ok) else 'FAIL'}")
    else:
        print("  Could not run final turn verification (earlier turns failed).")

    print()


if __name__ == "__main__":
    # Mock SMS sending so we don't hit Aircall
    with patch("wex_platform.services.sms_service.SMSService.send_buyer_sms", new_callable=AsyncMock):
        asyncio.run(main())
