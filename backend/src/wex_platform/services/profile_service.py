"""Property Profile Service — progressive AI-enriched property dossier.

Three triggers build the profile across the EarnCheck funnel:
  1. Gemini search completes → building specs + AI summary v1
  2. Configurator completed  → user preferences + AI summary v2
  3. Email submitted         → pricing + email + AI summary v3

AI Pipeline (2-step):
  Step 1 (Gemini 3 Flash): Analyze & understand — organizes raw data into
         a structured property profile summary.
  Step 2 (Gemini 2.5 Flash): Validate & extract — pulls structured field
         values from the summary text into DB columns.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from wex_platform.domain.models import PropertyProfile, Warehouse
from wex_platform.infra.database import async_session

logger = logging.getLogger(__name__)

# Structured fields that Step 2 AI can extract from any text
EXTRACTABLE_FIELDS = [
    "building_size_sqft", "clear_height_ft", "dock_doors", "drive_in_bays",
    "parking_spaces", "year_built", "construction_type", "has_sprinkler",
    "power_supply", "zoning", "building_class", "trailer_parking",
    "rail_served", "fenced_yard", "column_spacing_ft", "number_of_stories",
    "warehouse_heated", "year_renovated", "available_sqft", "lot_size_acres",
    "activity_tier", "has_office", "weekend_access", "min_term_months",
    "availability_start", "pricing_path", "rate_per_sqft", "sqft",
    "min_rentable",
]

# Fields that are boolean
BOOL_FIELDS = {
    "has_sprinkler", "rail_served", "fenced_yard", "warehouse_heated",
    "has_office", "weekend_access",
}

# Fields that are integer
INT_FIELDS = {
    "building_size_sqft", "dock_doors", "drive_in_bays", "parking_spaces",
    "year_built", "trailer_parking", "number_of_stories", "year_renovated",
    "available_sqft", "min_term_months", "sqft", "min_rentable",
}

# Fields that are float
FLOAT_FIELDS = {"clear_height_ft", "lot_size_acres", "rate_per_sqft"}


# ---------------------------------------------------------------------------
# Trigger 1: Gemini search completes
# ---------------------------------------------------------------------------

async def create_profile_from_search(
    session_id: str,
    warehouse_id: str,
    property_data: dict,
    city: str = "",
    state: str = "",
    zip_code: str = "",
    address: str = "",
    is_test: bool = False,
):
    """Create a PropertyProfile row from Gemini search results (Trigger 1).

    Called as a background task after create_warehouse_from_search().
    Creates its own DB session so it can run independently.
    """
    async with async_session() as db:
        try:
            profile = PropertyProfile(
                session_id=session_id,
                warehouse_id=warehouse_id,
                address=address,
                city=city or property_data.get("city", ""),
                state=state or property_data.get("state", ""),
                zip=zip_code or property_data.get("zip_code", ""),
                # Building specs from Gemini
                building_size_sqft=_safe_int(property_data.get("building_size_sqft")),
                clear_height_ft=_safe_float(property_data.get("clear_height_ft")),
                dock_doors=_safe_int(property_data.get("dock_doors")),
                drive_in_bays=_safe_int(property_data.get("drive_in_bays")),
                parking_spaces=_safe_int(property_data.get("parking_spaces")),
                year_built=_safe_int(property_data.get("year_built")),
                construction_type=property_data.get("construction_type"),
                has_sprinkler=_safe_bool(property_data.get("sprinkler_system")),
                power_supply=property_data.get("power_supply"),
                zoning=property_data.get("zoning"),
                # Extended specs (currently JSON-only in contextual_memories)
                building_class=property_data.get("building_class"),
                trailer_parking=_safe_int(property_data.get("trailer_parking")),
                rail_served=_safe_bool(property_data.get("rail_served")),
                fenced_yard=_safe_bool(property_data.get("fenced_yard")),
                column_spacing_ft=property_data.get("column_spacing_ft"),
                number_of_stories=_safe_int(property_data.get("number_of_stories")),
                warehouse_heated=_safe_bool(property_data.get("warehouse_heated")),
                year_renovated=_safe_int(property_data.get("year_renovated")),
                available_sqft=_safe_int(property_data.get("available_sqft")),
                lot_size_acres=_safe_float(property_data.get("lot_size_acres")),
                has_office=_safe_bool(property_data.get("has_office_space")),
                is_test=is_test,
                # sqft is set later by Trigger 2 (configurator) — not from building_size_sqft
            )

            # Copy images from linked Warehouse record
            if warehouse_id:
                wh_result = await db.execute(
                    select(Warehouse).where(Warehouse.id == warehouse_id)
                )
                wh = wh_result.scalar_one_or_none()
                if wh:
                    profile.primary_image_url = wh.primary_image_url
                    profile.image_urls = wh.image_urls or []

            db.add(profile)
            await db.commit()
            logger.info("[Profile] Created profile for session=%s, address=%s", session_id, address)

            # Run AI summary
            await _run_ai_pipeline(db, profile, _build_search_context(property_data, address))

        except Exception as exc:
            logger.error("[Profile] Failed to create profile for session=%s: %s", session_id, exc)
            await db.rollback()


# ---------------------------------------------------------------------------
# Trigger 2: Configurator completed
# ---------------------------------------------------------------------------

async def update_profile_configurator(session_id: str, properties: dict):
    """Update profile with configurator choices (Trigger 2).

    Called as a background task when configurator_completed event fires.
    Creates its own DB session so it can run independently.
    """
    async with async_session() as db:
        try:
            profile = await _get_profile(db, session_id)
            if not profile:
                # No profile yet (address wasn't found by Gemini) — create a minimal one
                profile = PropertyProfile(
                    session_id=session_id,
                    address=properties.get("address", ""),
                    state=properties.get("state", ""),
                )
                db.add(profile)

            # Update structured columns
            profile.activity_tier = properties.get("activityTier", profile.activity_tier)
            profile.has_office = _safe_bool(properties.get("hasOffice", profile.has_office))
            profile.weekend_access = _safe_bool(properties.get("weekendAccess", profile.weekend_access))
            profile.min_term_months = _safe_int(properties.get("minTermMonths", profile.min_term_months))
            profile.sqft = _safe_int(properties.get("sqft", profile.sqft))
            profile.min_rentable = _safe_int(properties.get("minRentable", profile.min_rentable))
            profile.availability_start = properties.get("availabilityStart", profile.availability_start)

            if properties.get("is_test"):
                profile.is_test = True

            # Capture additional notes (currently LOST)
            notes = properties.get("additionalNotes", "")
            if notes and notes.strip():
                profile.additional_notes = notes.strip()

            profile.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("[Profile] Updated configurator for session=%s", session_id)

            # Re-run AI to incorporate configurator choices + notes
            context = _build_configurator_context(profile, properties)
            await _run_ai_pipeline(db, profile, context)

        except Exception as exc:
            logger.error("[Profile] Failed to update configurator for session=%s: %s", session_id, exc)
            await db.rollback()


# ---------------------------------------------------------------------------
# Trigger 3: Email submitted
# ---------------------------------------------------------------------------

async def update_profile_email(session_id: str, properties: dict):
    """Update profile with email + pricing info (Trigger 3).

    Called as a background task when email_submitted event fires.
    Creates its own DB session so it can run independently.
    """
    async with async_session() as db:
        try:
            profile = await _get_profile(db, session_id)
            if not profile:
                profile = PropertyProfile(
                    session_id=session_id,
                    address=properties.get("address", ""),
                    city=properties.get("city", ""),
                    state=properties.get("state", ""),
                    zip=properties.get("zip", ""),
                )
                db.add(profile)

            profile.email = properties.get("email", profile.email)
            profile.pricing_path = properties.get("pricingPath", profile.pricing_path)
            profile.rate_per_sqft = _safe_float(properties.get("rateAsk", profile.rate_per_sqft))
            profile.market_rate_low = _safe_float(properties.get("market_rate_low", profile.market_rate_low))
            profile.market_rate_high = _safe_float(properties.get("market_rate_high", profile.market_rate_high))
            profile.recommended_rate = _safe_float(properties.get("recommended_rate", profile.recommended_rate))
            profile.sqft = _safe_int(properties.get("sqft", profile.sqft))

            if properties.get("is_test"):
                profile.is_test = True

            # Capture additional notes if sent
            notes = properties.get("additionalNotes", "")
            if notes and notes.strip() and not profile.additional_notes:
                profile.additional_notes = notes.strip()

            profile.updated_at = datetime.now(timezone.utc)
            await db.commit()
            logger.info("[Profile] Updated email for session=%s, email=%s", session_id, profile.email)

            # Final AI summary with pricing
            context = _build_email_context(profile, properties)
            await _run_ai_pipeline(db, profile, context)

        except Exception as exc:
            logger.error("[Profile] Failed to update email for session=%s: %s", session_id, exc)
            await db.rollback()


# ---------------------------------------------------------------------------
# AI Pipeline (2-step)
# ---------------------------------------------------------------------------

async def _run_ai_pipeline(db: AsyncSession, profile: PropertyProfile, raw_context: str):
    """Run the 2-step AI pipeline to generate/update the profile summary.

    Step 1 (Gemini 3 Flash): Analyze raw data → organized summary
    Step 2 (Gemini 2.5 Flash): Extract structured fields from summary → DB columns
    """
    try:
        from wex_platform.infra.gemini_client import get_model

        existing_summary = profile.ai_profile_summary or ""

        # --- Step 1: Gemini 3 Flash — Analyze & Understand ---
        step1_prompt = (
            "You are a commercial real estate data analyst for Warehouse Exchange (WEx). "
            "Analyze the following warehouse property data and create a structured property profile. "
            "Organize into these sections:\n"
            "## Building Specs\n## Location & Access\n## Operational Preferences\n"
            "## Pricing\n## Additional Notes\n\n"
            "Rules:\n"
            "- Fix any spelling errors in user-provided text\n"
            "- Include ALL details — highway proximity, rail access, building class, features, etc.\n"
            "- Be concise but miss nothing\n"
            "- If updating an existing profile, merge new info with existing (don't lose old data)\n"
        )

        if existing_summary:
            step1_input = (
                f"EXISTING PROFILE (update with new data below):\n{existing_summary}\n\n"
                f"NEW DATA TO INCORPORATE:\n{raw_context}"
            )
        else:
            step1_input = f"RAW PROPERTY DATA:\n{raw_context}"

        model_step1 = get_model(
            model_name="gemini-3-flash-preview",
            temperature=0.3,
            system_instruction=step1_prompt,
        )
        response1 = await asyncio.to_thread(model_step1.generate_content, step1_input)
        summary = response1.text.strip() if response1.text else ""

        if not summary:
            logger.warning("[Profile AI] Step 1 returned empty summary for session=%s", profile.session_id)
            return

        # --- Step 2: Gemini 2.5 Flash — Extract structured fields ---
        fields_list = ", ".join(EXTRACTABLE_FIELDS)
        step2_prompt = (
            "You are a data extraction tool. Given a property profile summary, "
            "extract structured field values as JSON.\n\n"
            "Return a JSON object with two keys:\n"
            '  "summary": the final clean profile summary text (same as input, minor cleanup only)\n'
            '  "fields": an object mapping field names to extracted values\n\n'
            f"Fields to extract: {fields_list}\n\n"
            "Rules:\n"
            "- Return null for any field you cannot determine from the text\n"
            "- Boolean fields: return true/false\n"
            "- Integer fields: return numbers without commas\n"
            "- Only extract values explicitly stated in the text\n"
            "- Return ONLY valid JSON, no markdown fences\n"
        )

        model_step2 = get_model(
            model_name="gemini-3-flash-preview",
            temperature=0.1,
            json_mode=True,
            system_instruction=step2_prompt,
        )
        response2 = await asyncio.to_thread(model_step2.generate_content, f"PROPERTY PROFILE:\n{summary}")
        raw_json = response2.text.strip() if response2.text else ""

        if not raw_json:
            # Step 2 failed — still save the summary from Step 1
            profile.ai_profile_summary = summary
            profile.profile_version = (profile.profile_version or 0) + 1
            profile.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # Parse Step 2 output
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError:
            logger.warning("[Profile AI] Step 2 JSON parse failed, saving summary only")
            profile.ai_profile_summary = summary
            profile.profile_version = (profile.profile_version or 0) + 1
            profile.updated_at = datetime.now(timezone.utc)
            await db.commit()
            return

        # Update summary
        final_summary = parsed.get("summary", summary)
        profile.ai_profile_summary = final_summary
        profile.profile_version = (profile.profile_version or 0) + 1

        # Update structured columns from AI extraction
        fields = parsed.get("fields", {})
        _apply_extracted_fields(profile, fields)

        profile.updated_at = datetime.now(timezone.utc)
        await db.commit()
        logger.info(
            "[Profile AI] Pipeline complete for session=%s, version=%d, fields_extracted=%d",
            profile.session_id, profile.profile_version,
            sum(1 for v in fields.values() if v is not None),
        )

    except Exception as exc:
        logger.error("[Profile AI] Pipeline failed for session=%s: %s", profile.session_id, exc)
        # Don't rollback — the profile row itself is already committed


# ---------------------------------------------------------------------------
# Context builders (format raw data for AI input)
# ---------------------------------------------------------------------------

def _build_search_context(property_data: dict, address: str) -> str:
    """Build AI input from Gemini search results."""
    lines = [f"Address: {address}"]

    # Core specs
    for key in ["building_size_sqft", "lot_size_acres", "year_built", "year_renovated",
                "construction_type", "zoning", "property_type", "building_class",
                "clear_height_ft", "dock_doors", "drive_in_bays", "parking_spaces",
                "sprinkler_system", "power_supply", "has_office_space",
                "trailer_parking", "rail_served", "fenced_yard", "column_spacing_ft",
                "number_of_stories", "warehouse_heated", "available_sqft"]:
        val = property_data.get(key)
        if val is not None:
            lines.append(f"{key}: {val}")

    # Rich text fields
    overview = property_data.get("property_overview")
    if overview:
        lines.append(f"\nProperty Overview: {overview}")

    features = property_data.get("additional_features", [])
    if features:
        lines.append(f"\nAdditional Features: {', '.join(str(f) for f in features)}")

    sources = property_data.get("source_urls", [])
    if sources:
        lines.append(f"\nData Sources: {', '.join(sources[:5])}")

    city = property_data.get("city", "")
    state = property_data.get("state", "")
    if city or state:
        lines.append(f"Location: {city}, {state} {property_data.get('zip_code', '')}")

    return "\n".join(lines)


def _build_configurator_context(profile: PropertyProfile, properties: dict) -> str:
    """Build AI input from configurator choices."""
    lines = ["User configurator choices:"]

    tier = properties.get("activityTier", "")
    if tier:
        label = "Storage + Light Assembly" if tier == "storage_light_assembly" else "Storage Only"
        lines.append(f"Activity Type: {label}")

    if properties.get("hasOffice"):
        lines.append("Office Space: Included")
    if properties.get("weekendAccess"):
        lines.append("Weekend Access: Available")

    term = properties.get("minTermMonths")
    if term:
        lines.append(f"Minimum Lease Term: {term} months")

    avail = properties.get("availabilityStart")
    if avail:
        lines.append(f"Available From: {avail}")

    sqft = properties.get("sqft")
    if sqft:
        lines.append(f"Available Space: {sqft:,} sqft")

    min_rent = properties.get("minRentable")
    if min_rent:
        lines.append(f"Minimum Rentable Unit: {min_rent:,} sqft")

    notes = properties.get("additionalNotes", "").strip()
    if notes:
        lines.append(f"\nAdditional Notes from Owner: {notes}")

    return "\n".join(lines)


def _build_email_context(profile: PropertyProfile, properties: dict) -> str:
    """Build AI input from email submission."""
    lines = ["Email submission / pricing info:"]

    email = properties.get("email", "")
    if email:
        lines.append(f"Owner Email: {email}")

    path = properties.get("pricingPath", "")
    if path:
        label = "Set Rate (Automated)" if path == "set_rate" else "Commission (Manual)"
        lines.append(f"Pricing Model: {label}")

    rate = properties.get("rateAsk")
    if rate:
        lines.append(f"Rate: ${rate}/sqft/mo")

    revenue = properties.get("revenue")
    if revenue:
        lines.append(f"Estimated Annual Revenue: ${revenue:,}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_profile(db: AsyncSession, session_id: str) -> PropertyProfile | None:
    """Find existing profile by session_id."""
    result = await db.execute(
        select(PropertyProfile).where(PropertyProfile.session_id == session_id)
    )
    return result.scalar_one_or_none()


def _apply_extracted_fields(profile: PropertyProfile, fields: dict):
    """Apply AI-extracted field values to profile columns (non-null only)."""
    for field_name in EXTRACTABLE_FIELDS:
        value = fields.get(field_name)
        if value is None:
            continue

        # Don't overwrite existing values with AI extraction if already set directly
        current = getattr(profile, field_name, None)
        if current is not None:
            continue

        # Type coercion
        if field_name in BOOL_FIELDS:
            value = _safe_bool(value)
        elif field_name in INT_FIELDS:
            value = _safe_int(value)
        elif field_name in FLOAT_FIELDS:
            value = _safe_float(value)
        else:
            value = str(value) if value else None

        if value is not None:
            setattr(profile, field_name, value)


def _safe_int(val) -> int | None:
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace(",", "").strip()
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _safe_float(val) -> float | None:
    if val is None:
        return None
    try:
        if isinstance(val, str):
            val = val.replace(",", "").strip()
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_bool(val) -> bool | None:
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1", "y")
    return bool(val)
