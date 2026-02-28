"""Gemini model factory for WEx agents."""

import copy

import google.generativeai as genai

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


def get_model(
    model_name: str = "gemini-3-flash-preview",
    temperature: float = 0.7,
    json_mode: bool = False,
    response_schema: dict | None = None,
    system_instruction: str | None = None,
):
    """Return a configured Gemini GenerativeModel instance.

    Args:
        model_name: Gemini model identifier.
        temperature: Generation temperature (0.0-2.0).
        json_mode: If True, constrain output to valid JSON.
        response_schema: Optional JSON Schema dict for structured output.
        system_instruction: Optional system-level instruction.

    Returns:
        A ``google.generativeai.GenerativeModel`` ready for generation.
    """
    settings = get_settings()
    genai.configure(api_key=settings.gemini_api_key)

    generation_config = {"temperature": temperature}
    if json_mode:
        generation_config["response_mime_type"] = "application/json"
        if response_schema:
            generation_config["response_schema"] = _inline_defs(response_schema)

    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
