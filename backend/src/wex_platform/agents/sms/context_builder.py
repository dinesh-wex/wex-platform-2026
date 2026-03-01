"""Context Builder — assembles structured prompt sections for each agent.

Converts raw state dicts, MessageInterpretation objects, and match data
into formatted text blocks that are injected into LLM prompts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import MessageInterpretation
from .field_catalog import get_label

MAX_RECENT_MESSAGES = 8


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CriteriaPropertyContext:
    """Minimal property info for Criteria Agent context — lets LLM match user references."""
    id: str
    city: str = ""
    state: str = ""
    rate: float | None = None
    features: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def format_recent_messages_as_text(
    history: list[dict], limit: int = MAX_RECENT_MESSAGES
) -> str:
    """Format conversation history into readable text.

    Args:
        history: List of dicts with ``role`` and ``content`` keys.
        limit: Maximum number of recent messages to include.

    Returns:
        Formatted string like::

            RECENT CONVERSATION:
            Buyer: Looking for 5000 sqft in Dallas
            You: Got it — any preference on timing?
    """
    if not history:
        return ""

    _BUYER_ROLES = {"buyer", "user", "inbound"}
    _AGENT_ROLES = {"agent", "assistant", "outbound"}

    recent = history[-limit:]
    lines: list[str] = []
    for msg in recent:
        role_raw = (msg.get("role") or "").lower().strip()
        if role_raw in _BUYER_ROLES:
            label = "Buyer"
        elif role_raw in _AGENT_ROLES:
            label = "You"
        else:
            label = role_raw.capitalize() or "?"
        content = (msg.get("content") or "")[:300]
        lines.append(f"{label}: {content}")

    if not lines:
        return ""
    return "RECENT CONVERSATION:\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# Criteria Agent context builders
# ---------------------------------------------------------------------------

def build_interpretation_context(interpretation: MessageInterpretation) -> str:
    """Render a MessageInterpretation as a readable prompt section.

    Returns a block like::

        PRE-PARSED MESSAGE DATA:
        - City: Dallas
        - Size: 5000 sqft
        ...
    """
    parts: list[str] = []

    if interpretation.cities:
        parts.append(f"- City: {', '.join(interpretation.cities)}")
    if interpretation.states:
        parts.append(f"- State: {', '.join(interpretation.states)}")

    if interpretation.sqft is not None:
        parts.append(f"- Size: {interpretation.sqft:,} sqft")
    if interpretation.min_sqft is not None and interpretation.min_sqft != interpretation.sqft:
        parts.append(f"- Min size: {interpretation.min_sqft:,} sqft")
    if interpretation.max_sqft is not None:
        parts.append(f"- Max size: {interpretation.max_sqft:,} sqft")

    if interpretation.features:
        parts.append(f"- Features: {', '.join(interpretation.features)}")
    if interpretation.topics:
        parts.append(f"- Topics: {', '.join(interpretation.topics)}")
    if interpretation.positional_references:
        parts.append(f"- Positional references: {', '.join(interpretation.positional_references)}")
    if interpretation.action_keywords:
        parts.append(f"- Action keywords: {', '.join(interpretation.action_keywords)}")
    if interpretation.emails:
        parts.append(f"- Emails: {', '.join(interpretation.emails)}")
    if interpretation.names:
        parts.append(f"- Names: {', '.join(interpretation.names)}")
    if interpretation.address_text:
        parts.append(f"- Address text: {interpretation.address_text}")
    if interpretation.query_type and interpretation.query_type != "general":
        parts.append(f"- Query type: {interpretation.query_type}")

    if not parts:
        return ""
    return "PRE-PARSED MESSAGE DATA:\n" + "\n".join(parts)


def build_criteria_agent_state(
    state: dict,
    presented_properties: list[CriteriaPropertyContext] | None = None,
) -> str:
    """Render the conversation state for the Criteria Agent.

    Args:
        state: Dict with keys ``turn``, ``phase``, ``renter_name``,
               ``criteria``, ``selected_property_id``.
        presented_properties: Optional list of lightweight property contexts
            so the LLM can resolve user references like "the Dallas one".

    Returns:
        Formatted state block.
    """
    lines: list[str] = [
        f"- Turn: {state.get('turn', 1)}",
        f"- Phase: {state.get('phase', 'INTAKE')}",
    ]

    renter_name = state.get("renter_name")
    if renter_name:
        lines.append(f"- Buyer name: {renter_name}")

    criteria = state.get("criteria")
    if criteria:
        crit_parts = [f"{k}={v}" for k, v in criteria.items() if v is not None]
        if crit_parts:
            lines.append(f"- Criteria so far: {', '.join(crit_parts)}")

    selected = state.get("selected_property_id")
    if selected:
        lines.append(f"- Focused property: {selected}")

    section = "CURRENT CONVERSATION STATE:\n" + "\n".join(lines)

    if presented_properties:
        prop_lines: list[str] = []
        for i, p in enumerate(presented_properties, 1):
            loc = f"{p.city}, {p.state}" if p.state else p.city
            rate_str = f"${p.rate:.2f}/sqft" if p.rate is not None else "rate TBD"
            feat_str = f" [{', '.join(p.features)}]" if p.features else ""
            prop_lines.append(f"  Option {i} (id={p.id}): {loc}, {rate_str}{feat_str}")
        section += "\n\nPRESENTED PROPERTIES:\n" + "\n".join(prop_lines)

    return section


# ---------------------------------------------------------------------------
# Response Agent context builders
# ---------------------------------------------------------------------------

def build_property_context(
    property_data: dict | None,
    match_summaries: list[dict] | None,
) -> str:
    """Format property details and match summaries for the Response Agent.

    Uses ``field_catalog.get_label`` for human-readable field names when
    rendering property_data answers.
    """
    sections: list[str] = []

    # Single-property detail block
    if property_data:
        lines: list[str] = []
        prop_id = property_data.get("id")
        if prop_id:
            lines.append(f"Property ID: {prop_id}")

        answers = property_data.get("answers")
        if answers and isinstance(answers, dict):
            for fkey, fval in answers.items():
                label = get_label(fkey)
                lines.append(f"- {label}: {fval}")

        # Fallback flat keys (from stub lookup)
        for key in ("city", "state", "address", "sqft", "rate"):
            val = property_data.get(key)
            if val is not None and key not in (answers or {}):
                label = get_label(key)
                lines.append(f"- {label}: {val}")

        if lines:
            sections.append("PROPERTY DETAILS:\n" + "\n".join(lines))

    # Match summaries
    if match_summaries:
        option_lines: list[str] = []
        for i, m in enumerate(match_summaries, 1):
            city = m.get("city", "?")
            st = m.get("state", "")
            location = f"{city}, {st}" if st else city
            rate = m.get("rate")
            rate_str = f"${rate:.2f}/sqft" if rate else "rate TBD"
            monthly = m.get("monthly")
            monthly_str = f" (~${monthly:,}/mo)" if monthly else ""
            option_lines.append(f"Option {i}: {location} - {rate_str}{monthly_str}")
        sections.append("MATCH OPTIONS:\n" + "\n".join(option_lines))

    return "\n\n".join(sections)


def build_action_context(
    action: str | None,
    clarification_needed: str | None = None,
    has_escalation: bool = False,
) -> str:
    """Map the decided action to an instruction block for the Response Agent.

    Actions: ``search``, ``lookup``, ``schedule_tour``,
    ``commitment_handoff``, ``collect_info``, ``None``.
    """
    _ACTION_INSTRUCTIONS = {
        "search": "Run a warehouse search with the buyer's criteria. Confirm what you understood and let them know you're looking.",
        "lookup": "Look up specific details about the focused property. Answer the buyer's question from the data provided.",
        "schedule_tour": "The buyer wants to tour a property. Acknowledge their interest and ask for 2-3 preferred days/times.",
        "commitment_handoff": "The buyer wants to commit/book. Guide them through the commitment flow and share any links provided.",
        "collect_info": "Collect the buyer's name and/or email to proceed. Ask naturally without being pushy.",
    }

    parts: list[str] = []

    if action:
        instruction = _ACTION_INSTRUCTIONS.get(action, f"Proceed with action: {action}")
        parts.append(f"- Action: {action}")
        parts.append(f"- Instruction: {instruction}")
    else:
        parts.append("- Action: respond (no tool execution needed)")
        parts.append("- Instruction: Reply naturally based on context and conversation state.")

    if clarification_needed:
        parts.append(f"- Clarification needed: {clarification_needed}")

    if has_escalation:
        parts.append("- Note: Some questions have been escalated to the property owner. Acknowledge that you're looking into it.")

    if not parts:
        return ""
    return "WHAT TO DO:\n" + "\n".join(parts)


def build_response_agent_state(
    state: dict,
    match_summaries: list[dict] | None = None,
    name_capture_prompt: str | None = None,
    pending_escalation: bool = False,
) -> str:
    """Render full state context for the Response Agent.

    Args:
        state: Dict with keys ``turn``, ``phase``, ``renter_name``,
               ``criteria``, ``selected_property_id``.
        match_summaries: Current match list (for count).
        name_capture_prompt: If set, the agent should append a name question.
        pending_escalation: If True, some buyer questions are awaiting owner answers.
    """
    turn = state.get("turn", 1)
    phase = state.get("phase", "INTAKE")
    renter_name = state.get("renter_name")
    criteria = state.get("criteria")
    selected = state.get("selected_property_id")

    lines: list[str] = [
        f"- Turn: {turn}",
        f"- Phase: {phase}",
    ]

    is_first = turn <= 1
    if is_first:
        lines.append("- IS_FIRST_MESSAGE: yes (can be longer, up to 800 chars)")

    if renter_name:
        lines.append(f"- Buyer name: {renter_name} (use naturally, don't overuse)")

    if criteria:
        crit_parts = [f"{k}={v}" for k, v in criteria.items() if v is not None]
        if crit_parts:
            lines.append(f"- Criteria: {', '.join(crit_parts)}")

    if selected:
        lines.append(f"- Focused property: {selected}")

    if match_summaries:
        lines.append(f"- Matches available: {len(match_summaries)}")

    section = "CONVERSATION STATE:\n" + "\n".join(lines)

    if name_capture_prompt:
        section += (
            f"\n\nNAME_CAPTURE:\n"
            f"Append this question naturally at the END of your response: \"{name_capture_prompt}\""
        )

    if pending_escalation:
        section += (
            "\n\nPENDING_OWNER_QUESTIONS:\n"
            "Some of the buyer's questions have been forwarded to the property owner. "
            "Let the buyer know you're looking into it and will follow up."
        )

    return section


# ---------------------------------------------------------------------------
# Top-level prompt assemblers (upgraded from dict-returning originals)
# ---------------------------------------------------------------------------

def build_criteria_context(
    message: str,
    interpretation: MessageInterpretation,
    phase: str,
    conversation_history: list[dict] | None = None,
    existing_criteria: dict | None = None,
    presented_match_summaries: list[dict] | None = None,
    *,
    turn: int = 1,
    renter_name: str | None = None,
    selected_property_id: str | None = None,
    presented_properties: list[CriteriaPropertyContext] | None = None,
) -> str:
    """Build a formatted prompt section for the Criteria Agent.

    Returns a single string combining state, interpretation, and history.
    """
    sections: list[str] = []

    # 1. State block
    state_dict = {
        "turn": turn,
        "phase": phase,
        "renter_name": renter_name,
        "criteria": existing_criteria,
        "selected_property_id": selected_property_id,
    }
    state_text = build_criteria_agent_state(state_dict, presented_properties)
    if state_text:
        sections.append(state_text)

    # 2. Interpretation context
    interp_text = build_interpretation_context(interpretation)
    if interp_text:
        sections.append(interp_text)

    # 3. Buyer message
    sections.append(f'BUYER MESSAGE:\n"{message}"')

    # 4. Conversation history
    history_text = format_recent_messages_as_text(
        conversation_history or [], limit=MAX_RECENT_MESSAGES
    )
    if history_text:
        sections.append(history_text)

    return "\n\n".join(sections)


def build_response_context(
    message: str,
    intent: str,
    phase: str,
    criteria: dict | None = None,
    property_data: dict | None = None,
    match_summaries: list[dict] | None = None,
    conversation_history: list[dict] | None = None,
    response_hint: str | None = None,
    is_first_message: bool = False,
    *,
    retry_hint: str | None = None,
    name_capture_prompt: str | None = None,
    renter_name: str | None = None,
    pending_escalation: bool = False,
    cached_answer: str | None = None,
    extracted_fields: dict | None = None,
    action: str | None = None,
    clarification_needed: str | None = None,
    has_escalation: bool = False,
    turn: int = 1,
    selected_property_id: str | None = None,
) -> str:
    """Build a formatted prompt section for the Response Agent.

    Returns a single string combining property context, action context,
    state, history, and any retry / hint information.
    """
    sections: list[str] = []

    # 1. Property + matches
    prop_text = build_property_context(property_data, match_summaries)
    if prop_text:
        sections.append(prop_text)

    # 2. Action context
    action_text = build_action_context(action, clarification_needed, has_escalation)
    if action_text:
        sections.append(action_text)

    # 3. State block
    state_dict = {
        "turn": turn,
        "phase": phase,
        "renter_name": renter_name,
        "criteria": criteria,
        "selected_property_id": selected_property_id,
    }
    state_text = build_response_agent_state(
        state_dict,
        match_summaries=match_summaries,
        name_capture_prompt=name_capture_prompt,
        pending_escalation=pending_escalation,
    )
    if state_text:
        sections.append(state_text)

    # 4. Buyer message + intent
    sections.append(f'BUYER MESSAGE (intent={intent}):\n"{message}"')

    # 5. Conversation history
    history_text = format_recent_messages_as_text(
        conversation_history or [], limit=MAX_RECENT_MESSAGES
    )
    if history_text:
        sections.append(history_text)

    # 6. Response hint from orchestrator / criteria agent
    if response_hint:
        sections.append(f"RESPONSE HINT:\n{response_hint}")

    # 7. Cached answer (from escalation cache or detail fetcher)
    if cached_answer:
        sections.append(f"CACHED ANSWER (use this to respond):\n{cached_answer}")

    # 8. Extracted fields (from detail fetcher)
    if extracted_fields:
        ef_lines = [f"- {get_label(k)}: {v}" for k, v in extracted_fields.items() if v is not None]
        if ef_lines:
            sections.append("EXTRACTED FIELDS:\n" + "\n".join(ef_lines))

    # 9. Retry hint (gatekeeper rejection feedback)
    if retry_hint:
        sections.append(f"PREVIOUS ATTEMPT REJECTED:\n{retry_hint}\nFix the issue in this attempt.")

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Match summary builder (UNCHANGED — preserve every line)
# ---------------------------------------------------------------------------

def build_match_summaries(matches: list, buyer_sqft: int | None = None) -> list[dict]:
    """Build match summary dicts from ClearingEngine tier1 results or ORM objects.

    Args:
        matches: ClearingEngine tier1 results or ORM objects.
        buyer_sqft: Buyer's requested sqft — used to calculate monthly estimate.

    ClearingEngine tier1 match structure:
        {
            "warehouse_id": "...",
            "warehouse": {"id": "...", "city": "...", "building_size_sqft": ...,
                          "truth_core": {"max_sqft": ..., "supplier_rate_per_sqft": ...}},
            "buyer_rate": 1.08,
            "match_score": 0.85,
        }
    """
    summaries = []
    for match in matches:
        if isinstance(match, dict):
            # ClearingEngine tier1 format (has "warehouse" sub-dict)
            wh = match.get("warehouse", {})
            tc = wh.get("truth_core", {}) if isinstance(wh, dict) else {}

            prop_id = match.get("warehouse_id") or wh.get("id") or match.get("id")
            city = wh.get("city", "") or match.get("city", "")
            state = wh.get("state", "") or match.get("state", "")
            address = wh.get("address", "") or match.get("address", "")
            sqft = (
                tc.get("max_sqft")
                or wh.get("building_size_sqft")
                or match.get("available_sqft")
                or match.get("sqft")
            )
            rate = (
                match.get("buyer_rate")
                or tc.get("supplier_rate_per_sqft")
                or match.get("rate")
            )

            monthly = round(rate * buyer_sqft) if rate and buyer_sqft else None
            # Match reasoning from ClearingAgent LLM + property description
            reasoning = match.get("reasoning", "")
            description = wh.get("description", "") or ""
            summaries.append({
                "id": prop_id,
                "city": city,
                "state": state,
                "address": address,
                "sqft": sqft,
                "rate": rate,
                "monthly": monthly,
                "match_score": match.get("match_score"),
                "reasoning": reasoning,
                "description": description,
            })
        else:
            # ORM object
            prop = getattr(match, 'warehouse', None) or getattr(match, 'property_ref', None) or match
            listing = getattr(prop, 'listing', None)
            knowledge = getattr(prop, 'knowledge', None)
            summaries.append({
                "id": getattr(prop, 'id', None),
                "city": getattr(prop, 'city', ''),
                "state": getattr(prop, 'state', ''),
                "address": getattr(prop, 'address', ''),
                "sqft": getattr(listing, 'available_sqft', None) or getattr(knowledge, 'building_size_sqft', None) if listing or knowledge else None,
                "rate": getattr(listing, 'supplier_rate_per_sqft', None) if listing else None,
            })
    return summaries
