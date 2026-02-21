"""Market Rate Agent - Gemini Search grounded NNN lease rate lookup."""

import asyncio
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

from google import genai
from google.genai import types

from wex_platform.agents.base import BaseAgent, AgentResult
from wex_platform.agents.prompts.market_rate import MARKET_RATE_SYSTEM_PROMPT, MARKET_RATE_TEMPLATE

logger = logging.getLogger(__name__)

# Cache TTL: 30 days
CACHE_TTL_DAYS = 30


class MarketRateAgent(BaseAgent):
    """Provides NNN warehouse lease rates using Gemini with Google Search grounding.

    Results are cached in the MarketRateCache DB table with a 30-day TTL
    to minimize API calls for repeated zipcode lookups.
    """

    _API_TIMEOUT = 30  # Market rate lookups should be fast

    def __init__(self):
        super().__init__(
            agent_name="market_rate",
            model_name="gemini-3-flash-preview",
            temperature=0.2,  # Factual, deterministic
        )
        from wex_platform.app.config import get_settings
        settings = get_settings()
        self._client = genai.Client(api_key=settings.gemini_api_key)

    async def get_nnn_rates(self, zipcode: str) -> AgentResult:
        """Get NNN warehouse lease rates for a zipcode.

        Checks DB cache first. If cached and < 30 days old, returns cached.
        Otherwise calls Gemini with Search grounding and caches the result.

        Args:
            zipcode: US zipcode string (e.g. "90210").

        Returns:
            AgentResult with data containing nnn_low, nnn_high, source_context.
        """
        # 1. Check cache
        cached = await self._get_cached(zipcode)
        if cached:
            logger.info("[market_rate] Cache hit for zipcode %s", zipcode)
            return AgentResult.success(data=cached)

        # 2. Call Gemini with Search grounding (new SDK)
        logger.info("[market_rate] Cache miss for zipcode %s — calling Gemini", zipcode)
        start_time = time.time()

        try:
            search_tool = types.Tool(google_search=types.GoogleSearch())
            prompt = MARKET_RATE_TEMPLATE.format(zipcode=zipcode)

            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=MARKET_RATE_SYSTEM_PROMPT,
                        tools=[search_tool],
                        temperature=self.temperature,
                        response_mime_type="application/json",
                    ),
                ),
                timeout=self._API_TIMEOUT,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            # Parse response
            tokens_used = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                tokens_used = response.usage_metadata.total_token_count or 0

            response_text = response.text
            parsed = json.loads(response_text)

            nnn_low = float(parsed.get("nnn_low", 0))
            nnn_high = float(parsed.get("nnn_high", 0))
            source_context = parsed.get("source_context", "")

            # Extract grounding source URLs from Gemini Search metadata
            grounding_urls = []
            try:
                for candidate in (response.candidates or []):
                    gm = getattr(candidate, "grounding_metadata", None)
                    if not gm:
                        continue
                    for chunk in (getattr(gm, "grounding_chunks", None) or []):
                        web = getattr(chunk, "web", None)
                        if web and getattr(web, "uri", None):
                            grounding_urls.append(web.uri)
            except Exception:
                pass
            if grounding_urls:
                logger.info("[market_rate] Grounding sources for %s: %s", zipcode, grounding_urls)
                source_context = f"{source_context}\nSources: {', '.join(grounding_urls)}"

            # Validate rates are reasonable (0.20 - 5.00 $/sqft/mo)
            if nnn_low < 0.20 or nnn_high > 5.00 or nnn_low >= nnn_high:
                logger.warning(
                    "[market_rate] Unreasonable rates for %s: low=%s, high=%s",
                    zipcode, nnn_low, nnn_high,
                )
                return AgentResult.failure(
                    f"Unreasonable rates returned: {nnn_low}-{nnn_high}",
                    latency_ms=latency_ms,
                )

            result_data = {
                "nnn_low": nnn_low,
                "nnn_high": nnn_high,
                "source_context": source_context,
            }

            # 3. Cache the result
            await self._cache_result(zipcode, nnn_low, nnn_high, source_context)

            # Log activity
            await self._safe_log_activity(
                action="nnn_lookup",
                input_summary=f"zipcode={zipcode}",
                output_summary=f"low={nnn_low}, high={nnn_high}",
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return AgentResult.success(
                data=result_data,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

        except asyncio.TimeoutError:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error("[market_rate] Timed out for zipcode %s after %ds", zipcode, self._API_TIMEOUT)
            return AgentResult.failure("Market rate lookup timed out", latency_ms=latency_ms)
        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error("[market_rate] Failed for zipcode %s: %s", zipcode, exc)
            return AgentResult.failure(str(exc), latency_ms=latency_ms)

    async def _get_cached(self, zipcode: str) -> Optional[dict]:
        """Check MarketRateCache for a fresh entry."""
        try:
            from wex_platform.infra.database import async_session
            from wex_platform.domain.models import MarketRateCache
            from sqlalchemy import select

            async with async_session() as session:
                stmt = select(MarketRateCache).where(MarketRateCache.zipcode == zipcode)
                result = await session.execute(stmt)
                cached = result.scalar_one_or_none()

                if cached and cached.fetched_at:
                    age = datetime.now(timezone.utc) - cached.fetched_at.replace(tzinfo=timezone.utc)
                    if age < timedelta(days=CACHE_TTL_DAYS):
                        return {
                            "nnn_low": cached.nnn_low,
                            "nnn_high": cached.nnn_high,
                            "source_context": cached.source_context or "",
                        }
                    else:
                        logger.info("[market_rate] Cache expired for %s (age=%s)", zipcode, age)
        except Exception as exc:
            logger.warning("[market_rate] Cache read failed: %s", exc)

        return None

    async def _cache_result(
        self, zipcode: str, nnn_low: float, nnn_high: float, source_context: str
    ) -> None:
        """Upsert a cache entry for the zipcode."""
        try:
            import uuid
            from wex_platform.infra.database import async_session
            from wex_platform.domain.models import MarketRateCache
            from sqlalchemy import select

            async with async_session() as session:
                stmt = select(MarketRateCache).where(MarketRateCache.zipcode == zipcode)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.nnn_low = nnn_low
                    existing.nnn_high = nnn_high
                    existing.source_context = source_context
                    existing.fetched_at = datetime.now(timezone.utc)
                else:
                    entry = MarketRateCache(
                        id=str(uuid.uuid4()),
                        zipcode=zipcode,
                        nnn_low=nnn_low,
                        nnn_high=nnn_high,
                        source_context=source_context,
                        fetched_at=datetime.now(timezone.utc),
                    )
                    session.add(entry)

                await session.commit()
                logger.info("[market_rate] Cached rates for %s: %.2f-%.2f", zipcode, nnn_low, nnn_high)

        except Exception as exc:
            logger.warning("[market_rate] Cache write failed: %s", exc)

    async def get_nearby_cached_rate(self, zipcode: str) -> Optional[dict]:
        """Find cached rates from nearby zip codes using prefix matching.

        Tier 1: Same 3-digit prefix (e.g., 314xx for 31401)
        Tier 2: Same 2-digit prefix (e.g., 31xxx for 31401) — wider geo net
        """
        try:
            from wex_platform.infra.database import async_session
            from wex_platform.domain.models import MarketRateCache
            from sqlalchemy import select

            cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_TTL_DAYS)

            async with async_session() as session:
                # Tier 1: 3-digit prefix
                prefix_3 = zipcode[:3]
                stmt = (
                    select(MarketRateCache)
                    .where(
                        MarketRateCache.zipcode.like(f"{prefix_3}%"),
                        MarketRateCache.zipcode != zipcode,
                        MarketRateCache.fetched_at >= cutoff,
                    )
                )
                result = await session.execute(stmt)
                rows = result.scalars().all()

                # Tier 2: widen to 2-digit prefix if no 3-digit matches
                if not rows:
                    prefix_2 = zipcode[:2]
                    stmt = (
                        select(MarketRateCache)
                        .where(
                            MarketRateCache.zipcode.like(f"{prefix_2}%"),
                            MarketRateCache.zipcode != zipcode,
                            MarketRateCache.fetched_at >= cutoff,
                        )
                    )
                    result = await session.execute(stmt)
                    rows = result.scalars().all()

                if not rows:
                    logger.info("[market_rate] No nearby cached rates for %s", zipcode)
                    return None

                # Average across nearby zips
                avg_low = sum(r.nnn_low for r in rows) / len(rows)
                avg_high = sum(r.nnn_high for r in rows) / len(rows)
                # Pick the closest zip (smallest numeric distance)
                closest = min(rows, key=lambda r: abs(int(r.zipcode) - int(zipcode)))

                logger.info(
                    "[market_rate] Nearby rate for %s from %d cached zips (closest=%s): %.2f-%.2f",
                    zipcode, len(rows), closest.zipcode, avg_low, avg_high,
                )
                return {
                    "nnn_low": round(avg_low, 2),
                    "nnn_high": round(avg_high, 2),
                    "source_zip": closest.zipcode,
                    "nearby_count": len(rows),
                }

        except Exception as exc:
            logger.warning("[market_rate] Nearby rate lookup failed: %s", exc)
            return None
