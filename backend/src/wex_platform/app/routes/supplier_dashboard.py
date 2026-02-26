"""Supplier Dashboard API routes.

Provides endpoints for the supplier dashboard UI: portfolio overview,
property management, engagements, payments, account/team management,
and tokenized photo uploads.

ECONOMIC ISOLATION: These endpoints only expose supplier-domain data.
No buyer rates, buyer identities, or WEx spread are ever returned.
"""

import os
import secrets
import uuid
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from wex_platform.infra.database import get_db
from wex_platform.domain.models import (
    User,
    Property,
    PropertyKnowledge,
    PropertyListing,
    PropertyContact,
    PropertyEvent,
    Deal,
    SupplierAgreement,
    SupplierLedger,
    NearMiss,
    SupplierResponse,
    BuyerEngagement,
    UploadToken,
)
from wex_platform.services.property_serializer import serialize_property_as_warehouse, serialize_truth_core_compat
from wex_platform.app.routes.auth import get_current_user_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/supplier", tags=["supplier-dashboard"])
upload_router = APIRouter(prefix="/api/upload", tags=["upload"])


# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------


class PortfolioSummary(BaseModel):
    total_projected_income: float = 0.0
    avg_rate: float = 0.0
    active_capacity_sqft: int = 0
    occupancy_pct: float = 0.0
    total_rented_sqft: int = 0
    total_available_sqft: int = 0
    property_count: int = 0


class ActionItem(BaseModel):
    id: str
    type: str  # deal_ping, dla_outreach, tour_confirm, agreement_sign, post_tour
    urgency: str  # high, medium, low
    title: str
    description: str
    action_label: str = ""
    action_url: str = ""
    engagement_id: Optional[str] = None
    property_id: Optional[str] = None
    deadline: Optional[str] = None
    created_at: Optional[str] = None


class PropertySpecsUpdate(BaseModel):
    building_sqft: Optional[int] = None
    year_built: Optional[int] = None
    construction_type: Optional[str] = None
    zoning: Optional[str] = None
    lot_size_acres: Optional[float] = None
    clear_height_ft: Optional[float] = None
    dock_doors: Optional[int] = None
    drive_in_bays: Optional[int] = None
    parking_spaces: Optional[int] = None
    sprinkler: Optional[bool] = None
    power_supply: Optional[str] = None


class PropertyConfigUpdate(BaseModel):
    available_sqft: Optional[int] = None
    min_rentable_sqft: Optional[int] = None
    activity_tier: Optional[str] = None
    has_office: Optional[bool] = None
    weekend_access: Optional[bool] = None
    access_24_7: Optional[bool] = None
    min_term_months: Optional[int] = None
    available_from: Optional[str] = None
    # Certifications (also sent via config)
    food_grade: Optional[bool] = None
    fda_registered: Optional[bool] = None
    hazmat_certified: Optional[bool] = None
    c_tpat: Optional[bool] = None
    temperature_controlled: Optional[bool] = None
    foreign_trade_zone: Optional[bool] = None


class PropertyPricingUpdate(BaseModel):
    rate: Optional[float] = None


class EngagementRespondRequest(BaseModel):
    action: str  # accepted, declined, counter
    reason: Optional[str] = None
    counter_rate: Optional[float] = None


class TourConfirmRequest(BaseModel):
    confirmed: bool
    proposed_date: Optional[str] = None
    proposed_time: Optional[str] = None


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


class NotificationPreferences(BaseModel):
    deal_pings_sms: Optional[bool] = None
    deal_pings_email: Optional[bool] = None
    tour_requests_sms: Optional[bool] = None
    tour_requests_email: Optional[bool] = None
    agreement_ready_email: Optional[bool] = None
    payment_deposited_email: Optional[bool] = None
    profile_suggestions_email: Optional[bool] = None
    monthly_summary_email: Optional[bool] = None


class TeamInvite(BaseModel):
    email: str
    name: Optional[str] = None  # Defaults to email prefix if not provided
    role: str = "member"  # admin, member


class TeamMemberUpdate(BaseModel):
    role: Optional[str] = None
    is_active: Optional[bool] = None


class SuggestionResponse(BaseModel):
    suggestion_id: str
    action: str  # accepted, dismissed, snoozed


class PhotoReorderRequest(BaseModel):
    order: list[str]  # e.g. ["primary", "photo_0", "photo_1", "photo_2"]


# ---------------------------------------------------------------------------
# Helper: get supplier's properties (via PropertyContact join)
# ---------------------------------------------------------------------------


async def _get_supplier_properties(
    db: AsyncSession, user: User
) -> list[Property]:
    """Return all properties belonging to the current supplier via PropertyContact email match."""
    result = await db.execute(
        select(Property)
        .join(PropertyContact, PropertyContact.property_id == Property.id)
        .where(func.lower(PropertyContact.email) == func.lower(user.email))
        .options(
            selectinload(Property.knowledge),
            selectinload(Property.listing),
            selectinload(Property.contacts),
            selectinload(Property.events),
        )
    )
    return list(result.unique().scalars().all())


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


