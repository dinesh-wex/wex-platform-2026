"""Gemini model factory for WEx agents.

Uses the ``google-genai`` SDK (``from google import genai``) which is the
current client for Gemini 3-series models.
"""

import copy
from typing import Optional

from google import genai
from google.genai import types

from wex_platform.app.config import get_settings


# Fields that Pydantic v2 adds to JSON Schema but Gemini's API rejects
_UNSUPPORTED_KEYS = {
    "$defs", "definitions", "title", "default", "examples",
    "additionalProperties", "maximum", "minimum", "exclusiveMaximum",
    "exclusiveMinimum", "maxLength", "minLength", "pattern",
    "maxItems", "minItems", "uniqueItems",
}


def _inline_defs(schema: dict) -> dict:
    """Clean a Pydantic JSON Schema for Gemini consumption.

    Resolves $defs/$ref references (inlines them) and strips fields
    that the Google genai SDK doesn't support (title, default, etc.).
    """
    schema = copy.deepcopy(schema)
    defs = schema.pop("$defs", None) or schema.pop("definitions", None)

    def _resolve(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = node["$ref"]
                ref_name = ref_path.rsplit("/", 1)[-1]
                if defs and ref_name in defs:
                    resolved = copy.deepcopy(defs[ref_name])
                    _resolve(resolved)
                    return resolved
                return node
            # Strip unsupported keys
            for key in _UNSUPPORTED_KEYS:
                node.pop(key, None)
            for key, value in list(node.items()):
                node[key] = _resolve(value)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                node[i] = _resolve(item)
        return node

    return _resolve(schema)


# ---------------------------------------------------------------------------
# Module-level client singleton
# ---------------------------------------------------------------------------
_client: Optional[genai.Client] = None


def get_client() -> genai.Client:
    """Return a singleton ``genai.Client`` configured with the API key."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def build_generate_config(
    temperature: float = 0.7,
    json_mode: bool = False,
    response_schema: dict | None = None,
    system_instruction: str | None = None,
) -> types.GenerateContentConfig:
    """Build a ``GenerateContentConfig`` for ``client.models.generate_content``.

    Args:
        temperature: Generation temperature (0.0-2.0).
        json_mode: If True, constrain output to valid JSON.
        response_schema: Optional JSON Schema dict for structured output.
        system_instruction: Optional system-level instruction.

    Returns:
        A ``types.GenerateContentConfig`` instance.
    """
    kwargs: dict = {"temperature": temperature}

    if json_mode:
        kwargs["response_mime_type"] = "application/json"
        if response_schema:
            kwargs["response_schema"] = _inline_defs(response_schema)

    if system_instruction:
        kwargs["system_instruction"] = system_instruction

    return types.GenerateContentConfig(**kwargs)
