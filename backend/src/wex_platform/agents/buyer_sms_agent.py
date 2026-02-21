"""Buyer SMS intake pipeline — multi-step agent for processing inbound buyer texts.

Ported from the wex-leasing-service-python multi-agent orchestrator pattern.
Adapted for WEx Platform 2026's Gemini-based agent infrastructure.

Pipeline steps:
1. Message Interpreter — classify intent (deterministic + LLM)
2. Criteria Agent — extract structured warehouse requirements
3. Gatekeeper — deterministic validation (length, PII, profanity)
4. Response Agent — generate contextual SMS reply
5. Persistence — create/update BuyerNeed and trigger clearing engine
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from wex_platform.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Intent classifications
INTENT_NEW_SEARCH = "new_search"
INTENT_REFINE_SEARCH = "refine_search"
INTENT_QUESTION = "question"
INTENT_GREETING = "greeting"
INTENT_OTHER = "other"

VALID_INTENTS = {INTENT_NEW_SEARCH, INTENT_REFINE_SEARCH, INTENT_QUESTION, INTENT_GREETING, INTENT_OTHER}

# Gatekeeper limits
MAX_INBOUND_LENGTH = 1600  # SMS can be up to ~1600 chars with concatenation
MAX_OUTBOUND_LENGTH = 480  # Keep replies short for SMS
MIN_OUTBOUND_LENGTH = 20

# Profanity blocklist (minimal)
PROFANITY_WORDS = frozenset([
    "fuck", "fucking", "fucker", "shit", "shitty", "asshole",
    "bitch", "dick", "cock", "pussy",
])

# PII patterns
PHONE_PATTERN = re.compile(
    r"(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}"
)
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Greeting patterns (deterministic fast-path)
GREETING_PATTERNS = re.compile(
    r"^\s*(hi|hey|hello|sup|yo|what'?s up|howdy|good (morning|afternoon|evening))\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class GatekeeperResult:
    """Result of SMS validation."""
    ok: bool
    hint: str | None = None
    violation: str | None = None


@dataclass
class BuyerSMSResult:
    """Result from the full SMS pipeline."""
    response: str
    intent: str
    criteria: dict | None = None
    buyer_need_id: str | None = None
    conversation_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Gatekeeper (deterministic, no AI)
# ---------------------------------------------------------------------------

def validate_inbound(text: str) -> GatekeeperResult:
    """Validate an inbound buyer SMS. Deterministic only."""
    if not text or not text.strip():
        return GatekeeperResult(ok=False, hint="Empty message", violation="empty")

    if len(text) > MAX_INBOUND_LENGTH:
        return GatekeeperResult(
            ok=False,
            hint=f"Message too long ({len(text)} chars)",
            violation="too_long",
        )

    # Profanity check
    words = set(re.findall(r"\b\w+\b", text.lower()))
    found = words & PROFANITY_WORDS
    if found:
        return GatekeeperResult(
            ok=False,
            hint="Message contains inappropriate language",
            violation="profanity",
        )

    return GatekeeperResult(ok=True)


def validate_outbound(text: str) -> GatekeeperResult:
    """Validate an outbound SMS reply before sending."""
    if not text or not text.strip():
        return GatekeeperResult(ok=False, hint="Empty reply", violation="empty")

    if len(text) > MAX_OUTBOUND_LENGTH:
        return GatekeeperResult(
            ok=False,
            hint=f"Reply too long ({len(text)} chars, max {MAX_OUTBOUND_LENGTH})",
            violation="too_long",
        )

    if len(text) < MIN_OUTBOUND_LENGTH:
        return GatekeeperResult(
            ok=False,
            hint=f"Reply too short ({len(text)} chars)",
            violation="too_short",
        )

    # PII leak check (block multiple phones/emails)
    phones = PHONE_PATTERN.findall(text)
    if len(phones) > 1:
        return GatekeeperResult(
            ok=False,
            hint="Reply contains multiple phone numbers",
            violation="multiple_phones",
        )

    emails = EMAIL_PATTERN.findall(text)
    if len(emails) > 1:
        return GatekeeperResult(
            ok=False,
            hint="Reply contains multiple email addresses",
            violation="multiple_emails",
        )

    return GatekeeperResult(ok=True)


# ---------------------------------------------------------------------------
# Pipeline Agents
# ---------------------------------------------------------------------------

class IntentClassifier(BaseAgent):
    """Step 1: Classify buyer SMS intent using Gemini."""

    def __init__(self):
        super().__init__(
            agent_name="buyer_sms_intent",
            model_name="gemini-2.0-flash",
            temperature=0.1,
        )

    async def classify(self, message: str, conversation_history: list[dict] | None = None) -> str:
        """Classify the intent of a buyer SMS.

        Returns one of: new_search, refine_search, question, greeting, other.
        """
        # Fast-path: deterministic greeting detection
        if GREETING_PATTERNS.match(message) and len(message.split()) <= 5:
            return INTENT_GREETING

        history_context = ""
        if conversation_history:
            recent = conversation_history[-4:]
            history_lines = []
            for msg in recent:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:200]
                history_lines.append(f"  {role}: {content}")
            history_context = f"\nRecent conversation:\n" + "\n".join(history_lines)

        prompt = (
            f"Classify this warehouse search SMS into exactly one of: "
            f"new_search, refine_search, question, greeting, other.\n"
            f"{history_context}\n"
            f"Message: \"{message}\"\n\n"
            f"Respond with ONLY the classification word, nothing else."
        )

        result = await self.generate(prompt=prompt)

        if not result.ok:
            logger.warning("Intent classification failed: %s", result.error)
            return INTENT_OTHER

        intent = result.data.strip().lower().replace('"', "").replace("'", "")
        if intent not in VALID_INTENTS:
            logger.warning("Unknown intent from LLM: %s — defaulting to other", intent)
            return INTENT_OTHER

        return intent


class CriteriaExtractor(BaseAgent):
    """Step 2: Extract structured warehouse search criteria from buyer SMS."""

    def __init__(self):
        super().__init__(
            agent_name="buyer_sms_criteria",
            model_name="gemini-2.0-flash",
            temperature=0.2,
        )

    async def extract(
        self, message: str, existing_criteria: dict | None = None
    ) -> dict:
        """Extract structured search criteria from a buyer message.

        Returns dict with keys:
            location, sqft, use_type, goods_type, timing, duration, features
        """
        existing_context = ""
        if existing_criteria:
            existing_context = (
                f"\nPreviously extracted criteria (merge with new info, "
                f"new values override old):\n{json.dumps(existing_criteria)}\n"
            )

        prompt = (
            f"Extract warehouse search criteria from this buyer SMS. "
            f"Return a JSON object with these fields (use null if not mentioned):\n"
            f"- location: string (city, state, or area mentioned)\n"
            f"- sqft: number (square footage needed, convert 'k' suffix e.g. 10k = 10000)\n"
            f"- use_type: string (one of: storage, light_ops, distribution, manufacturing, flex)\n"
            f"- goods_type: string (one of: general, food, chemicals, high_value, electronics, raw_materials)\n"
            f"- timing: string (one of: immediately, 30_days, 1_3_months, flexible)\n"
            f"- duration: string (one of: 1_3, 3_6, 6_12, 12_24, 24_plus) — months\n"
            f"- features: list of strings from: office, dock_doors, climate, power, 24_7, sprinkler, parking, forklift\n"
            f"{existing_context}\n"
            f"Message: \"{message}\"\n\n"
            f"Respond with ONLY the JSON object, no explanation."
        )

        result = await self.generate_json(prompt=prompt)

        if not result.ok:
            logger.warning("Criteria extraction failed: %s", result.error)
            return {}

        criteria = result.data if isinstance(result.data, dict) else {}

        # Merge with existing if provided
        if existing_criteria:
            for key, value in criteria.items():
                if value is not None:
                    existing_criteria[key] = value
            return existing_criteria

        return criteria


class ResponseGenerator(BaseAgent):
    """Step 4: Generate a contextual SMS reply to the buyer."""

    def __init__(self):
        super().__init__(
            agent_name="buyer_sms_response",
            model_name="gemini-2.0-flash",
            temperature=0.7,
        )

    async def generate_reply(
        self,
        intent: str,
        message: str,
        criteria: dict | None = None,
        conversation_history: list[dict] | None = None,
        matches_found: int = 0,
        retry_hint: str | None = None,
    ) -> str:
        """Generate a contextual SMS reply.

        Returns the SMS text to send back to the buyer.
        """
        # Deterministic fast-path for greetings
        if intent == INTENT_GREETING:
            return (
                "Hey! I'm the WEx warehouse assistant. "
                "Tell me what kind of space you need — size, location, "
                "and what you'll store. I'll find options fast."
            )

        history_context = ""
        if conversation_history:
            recent = conversation_history[-4:]
            history_lines = []
            for msg in recent:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")[:200]
                history_lines.append(f"  {role}: {content}")
            history_context = f"\nRecent conversation:\n" + "\n".join(history_lines)

        criteria_context = ""
        if criteria:
            criteria_context = f"\nExtracted criteria: {json.dumps(criteria)}"

        matches_context = ""
        if matches_found > 0:
            matches_context = f"\nMatches found: {matches_found} warehouses match their criteria."

        retry_context = ""
        if retry_hint:
            retry_context = f"\n\nPREVIOUS ATTEMPT REJECTED: {retry_hint}. Fix the issue."

        prompt = (
            f"You are the WEx warehouse assistant responding via SMS. "
            f"Keep replies under {MAX_OUTBOUND_LENGTH} characters. "
            f"Be conversational, helpful, and concise. No emojis. "
            f"Never reveal you are AI.\n\n"
            f"Intent: {intent}\n"
            f"Buyer's message: \"{message}\"\n"
            f"{history_context}"
            f"{criteria_context}"
            f"{matches_context}"
            f"{retry_context}\n\n"
            f"Guidelines by intent:\n"
            f"- new_search: Confirm what you understood. If criteria has location and sqft, "
            f"say you're searching. If missing info, ask for it.\n"
            f"- refine_search: Acknowledge the refinement, confirm updated criteria.\n"
            f"- question: Answer if you can, otherwise say you'll find out.\n"
            f"- other: Ask them to describe the warehouse space they need.\n\n"
            f"Respond with ONLY the SMS text, nothing else."
        )

        result = await self.generate(prompt=prompt)

        if not result.ok:
            logger.warning("Response generation failed: %s", result.error)
            return self._fallback_response(intent, criteria)

        return result.data.strip().strip('"').strip("'")

    @staticmethod
    def _fallback_response(intent: str, criteria: dict | None = None) -> str:
        """Deterministic fallback when LLM fails."""
        if intent == INTENT_NEW_SEARCH:
            if criteria and criteria.get("location"):
                return (
                    f"Got it — looking for space in {criteria['location']}. "
                    f"Searching now, I'll text you back with options shortly."
                )
            return (
                "I'd love to help you find warehouse space. "
                "What city are you looking in and how much space do you need?"
            )

        if intent == INTENT_REFINE_SEARCH:
            return "Noted — updating your search with those details. One moment."

        if intent == INTENT_QUESTION:
            return (
                "Good question — let me look into that for you. "
                "I'll text back shortly with an answer."
            )

        return (
            "Thanks for reaching out to WEx! "
            "Tell me what kind of warehouse space you need — "
            "city, size, and what you'll use it for."
        )


# ---------------------------------------------------------------------------
# Pipeline Orchestrator
# ---------------------------------------------------------------------------

class BuyerSMSPipeline:
    """Orchestrates the full buyer SMS intake pipeline.

    Coordinates:
    1. IntentClassifier — classify message intent
    2. CriteriaExtractor — extract structured requirements
    3. Gatekeeper — validate inbound/outbound messages
    4. ResponseGenerator — generate contextual reply
    """

    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.criteria_extractor = CriteriaExtractor()
        self.response_generator = ResponseGenerator()

    async def process_message(
        self,
        phone: str,
        message: str,
        conversation_history: list[dict] | None = None,
        existing_criteria: dict | None = None,
    ) -> BuyerSMSResult:
        """Run the full pipeline on an inbound buyer SMS.

        Args:
            phone: Sender's phone number (E.164).
            message: The SMS body text.
            conversation_history: Previous messages [{role, content}].
            existing_criteria: Previously extracted criteria to merge with.

        Returns:
            BuyerSMSResult with response text, intent, and extracted criteria.
        """
        logger.info("Buyer SMS pipeline start — phone=%s, len=%d", phone, len(message))

        # ── Step 3a: Gatekeeper — validate inbound ──────────────────
        gate = validate_inbound(message)
        if not gate.ok:
            logger.warning(
                "Buyer SMS gatekeeper rejected inbound from %s: %s",
                phone, gate.violation,
            )
            return BuyerSMSResult(
                response="",
                intent=INTENT_OTHER,
                error=f"Inbound rejected: {gate.violation}",
            )

        # ── Step 1: Classify intent ─────────────────────────────────
        intent = await self.intent_classifier.classify(
            message=message,
            conversation_history=conversation_history,
        )
        logger.info("Buyer SMS intent: %s (phone=%s)", intent, phone)

        # ── Step 2: Extract criteria (if search-related) ────────────
        criteria = existing_criteria
        if intent in (INTENT_NEW_SEARCH, INTENT_REFINE_SEARCH):
            criteria = await self.criteria_extractor.extract(
                message=message,
                existing_criteria=existing_criteria,
            )
            logger.info("Buyer SMS criteria extracted: %s", criteria)

        # ── Step 4: Generate response ───────────────────────────────
        response = await self.response_generator.generate_reply(
            intent=intent,
            message=message,
            criteria=criteria,
            conversation_history=conversation_history,
        )

        # ── Step 3b: Gatekeeper — validate outbound ─────────────────
        # Retry up to 2 times if gatekeeper rejects the response
        for attempt in range(3):
            gate = validate_outbound(response)
            if gate.ok:
                break

            logger.warning(
                "Buyer SMS outbound gatekeeper rejected (attempt %d): %s",
                attempt + 1, gate.hint,
            )

            if attempt < 2:
                # Retry with hint
                response = await self.response_generator.generate_reply(
                    intent=intent,
                    message=message,
                    criteria=criteria,
                    conversation_history=conversation_history,
                    retry_hint=gate.hint,
                )
            else:
                # Final fallback — use deterministic template
                response = ResponseGenerator._fallback_response(intent, criteria)
                logger.warning("Using fallback response after 3 gatekeeper rejections")

        logger.info(
            "Buyer SMS pipeline complete — intent=%s, response_len=%d",
            intent, len(response),
        )

        return BuyerSMSResult(
            response=response,
            intent=intent,
            criteria=criteria,
        )