@router.get("/portfolio")
async def get_portfolio(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return portfolio summary for the authenticated supplier."""
    properties = await _get_supplier_properties(db, user)

    total_properties = len(properties)
    active_properties = 0
    total_capacity = 0
    occupied_sqft = 0
    total_rate = 0.0
    rate_count = 0
    total_monthly = 0.0

    prop_ids = [p.id for p in properties]

    # Fetch active deals for all properties
    deal_map: dict[str, list] = {}
    if prop_ids:
        deal_result = await db.execute(
            select(Deal).where(Deal.warehouse_id.in_(prop_ids))
        )
        for deal in deal_result.scalars().all():
            deal_map.setdefault(deal.warehouse_id, []).append(deal)

    for prop in properties:
        pl = prop.listing
        if pl and pl.activation_status == "on":
            active_properties += 1
            total_capacity += pl.max_sqft or 0
            if pl.supplier_rate_per_sqft:
                total_rate += pl.supplier_rate_per_sqft
                rate_count += 1

        # Sum active deal revenue
        for deal in deal_map.get(prop.id, []):
            if deal.status in ("active", "confirmed"):
                occupied_sqft += deal.sqft_allocated or 0
                total_monthly += (deal.supplier_rate or 0) * (deal.sqft_allocated or 0)

    avg_rate = round(total_rate / rate_count, 2) if rate_count > 0 else 0.0
    occupancy_pct = round((occupied_sqft / total_capacity * 100), 1) if total_capacity > 0 else 0.0

    total_available = total_capacity - occupied_sqft

    return PortfolioSummary(
        total_projected_income=round(total_monthly * 12, 2),
        avg_rate=avg_rate,
        active_capacity_sqft=total_capacity,
        occupancy_pct=occupancy_pct,
        total_rented_sqft=occupied_sqft,
        total_available_sqft=max(total_available, 0),
        property_count=total_properties,
    ).model_dump()


@router.get("/actions")
async def get_actions(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return pending action items sorted by urgency."""
    properties = await _get_supplier_properties(db, user)
    prop_ids = [p.id for p in properties]

    if not prop_ids:
        return []

    actions: list[dict] = []

    # Pending deal pings (supplier responses awaiting action)
    sr_result = await db.execute(
        select(SupplierResponse)
        .where(
            SupplierResponse.property_id.in_(prop_ids),
            SupplierResponse.outcome.is_(None),
        )
        .order_by(SupplierResponse.deadline_at.asc())
    )
    for sr in sr_result.scalars().all():
        actions.append(ActionItem(
            id=sr.id,
            type=sr.event_type or "deal_ping",
            urgency="high",
            title=f"Respond to {sr.event_type or 'deal ping'}",
            description=f"Deadline: {sr.deadline_at.isoformat() if sr.deadline_at else 'N/A'}",
            action_label="Respond",
            action_url=f"/supplier/engagements/{sr.id}",
            engagement_id=sr.id,
            property_id=sr.property_id,
            deadline=sr.deadline_at.isoformat() if sr.deadline_at else None,
            created_at=sr.created_at.isoformat() if sr.created_at else None,
        ).model_dump())

    # Unconfirmed tours
    tour_result = await db.execute(
        select(Deal)
        .where(
            Deal.warehouse_id.in_(prop_ids),
            Deal.tour_status == "requested",
        )
        .order_by(Deal.tour_scheduled_at.asc())
    )
    for deal in tour_result.scalars().all():
        actions.append(ActionItem(
            id=deal.id,
            type="tour_confirm",
            urgency="high",
            title="Confirm tour request",
            description=f"Tour requested for {deal.tour_preferred_date or 'TBD'}",
            action_label="Confirm Tour",
            action_url=f"/supplier/engagements/{deal.id}",
            engagement_id=deal.id,
            property_id=deal.warehouse_id,
            deadline=None,
            created_at=deal.created_at.isoformat() if deal.created_at else None,
        ).model_dump())

    # Unsigned agreements
    agree_result = await db.execute(
        select(SupplierAgreement)
        .where(
            SupplierAgreement.warehouse_id.in_(prop_ids),
            SupplierAgreement.status == "draft",
        )
        .order_by(SupplierAgreement.created_at.asc())
    )
    for agr in agree_result.scalars().all():
        actions.append(ActionItem(
            id=agr.id,
            type="agreement_sign",
            urgency="medium",
            title="Sign pending agreement",
            description=f"Agreement {agr.agreement_type} awaiting signature",
            action_label="Sign Agreement",
            action_url=f"/supplier/engagements/{agr.id}",
            engagement_id=agr.id,
            property_id=agr.warehouse_id,
            deadline=None,
            created_at=agr.created_at.isoformat() if agr.created_at else None,
        ).model_dump())

    # Sort by urgency: high first
    urgency_order = {"high": 0, "medium": 1, "low": 2}
    actions.sort(key=lambda a: urgency_order.get(a.get("urgency", "low"), 2))

    return actions


# ---------------------------------------------------------------------------
# Helpers: field mapping (DB -> frontend interface)
# ---------------------------------------------------------------------------


def _build_property_name(prop: Property) -> str:
    """Construct a display name from address components since DB has no name field."""
    parts = [prop.address]
    if prop.city:
        parts.append(prop.city)
    return ", ".join(parts) if parts else "Unnamed Property"


def _derive_frontend_status(prop: Property, pl: PropertyListing | None) -> str:
    """Map DB activation_status / relationship_status to frontend status values.

    Frontend expects: 'in_network', 'in_network_paused', 'onboarding', etc.
    DB has: PropertyListing.activation_status ('on'/'off') and Property.relationship_status.

    PropertyListing.activation_status is the primary source of truth for the toggle:
    - 'on'  -> 'in_network'
    - 'off' -> 'in_network_paused'
    If there is no PropertyListing, fall back to relationship_status.
    """
    if pl:
        if pl.activation_status == "on":
            return "in_network"
        if pl.activation_status == "off":
            return "in_network_paused"
    # No listing -- fall back to relationship_status
    from wex_platform.services.property_serializer import _relationship_to_supplier_status
    supplier_status = _relationship_to_supplier_status(prop.relationship_status)
    if supplier_status in ("onboarding", "third_party"):
        return "onboarding"
    return supplier_status or "onboarding"


def _build_truth_core_dict(prop: Property, pk: PropertyKnowledge | None, pl: PropertyListing | None) -> dict:
    """Map DB PropertyKnowledge + PropertyListing to the frontend TruthCore interface.

    The frontend TruthCore interface uses different field names than the DB:
    - building_sqft (from pk.building_size_sqft)
    - dock_doors (from pk.dock_doors_receiving + pk.dock_doors_shipping)
    - sprinkler (from pk.has_sprinkler)
    - available_sqft (from pl.max_sqft)
    - min_rentable_sqft (from pl.min_sqft)
    - has_office (from pk.has_office)
    - target_rate_sqft (from pl.supplier_rate_per_sqft)
    - year_built, construction_type, zoning, lot_size_acres from pk
    """
    return {
        # Building specs (sourced from PropertyKnowledge)
        "building_sqft": pk.building_size_sqft if pk else None,
        "year_built": pk.year_built if pk else None,
        "construction_type": pk.construction_type if pk else None,
        "zoning": pk.zoning if pk else None,
        "lot_size_acres": pk.lot_size_acres if pk else None,
        "clear_height_ft": pk.clear_height_ft if pk else None,
        "dock_doors": ((pk.dock_doors_receiving or 0) + (pk.dock_doors_shipping or 0)) if pk else 0,
        "drive_in_bays": pk.drive_in_bays if pk else None,
        "parking_spaces": pk.parking_spaces if pk else None,
        "sprinkler": pk.has_sprinkler if pk else None,
        "power_supply": pk.power_supply if pk else None,
        # Configuration (sourced from PropertyListing)
        "available_sqft": pl.max_sqft if pl else None,
        "min_rentable_sqft": pl.min_sqft if pl else None,
        "activity_tier": pk.activity_tier if pk else None,
        "has_office": pk.has_office if pk else None,
        "weekend_access": pk.weekend_access if pk else None,
        "access_24_7": None,  # Not present in new schema
        "min_term_months": pl.min_term_months if pl else None,
        "available_from": pl.available_from.isoformat() if pl and pl.available_from else None,
        # Pricing
        "target_rate_sqft": pl.supplier_rate_per_sqft if pl else None,
        # Certifications (stored in PropertyListing.constraints or PropertyKnowledge fields)
        "food_grade": None,
        "fda_registered": None,
        "hazmat_certified": None,
        "c_tpat": None,
        "temperature_controlled": None,
        "foreign_trade_zone": None,
    }


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@router.get("/properties")
async def list_properties(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """List all properties belonging to the authenticated supplier."""
    properties = await _get_supplier_properties(db, user)
    prop_ids = [p.id for p in properties]

    # Fetch deals for all properties
    deal_map: dict[str, list] = {}
    if prop_ids:
        deal_result = await db.execute(
            select(Deal).where(Deal.warehouse_id.in_(prop_ids))
        )
        for deal in deal_result.scalars().all():
            deal_map.setdefault(deal.warehouse_id, []).append(deal)

    items = []
    for prop in properties:
        pk = prop.knowledge
        pl = prop.listing

        # Compute rented sqft and occupancy from active deals
        rented_sqft = 0
        for deal in deal_map.get(prop.id, []):
            if deal.status in ("active", "confirmed"):
                rented_sqft += deal.sqft_allocated or 0
        rental_sqft = (pl.available_sqft or pl.max_sqft or 0) if pl else 0
        building_sqft = pk.building_size_sqft if pk else 0
        total_sqft = rental_sqft or building_sqft or 0
        occupancy_pct = round((rented_sqft / total_sqft * 100), 1) if total_sqft > 0 else 0.0

        # Derive status: map activation_status / relationship_status to frontend values
        status = _derive_frontend_status(prop, pl)

        items.append({
            "id": prop.id,
            "name": _build_property_name(prop),
            "address": prop.address,
            "city": prop.city,
            "state": prop.state,
            "zip_code": prop.zip,
            "total_sqft": total_sqft,
            "available_sqft": pl.max_sqft if pl else 0,
            "min_sqft": pl.min_sqft if pl else 0,
            "status": status,
            "supplier_rate": pl.supplier_rate_per_sqft if pl else 0,
            "image_url": prop.primary_image_url,
            "image_urls": prop.image_urls or [],
            "rented_sqft": rented_sqft,
            "occupancy_pct": occupancy_pct,
            "truth_core": _build_truth_core_dict(prop, pk, pl) if pl else None,
            "created_at": prop.created_at.isoformat() if prop.created_at else None,
        })

    return {"properties": items, "count": len(items)}


@router.get("/properties/{property_id}")
async def get_property(
    property_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return detailed property info for a single property."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(
            selectinload(Property.knowledge),
            selectinload(Property.listing),
            selectinload(Property.contacts),
            selectinload(Property.memories),
            selectinload(Property.events),
        )
    )
    prop = result.scalar_one_or_none()

    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    pk = prop.knowledge
    pl = prop.listing

    # Fetch deals for this property
    deal_result = await db.execute(
        select(Deal).where(Deal.warehouse_id == property_id)
    )
    deals = deal_result.scalars().all()

    # Compute rented sqft and occupancy from active deals
    rented_sqft = 0
    for deal in deals:
        if deal.status in ("active", "confirmed"):
            rented_sqft += deal.sqft_allocated or 0
    rental_sqft = (pl.available_sqft or pl.max_sqft or 0) if pl else 0
    building_sqft = pk.building_size_sqft if pk else 0
    total_sqft = rental_sqft or building_sqft or 0
    occupancy_pct = round((rented_sqft / total_sqft * 100), 1) if total_sqft > 0 else 0.0

    # Build truth_core dict mapped to frontend TruthCore interface
    tc_dict = _build_truth_core_dict(prop, pk, pl) if pl else None

    # Derive status for frontend
    status = _derive_frontend_status(prop, pl)

    # Active deals summary (supplier-safe)
    deals_list = []
    for d in deals:
        deals_list.append({
            "id": d.id,
            "status": d.status,
            "sqft_allocated": d.sqft_allocated,
            "supplier_rate": d.supplier_rate,
            "start_date": d.start_date.isoformat() if d.start_date else None,
            "end_date": d.end_date.isoformat() if d.end_date else None,
            "tour_status": d.tour_status,
        })

    return {
        "id": prop.id,
        "name": _build_property_name(prop),
        "address": prop.address,
        "city": prop.city,
        "state": prop.state,
        "zip_code": prop.zip,
        "total_sqft": total_sqft,
        "available_sqft": pl.max_sqft if pl else 0,
        "min_sqft": pl.min_sqft if pl else 0,
        "status": status,
        "supplier_rate": pl.supplier_rate_per_sqft if pl else 0,
        "image_url": prop.primary_image_url,
        "image_urls": prop.image_urls or [],
        "rented_sqft": rented_sqft,
        "occupancy_pct": occupancy_pct,
        "lat": prop.lat,
        "lng": prop.lng,
        "property_type": prop.property_type,
        "description": pk.additional_notes if pk else None,
        "truth_core": tc_dict,
        "deals": deals_list,
        "created_at": prop.created_at.isoformat() if prop.created_at else None,
        "updated_at": prop.updated_at.isoformat() if prop.updated_at else None,
    }


@router.patch("/properties/{property_id}/specs")
async def update_property_specs(
    property_id: str,
    body: PropertySpecsUpdate,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update physical building specs for a property."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(
            selectinload(Property.knowledge),
            selectinload(Property.contacts),
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    updates = body.model_dump(exclude_unset=True)

    # All specs go to PropertyKnowledge now
    field_map = {
        "building_sqft": "building_size_sqft",
        "year_built": "year_built",
        "construction_type": "construction_type",
        "zoning": "zoning",
        "lot_size_acres": "lot_size_acres",
        "clear_height_ft": "clear_height_ft",
        "dock_doors": "dock_doors_receiving",  # single dock_doors maps to receiving
        "drive_in_bays": "drive_in_bays",
        "parking_spaces": "parking_spaces",
        "sprinkler": "has_sprinkler",
        "power_supply": "power_supply",
    }

    pk = prop.knowledge
    if not pk:
        # Create PropertyKnowledge if it doesn't exist
        pk = PropertyKnowledge(
            id=str(uuid.uuid4()),
            property_id=property_id,
        )
        db.add(pk)
        await db.flush()

    provenance = dict(pk.field_provenance or {})
    provenance_updated = False

    for field, value in updates.items():
        db_field = field_map.get(field)
        if not db_field:
            continue
        if hasattr(pk, db_field):
            setattr(pk, db_field, value)
            # Update provenance for PROVENANCE_FIELDS
            if db_field in PropertyKnowledge.PROVENANCE_FIELDS:
                provenance[db_field] = {"source": "supplier_dashboard", "updated_at": datetime.now(timezone.utc).isoformat()}
                provenance_updated = True

    if provenance_updated:
        pk.field_provenance = provenance
        flag_modified(pk, "field_provenance")

    await db.commit()
    return {"ok": True, "updated_fields": list(updates.keys())}


@router.patch("/properties/{property_id}/config")
async def update_property_config(
    property_id: str,
    body: PropertyConfigUpdate,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update availability configuration for a property."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(
            selectinload(Property.listing),
            selectinload(Property.knowledge),
            selectinload(Property.contacts),
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    pl = prop.listing
    if not pl:
        raise HTTPException(status_code=400, detail="Property has no listing. Activate first.")

    pk = prop.knowledge

    updates = body.model_dump(exclude_unset=True)

    # Map frontend field names to DB column names on PropertyListing
    listing_field_map = {
        "available_sqft": "max_sqft",
        "min_rentable_sqft": "min_sqft",
        "min_term_months": "min_term_months",
        "available_from": "available_from",
    }

    # Fields that go to PropertyKnowledge
    knowledge_field_map = {
        "activity_tier": "activity_tier",
        "has_office": "has_office",
        "weekend_access": "weekend_access",
    }

    for field, value in updates.items():
        # Check listing fields first
        db_field = listing_field_map.get(field)
        if db_field and hasattr(pl, db_field):
            setattr(pl, db_field, value)
            continue

        # Check knowledge fields
        db_field = knowledge_field_map.get(field)
        if db_field and pk and hasattr(pk, db_field):
            setattr(pk, db_field, value)
            continue

        # Certifications and other fields stored in listing constraints
        # access_24_7, food_grade, fda_registered, hazmat_certified, c_tpat,
        # temperature_controlled, foreign_trade_zone
        if field in ("access_24_7", "food_grade", "fda_registered", "hazmat_certified",
                      "c_tpat", "temperature_controlled", "foreign_trade_zone"):
            constraints = dict(pl.constraints or {})
            constraints[field] = value
            pl.constraints = constraints
            flag_modified(pl, "constraints")

    await db.commit()
    return {"ok": True, "updated_fields": list(updates.keys())}


@router.patch("/properties/{property_id}/pricing")
async def update_property_pricing(
    property_id: str,
    body: PropertyPricingUpdate,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update pricing for a property."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(
            selectinload(Property.listing),
            selectinload(Property.contacts),
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    pl = prop.listing
    if not pl:
        raise HTTPException(status_code=400, detail="Property has no listing. Activate first.")

    if body.rate is not None:
        pl.supplier_rate_per_sqft = body.rate

    await db.commit()
    return {"ok": True, "updated_fields": ["rate"]}


@router.get("/properties/{property_id}/photos")
async def get_property_photos(
    property_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return photos for a property."""
    result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    photos = []
    if prop.primary_image_url:
        photos.append({
            "id": "primary",
            "url": prop.primary_image_url,
            "is_primary": True,
        })
    for i, url in enumerate(prop.image_urls or []):
        photos.append({
            "id": f"photo_{i}",
            "url": url,
            "is_primary": False,
        })

    return photos


@router.delete("/properties/{property_id}/photos/{photo_id}")
async def delete_property_photo(
    property_id: str,
    photo_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Delete a photo from a property."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(selectinload(Property.contacts))
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    if photo_id == "primary":
        prop.primary_image_url = None
    else:
        # Remove by index
        try:
            idx = int(photo_id.replace("photo_", ""))
            urls = list(prop.image_urls or [])
            if 0 <= idx < len(urls):
                urls.pop(idx)
                prop.image_urls = urls
                flag_modified(prop, "image_urls")
            else:
                raise HTTPException(status_code=404, detail="Photo not found")
        except ValueError:
            raise HTTPException(status_code=404, detail="Photo not found")

    await db.commit()
    return {"ok": True}


@router.patch("/properties/{property_id}/photos/reorder")
async def reorder_property_photos(
    property_id: str,
    body: PhotoReorderRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Reorder photos for a property.

    The first item in the order array becomes the new primary_image_url.
    The rest become the new image_urls array.
    """
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(selectinload(Property.contacts))
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    # Build a map of photo_id -> URL from current photos
    url_map: dict[str, str] = {}
    if prop.primary_image_url:
        url_map["primary"] = prop.primary_image_url
    for i, url in enumerate(prop.image_urls or []):
        url_map[f"photo_{i}"] = url

    # Validate that all IDs in the order exist in the current photos
    for pid in body.order:
        if pid not in url_map:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown photo ID: {pid}",
            )

    # Validate that all current photos are accounted for
    if set(body.order) != set(url_map.keys()):
        missing = set(url_map.keys()) - set(body.order)
        raise HTTPException(
            status_code=400,
            detail=f"Order must include all photo IDs. Missing: {sorted(missing)}",
        )

    # Reorder: first item becomes primary, rest become image_urls
    ordered_urls = [url_map[pid] for pid in body.order]
    prop.primary_image_url = ordered_urls[0]
    prop.image_urls = ordered_urls[1:] if len(ordered_urls) > 1 else []
    flag_modified(prop, "image_urls")

    await db.commit()

    # Return the new photo list in the same format as the GET endpoint
    photos = []
    if prop.primary_image_url:
        photos.append({
            "id": "primary",
            "url": prop.primary_image_url,
            "is_primary": True,
        })
    for i, url in enumerate(prop.image_urls or []):
        photos.append({
            "id": f"photo_{i}",
            "url": url,
            "is_primary": False,
        })

    return photos


@router.post("/properties/{property_id}/upload-token")
async def create_upload_token(
    property_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Generate a tokenized upload URL for property photos."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(selectinload(Property.contacts))
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Verify ownership via PropertyContact
    primary_contact = next((c for c in (prop.contacts or []) if c.is_primary), (prop.contacts or [None])[0] if prop.contacts else None)
    if primary_contact and primary_contact.email and primary_contact.email.lower() != user.email.lower():
        raise HTTPException(status_code=403, detail="Not your property")

    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()
    upload_token = UploadToken(
        token=token,
        property_id=property_id,
        created_at=now,
        expires_at=now + timedelta(hours=1),
        is_used=False,
    )
    db.add(upload_token)
    await db.commit()

    return {
        "token": token,
        "upload_url": f"/api/upload/{property_id}/{token}/photos",
        "verify_url": f"/api/upload/{property_id}/{token}/verify",
        "expires_at": upload_token.expires_at.isoformat(),
    }


@router.get("/properties/{property_id}/activity")
async def get_property_activity(
    property_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return recent activity for a property as a unified timeline of PropertyActivity objects."""
    timeline: list[dict] = []

    # Buyer engagements -> shown_to_buyers events
    eng_result = await db.execute(
        select(BuyerEngagement)
        .where(BuyerEngagement.property_id == property_id)
        .order_by(BuyerEngagement.created_at.desc())
        .limit(50)
    )
    for e in eng_result.scalars().all():
        ts = (e.shown_at or e.created_at)
        timeline.append({
            "id": e.id,
            "type": "shown_to_buyers",
            "description": f"Property shown to buyer (tier {e.tier}, position #{e.position_in_results})",
            "timestamp": ts.isoformat() if ts else None,
            "metadata": {
                "tier": e.tier,
                "position": e.position_in_results,
                "action": e.action_taken,
            },
        })

    # Near misses -> near_miss_summary events
    nm_result = await db.execute(
        select(NearMiss)
        .where(NearMiss.property_id == property_id)
        .order_by(NearMiss.evaluated_at.desc())
        .limit(20)
    )
    for nm in nm_result.scalars().all():
        timeline.append({
            "id": nm.id,
            "type": "near_miss_summary",
            "description": f"Near miss ({nm.outcome}): match score {nm.match_score}",
            "timestamp": nm.evaluated_at.isoformat() if nm.evaluated_at else None,
            "metadata": {
                "outcome": nm.outcome,
                "match_score": nm.match_score,
                "reasons": nm.reasons,
            },
        })

    # Supplier responses -> deal_ping_sent / deal_ping_response events
    sr_result = await db.execute(
        select(SupplierResponse)
        .where(SupplierResponse.property_id == property_id)
        .order_by(SupplierResponse.created_at.desc())
        .limit(20)
    )
    for sr in sr_result.scalars().all():
        # Deal ping sent event
        if sr.sent_at:
            timeline.append({
                "id": f"{sr.id}_sent",
                "type": "deal_ping_sent",
                "description": f"Deal ping sent ({sr.event_type or 'deal_ping'})",
                "timestamp": sr.sent_at.isoformat(),
                "metadata": {
                    "event_type": sr.event_type,
                },
            })
        # Response event
        if sr.responded_at:
            timeline.append({
                "id": f"{sr.id}_response",
                "type": "deal_ping_response",
                "description": f"Supplier responded: {sr.outcome or 'pending'} (response time: {sr.response_time_hours or 'N/A'}h)",
                "timestamp": sr.responded_at.isoformat(),
                "metadata": {
                    "outcome": sr.outcome,
                    "response_time_hours": sr.response_time_hours,
                },
            })

    # Sort by timestamp descending (most recent first)
    timeline.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    return timeline


@router.get("/properties/{property_id}/suggestions")
async def get_property_suggestions(
    property_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return AI-generated suggestions for improving a property listing."""
    result = await db.execute(
        select(Property)
        .where(Property.id == property_id)
        .options(
            selectinload(Property.knowledge),
            selectinload(Property.listing),
            selectinload(Property.memories),
        )
    )
    prop = result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Generate suggestions based on missing data
    suggestions = []
    pk = prop.knowledge
    pl = prop.listing

    # Count photos
    photo_count = len(prop.image_urls or []) + (1 if prop.primary_image_url else 0)

    if photo_count < 3:
        suggestions.append({
            "id": f"sug_{property_id}_photo",
            "type": "add_photos",
            "priority": 1,
            "title": "Add property photos",
            "description": f"Properties with 3+ photos get 2x more tour requests. You have {photo_count}.",
            "action_label": "Add Photos",
            "target_tab": "photos",
        })

    if pl:
        # Tier 1 fields
        if pl.max_sqft is None:
            suggestions.append({
                "id": f"sug_{property_id}_sqft",
                "type": "add_spec",
                "priority": 1,
                "title": "Set available space",
                "description": "The clearing engine can't match without available sqft.",
                "action_label": "Fix this",
                "target_tab": "config",
                "target_field": "available_sqft",
            })
        if not pl.supplier_rate_per_sqft or pl.supplier_rate_per_sqft <= 0:
            suggestions.append({
                "id": f"sug_{property_id}_rate",
                "type": "add_spec",
                "priority": 1,
                "title": "Set your rate",
                "description": "Buyer pricing is calculated from your rate.",
                "action_label": "Fix this",
                "target_tab": "pricing",
                "target_field": "target_rate_sqft",
            })
        if pk and not pk.clear_height_ft:
            suggestions.append({
                "id": f"sug_{property_id}_height",
                "type": "add_spec",
                "priority": 1,
                "title": "Add clear height",
                "description": "Buyers frequently filter by clear height.",
                "action_label": "Fix this",
                "target_tab": "building",
                "target_field": "clear_height_ft",
            })
        if pk and (pk.dock_doors_receiving or 0) == 0 and (pk.dock_doors_shipping or 0) == 0:
            suggestions.append({
                "id": f"sug_{property_id}_docks",
                "type": "add_spec",
                "priority": 1,
                "title": "Add dock door information",
                "description": "Dock door count is a top-3 buyer filter.",
                "action_label": "Fix this",
                "target_tab": "building",
                "target_field": "dock_doors",
            })
        if pk and not pk.activity_tier:
            suggestions.append({
                "id": f"sug_{property_id}_tier",
                "type": "add_spec",
                "priority": 1,
                "title": "Set activity tier",
                "description": "Determines use-type compatibility (storage, light ops, distribution).",
                "action_label": "Fix this",
                "target_tab": "config",
                "target_field": "activity_tier",
            })
        if pl.available_from is None:
            suggestions.append({
                "id": f"sug_{property_id}_avail",
                "type": "add_spec",
                "priority": 1,
                "title": "Set availability date",
                "description": "Buyers filter by when they need space.",
                "action_label": "Fix this",
                "target_tab": "config",
                "target_field": "available_from",
            })

        # Tier 2 fields (only suggest if all tier 1 are filled)
        tier1_complete = (
            photo_count >= 3
            and pl.max_sqft is not None
            and pl.supplier_rate_per_sqft and pl.supplier_rate_per_sqft > 0
            and (pk and pk.clear_height_ft)
            and (pk and ((pk.dock_doors_receiving or 0) + (pk.dock_doors_shipping or 0)) > 0)
            and (pk and pk.activity_tier)
            and pl.available_from is not None
        )
        if tier1_complete:
            if pk and (pk.parking_spaces is None or pk.parking_spaces == 0):
                suggestions.append({
                    "id": f"sug_{property_id}_parking",
                    "type": "add_spec",
                    "priority": 2,
                    "title": "Add parking information",
                    "description": "Some buyer segments require parking details.",
                    "action_label": "Fix this",
                    "target_tab": "building",
                    "target_field": "parking_spaces",
                })
            if pk and not pk.power_supply:
                suggestions.append({
                    "id": f"sug_{property_id}_power",
                    "type": "add_spec",
                    "priority": 2,
                    "title": "Add power supply details",
                    "description": "Relevant for light ops and distribution buyers.",
                    "action_label": "Fix this",
                    "target_tab": "building",
                    "target_field": "power_supply",
                })
    else:
        suggestions.append({
            "id": f"sug_{property_id}_activate",
            "type": "activate",
            "priority": 1,
            "title": "Activate this property",
            "description": "Complete activation to start receiving buyer matches.",
            "action_label": "Activate",
        })

    # Sort by priority (tier 1 first)
    suggestions.sort(key=lambda s: s.get("priority", 99))

    # Check near miss patterns for actionable suggestions
    nm_result = await db.execute(
        select(NearMiss)
        .where(NearMiss.property_id == property_id)
        .order_by(NearMiss.evaluated_at.desc())
        .limit(10)
    )
    near_misses = nm_result.scalars().all()
    if len(near_misses) >= 3:
        suggestions.append({
            "id": f"sug_{property_id}_near_miss",
            "type": "near_miss_pattern",
            "priority": "medium",
            "title": "Frequent near-misses detected",
            "description": f"Your property was close to matching {len(near_misses)} recent buyer needs. Review your listing specs.",
        })

    return suggestions


@router.post("/properties/{property_id}/suggestion-response")
async def respond_to_suggestion(
    property_id: str,
    body: SuggestionResponse,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Record supplier's response to a suggestion."""
    # For now, just acknowledge. In the future, track in a suggestions table.
    return {
        "ok": True,
        "suggestion_id": body.suggestion_id,
        "action": body.action,
    }


# ---------------------------------------------------------------------------
# Photo Upload (tokenized, no auth required)
# ---------------------------------------------------------------------------


@upload_router.get("/{property_id}/{token}/verify")
async def verify_upload_token(
    property_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    """Verify an upload token is valid and not expired."""
    result = await db.execute(
        select(UploadToken)
        .where(
            UploadToken.token == token,
            UploadToken.property_id == property_id,
        )
    )
    upload_token = result.scalar_one_or_none()

    if not upload_token:
        raise HTTPException(status_code=404, detail="Invalid upload token")

    now = datetime.utcnow()
    if upload_token.is_used:
        raise HTTPException(status_code=410, detail="Token already used")
    if upload_token.expires_at and upload_token.expires_at < now:
        raise HTTPException(status_code=410, detail="Token expired")

    return {
        "valid": True,
        "property_id": property_id,
        "expires_at": upload_token.expires_at.isoformat() if upload_token.expires_at else None,
    }


@upload_router.post("/{property_id}/{token}/photos")
async def upload_photos(
    property_id: str,
    token: str,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload photos using a tokenized URL (no auth required).

    Accepts multipart file uploads, saves them to the local uploads
    directory, and appends the resulting URLs to the property's
    image_urls JSON array.
    """
    # Verify token
    result = await db.execute(
        select(UploadToken)
        .where(
            UploadToken.token == token,
            UploadToken.property_id == property_id,
        )
    )
    upload_token = result.scalar_one_or_none()

    if not upload_token:
        raise HTTPException(status_code=404, detail="Invalid upload token")

    now = datetime.utcnow()
    if upload_token.is_used:
        raise HTTPException(status_code=410, detail="Token already used")
    if upload_token.expires_at and upload_token.expires_at < now:
        raise HTTPException(status_code=410, detail="Token expired")

    # Fetch the property to update image_urls
    prop_result = await db.execute(
        select(Property).where(Property.id == property_id)
    )
    prop = prop_result.scalar_one_or_none()
    if not prop:
        raise HTTPException(status_code=404, detail="Property not found")

    # Determine upload directory (relative to backend root)
    backend_root = Path(__file__).resolve().parents[4]  # up from routes -> app -> wex_platform -> src -> backend
    upload_dir = backend_root / "uploads" / "properties" / property_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    uploaded_urls: list[str] = []

    for file in files:
        # Sanitize filename and make unique to avoid collisions
        original_name = file.filename or "photo.jpg"
        # Strip path separators from filename for safety
        safe_name = original_name.replace("/", "_").replace("\\", "_")
        unique_name = f"{uuid.uuid4().hex[:8]}_{safe_name}"

        file_path = upload_dir / unique_name
        content = await file.read()
        file_path.write_bytes(content)

        url_path = f"/uploads/properties/{property_id}/{unique_name}"
        uploaded_urls.append(url_path)

    # Append new URLs to the property's image_urls
    current_urls = list(prop.image_urls or [])
    current_urls.extend(uploaded_urls)
    prop.image_urls = current_urls
    flag_modified(prop, "image_urls")

    # If there is no primary image, set the first uploaded photo as primary
    if not prop.primary_image_url and uploaded_urls:
        prop.primary_image_url = uploaded_urls[0]

    # Mark token as used only after successful upload
    upload_token.is_used = True
    await db.commit()

    return {
        "ok": True,
        "property_id": property_id,
        "uploaded_urls": uploaded_urls,
        "total_photos": len(current_urls),
    }


# ---------------------------------------------------------------------------
# Engagements
# ---------------------------------------------------------------------------


@router.get("/engagements")
async def list_engagements(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """List all engagements across the supplier's properties, enriched with deal/warehouse data."""
    properties = await _get_supplier_properties(db, user)
    prop_ids = [p.id for p in properties]
    prop_map = {p.id: p for p in properties}

    if not prop_ids:
        return []

    result = await db.execute(
        select(SupplierResponse)
        .where(SupplierResponse.property_id.in_(prop_ids))
        .order_by(SupplierResponse.created_at.desc())
        .limit(100)
    )
    responses = result.scalars().all()

    # Gather deal IDs to fetch deal details
    deal_ids = [sr.deal_id for sr in responses if sr.deal_id]
    deal_map: dict = {}
    if deal_ids:
        deal_result = await db.execute(
            select(Deal).where(Deal.id.in_(deal_ids))
        )
        deal_map = {d.id: d for d in deal_result.scalars().all()}

    items = []
    for sr in responses:
        prop = prop_map.get(sr.property_id)
        deal = deal_map.get(sr.deal_id) if sr.deal_id else None

        # Build address
        property_address = ""
        if prop:
            property_address = f"{prop.address}, {prop.city}, {prop.state}"

        # Map outcome to engagement status
        status = sr.outcome or sr.event_type or "deal_ping"

        sqft = deal.sqft_allocated if deal and deal.sqft_allocated else 0
        supplier_rate = deal.supplier_rate if deal and deal.supplier_rate else 0.0
        term_months = deal.term_months if deal and hasattr(deal, "term_months") and deal.term_months else 12
        monthly_payout = supplier_rate * sqft
        total_value = monthly_payout * term_months

        # Build timeline from available data
        timeline = []
        if sr.sent_at:
            timeline.append({
                "id": f"{sr.id}_sent",
                "type": sr.event_type or "deal_ping",
                "description": f"Deal ping sent",
                "timestamp": sr.sent_at.isoformat(),
                "completed": True,
            })
        if sr.responded_at:
            timeline.append({
                "id": f"{sr.id}_responded",
                "type": "response",
                "description": f"Supplier responded: {sr.outcome or 'pending'}",
                "timestamp": sr.responded_at.isoformat(),
                "completed": True,
            })

        items.append({
            "id": sr.id,
            "property_id": sr.property_id,
            "property_address": property_address,
            "property_image_url": prop.primary_image_url if prop else None,
            "buyer_need_id": deal.buyer_need_id if deal and hasattr(deal, "buyer_need_id") else "",
            "status": status,
            "buyer_company": None,  # Hidden pre-tour (economic isolation)
            "buyer_use_type": deal.use_type if deal and hasattr(deal, "use_type") else "",
            "sqft": sqft,
            "use_type": deal.use_type if deal and hasattr(deal, "use_type") else "",
            "supplier_rate": supplier_rate,
            "monthly_payout": round(monthly_payout, 2),
            "term_months": term_months,
            "total_value": round(total_value, 2),
            "created_at": sr.created_at.isoformat() if sr.created_at else None,
            "updated_at": sr.responded_at.isoformat() if sr.responded_at else (sr.created_at.isoformat() if sr.created_at else None),
            "next_step": sr.event_type if not sr.outcome else None,
            "timeline": timeline,
        })

    return items


@router.get("/engagements/{engagement_id}")
async def get_engagement(
    engagement_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return detail for a single engagement/supplier response."""
    result = await db.execute(
        select(SupplierResponse).where(SupplierResponse.id == engagement_id)
    )
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Engagement not found")

    return {
        "id": sr.id,
        "property_id": sr.property_id,
        "deal_id": sr.deal_id,
        "event_type": sr.event_type,
        "outcome": sr.outcome,
        "sent_at": sr.sent_at.isoformat() if sr.sent_at else None,
        "deadline_at": sr.deadline_at.isoformat() if sr.deadline_at else None,
        "responded_at": sr.responded_at.isoformat() if sr.responded_at else None,
        "response_time_hours": sr.response_time_hours,
        "decline_reason": sr.decline_reason,
        "counter_rate": sr.counter_rate,
        "created_at": sr.created_at.isoformat() if sr.created_at else None,
    }


@router.post("/engagements/{engagement_id}/respond")
async def respond_to_engagement(
    engagement_id: str,
    body: EngagementRespondRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Supplier responds to an engagement (accept, decline, counter)."""
    result = await db.execute(
        select(SupplierResponse).where(SupplierResponse.id == engagement_id)
    )
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Engagement not found")

    if sr.outcome is not None:
        raise HTTPException(status_code=400, detail="Already responded to this engagement")

    now = datetime.now(timezone.utc)
    sr.outcome = body.action
    sr.responded_at = now
    sr.decline_reason = body.reason
    sr.counter_rate = body.counter_rate

    # Calculate response time
    if sr.sent_at:
        delta = now - sr.sent_at
        sr.response_time_hours = round(delta.total_seconds() / 3600, 2)

    await db.commit()

    return {
        "ok": True,
        "engagement_id": engagement_id,
        "outcome": body.action,
        "response_time_hours": sr.response_time_hours,
    }


@router.post("/engagements/{engagement_id}/tour/confirm")
async def confirm_engagement_tour(
    engagement_id: str,
    body: TourConfirmRequest,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Confirm or reschedule a tour from an engagement."""
    result = await db.execute(
        select(SupplierResponse).where(SupplierResponse.id == engagement_id)
    )
    sr = result.scalar_one_or_none()
    if not sr:
        raise HTTPException(status_code=404, detail="Engagement not found")

    if not sr.deal_id:
        raise HTTPException(status_code=400, detail="No deal associated with this engagement")

    # Delegate to the deal tour confirmation
    deal_result = await db.execute(
        select(Deal).where(Deal.id == sr.deal_id)
    )
    deal = deal_result.scalar_one_or_none()
    if not deal:
        raise HTTPException(status_code=404, detail="Associated deal not found")

    now = datetime.now(timezone.utc)

    if body.confirmed:
        deal.tour_status = "confirmed"
        deal.supplier_confirmed_at = now
        sr.outcome = "confirmed"
        sr.responded_at = now
    else:
        if not body.proposed_date or not body.proposed_time:
            raise HTTPException(
                status_code=400,
                detail="Must provide proposed_date and proposed_time when not confirming.",
            )
        deal.tour_status = "rescheduled"
        deal.supplier_proposed_date = body.proposed_date
        deal.supplier_proposed_time = body.proposed_time
        sr.outcome = "rescheduled"
        sr.responded_at = now

    await db.commit()

    return {
        "ok": True,
        "tour_status": deal.tour_status,
        "deal_id": deal.id,
    }


# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------


@router.get("/payments")
async def list_payments(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return payment history across all supplier properties."""
    properties = await _get_supplier_properties(db, user)
    prop_ids = [p.id for p in properties]
    prop_map = {p.id: p for p in properties}

    if not prop_ids:
        return []

    result = await db.execute(
        select(SupplierLedger)
        .where(SupplierLedger.warehouse_id.in_(prop_ids))
        .order_by(SupplierLedger.created_at.desc())
        .limit(200)
    )
    entries = result.scalars().all()

    items = []
    for e in entries:
        prop = prop_map.get(e.warehouse_id)
        property_address = f"{prop.address}, {prop.city}, {prop.state}" if prop else ""
        items.append({
            "id": e.id,
            "date": e.created_at.isoformat() if e.created_at else None,
            "property_id": e.warehouse_id,
            "property_address": property_address,
            "engagement_id": e.deal_id or "",
            "type": e.entry_type or "monthly_deposit",
            "amount": e.amount,
            "status": e.status or "pending",
        })

    return items


@router.get("/payments/summary")
async def get_payment_summary(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return payment summary matching frontend PaymentSummary type."""
    properties = await _get_supplier_properties(db, user)
    prop_ids = [p.id for p in properties]

    if not prop_ids:
        return {
            "total_earned": 0.0,
            "this_month": 0.0,
            "next_deposit": 0.0,
            "next_deposit_date": "",
            "pending_amount": 0.0,
            "active_engagements": 0,
        }

    # Total earned (paid entries)
    paid_result = await db.execute(
        select(func.coalesce(func.sum(SupplierLedger.amount), 0.0))
        .where(
            SupplierLedger.warehouse_id.in_(prop_ids),
            SupplierLedger.status == "paid",
        )
    )
    total_earned = float(paid_result.scalar() or 0.0)

    # This month earnings
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    this_month_result = await db.execute(
        select(func.coalesce(func.sum(SupplierLedger.amount), 0.0))
        .where(
            SupplierLedger.warehouse_id.in_(prop_ids),
            SupplierLedger.status == "paid",
            SupplierLedger.created_at >= month_start,
        )
    )
    this_month = float(this_month_result.scalar() or 0.0)

    # Total pending
    pending_result = await db.execute(
        select(func.coalesce(func.sum(SupplierLedger.amount), 0.0))
        .where(
            SupplierLedger.warehouse_id.in_(prop_ids),
            SupplierLedger.status == "pending",
        )
    )
    pending_amount = float(pending_result.scalar() or 0.0)

    # Next scheduled deposit
    next_deposit_result = await db.execute(
        select(SupplierLedger)
        .where(
            SupplierLedger.warehouse_id.in_(prop_ids),
            SupplierLedger.status.in_(["pending", "scheduled"]),
        )
        .order_by(SupplierLedger.created_at.asc())
        .limit(1)
    )
    next_payment = next_deposit_result.scalar_one_or_none()

    # Count active engagements (active deals)
    active_deals_result = await db.execute(
        select(func.count(Deal.id))
        .where(
            Deal.warehouse_id.in_(prop_ids),
            Deal.status.in_(["active", "confirmed"]),
        )
    )
    active_engagements = int(active_deals_result.scalar() or 0)

    return {
        "total_earned": round(total_earned, 2),
        "this_month": round(this_month, 2),
        "next_deposit": round(next_payment.amount, 2) if next_payment else 0.0,
        "next_deposit_date": next_payment.created_at.isoformat() if next_payment and next_payment.created_at else "",
        "pending_amount": round(pending_amount, 2),
        "active_engagements": active_engagements,
    }


@router.get("/payments/export")
async def export_payments(
    request: Request,
    format: str = Query("json", description="Export format: json or csv"),
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Export payment data for accounting purposes."""
    properties = await _get_supplier_properties(db, user)
    prop_ids = [p.id for p in properties]

    if not prop_ids:
        return {"payments": [], "count": 0, "format": format}

    result = await db.execute(
        select(SupplierLedger)
        .where(SupplierLedger.warehouse_id.in_(prop_ids))
        .order_by(SupplierLedger.created_at.desc())
    )
    entries = result.scalars().all()

    items = [
        {
            "id": e.id,
            "warehouse_id": e.warehouse_id,
            "deal_id": e.deal_id,
            "entry_type": e.entry_type,
            "amount": e.amount,
            "description": e.description,
            "period_start": e.period_start.isoformat() if e.period_start else None,
            "period_end": e.period_end.isoformat() if e.period_end else None,
            "status": e.status,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in entries
    ]

    if format == "csv":
        # Return CSV-ready data (actual CSV response can be added later)
        import csv
        import io
        from fastapi.responses import StreamingResponse

        output = io.StringIO()
        if items:
            writer = csv.DictWriter(output, fieldnames=items[0].keys())
            writer.writeheader()
            writer.writerows(items)

        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=payments_export.csv"},
        )

    return {"payments": items, "count": len(items), "format": format}


# ---------------------------------------------------------------------------
# Account & Team
# ---------------------------------------------------------------------------


@router.get("/account")
async def get_account(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return current user account info."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "company": user.company,
        "phone": user.phone,
        "role": user.role,
        "company_id": user.company_id,
        "company_role": user.company_role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
    }


@router.patch("/account")
async def update_account(
    body: AccountUpdate,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update current user account info."""
    updates = body.model_dump(exclude_unset=True)

    if "name" in updates and updates["name"] is not None:
        user.name = updates["name"]
    if "company" in updates and updates["company"] is not None:
        user.company = updates["company"]
    if "phone" in updates and updates["phone"] is not None:
        user.phone = updates["phone"]
    # Email changes require verification; placeholder for now
    if "email" in updates and updates["email"] is not None:
        user.email = updates["email"]

    await db.commit()
    await db.refresh(user)

    return {
        "ok": True,
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "company": user.company,
        "phone": user.phone,
    }


@router.post("/account/password")
async def change_password(
    body: PasswordChange,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Change current user's password."""
    from wex_platform.services.auth_service import verify_password, hash_password

    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    user.password_hash = hash_password(body.new_password)
    await db.commit()

    return {"ok": True, "message": "Password updated successfully"}


@router.get("/account/notifications")
async def get_notification_preferences(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return notification preferences for the current user."""
    # Placeholder: In the future, store in a user_preferences table
    return {
        "deal_pings_sms": False,
        "deal_pings_email": True,
        "tour_requests_sms": False,
        "tour_requests_email": True,
        "agreement_ready_email": True,
        "payment_deposited_email": True,
        "profile_suggestions_email": True,
        "monthly_summary_email": True,
    }


@router.patch("/account/notifications")
async def update_notification_preferences(
    body: NotificationPreferences,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update notification preferences for the current user."""
    # Placeholder: In the future, persist to a user_preferences table
    updates = body.model_dump(exclude_unset=True)
    return {"ok": True, "updated_preferences": updates}


@router.get("/team")
async def list_team(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """List team members in the same company."""
    def _member_status(m: User) -> str:
        """Map is_active + email_verified to TeamMemberStatus."""
        if not m.is_active:
            return "disabled"
        if not m.email_verified:
            return "invited"
        return "active"

    if not user.company_id:
        # Solo supplier -- just return themselves
        return [
            {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.company_role or "admin",
                "status": _member_status(user),
                "joined_at": user.created_at.isoformat() if user.created_at else None,
                "invited_at": None,
            }
        ]

    result = await db.execute(
        select(User).where(User.company_id == user.company_id)
    )
    members = result.scalars().all()

    return [
        {
            "id": m.id,
            "email": m.email,
            "name": m.name,
            "role": m.company_role or "member",
            "status": _member_status(m),
            "joined_at": m.created_at.isoformat() if m.created_at and m.email_verified else None,
            "invited_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in members
    ]


@router.post("/team/invite")
async def invite_team_member(
    body: TeamInvite,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Invite a new team member to the supplier's company."""
    # Check if the user has admin privileges
    if user.company_role and user.company_role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can invite team members")

    # Check if email already exists
    existing = await db.execute(
        select(User).where(func.lower(User.email) == func.lower(body.email))
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email already registered")

    # Ensure company_id exists
    company_id = user.company_id
    if not company_id:
        company_id = str(uuid.uuid4())
        user.company_id = company_id

    # Default name to email prefix if not provided
    invite_name = body.name or body.email.split("@")[0]

    # Placeholder: In production, send an invite email instead of creating directly
    # For now, return the invite details
    return {
        "ok": True,
        "message": f"Invitation sent to {body.email}",
        "invite": {
            "email": body.email,
            "name": invite_name,
            "role": body.role,
            "company_id": company_id,
        },
    }


@router.delete("/team/{user_id}")
async def remove_team_member(
    user_id: str,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Remove a team member from the company."""
    if user.company_role and user.company_role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can remove team members")

    if user_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="User is not in your company")

    target.company_id = None
    target.company_role = None
    target.is_active = False
    await db.commit()

    return {"ok": True, "removed_user_id": user_id}


@router.patch("/team/{user_id}")
async def update_team_member(
    user_id: str,
    body: TeamMemberUpdate,
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Update a team member's role or status."""
    if user.company_role and user.company_role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can update team members")

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    target = result.scalar_one_or_none()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.company_id != user.company_id:
        raise HTTPException(status_code=403, detail="User is not in your company")

    if body.role is not None:
        target.company_role = body.role
    if body.is_active is not None:
        target.is_active = body.is_active

    await db.commit()

    return {
        "ok": True,
        "user_id": user_id,
        "role": target.company_role,
        "is_active": target.is_active,
    }


# ---------------------------------------------------------------------------
# Suggestions (portfolio-level)
# ---------------------------------------------------------------------------


@router.get("/suggestions")
async def get_portfolio_suggestions(
    request: Request,
    user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Return portfolio-level suggestions for the supplier."""
    properties = await _get_supplier_properties(db, user)

    suggestions = []

    # Check for properties without photos
    no_photos = [p for p in properties if not p.primary_image_url]
    if no_photos:
        suggestions.append({
            "id": "sug_portfolio_photos",
            "type": "add_photos",
            "priority": "high",
            "title": f"{len(no_photos)} properties need photos",
            "description": "Properties with photos get significantly more buyer interest. Add photos to improve visibility.",
            "affected_properties": [p.id for p in no_photos],
        })

    # Check for inactive properties
    inactive = [p for p in properties if not p.listing or p.listing.activation_status != "on"]
    if inactive:
        suggestions.append({
            "id": "sug_portfolio_activate",
            "type": "activate_properties",
            "priority": "medium",
            "title": f"{len(inactive)} properties are not active",
            "description": "Activate these properties to start receiving buyer matches.",
            "affected_properties": [p.id for p in inactive],
        })

    # Check for properties with low rates
    active_with_rates = [
        p for p in properties
        if p.listing and p.listing.supplier_rate_per_sqft
    ]
    if active_with_rates:
        rates = [p.listing.supplier_rate_per_sqft for p in active_with_rates]
        avg = sum(rates) / len(rates)
        low_rate = [p for p in active_with_rates if p.listing.supplier_rate_per_sqft < avg * 0.7]
        if low_rate:
            suggestions.append({
                "id": "sug_portfolio_pricing",
                "type": "review_pricing",
                "priority": "low",
                "title": f"{len(low_rate)} properties may be underpriced",
                "description": "These properties have rates significantly below your portfolio average. Consider a pricing review.",
                "affected_properties": [p.id for p in low_rate],
            })

    return suggestions
