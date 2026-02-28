"""Clear all SMS-related data from the database for testing.

Usage:
    conda run -n wex python clear_sms_data.py          # clear ALL SMS data
    conda run -n wex python clear_sms_data.py --phone "+1 415 766 1133"  # one number
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from sqlalchemy import text
from wex_platform.infra.database import async_session

# Delete order: children first (FK constraints)
SMS_TABLES = [
    "escalation_threads",
    "sms_signup_tokens",
    "sms_conversation_states",
    "search_sessions",
    "buyer_conversations",
    "buyer_needs",
    "buyers",
]


async def clear_all():
    async with async_session() as db:
        for table in SMS_TABLES:
            try:
                r = await db.execute(text(f"DELETE FROM {table}"))
                print(f"  {table}: {r.rowcount} rows deleted")
            except Exception as e:
                print(f"  {table}: skipped ({e})")
        await db.commit()
    print("\nDone.")


async def clear_phone(phone: str):
    async with async_session() as db:
        # Find buyer
        row = await db.execute(
            text("SELECT id FROM buyers WHERE phone = :p"), {"p": phone}
        )
        buyer = row.first()
        if not buyer:
            print(f"No buyer found with phone {phone}")
            return

        bid = buyer[0]
        print(f"Buyer: {bid}\n")

        # Get conversation IDs
        rows = await db.execute(
            text("SELECT id FROM buyer_conversations WHERE buyer_id = :b"), {"b": bid}
        )
        conv_ids = [r[0] for r in rows.all()]

        # Get state IDs (for escalation threads FK)
        state_ids = []
        if conv_ids:
            ph = ",".join(f"'{c}'" for c in conv_ids)
            rows = await db.execute(text(
                f"SELECT id FROM sms_conversation_states WHERE conversation_id IN ({ph})"
            ))
            state_ids = [r[0] for r in rows.all()]

        # Delete escalation threads via state IDs
        if state_ids:
            ph = ",".join(f"'{s}'" for s in state_ids)
            r = await db.execute(text(
                f"DELETE FROM escalation_threads WHERE conversation_state_id IN ({ph})"
            ))
            print(f"  escalation_threads: {r.rowcount}")

        # Delete states
        if conv_ids:
            ph = ",".join(f"'{c}'" for c in conv_ids)
            r = await db.execute(text(
                f"DELETE FROM sms_conversation_states WHERE conversation_id IN ({ph})"
            ))
            print(f"  sms_conversation_states: {r.rowcount}")

        # Delete search sessions via buyer_needs
        rows = await db.execute(
            text("SELECT id FROM buyer_needs WHERE buyer_id = :b"), {"b": bid}
        )
        need_ids = [r[0] for r in rows.all()]
        if need_ids:
            ph = ",".join(f"'{n}'" for n in need_ids)
            r = await db.execute(text(
                f"DELETE FROM search_sessions WHERE buyer_need_id IN ({ph})"
            ))
            print(f"  search_sessions: {r.rowcount}")

        # Delete conversations
        if conv_ids:
            ph = ",".join(f"'{c}'" for c in conv_ids)
            r = await db.execute(text(
                f"DELETE FROM buyer_conversations WHERE id IN ({ph})"
            ))
            print(f"  buyer_conversations: {r.rowcount}")

        # Delete needs and buyer
        r = await db.execute(
            text("DELETE FROM buyer_needs WHERE buyer_id = :b"), {"b": bid}
        )
        print(f"  buyer_needs: {r.rowcount}")

        r = await db.execute(
            text("DELETE FROM buyers WHERE id = :b"), {"b": bid}
        )
        print(f"  buyers: {r.rowcount}")

        await db.commit()
        print(f"\nCleared all SMS data for {phone}.")


def main():
    parser = argparse.ArgumentParser(description="Clear SMS test data")
    parser.add_argument("--phone", help="Clear for specific phone only")
    args = parser.parse_args()

    if args.phone:
        print(f"Clearing SMS data for: {args.phone}\n")
        asyncio.run(clear_phone(args.phone))
    else:
        print("Clearing ALL SMS data...\n")
        asyncio.run(clear_all())


if __name__ == "__main__":
    main()
