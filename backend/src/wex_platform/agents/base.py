"""Base agent class for all WEx AI agents.

Every WEx Clearing House agent (Intake, Valuation, Matching, Deal-Structuring,
Compliance, Orchestrator) inherits from BaseAgent, which provides:

- Gemini model access via the infra.gemini_client wrapper
- A standard AgentResult return type (Result pattern)
- Automatic latency measurement and token tracking
- Database activity logging via AgentLog records
- Multi-turn chat support
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Standard result type for all agent operations.

    Follows the Result pattern: every agent call returns an AgentResult
    instead of raising exceptions. Callers check ``result.ok`` to
    determine success or failure.

    Attributes:
        ok: True if the operation succeeded.
        data: The response payload (text, parsed JSON, etc.).
        error: Human-readable error description when ``ok`` is False.
        tokens_used: Total tokens consumed (prompt + completion).
        latency_ms: Wall-clock time for the operation in milliseconds.
    """

    ok: bool
    data: Any = None
    error: Optional[str] = None
    tokens_used: int = 0
    latency_ms: int = 0

    @classmethod
    def success(
        cls,
        data: Any,
        tokens_used: int = 0,
        latency_ms: int = 0,
    ) -> "AgentResult":
        """Create a successful result."""
        return cls(
            ok=True,
            data=data,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
        )

    @classmethod
    def failure(cls, error: str, latency_ms: int = 0) -> "AgentResult":
        """Create a failure result."""
        return cls(ok=False, error=error, latency_ms=latency_ms)


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------

