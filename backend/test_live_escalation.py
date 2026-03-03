"""
Live E2E test: Seeds test data and triggers an escalation email.
Run while the server is running (uses same DB).

Usage: conda run -n wex python test_live_escalation.py
"""
import asyncio
import uuid
import sys
import os

# Add backend/src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from datetime import datetime, timezone, timedelta


async def main():
    # Import after path setup
    from sqlalchemy import select
    from wex_platform.infra.database import async_session
    from wex_platform.domain.models import Property, Warehouse
    from wex_platform.domain.sms_models import SMSConversationState, EscalationThread
    from wex_platform.services.email_service import send_escalation_email
    from wex_platform.app.config import get_settings
    settings = get_settings()

    print("=" * 60)
    print("LIVE ESCALATION EMAIL TEST")
    print("=" * 60)
    print(f"SendGrid from: {settings.supply_alert_from}")
    print(f"SendGrid to:   {settings.supply_alert_to}")
    print(f"Frontend URL:  {settings.frontend_url}")
    print()

    async with async_session() as db:
        # 1. Find an existing property to use (more realistic)
        result = await db.execute(
            select(Property).limit(1)
        )
        prop = result.scalar_one_or_none()

        if not prop:
            # Try Warehouse table as fallback
            result = await db.execute(select(Warehouse).limit(1))
            wh = result.scalar_one_or_none()
            if wh:
                prop_address = f"{wh.address}, {wh.city}, {wh.state}"
                prop_id = wh.id
            else:
                # No data at all — create a fake property ID
                prop_id = str(uuid.uuid4())
                prop_address = "123 Test Warehouse Blvd, Dallas, TX"
        else:
            prop_address = f"{prop.address or '123 Main St'}, {prop.city or 'Dallas'}, {prop.state or 'TX'}"
            prop_id = prop.id

        print(f"Using property: {prop_address}")
        print(f"Property ID:    {prop_id}")

        # 2. Find any existing SMS conversation state (optional, for context)
        result = await db.execute(
            select(SMSConversationState).limit(1)
        )
        state = result.scalar_one_or_none()
        state_id = state.id if state else str(uuid.uuid4())
        buyer_name = (state.renter_first_name if state else None) or "Test Buyer"
        buyer_phone = (state.phone if state else None) or "+12025551234"
        print(f"Using state ID: {state_id} (buyer: {buyer_name}, phone: {buyer_phone})")

        # 3. Create an escalation thread
        thread_id = str(uuid.uuid4())
        thread = EscalationThread(
            id=thread_id,
            conversation_state_id=state_id,
            property_id=prop_id,
            question_text="Does this warehouse have EV charging stations?",
            field_key=None,
            status="pending",
            source_type="sms",
            sla_deadline_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        db.add(thread)
        await db.commit()
        print(f"Created escalation thread: {thread_id}")

        # 4. Build email data and send
        reply_tool_url = f"{settings.frontend_url}/api/sms/internal/form/{thread_id}?token={settings.admin_password}"

        # Simulated recent conversation
        recent_messages = [
            {"role": "assistant", "content": "Hey! I found a few warehouse options near Chicago. Want to hear about them?"},
            {"role": "user", "content": "Yes, tell me about option 1"},
            {"role": "assistant", "content": f"Option 1 is at {prop_address}. It's 10,000 sqft with dock-high loading."},
            {"role": "user", "content": "Does it have EV charging stations?"},
        ]

        email_data = {
            "property_address": prop_address,
            "property_id": prop_id,
            "question_text": "Does this warehouse have EV charging stations?",
            "source_type": "sms",
            "buyer_phone": buyer_phone,
            "buyer_name": buyer_name,
            "thread_id": thread_id,
            "reply_tool_url": reply_tool_url,
            "recent_messages": recent_messages,
            "field_key": None,
        }

        print()
        print("Sending escalation email...")
        print(f"  Reply Tool URL: {reply_tool_url}")
        print()

        success = await send_escalation_email(email_data)

        if success:
            print("SUCCESS! Email sent.")
            print(f"Check inbox at: {settings.supply_alert_to}")
            print(f"Reply tool link in email points to: {reply_tool_url}")
        else:
            print("FAILED to send email. Check SendGrid config and logs above.")

    print()
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
