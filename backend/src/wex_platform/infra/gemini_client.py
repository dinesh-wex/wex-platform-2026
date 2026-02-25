"""Gemini model factory for WEx agents."""

import google.generativeai as genai

from wex_platform.app.config import get_settings


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
            generation_config["response_schema"] = response_schema

    return genai.GenerativeModel(
        model_name=model_name,
        generation_config=generation_config,
        system_instruction=system_instruction,
    )
