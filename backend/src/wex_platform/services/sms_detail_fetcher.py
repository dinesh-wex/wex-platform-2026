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
            )

        # Layer 2: Query DB
        catalog_entry = FIELD_CATALOG.get(field_key)
        if not catalog_entry:
            return DetailFetchResult(
                status="UNMAPPED",
                field_key=field_key,
                needs_escalation=True,
            )

        table = catalog_entry["table"]
        column = catalog_entry["column"]

        value = await self._query_field(property_id, table, column)

        if value is None:
            return DetailFetchResult(
                status="UNMAPPED",
                field_key=field_key,
                needs_escalation=True,
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
