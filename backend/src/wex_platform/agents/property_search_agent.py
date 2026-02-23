"""Property search agent using Gemini with Google Search grounding.

Uses the google-genai SDK to search for and extract commercial property data
through a multi-step pipeline:
  1. Grounded search with Google Search to find property information
  2. Evidence bundle parsing with structured section extraction
  3. Optional supplemental search if coverage is low
  4. Structured JSON extraction via a second LLM call
  5. Post-extraction validation, confidence scoring, and result classification
"""

import asyncio
import json
import logging
import re
import time
from typing import Optional

from google import genai
from google.genai import types

from wex_platform.agents.base import AgentResult
from wex_platform.services.validation_service import check_address_match, check_sanity_flags
from wex_platform.services.confidence_calculator import compute_confidence, compute_source_quality_summary
from wex_platform.agents.prompts.property_search import SEARCH_PROMPT, EXTRACTION_PROMPT, SUPPLEMENTAL_SEARCH_PROMPT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level parse tracking counters
# ---------------------------------------------------------------------------
_parse_attempts = 0
_parse_successes = 0  # at least 1 fact parsed from structured format


class PropertySearchAgent:
    """Multi-step pipeline: grounded search -> evidence parsing -> structured extraction."""

    # Fields used to determine whether a supplemental search is needed.
    _COVERAGE_FIELDS = ["building_size_sqft", "year_built", "clear_height_ft", "dock_doors"]
    # Timeout for individual Gemini API calls (seconds)
    _API_TIMEOUT = 90

    def __init__(self):
        from wex_platform.app.config import get_settings
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)

    # ------------------------------------------------------------------
    # Evidence bundle parsing
    # ------------------------------------------------------------------

    def _parse_evidence_bundle(self, raw_text: str) -> dict:
        """Parse structured output from the grounded search step.

        Splits on ``===SECTION===`` headers and extracts pipe-delimited
        facts and sources.  Defensive — falls back gracefully when sections
        are missing or malformed.

        Returns:
            A dict with keys: raw_text, property_identification, sources,
            facts, notes.
        """
        global _parse_attempts, _parse_successes
        _parse_attempts += 1

        result: dict = {
            "raw_text": raw_text,
            "property_identification": "",
            "sources": [],
            "facts": [],
            "notes": "",
        }

        if not raw_text:
            return result

        # Find section boundaries using regex that accepts synonyms.
        # e.g. ===PROPERTY IDENTIFICATION===, ===SOURCES===, ===FACTS===, etc.
        header_pattern = re.compile(r'={3,}\s*(\w[\w\s]*?\w?)\s*={3,}')
        headers = list(header_pattern.finditer(raw_text))

        if not headers:
            # No structured sections found — return raw text only.
            return result

        # Build a mapping of normalized section name -> text content
        sections: dict[str, str] = {}
        for i, match in enumerate(headers):
            name = match.group(1).strip().upper()
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(raw_text)
            sections[name] = raw_text[start:end].strip()

        # --- Property Identification ---
        for key in ("PROPERTY IDENTIFICATION", "PROPERTY_IDENTIFICATION", "IDENTIFICATION"):
            if key in sections:
                result["property_identification"] = sections[key]
                break

        # --- Sources ---
        sources_text = ""
        for key in ("SOURCES", "SOURCE"):
            if key in sections:
                sources_text = sections[key]
                break

        if sources_text:
            for line in sources_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                parsed_source = self._parse_pipe_delimited_line(line)
                if parsed_source:
                    result["sources"].append(parsed_source)

        # --- Facts ---
        facts_text = ""
        for key in ("FACTS", "FACT"):
            if key in sections:
                facts_text = sections[key]
                break

        seen_facts: set[tuple] = set()
        if facts_text:
            for line in facts_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                fact = self._parse_fact_line(line)
                if fact is None:
                    continue
                # Deduplicate by (field, value, source)
                dedup_key = (fact["field"], fact["value"], fact["source"])
                if dedup_key in seen_facts:
                    continue
                seen_facts.add(dedup_key)
                result["facts"].append(fact)

        # --- Notes ---
        for key in ("NOTES", "NOTE", "WARNINGS"):
            if key in sections:
                result["notes"] = sections[key]
                break

        # Track parse success
        if result["facts"]:
            _parse_successes += 1

        return result

    @staticmethod
    def _parse_pipe_delimited_line(line: str) -> dict | None:
        """Parse a single pipe-delimited line into a dict of key=value pairs.

        Each segment is split on the **first** ``=`` only, so values
        containing ``=``, ``/``, or commas are preserved intact.

        Returns None if no valid key=value pairs were found.
        """
        segments = line.split(" | ")
        parsed: dict[str, str] = {}
        for segment in segments:
            segment = segment.strip()
            if "=" not in segment:
                continue
            key, _, value = segment.partition("=")
            key = key.strip().lower()
            value = value.strip()
            if key and value:
                parsed[key] = value
        return parsed if parsed else None

    @staticmethod
    def _parse_fact_line(line: str) -> dict | None:
        """Parse a single fact line into a structured fact dict.

        Expected format:
            FIELD=VALUE | source=URL | type=source_type

        Returns:
            A dict with keys: field, value, source, type.
            Returns None if the line cannot be parsed into a valid fact.
        """
        segments = line.split(" | ")
        if not segments:
            return None

        # First segment is FIELD=VALUE
        first_segment = segments[0].strip()
        if "=" not in first_segment:
            return None

        field, _, value = first_segment.partition("=")
        field = field.strip().lower()
        value = value.strip()

        if not field or not value:
            return None

        # Parse remaining segments for source and type
        source = ""
        source_type = ""
        for segment in segments[1:]:
            segment = segment.strip()
            if "=" not in segment:
                continue
            key, _, val = segment.partition("=")
            key = key.strip().lower()
            val = val.strip()
            if key == "source":
                source = val
            elif key == "type":
                source_type = val

        return {
            "field": field,
            "value": value,
            "source": source,
            "type": source_type,
        }

    # ------------------------------------------------------------------
    # Supplemental search decision
    # ------------------------------------------------------------------

    def _needs_second_search(self, bundle: dict) -> bool:
        """Return True if 3+ of 4 coverage fields are missing from the bundle."""
        present_fields = {fact["field"] for fact in bundle.get("facts", [])}
        missing_count = sum(
            1 for f in self._COVERAGE_FIELDS if f not in present_fields
        )
        return missing_count >= 3

    # ------------------------------------------------------------------
    # Merge supplemental results
    # ------------------------------------------------------------------

    def _merge_supplemental(self, primary: dict, supplemental: dict) -> dict:
        """Merge supplemental facts into the primary evidence bundle.

        - Deduplicates by (field, value, source) tuple.
        - Prefers non-inferred sources over inferred: if primary has a field
          from an ``inferred`` source and supplemental has it from a
          non-inferred source, the supplemental fact replaces the primary.
        - Tracks conflicts: if the same field has different values from
          different sources, both are kept and a note is appended.
        - Merges supplemental sources list into primary.
        """
        merged = dict(primary)
        conflict_notes: list[str] = []

        # Index primary facts by field for fast lookup
        primary_by_field: dict[str, list[dict]] = {}
        for fact in merged["facts"]:
            primary_by_field.setdefault(fact["field"], []).append(fact)

        # Dedup set based on existing primary facts
        seen: set[tuple] = set()
        for fact in merged["facts"]:
            seen.add((fact["field"], fact["value"], fact["source"]))

        for supp_fact in supplemental.get("facts", []):
            dedup_key = (supp_fact["field"], supp_fact["value"], supp_fact["source"])
            if dedup_key in seen:
                continue  # Exact duplicate — skip

            field = supp_fact["field"]
            existing = primary_by_field.get(field, [])

            if existing:
                # Check if we should replace inferred with non-inferred
                replaced = False
                if supp_fact["type"] != "inferred":
                    for i, ex_fact in enumerate(existing):
                        if ex_fact["type"] == "inferred":
                            # Replace inferred fact with non-inferred supplemental
                            old_key = (ex_fact["field"], ex_fact["value"], ex_fact["source"])
                            seen.discard(old_key)
                            merged["facts"].remove(ex_fact)
                            merged["facts"].append(supp_fact)
                            seen.add(dedup_key)
                            existing[i] = supp_fact
                            replaced = True
                            break

                if not replaced:
                    # Same field, different value — conflict, keep both
                    has_different_value = any(
                        ex["value"] != supp_fact["value"] for ex in existing
                    )
                    if has_different_value:
                        conflict_notes.append(
                            f"Conflict on '{field}': primary={existing[0]['value']}, "
                            f"supplemental={supp_fact['value']} (source={supp_fact['source']})"
                        )
                    merged["facts"].append(supp_fact)
                    seen.add(dedup_key)
                    existing.append(supp_fact)
            else:
                # New field not in primary
                merged["facts"].append(supp_fact)
                seen.add(dedup_key)
                primary_by_field.setdefault(field, []).append(supp_fact)

        # Merge sources
        existing_source_keys = {
            (s.get("source"), s.get("type"))
            for s in merged.get("sources", [])
        }
        for supp_source in supplemental.get("sources", []):
            key = (supp_source.get("source"), supp_source.get("type"))
            if key not in existing_source_keys:
                merged["sources"].append(supp_source)
                existing_source_keys.add(key)

        # Append conflict notes
        if conflict_notes:
            existing_notes = merged.get("notes", "")
            separator = "\n" if existing_notes else ""
            merged["notes"] = existing_notes + separator + "\n".join(conflict_notes)

        return merged

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def search_property(
        self,
        address: str,
        geocoded_city: str | None = None,
        geocoded_state: str | None = None,
        geocoded_zip: str | None = None,
    ) -> AgentResult:
        """Search for property data at the given address.

        Pipeline:
          1. Grounded search with Google Search to find property info
          2. Parse evidence bundle from structured response
          3. Conditional supplemental search if coverage is low
          4. Structured extraction to parse into JSON schema
          5. Post-extraction validation, confidence scoring, classification
        """
        global _parse_attempts, _parse_successes
        start = time.perf_counter()
        total_tokens = 0
        second_search_triggered = False

        try:
            # --- Step 1: Grounded Search ---
            logger.info("[PropertySearch] Step 1: Grounded search for '%s'...", address)
            search_tool = types.Tool(google_search=types.GoogleSearch())
            try:
                search_response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=f"Search for warehouse or industrial property listing and building details at this address: {address}",
                        config=types.GenerateContentConfig(
                            system_instruction=SEARCH_PROMPT,
                            tools=[search_tool],
                            temperature=0.3,
                        ),
                    ),
                    timeout=self._API_TIMEOUT,
                )
            except asyncio.TimeoutError:
                latency = int((time.perf_counter() - start) * 1000)
                logger.error("[PropertySearch] Step 1 timed out after %ds for '%s'", self._API_TIMEOUT, address)
                return AgentResult.failure(error="Grounded search timed out", latency_ms=latency)

            raw_search_text = search_response.text
            if not raw_search_text:
                return AgentResult.failure(
                    error="Gemini search returned empty response",
                    latency_ms=int((time.perf_counter() - start) * 1000),
                )

            # Extract grounding URLs
            grounding_urls = []
            if hasattr(search_response, 'candidates') and search_response.candidates:
                candidate = search_response.candidates[0]
                if hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
                    metadata = candidate.grounding_metadata
                    if hasattr(metadata, 'grounding_chunks') and metadata.grounding_chunks:
                        for chunk in metadata.grounding_chunks:
                            if hasattr(chunk, 'web') and chunk.web:
                                grounding_urls.append(chunk.web.uri)

            if hasattr(search_response, 'usage_metadata') and search_response.usage_metadata:
                total_tokens += (search_response.usage_metadata.total_token_count or 0)

            logger.info("[PropertySearch] Step 1 complete — %d tokens, %d grounding URLs", total_tokens, len(grounding_urls))

            # Parse evidence bundle
            bundle = self._parse_evidence_bundle(raw_search_text)
            logger.info("[PropertySearch] Evidence parsed: %d facts, %d sources", len(bundle["facts"]), len(bundle["sources"]))

            # --- Build extraction input (raw text + parsed bundle for context) ---
            extraction_input = f"""Raw property research for address "{address}":

{raw_search_text}

Parsed evidence:
Sources: {json.dumps(bundle['sources'])}
Facts: {json.dumps(bundle['facts'])}
Warnings: {bundle['notes']}

Extract the structured property data as JSON."""

            # --- Conditional second search (parallel with extraction) ---
            needs_supplemental = self._needs_second_search(bundle)
            if needs_supplemental:
                second_search_triggered = True
                missing = [f for f in self._COVERAGE_FIELDS if f not in {fact["field"] for fact in bundle.get("facts", [])}]
                logger.info("[PropertySearch] Supplemental search triggered (parallel) — missing: %s", ", ".join(missing))

            # Define coroutines
            async def _run_extraction():
                return await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=extraction_input,
                        config=types.GenerateContentConfig(
                            system_instruction=EXTRACTION_PROMPT,
                            temperature=0.1,
                            response_mime_type="application/json",
                        ),
                    ),
                    timeout=self._API_TIMEOUT,
                )

            async def _run_supplemental():
                try:
                    return await asyncio.wait_for(
                        self._client.aio.models.generate_content(
                            model="gemini-3-flash-preview",
                            contents=f"Search county tax records and property assessment data for: {address}",
                            config=types.GenerateContentConfig(
                                system_instruction=SUPPLEMENTAL_SEARCH_PROMPT,
                                tools=[search_tool],
                                temperature=0.3,
                            ),
                        ),
                        timeout=self._API_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    logger.warning("[PropertySearch] Supplemental search timed out, continuing without it")
                    return None

            # --- Step 2: Run extraction (+ supplemental if needed) ---
            logger.info("[PropertySearch] Step 2: Extracting structured JSON (%d chars input)...", len(extraction_input))
            supplemental_response = None
            try:
                if needs_supplemental:
                    extraction_response, supplemental_response = await asyncio.gather(
                        _run_extraction(), _run_supplemental()
                    )
                else:
                    extraction_response = await _run_extraction()
            except asyncio.TimeoutError:
                latency = int((time.perf_counter() - start) * 1000)
                logger.error("[PropertySearch] Step 2 timed out after %ds for '%s'", self._API_TIMEOUT, address)
                return AgentResult.failure(error="Extraction timed out", latency_ms=latency)

            # Process supplemental results
            if supplemental_response is not None:
                if hasattr(supplemental_response, 'usage_metadata') and supplemental_response.usage_metadata:
                    total_tokens += (supplemental_response.usage_metadata.total_token_count or 0)
                supplemental_bundle = self._parse_evidence_bundle(supplemental_response.text or "")
                bundle = self._merge_supplemental(bundle, supplemental_bundle)
                logger.info("[PropertySearch] Supplemental search complete — bundle now has %d facts", len(bundle["facts"]))

            if hasattr(extraction_response, 'usage_metadata') and extraction_response.usage_metadata:
                total_tokens += (extraction_response.usage_metadata.total_token_count or 0)

            # Parse JSON with repair fallback
            raw_json = extraction_response.text.strip()
            try:
                property_data = json.loads(raw_json)
            except json.JSONDecodeError:
                logger.warning("JSON parse failed for '%s', attempting repair", address)
                repair_response = await asyncio.wait_for(
                    self._client.aio.models.generate_content(
                        model="gemini-3-flash-preview",
                        contents=f"Fix this malformed JSON, return ONLY valid JSON:\n\n{raw_json}",
                        config=types.GenerateContentConfig(
                            temperature=0.0,
                            response_mime_type="application/json",
                        ),
                    ),
                    timeout=30,
                )
                if hasattr(repair_response, 'usage_metadata') and repair_response.usage_metadata:
                    total_tokens += (repair_response.usage_metadata.total_token_count or 0)
                # Outer except catches if this also fails
                property_data = json.loads(repair_response.text.strip())

            # Patch supplemental facts into extracted JSON (fill nulls only)
            if supplemental_response is not None:
                supp_facts = {fact["field"]: fact["value"] for fact in bundle.get("facts", [])}
                field_map = {
                    "building_size_sqft": int, "year_built": int,
                    "clear_height_ft": float, "dock_doors": int,
                    "lot_size_acres": float,
                }
                for field_name, cast_fn in field_map.items():
                    if property_data.get(field_name) is None and field_name in supp_facts:
                        try:
                            property_data[field_name] = cast_fn(supp_facts[field_name])
                        except (ValueError, TypeError):
                            pass

            # Merge grounding URLs
            if grounding_urls and not property_data.get("source_urls"):
                property_data["source_urls"] = grounding_urls
            elif grounding_urls:
                property_data["source_urls"] = list(
                    set(property_data.get("source_urls", []) + grounding_urls)
                )

            # Ensure image_urls is a list (Gemini sometimes returns null or omits it)
            if not isinstance(property_data.get("image_urls"), list):
                property_data["image_urls"] = []

            # Log image extraction results
            img_urls = property_data.get("image_urls")
            logger.info(
                "[PropertySearch] Step 2 complete — extracted %d non-null fields, image_urls=%s",
                sum(1 for v in property_data.values() if v is not None),
                f"{len(img_urls)} URLs" if isinstance(img_urls, list) else repr(img_urls),
            )
            if isinstance(img_urls, list) and img_urls:
                for u in img_urls[:3]:
                    logger.info("[PropertySearch]   image: %s", u)

            # --- Post-extraction pipeline (execution order matters!) ---

            # Step 2: Address match
            address_match = check_address_match(
                property_data.get("city"),
                property_data.get("state"),
                property_data.get("zip_code"),
                geocoded_city,
                geocoded_state,
                geocoded_zip,
            )

            # Step 3: Pop internal fields
            fields_by_source = property_data.pop("fields_by_source", {})
            llm_confidence = property_data.pop("confidence", None)

            # Step 4: Sanity flags (needs fields_by_source)
            sanity_flags = check_sanity_flags(property_data, fields_by_source)

            # Step 5: Compute confidence (needs sanity_flags)
            computed_confidence = compute_confidence(
                property_data,
                fields_by_source,
                address_match["match_quality"],
                sanity_flags,
            )
            property_data["confidence"] = computed_confidence

            # Log both for baseline comparison
            if llm_confidence is not None:
                logger.info(
                    "Confidence comparison for '%s': computed=%.3f, llm=%.3f, delta=%.3f",
                    address,
                    computed_confidence,
                    llm_confidence,
                    abs(computed_confidence - llm_confidence),
                )

            quality_summary = compute_source_quality_summary(fields_by_source)

            # Step 6: Result classification
            match_quality = address_match["match_quality"]
            is_commercial = property_data.get("is_commercial_industrial", False)

            if not is_commercial or match_quality == "mismatch":
                result_class = "not_verified"
            elif match_quality == "partial" and (sanity_flags or computed_confidence < 0.55):
                result_class = "verified_not_persisted"
            elif match_quality == "partial" and not sanity_flags and computed_confidence >= 0.55:
                result_class = "verified_persisted"
            elif match_quality == "exact":
                result_class = "verified_persisted"
            else:
                result_class = "not_verified"

            latency = int((time.perf_counter() - start) * 1000)

            # Summary log (visible in terminal)
            logger.info(
                "[PropertySearch] DONE '%s' -> %s | confidence=%.3f | match=%s | flags=%d | tokens=%d | %dms",
                address, result_class, computed_confidence, match_quality,
                len(sanity_flags), total_tokens, latency,
            )

            # Structured logging (for analytics)
            logger.info(
                "Property search completed",
                extra={
                    "address": address,
                    "result_class": result_class,
                    "confidence": computed_confidence,
                    "match_quality": address_match["match_quality"],
                    "sanity_flags_count": len(sanity_flags),
                    "second_search_triggered": second_search_triggered,
                    "parse_success_rate": _parse_successes / max(_parse_attempts, 1),
                    "tokens": total_tokens,
                    "latency_ms": latency,
                },
            )

            # Step 7: Assemble and return
            return AgentResult.success(
                data={
                    "property_data": property_data,
                    "meta": {
                        "evidence_bundle": bundle,
                        "grounding_urls": grounding_urls,
                        "address_match": address_match,
                        "sanity_flags": sanity_flags,
                        "fields_by_source": fields_by_source,
                        "source_quality_summary": quality_summary,
                        "llm_confidence": llm_confidence,
                        "result_class": result_class,
                        "second_search_triggered": second_search_triggered,
                    },
                },
                tokens_used=total_tokens,
                latency_ms=latency,
            )

        except json.JSONDecodeError as exc:
            latency = int((time.perf_counter() - start) * 1000)
            logger.error("Failed to parse extraction JSON for '%s': %s", address, exc)
            return AgentResult.failure(
                error=f"JSON parsing failed: {exc}",
                latency_ms=latency,
            )
        except Exception as exc:
            latency = int((time.perf_counter() - start) * 1000)
            logger.error("Property search failed for '%s': %s", address, exc)
            return AgentResult.failure(error=str(exc), latency_ms=latency)
