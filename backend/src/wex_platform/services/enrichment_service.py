"""Post-onboarding progressive enrichment service.

After a supplier onboards, WEx continues to enrich their property profile over
time through one-question SMS or email follow-ups, photo requests, and answers
stored automatically into property record + ContextualMemory.  Never feels like
form-filling -- feels like occasional check-ins.
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from wex_platform.domain.models import (
    Warehouse,
    TruthCore,
    Property,
    PropertyKnowledge,
    PropertyListing,
    ContextualMemory,
)

# ---------------------------------------------------------------------------
# Enrichment questions -- asked one at a time via SMS / email
# ---------------------------------------------------------------------------

ENRICHMENT_QUESTIONS = [
    {
        "id": "photos",
        "question": "Can you share a few photos of your warehouse? Upload here: {upload_link}",
        "type": "photo_request",
        "priority": 1,
    },
    {
        "id": "ceiling_height",
        "question": "What's the clear ceiling height in your warehouse?",
        "type": "text",
        "field": "clear_height_ft",
        "priority": 2,
    },
    {
        "id": "loading_docks",
        "question": "How many loading dock doors does your space have?",
        "type": "number",
        "field": "dock_doors_receiving",
        "priority": 3,
    },
    {
        "id": "office_sqft",
        "question": "Does your space include office area? If so, approximately how many sqft?",
        "type": "text",
        "field": "has_office",
        "priority": 4,
    },
    {
        "id": "power",
        "question": "What power capacity does your warehouse have? (standard, 3-phase, high amperage)",
        "type": "text",
        "field": "power_supply",
        "priority": 5,
    },
    {
        "id": "security",
        "question": "What security features does your property have? (cameras, guard, gated, alarm)",
        "type": "text",
        "priority": 6,
    },
    {
        "id": "parking",
        "question": "How many parking spots are available?",
        "type": "number",
        "field": "parking_spaces",
        "priority": 7,
    },
    {
        "id": "access_hours",
        "question": "What are the access hours for your space? (24/7, business hours, custom)",
        "type": "text",
        "priority": 8,
    },
    {
        "id": "recent_improvements",
        "question": "Any recent improvements or renovations to the property?",
        "type": "text",
        "priority": 9,
    },
    {
        "id": "special_features",
        "question": "Anything special about your space that tenants should know?",
        "type": "text",
        "priority": 10,
    },
]

# Quick lookup by question id
_QUESTION_MAP: dict[str, dict] = {q["id"]: q for q in ENRICHMENT_QUESTIONS}

# Minimum days between follow-up questions
_MIN_DAYS_BETWEEN = 3
# Max follow-ups per week
_MAX_PER_WEEK = 2


class EnrichmentService:
    """Manages progressive enrichment of property profiles post-onboarding."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_next_question(self, warehouse_id: str) -> dict | None:
        """Determine the next unanswered enrichment question for a property.

        Returns the highest-priority unanswered question dict (with ``id``,
        ``question``, ``type``, ``priority``), or ``None`` if all questions
        have been answered.
        """
        answered_ids = await self._get_answered_question_ids(warehouse_id)
        for q in ENRICHMENT_QUESTIONS:
            if q["id"] not in answered_ids:
                return {
                    "id": q["id"],
                    "question": q["question"],
                    "type": q["type"],
                    "priority": q["priority"],
                }
        return None

    async def store_response(
        self, warehouse_id: str, question_id: str, response: str
    ) -> dict:
        """Store an enrichment response.

        * Saves to ContextualMemory (memory_type = ``enrichment_response``).
        * If the question maps to a PropertyKnowledge field, updates it directly.
        * Falls back to TruthCore for legacy properties without PropertyKnowledge.
        * Returns confirmation + next question (if any).
        """
        question = _QUESTION_MAP.get(question_id)
        if question is None:
            raise ValueError(f"Unknown enrichment question id: {question_id}")

        # 1. Persist to ContextualMemory
        memory = ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            memory_type="enrichment_response",
            content=response,
            source="enrichment",
            confidence=1.0,
            metadata_={"question_id": question_id, "question_text": question["question"]},
        )

        # Also link to Property if it exists
        prop_result = await self.db.execute(
            select(Property).where(Property.id == warehouse_id)
        )
        prop = prop_result.scalar_one_or_none()
        if prop:
            memory.property_id = warehouse_id

        self.db.add(memory)

        # 2. If the question has a mapped field, update PropertyKnowledge (preferred) or TruthCore (fallback)
        field_name = question.get("field")
        if field_name:
            await self._update_knowledge_field(warehouse_id, field_name, response, question)

        await self.db.commit()

        # 3. Fetch the next unanswered question
        next_q = await self.get_next_question(warehouse_id)

        return {
            "stored": True,
            "question_id": question_id,
            "next_question": next_q,
        }

    async def get_profile_completeness(self, warehouse_id: str) -> dict:
        """Calculate how complete a property profile is.

        Returns::

            {
                "total_questions": int,
                "answered": int,
                "percentage": float,   # 0-100
                "missing": list[str],  # question ids still unanswered
            }
        """
        answered_ids = await self._get_answered_question_ids(warehouse_id)
        total = len(ENRICHMENT_QUESTIONS)
        answered = len(answered_ids)
        missing = [q["id"] for q in ENRICHMENT_QUESTIONS if q["id"] not in answered_ids]
        percentage = round((answered / total) * 100, 1) if total else 0.0
        return {
            "total_questions": total,
            "answered": answered,
            "percentage": percentage,
            "missing": missing,
        }

    async def store_photos(self, warehouse_id: str, photo_urls: list[str]) -> dict:
        """Store uploaded photos to the property record.

        Appends new URLs to the existing image_urls list.
        Tries Property first, falls back to Warehouse.
        """
        # Try Property table first
        prop_result = await self.db.execute(
            select(Property).where(Property.id == warehouse_id)
        )
        prop = prop_result.scalar_one_or_none()

        if prop:
            existing: list[str] = prop.image_urls or []
            new_urls = [url for url in photo_urls if url not in existing]
            prop.image_urls = existing + new_urls
            flag_modified(prop, "image_urls")

            if not prop.primary_image_url and new_urls:
                prop.primary_image_url = new_urls[0]
        else:
            # Fallback to Warehouse
            stmt = select(Warehouse).where(Warehouse.id == warehouse_id)
            result = await self.db.execute(stmt)
            warehouse = result.scalar_one_or_none()
            if warehouse is None:
                raise ValueError(f"Property/Warehouse {warehouse_id} not found")

            existing = warehouse.image_urls or []
            new_urls = [url for url in photo_urls if url not in existing]
            warehouse.image_urls = existing + new_urls

            if not warehouse.primary_image_url and new_urls:
                warehouse.primary_image_url = new_urls[0]

        # Also record as a contextual memory
        memory = ContextualMemory(
            id=str(uuid.uuid4()),
            warehouse_id=warehouse_id,
            memory_type="enrichment_response",
            content=f"Photos uploaded: {', '.join(new_urls)}",
            source="enrichment",
            confidence=1.0,
            metadata_={"question_id": "photos", "photo_urls": new_urls},
        )
        if prop:
            memory.property_id = warehouse_id
        self.db.add(memory)

        await self.db.commit()

        total_photos = len((prop.image_urls if prop else warehouse.image_urls) or [])

        return {
            "stored": True,
            "new_photos": len(new_urls),
            "total_photos": total_photos,
        }

    async def schedule_next_followup(self, warehouse_id: str) -> dict:
        """Determine when to send the next enrichment follow-up.

        Logic:
        * Wait at least 3 days between questions.
        * Don't send more than 2 per week.
        * Returns ``{"next_question": dict | None, "send_at": datetime | None}``.
        """
        next_q = await self.get_next_question(warehouse_id)
        if next_q is None:
            return {"next_question": None, "send_at": None}

        now = datetime.now(timezone.utc)

        # Find the most recent enrichment response for this warehouse
        stmt = (
            select(ContextualMemory.created_at)
            .where(
                and_(
                    ContextualMemory.warehouse_id == warehouse_id,
                    ContextualMemory.memory_type == "enrichment_response",
                )
            )
            .order_by(ContextualMemory.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        last_response_at = result.scalar_one_or_none()

        # Enforce minimum gap
        if last_response_at:
            earliest_next = last_response_at + timedelta(days=_MIN_DAYS_BETWEEN)
        else:
            # First follow-up: can send right away (or 1 day after onboarding)
            earliest_next = now + timedelta(days=1)

        # Check how many follow-ups were sent in the last 7 days
        week_ago = now - timedelta(days=7)
        count_stmt = (
            select(func.count())
            .select_from(ContextualMemory)
            .where(
                and_(
                    ContextualMemory.warehouse_id == warehouse_id,
                    ContextualMemory.memory_type == "enrichment_response",
                    ContextualMemory.created_at >= week_ago,
                )
            )
        )
        count_result = await self.db.execute(count_stmt)
        this_week_count = count_result.scalar() or 0

        if this_week_count >= _MAX_PER_WEEK:
            # Push to next week
            send_at = now + timedelta(days=7 - now.weekday())  # next Monday
        else:
            send_at = max(earliest_next, now)

        return {
            "next_question": next_q,
            "send_at": send_at.isoformat(),
        }

    async def get_enrichment_history(self, warehouse_id: str) -> list[dict]:
        """Get all enrichment responses for a property, newest first."""
        stmt = (
            select(ContextualMemory)
            .where(
                and_(
                    ContextualMemory.warehouse_id == warehouse_id,
                    ContextualMemory.memory_type == "enrichment_response",
                )
            )
            .order_by(ContextualMemory.created_at.desc())
        )
        result = await self.db.execute(stmt)
        memories = result.scalars().all()

        history = []
        for mem in memories:
            meta = mem.metadata_ or {}
            question_id = meta.get("question_id", "unknown")
            question_def = _QUESTION_MAP.get(question_id)
            history.append({
                "id": mem.id,
                "question_id": question_id,
                "question_text": meta.get("question_text", question_def["question"] if question_def else ""),
                "response": mem.content,
                "created_at": mem.created_at.isoformat() if mem.created_at else None,
            })
        return history

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _get_answered_question_ids(self, warehouse_id: str) -> set[str]:
        """Return set of enrichment question ids already answered."""
        stmt = (
            select(ContextualMemory.metadata_)
            .where(
                and_(
                    ContextualMemory.warehouse_id == warehouse_id,
                    ContextualMemory.memory_type == "enrichment_response",
                )
            )
        )
        result = await self.db.execute(stmt)
        rows = result.scalars().all()
        answered: set[str] = set()
        for meta in rows:
            if isinstance(meta, dict) and "question_id" in meta:
                answered.add(meta["question_id"])
        return answered

    async def _update_knowledge_field(
        self,
        warehouse_id: str,
        field_name: str,
        response: str,
        question: dict,
    ) -> None:
        """Update the corresponding PropertyKnowledge column from an enrichment answer.

        Falls back to TruthCore for legacy properties without PropertyKnowledge.
        """
        # Type coercion based on question type / field
        value: object = response
        if question.get("type") == "number":
            try:
                value = int(response)
            except ValueError:
                try:
                    value = float(response)
                except ValueError:
                    pass  # keep as string
        elif field_name == "clear_height_ft":
            # Try to parse numeric feet value from text like "32 ft"
            try:
                value = float("".join(c for c in response if c.isdigit() or c == "."))
            except ValueError:
                pass
        elif field_name in ("has_office", "has_office_space"):
            # Parse boolean-ish answer
            lower = response.lower().strip()
            if lower in ("no", "none", "n/a", "0"):
                value = False
            else:
                value = True

        # Try PropertyKnowledge first
        pk_result = await self.db.execute(
            select(PropertyKnowledge).where(PropertyKnowledge.property_id == warehouse_id)
        )
        pk = pk_result.scalar_one_or_none()

        if pk:
            # Map field names: enrichment uses TruthCore names, PropertyKnowledge may differ
            pk_field_map = {
                "has_office_space": "has_office",
                "dock_doors_receiving": "dock_doors_receiving",
                "clear_height_ft": "clear_height_ft",
                "parking_spaces": "parking_spaces",
                "power_supply": "power_supply",
                "has_office": "has_office",
            }
            pk_field = pk_field_map.get(field_name, field_name)

            if hasattr(pk, pk_field):
                setattr(pk, pk_field, value)

                # Update field_provenance for PROVENANCE_FIELDS
                if pk_field in PropertyKnowledge.PROVENANCE_FIELDS:
                    provenance = dict(pk.field_provenance or {})
                    provenance[pk_field] = {
                        "source": "enrichment",
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                    pk.field_provenance = provenance
                    flag_modified(pk, "field_provenance")
                return

        # Fallback to TruthCore
        stmt = select(TruthCore).where(TruthCore.warehouse_id == warehouse_id)
        result = await self.db.execute(stmt)
        truth_core = result.scalar_one_or_none()
        if truth_core is None:
            return  # No truth core yet; skip

        if hasattr(truth_core, field_name):
            setattr(truth_core, field_name, value)
