"""Backward-compatible serialization: Property tables -> old Warehouse-shaped API responses.

This layer ensures frontend consumers continue receiving the same JSON shape they expect
while the backend reads from the new Property/PropertyKnowledge/PropertyListing tables.
"""

from wex_platform.domain.models import Property, PropertyKnowledge, PropertyListing, PropertyContact


def serialize_property_as_warehouse(
    prop: Property,
    pk: PropertyKnowledge | None = None,
    pl: PropertyListing | None = None,
    contacts: list[PropertyContact] | None = None,
) -> dict:
    """Produce the old Warehouse-shaped response dict from new tables."""
    pk = pk or prop.knowledge
    pl = pl or prop.listing
    primary_contact = None
    if contacts:
        primary_contact = next((c for c in contacts if c.is_primary), contacts[0] if contacts else None)
    elif prop.contacts:
        primary_contact = next((c for c in prop.contacts if c.is_primary), prop.contacts[0] if prop.contacts else None)

    return {
        "id": prop.id,
        "address": prop.address,
        "city": prop.city,
        "state": prop.state,
        "zip": prop.zip,
        "lat": prop.lat,
        "lng": prop.lng,
        "neighborhood": prop.neighborhood,
        "building_size_sqft": pk.building_size_sqft if pk else None,
        "available_sqft": pl.available_sqft if pl else None,
        "lot_size_acres": pk.lot_size_acres if pk else None,
        "year_built": pk.year_built if pk else None,
        "construction_type": pk.construction_type if pk else None,
        "zoning": pk.zoning if pk else None,
        "property_type": prop.property_type,
        "primary_image_url": prop.primary_image_url,
        "image_urls": prop.image_urls or [],
        "description": pk.additional_notes if pk else None,
        "supplier_status": _relationship_to_supplier_status(prop.relationship_status),
        "owner_name": primary_contact.name if primary_contact else None,
        "owner_email": primary_contact.email if primary_contact else None,
        "owner_phone": primary_contact.phone if primary_contact else None,
        "company_id": prop.company_id,
        "created_at": prop.created_at.isoformat() if prop.created_at else None,
        "updated_at": prop.updated_at.isoformat() if prop.updated_at else None,
        "truth_core": serialize_truth_core_compat(prop, pk, pl) if pl else None,
    }


def serialize_truth_core_compat(
    prop: Property,
    pk: PropertyKnowledge | None = None,
    pl: PropertyListing | None = None,
) -> dict:
    """Produce the old TruthCore-shaped dict from new tables."""
    pk = pk or prop.knowledge
    pl = pl or prop.listing
    return {
        "warehouse_id": prop.id,
        "activation_status": pl.activation_status if pl else "off",
        "min_sqft": pl.min_sqft if pl else None,
        "max_sqft": pl.max_sqft if pl else None,
        "min_term_months": pl.min_term_months if pl else 1,
        "max_term_months": pl.max_term_months if pl else 12,
        "activity_tier": pk.activity_tier if pk else None,
        "constraints": pl.constraints if pl else {},
        "supplier_rate_per_sqft": pl.supplier_rate_per_sqft if pl else None,
        "buyer_rate_per_sqft": None,  # Computed at transaction time now
        "tour_readiness": pl.tour_readiness if pl else "48_hours",
        "trust_level": pl.trust_level if pl else 0,
        "clear_height_ft": pk.clear_height_ft if pk else None,
        "dock_doors_receiving": pk.dock_doors_receiving if pk else 0,
        "dock_doors_shipping": pk.dock_doors_shipping if pk else 0,
        "drive_in_bays": pk.drive_in_bays if pk else 0,
        "parking_spaces": pk.parking_spaces if pk else 0,
        "has_office_space": pk.has_office if pk else False,
        "has_sprinkler": pk.has_sprinkler if pk else False,
        "power_supply": pk.power_supply if pk else None,
        "available_from": pl.available_from.isoformat() if pl and pl.available_from else None,
        "available_to": pl.available_to.isoformat() if pl and pl.available_to else None,
    }


def _relationship_to_supplier_status(relationship_status: str | None) -> str:
    """Map new relationship_status back to old supplier_status for API compat."""
    mapping = {
        "prospect": "third_party",
        "contacted": "third_party",
        "interested": "interested",
        "earncheck_only": "earncheck_only",
        "active": "in_network",
        "declined": "third_party",
        "unresponsive": "third_party",
        "churned": "third_party",
    }
    return mapping.get(relationship_status or "", "third_party")
