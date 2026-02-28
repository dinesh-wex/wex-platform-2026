"""Tests for DetailFetcher — cache-first property info lookup for SMS conversations."""

import uuid
from types import SimpleNamespace

import pytest

from wex_platform.services.sms_detail_fetcher import DetailFetcher
from wex_platform.domain.models import PropertyKnowledge, PropertyListing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(known_answers=None):
    """Build a minimal state object that DetailFetcher expects."""
    return SimpleNamespace(known_answers=known_answers or {})


async def _seed_property(db_session, **knowledge_overrides):
    """Create a Property + PropertyKnowledge + PropertyListing and return prop id."""
    from wex_platform.domain.models import Property

    prop_id = str(uuid.uuid4())
    prop = Property(id=prop_id, address="1 Test St", city="Detroit", state="MI", source="test")
    db_session.add(prop)

    kw_defaults = {
        "clear_height_ft": 28,
        "dock_doors": 4,
        "has_office": True,
        "power_supply": "3-phase 400A",
    }
    kw_defaults.update(knowledge_overrides)

    knowledge = PropertyKnowledge(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        **kw_defaults,
    )
    db_session.add(knowledge)

    listing = PropertyListing(
        id=str(uuid.uuid4()),
        property_id=prop_id,
        supplier_rate_per_sqft=0.85,
        available_sqft=15000,
        activation_status="live",
    )
    db_session.add(listing)

    await db_session.flush()
    return prop_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestFetchKnownField:
    """Fetch a knowledge field that exists on the property."""

    async def test_fetch_known_field(self, db_session):
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        result = await fetcher.fetch_by_field_key(prop_id, "clear_height_ft", state)

        assert result.status == "FOUND"
        assert "28" in result.formatted
        assert "ft" in result.formatted


class TestCacheHit:
    """Second fetch of the same field returns CACHE_HIT without extra DB query."""

    async def test_cache_hit(self, db_session):
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        first = await fetcher.fetch_by_field_key(prop_id, "clear_height_ft", state)
        assert first.status == "FOUND"

        second = await fetcher.fetch_by_field_key(prop_id, "clear_height_ft", state)
        assert second.status == "CACHE_HIT"


class TestFetchListingField:
    """Fetch a field that lives on PropertyListing, not PropertyKnowledge."""

    async def test_fetch_listing_field(self, db_session):
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        result = await fetcher.fetch_by_field_key(prop_id, "supplier_rate_per_sqft", state)

        assert result.status == "FOUND"
        assert "$0.85" in result.formatted


class TestUnmappedField:
    """Field key not in FIELD_CATALOG returns UNMAPPED + needs_escalation."""

    async def test_unmapped_field(self, db_session):
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        result = await fetcher.fetch_by_field_key(prop_id, "nonexistent_field_xyz", state)

        assert result.status == "UNMAPPED"
        assert result.needs_escalation is True


class TestNullField:
    """Property exists but the field value is None -> UNMAPPED, needs_escalation."""

    async def test_null_field(self, db_session):
        # year_renovated is not set, so it's None
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        result = await fetcher.fetch_by_field_key(prop_id, "year_renovated", state)

        assert result.status == "UNMAPPED"
        assert result.needs_escalation is True


class TestFetchByTopics:
    """fetch_by_topics resolves topic names to field keys and fetches them."""

    async def test_fetch_by_topics(self, db_session):
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        results = await fetcher.fetch_by_topics(prop_id, ["clear_height", "dock_doors"], state)

        field_keys = {r.field_key for r in results}
        # clear_height -> clear_height_ft
        assert "clear_height_ft" in field_keys
        # dock_doors -> dock_doors, dock_doors_receiving, dock_doors_shipping
        assert "dock_doors" in field_keys

        # At least clear_height_ft and dock_doors should be FOUND
        found = [r for r in results if r.status == "FOUND"]
        assert len(found) >= 2


class TestCachePersistedOnState:
    """After a FOUND fetch, the value is persisted in state.known_answers."""

    async def test_cache_persisted_on_state(self, db_session):
        prop_id = await _seed_property(db_session)
        fetcher = DetailFetcher(db_session)
        state = _make_state()

        await fetcher.fetch_by_field_key(prop_id, "clear_height_ft", state)

        assert prop_id in state.known_answers
        assert "clear_height_ft" in state.known_answers[prop_id]
        cached = state.known_answers[prop_id]["clear_height_ft"]
        assert "value" in cached
        assert "formatted" in cached
