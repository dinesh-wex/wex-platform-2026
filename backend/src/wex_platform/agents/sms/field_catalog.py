"""Field catalog — defines how each property attribute is formatted for SMS."""

FIELD_CATALOG = {
    "clear_height_ft": {
        "table": "knowledge",
        "column": "clear_height_ft",
        "label": "Clear height",
        "format_fn": lambda v: f"{v} ft" if v else "Not specified",
    },
    "dock_doors": {
        "table": "knowledge",
        "column": "dock_doors",
        "label": "Dock doors",
        "format_fn": lambda v: f"{v} dock doors" if v else "Not specified",
    },
    "dock_doors_receiving": {
        "table": "knowledge",
        "column": "dock_doors_receiving",
        "label": "Receiving docks",
        "format_fn": lambda v: str(v) if v else "Not specified",
    },
    "dock_doors_shipping": {
        "table": "knowledge",
        "column": "dock_doors_shipping",
        "label": "Shipping docks",
        "format_fn": lambda v: str(v) if v else "Not specified",
    },
    "power_supply": {
        "table": "knowledge",
        "column": "power_supply",
        "label": "Power",
        "format_fn": lambda v: v if v else "Not specified",
    },
    "has_office": {
        "table": "knowledge",
        "column": "has_office",
        "label": "Office space",
        "format_fn": lambda v: "Yes" if v else "No" if v is not None else "Not specified",
    },
    "has_sprinkler": {
        "table": "knowledge",
        "column": "has_sprinkler",
        "label": "Sprinkler system",
        "format_fn": lambda v: "Yes" if v else "No" if v is not None else "Not specified",
    },
    "parking_spaces": {
        "table": "knowledge",
        "column": "parking_spaces",
        "label": "Parking spaces",
        "format_fn": lambda v: str(v) if v else "Not specified",
    },
    "trailer_parking": {
        "table": "knowledge",
        "column": "trailer_parking",
        "label": "Trailer parking",
        "format_fn": lambda v: f"{v} spots" if v else "Not specified",
    },
    "building_size_sqft": {
        "table": "knowledge",
        "column": "building_size_sqft",
        "label": "Building size",
        "format_fn": lambda v: f"{v:,} sqft" if v else "Not specified",
    },
    "year_built": {
        "table": "knowledge",
        "column": "year_built",
        "label": "Year built",
        "format_fn": lambda v: str(v) if v else "Not specified",
    },
    "year_renovated": {
        "table": "knowledge",
        "column": "year_renovated",
        "label": "Year renovated",
        "format_fn": lambda v: str(v) if v else "Not specified",
    },
    "construction_type": {
        "table": "knowledge",
        "column": "construction_type",
        "label": "Construction",
        "format_fn": lambda v: v if v else "Not specified",
    },
    "zoning": {
        "table": "knowledge",
        "column": "zoning",
        "label": "Zoning",
        "format_fn": lambda v: v if v else "Not specified",
    },
    "rail_served": {
        "table": "knowledge",
        "column": "rail_served",
        "label": "Rail served",
        "format_fn": lambda v: "Yes" if v else "No" if v is not None else "Not specified",
    },
    "fenced_yard": {
        "table": "knowledge",
        "column": "fenced_yard",
        "label": "Fenced yard",
        "format_fn": lambda v: "Yes" if v else "No" if v is not None else "Not specified",
    },
    "supplier_rate_per_sqft": {
        "table": "listing",
        "column": "supplier_rate_per_sqft",
        "label": "Rate",
        "format_fn": lambda v: f"${v:.2f}/sqft" if v else "Not specified",
    },
    "available_sqft": {
        "table": "listing",
        "column": "available_sqft",
        "label": "Available space",
        "format_fn": lambda v: f"{v:,} sqft" if v else "Not specified",
    },
    "available_from": {
        "table": "listing",
        "column": "available_from",
        "label": "Available from",
        "format_fn": lambda v: v.strftime("%B %Y") if v else "Now",
    },
    "available_to": {
        "table": "listing",
        "column": "available_to",
        "label": "Available to",
        "format_fn": lambda v: v.strftime("%B %Y") if v else "Open-ended",
    },
    "lot_size_acres": {
        "table": "knowledge",
        "column": "lot_size_acres",
        "label": "Lot size",
        "format_fn": lambda v: f"{v:.1f} acres" if v else "Not specified",
    },
    "activity_tier": {
        "table": "knowledge",
        "column": "activity_tier",
        "label": "Activity level",
        "format_fn": lambda v: v.replace("_", " ").title() if v else "Not specified",
    },
}


def format_field(field_key: str, value) -> str | None:
    """Format a field value for SMS display. Returns None if field unknown."""
    entry = FIELD_CATALOG.get(field_key)
    if not entry:
        return None
    return entry["format_fn"](value)


def get_label(field_key: str) -> str:
    """Get human-readable label for a field key."""
    entry = FIELD_CATALOG.get(field_key)
    return entry["label"] if entry else field_key.replace("_", " ").title()
