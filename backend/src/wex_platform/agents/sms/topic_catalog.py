"""Topic catalog — maps buyer questions to PropertyKnowledge field keys."""

import re

TOPIC_TO_FIELD_KEYS = {
    "clear_height": {
        "keywords": ["ceiling", "height", "clearance", "clear height"],
        "field_keys": ["clear_height_ft"],
    },
    "dock_doors": {
        "keywords": ["dock", "loading dock", "dock door"],
        "field_keys": ["dock_doors", "dock_doors_receiving", "dock_doors_shipping"],
    },
    "power": {
        "keywords": ["power", "electric", "amps", "voltage", "3 phase", "three phase"],
        "field_keys": ["power_supply"],
    },
    "office": {
        "keywords": ["office", "office space"],
        "field_keys": ["has_office"],
    },
    "sprinkler": {
        "keywords": ["sprinkler", "fire suppression", "fire protection"],
        "field_keys": ["has_sprinkler"],
    },
    "parking": {
        "keywords": ["parking", "trailer parking", "truck parking"],
        "field_keys": ["parking_spaces", "trailer_parking"],
    },
    "size": {
        "keywords": ["how big", "square feet", "square footage", "size", "how large"],
        "field_keys": ["building_size_sqft"],
    },
    "year_built": {
        "keywords": ["year built", "how old", "when built", "age of"],
        "field_keys": ["year_built", "year_renovated"],
    },
    "construction": {
        "keywords": ["construction", "material", "tilt-up", "steel", "concrete"],
        "field_keys": ["construction_type"],
    },
    "zoning": {
        "keywords": ["zoning", "zone", "zoned for"],
        "field_keys": ["zoning"],
    },
    "rail": {
        "keywords": ["rail", "railroad", "rail siding", "rail served"],
        "field_keys": ["rail_served"],
    },
    "yard": {
        "keywords": ["yard", "fenced", "outdoor storage", "fenced yard"],
        "field_keys": ["fenced_yard"],
    },
    "rate": {
        "keywords": ["rate", "price", "cost", "how much", "per sqft", "per square foot", "monthly"],
        "field_keys": ["supplier_rate_per_sqft"],  # This is on PropertyListing
    },
    "availability": {
        "keywords": ["available", "when available", "move in", "start date"],
        "field_keys": ["available_from", "available_to", "available_sqft"],
    },
}


def detect_topics(text: str) -> list[str]:
    """Detect property topics mentioned in text. Returns topic keys."""
    text_lower = text.lower()
    found = []
    for topic_key, config in TOPIC_TO_FIELD_KEYS.items():
        hits = sum(1 for kw in config["keywords"] if kw in text_lower)
        if hits >= 1:  # At least one keyword match
            found.append(topic_key)
    return found


def get_field_keys_for_topics(topics: list[str]) -> list[str]:
    """Get all field keys for a list of topics."""
    keys = []
    for topic in topics:
        if topic in TOPIC_TO_FIELD_KEYS:
            keys.extend(TOPIC_TO_FIELD_KEYS[topic]["field_keys"])
    return list(set(keys))