class BaseAgent:
    """Base class for all WEx Clearing House agents.

    Subclasses should override nothing in the base to use vanilla Gemini
    generation, or extend ``generate`` / ``generate_json`` with
    domain-specific prompt assembly.

    Example::

        class IntakeAgent(BaseAgent):
            def __init__(self):
                super().__init__(agent_name="intake_agent")

            async def process(self, description: str) -> AgentResult:
                return await self.generate_json(
                    prompt=f"Extract warehouse metadata: {description}",
                    system_instruction="You are a warehouse data extraction expert.",
                )
    """

    def __init__(
        self,
        agent_name: str,
        model_name: str = "gemini-3-flash-preview",
        temperature: float = 0.7,
    ):
        """Initialise the agent.

        Args:
            agent_name: A short, unique name for this agent (used in logs).
            model_name: The Gemini model identifier.
            temperature: Generation temperature (0.0-1.0).
        """
        self.agent_name = agent_name
        self.model_name = model_name
        self.temperature = temperature

    # ------------------------------------------------------------------
    # Core generation
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        json_mode: bool = False,
        response_schema: dict | None = None,
    ) -> AgentResult:
        """Generate a single-turn response from Gemini.

        Args:
            prompt: The user prompt to send.
            system_instruction: Optional system instruction that shapes
                the model's behaviour.
            json_mode: If True the model is instructed to return valid JSON.

        Returns:
            An ``AgentResult`` with the response text in ``data``.
        """
        start_time = time.time()
        try:
            from wex_platform.infra.gemini_client import get_model

            model = get_model(
                model_name=self.model_name,
                temperature=self.temperature,
                json_mode=json_mode,
                response_schema=response_schema,
                system_instruction=system_instruction,
            )

            response = await asyncio.wait_for(
                model.generate_content_async(prompt),
                timeout=120,  # 2 min hard limit — prevents indefinite hangs
            )
            latency_ms = int((time.time() - start_time) * 1000)

            # Extract token usage from response metadata
            tokens_used = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = getattr(
                    response.usage_metadata, "prompt_token_count", 0
                ) or 0
                completion_tokens = getattr(
                    response.usage_metadata, "candidates_token_count", 0
                ) or 0
                tokens_used = prompt_tokens + completion_tokens

            response_text = response.text

            logger.info(
                "[%s] Generation succeeded: tokens=%d, latency=%dms",
                self.agent_name,
                tokens_used,
                latency_ms,
            )

            # Fire-and-forget DB log (non-blocking)
            await self._safe_log_activity(
                action="generate",
                input_summary=prompt[:500],
                output_summary=(response_text or "")[:500],
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return AgentResult.success(
                data=response_text,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "[%s] Generation failed after %dms: %s",
                self.agent_name,
                latency_ms,
                exc,
            )
            return AgentResult.failure(str(exc), latency_ms=latency_ms)

    # ------------------------------------------------------------------
    # JSON generation convenience
    # ------------------------------------------------------------------

    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        response_schema: dict | None = None,
    ) -> AgentResult:
        """Generate a response and parse it as JSON.

        Calls ``generate`` with ``json_mode=True``, then deserialises the
        response text into a Python dict or list.  If parsing fails the
        result will be a failure with the parse error.

        Args:
            prompt: The user prompt.
            system_instruction: Optional system instruction.

        Returns:
            An ``AgentResult`` whose ``data`` field contains the parsed
            JSON (dict or list).
        """
        result = await self.generate(
            prompt=prompt,
            system_instruction=system_instruction,
            json_mode=True,
            response_schema=response_schema,
        )

        if not result.ok:
            return result

        try:
            parsed = json.loads(result.data)
            return AgentResult.success(
                data=parsed,
                tokens_used=result.tokens_used,
                latency_ms=result.latency_ms,
            )
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "[%s] JSON parse failed: %s — raw text: %.200s",
                self.agent_name,
                exc,
                result.data,
            )
            return AgentResult.failure(
                error=f"JSON parse error: {exc}",
                latency_ms=result.latency_ms,
            )

    # ------------------------------------------------------------------
    # Multi-turn chat
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict],
        system_instruction: Optional[str] = None,
    ) -> AgentResult:
        """Conduct a multi-turn conversation with Gemini.

        Args:
            messages: A list of message dicts, each with ``role``
                (``"user"`` or ``"model"``) and ``parts`` (list of
                strings).  The **last** message is sent as the new user
                turn; all preceding messages form the chat history.
            system_instruction: Optional system instruction.

        Returns:
            An ``AgentResult`` with the model's latest reply in ``data``.
        """
        start_time = time.time()
        try:
            from wex_platform.infra.gemini_client import get_model

            if not messages:
                return AgentResult.failure("No messages provided for chat.")

            model = get_model(
                model_name=self.model_name,
                temperature=self.temperature,
                system_instruction=system_instruction,
            )

            # Split history and the latest user turn
            history = messages[:-1]
            last_message = messages[-1]

            # Build history objects compatible with the SDK
            chat_history = []
            for msg in history:
                chat_history.append(
                    {
                        "role": msg.get("role", "user"),
                        "parts": msg.get("parts", []),
                    }
                )

            chat_session = model.start_chat(history=chat_history)

            # The latest message's parts joined as text
            last_parts = last_message.get("parts", [])
            user_text = "\n".join(str(p) for p in last_parts)

            response = await chat_session.send_message_async(user_text)
            latency_ms = int((time.time() - start_time) * 1000)

            tokens_used = 0
            if hasattr(response, "usage_metadata") and response.usage_metadata:
                prompt_tokens = getattr(
                    response.usage_metadata, "prompt_token_count", 0
                ) or 0
                completion_tokens = getattr(
                    response.usage_metadata, "candidates_token_count", 0
                ) or 0
                tokens_used = prompt_tokens + completion_tokens

            response_text = response.text

            logger.info(
                "[%s] Chat succeeded: tokens=%d, latency=%dms, turns=%d",
                self.agent_name,
                tokens_used,
                latency_ms,
                len(messages),
            )

            await self._safe_log_activity(
                action="chat",
                input_summary=user_text[:500],
                output_summary=(response_text or "")[:500],
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

            return AgentResult.success(
                data=response_text,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "[%s] Chat failed after %dms: %s",
                self.agent_name,
                latency_ms,
                exc,
            )
            return AgentResult.failure(str(exc), latency_ms=latency_ms)

    # ------------------------------------------------------------------
    # Activity logging
    # ------------------------------------------------------------------

    async def log_activity(
        self,
        action: str,
        input_summary: str,
        output_summary: str,
        tokens_used: int,
        latency_ms: int,
        warehouse_id: Optional[str] = None,
        buyer_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> None:
        """Persist an activity log entry to the database.

        Creates an ``AgentLog`` record capturing what the agent did,
        how many tokens it consumed, and which domain entities were
        involved.

        Args:
            action: Short verb describing the action (e.g. "generate",
                    "chat", "validate").
            input_summary: Truncated version of the input prompt.
            output_summary: Truncated version of the model response.
            tokens_used: Total tokens consumed.
            latency_ms: Wall-clock duration in milliseconds.
            warehouse_id: Optional related warehouse UUID.
            buyer_id: Optional related buyer UUID.
            deal_id: Optional related deal UUID.
        """
        try:
            from wex_platform.infra.database import async_session
            from wex_platform.domain.models import AgentLog  # noqa: WPS433

            async with async_session() as session:
                log_entry = AgentLog(
                    id=str(uuid.uuid4()),
                    agent_name=self.agent_name,
                    action=action,
                    input_summary=input_summary,
                    output_summary=output_summary,
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                    related_warehouse_id=warehouse_id,
                    related_buyer_id=buyer_id,
                    related_deal_id=deal_id,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(log_entry)
                await session.commit()
                logger.debug(
                    "[%s] Activity logged: action=%s, tokens=%d",
                    self.agent_name,
                    action,
                    tokens_used,
                )

        except Exception as exc:
            # DB logging must never break agent operation
            logger.warning(
                "[%s] Failed to log activity to DB: %s", self.agent_name, exc
            )

    async def _safe_log_activity(
        self,
        action: str,
        input_summary: str,
        output_summary: str,
        tokens_used: int,
        latency_ms: int,
        warehouse_id: Optional[str] = None,
        buyer_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> None:
        """Fire-and-forget wrapper around ``log_activity``.

        Schedules the DB write as a background task so it never blocks
        the calling agent (prevents SQLite lock contention during
        concurrent AI calls).
        """
        import asyncio

        asyncio.ensure_future(self._do_log_activity(
            action=action,
            input_summary=input_summary,
            output_summary=output_summary,
            tokens_used=tokens_used,
            latency_ms=latency_ms,
            warehouse_id=warehouse_id,
            buyer_id=buyer_id,
            deal_id=deal_id,
        ))

    async def _do_log_activity(
        self,
        action: str,
        input_summary: str,
        output_summary: str,
        tokens_used: int,
        latency_ms: int,
        warehouse_id: Optional[str] = None,
        buyer_id: Optional[str] = None,
        deal_id: Optional[str] = None,
    ) -> None:
        """Actual DB write for agent logs, runs in background."""
        try:
            await self.log_activity(
                action=action,
                input_summary=input_summary,
                output_summary=output_summary,
                tokens_used=tokens_used,
                latency_ms=latency_ms,
                warehouse_id=warehouse_id,
                buyer_id=buyer_id,
                deal_id=deal_id,
            )
        except Exception as exc:
            logger.warning(
                "[%s] _safe_log_activity suppressed error: %s",
                self.agent_name,
                exc,
            )
