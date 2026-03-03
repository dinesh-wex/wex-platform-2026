"""Detail Fetcher — cache-first property info lookup for SMS conversations."""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.agents.sms.contracts import DetailFetchResult
from wex_platform.agents.sms.field_catalog import FIELD_CATALOG, format_field, get_label
from wex_platform.agents.sms.topic_catalog import get_field_keys_for_topics

logger = logging.getLogger(__name__)


class DetailFetcher:
    """Fetches property details with a two-layer cache.

    Lookup order:
    1. Check known_answers cache on SMSConversationState
    2. Query PropertyKnowledge/PropertyListing via SQLAlchemy
    3. Format via field_catalog
    4. Persist to known_answers cache
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def fetch_by_field_key(
        self,
        property_id: str,
        field_key: str,
        state,  # SMSConversationState
    ) -> DetailFetchResult:
        """Fetch a single field value for a property."""
        # Layer 1: Check known_answers cache
        known = (state.known_answers or {}).get(property_id, {}).get(field_key)
        if known is not None:
            return DetailFetchResult(
                status="CACHE_HIT",
                field_key=field_key,
                value=str(known.get("value", "")),
                formatted=known.get("formatted", ""),
                label=get_label(field_key),
            )

        # Layer 2: Query DB
        catalog_entry = FIELD_CATALOG.get(field_key)
        if not catalog_entry:
            return DetailFetchResult(
                status="UNMAPPED",
                field_key=field_key,
                needs_escalation=True,
                label=get_label(field_key),
            )

        table = catalog_entry["table"]
        column = catalog_entry["column"]

        value = await self._query_field(property_id, table, column)

        if value is None:
            return DetailFetchResult(
                status="UNMAPPED",
                field_key=field_key,
                needs_escalation=True,
                label=get_label(field_key),
            )

        # Format
        formatted = format_field(field_key, value)

        # Cache
        self._cache_answer(state, property_id, field_key, value, formatted)

        return DetailFetchResult(
            status="FOUND",
            field_key=field_key,
            value=str(value),
            formatted=formatted,
            label=get_label(field_key),
        )

    async def fetch_by_topics(
        self,
        property_id: str,
        topics: list[str],
        state,
    ) -> list[DetailFetchResult]:
        """Fetch all field values for a list of topics."""
        field_keys = get_field_keys_for_topics(topics)
        results = []
        for fk in field_keys:
            result = await self.fetch_by_field_key(property_id, fk, state)
            results.append(result)
        return results

    async def fetch_with_insight_fallback(
        self,
        property_id: str,
        topics: list[str],
        state,
        question_text: str,  # Required — no default to prevent empty-string bugs
        channel: str = "sms",
    ) -> list[DetailFetchResult]:
        """Like fetch_by_topics, but checks PropertyInsight for needs_escalation results.

        For any result where needs_escalation=True (mapped field but NULL in DB,
        or unmapped field), attempts a PropertyInsight lookup. If PropertyInsight
        finds an answer, converts those results to FOUND with source="property_insight".
        """
        results = await self.fetch_by_topics(property_id, topics, state)

        if not question_text:
            return results

        needs_insight = [r for r in results if r.needs_escalation]
        if not needs_insight:
            return results

        # Lazy import to avoid circular dependency
        from wex_platform.services.property_insight_service import PropertyInsightService

        insight_service = PropertyInsightService(self.db)
        insight = await insight_service.search(property_id, question_text, channel=channel)

        if insight.found and insight.answer:
            for r in results:
                if r.needs_escalation:
                    r.status = "FOUND"
                    r.value = insight.answer
                    r.formatted = insight.answer
                    r.needs_escalation = False
                    r.source = "property_insight"

        return results

    async def _query_field(self, property_id: str, table: str, column: str):
        """Query a single field from the appropriate table."""
        if table == "knowledge":
            from wex_platform.domain.models import PropertyKnowledge
            result = await self.db.execute(
                select(getattr(PropertyKnowledge, column))
                .where(PropertyKnowledge.property_id == property_id)
            )
            return result.scalar_one_or_none()

        elif table == "listing":
            from wex_platform.domain.models import PropertyListing
            result = await self.db.execute(
                select(getattr(PropertyListing, column))
                .where(PropertyListing.property_id == property_id)
            )
            return result.scalar_one_or_none()

        return None

    @staticmethod
    def _cache_answer(state, property_id: str, field_key: str, value, formatted: str):
        """Cache an answer in state.known_answers."""
        known = dict(state.known_answers or {})
        if property_id not in known:
            known[property_id] = {}
        known[property_id][field_key] = {
            "value": value if not hasattr(value, 'isoformat') else str(value),
            "formatted": formatted,
        }
        state.known_answers = known
