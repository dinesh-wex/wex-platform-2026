"""Clear all Voice-related data from the database for testing.

Usage:
    conda run -n wex python clear_voice_data.py          # clear ALL voice data
    conda run -n wex python clear_voice_data.py --phone "+14157661133"  # one number
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from sqlalchemy import text
from wex_platform.infra.database import async_session


async def clear_all():
    async with async_session() as db:
        # Voice call states + related escalation threads
        # Delete escalation threads linked to voice call state IDs
        rows = await db.execute(text("SELECT id FROM voice_call_states"))
        state_ids = [r[0] for r in rows.all()]
        if state_ids:
            ph = ",".join(f"'{s}'" for s in state_ids)
            r = await db.execute(text(
                f"DELETE FROM escalation_threads WHERE conversation_state_id IN ({ph})"
            ))
            print(f"  escalation_threads: {r.rowcount}")
        else:
            print(f"  escalation_threads: 0")

        r = await db.execute(text("DELETE FROM voice_call_states"))
        print(f"  voice_call_states: {r.rowcount}")

        await db.commit()
    print("\nDone.")


async def clear_phone(phone: str):
    async with async_session() as db:
        # Find voice call states for this phone
        rows = await db.execute(
            text("SELECT id FROM voice_call_states WHERE caller_phone = :p"),
            {"p": phone},
        )
        state_ids = [r[0] for r in rows.all()]

        if not state_ids:
            print(f"No voice call states found for phone {phone}")
            return

        print(f"Found {len(state_ids)} voice call(s)\n")

        # Delete escalation threads linked to these voice states
        ph = ",".join(f"'{s}'" for s in state_ids)
        r = await db.execute(text(
            f"DELETE FROM escalation_threads WHERE conversation_state_id IN ({ph})"
        ))
        print(f"  escalation_threads: {r.rowcount}")

        # Delete voice call states
        r = await db.execute(text(
            f"DELETE FROM voice_call_states WHERE id IN ({ph})"
        ))
        print(f"  voice_call_states: {r.rowcount}")

        await db.commit()
        print(f"\nCleared all voice data for {phone}.")


def main():
    parser = argparse.ArgumentParser(description="Clear Voice test data")
    parser.add_argument("--phone", help="Clear for specific phone only")
    args = parser.parse_args()

    if args.phone:
        print(f"Clearing voice data for: {args.phone}\n")
        asyncio.run(clear_phone(args.phone))
    else:
        print("Clearing ALL voice data...\n")
        asyncio.run(clear_all())


if __name__ == "__main__":
    main()
