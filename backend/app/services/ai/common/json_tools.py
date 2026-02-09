"""Robust JSON extraction from LLM responses using sliding brace-balancing."""

from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def extract_json(text: str) -> dict | list | None:
    """Try to extract the first valid JSON object or array from *text*.

    Strategy:
    1. Attempt ``json.loads`` on the full text (fast path).
    2. Slide through the text looking for ``{`` or ``[`` and attempt
       brace-balanced extraction.
    3. Return ``None`` if nothing works.
    """
    if not text or not text.strip():
        return None

    stripped = text.strip()

    # Fast path: whole text is valid JSON
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # Sliding brace-balance
    for i, ch in enumerate(stripped):
        if ch == "{":
            result = _extract_balanced(stripped, i, "{", "}")
            if result is not None:
                return result
        elif ch == "[":
            result = _extract_balanced(stripped, i, "[", "]")
            if result is not None:
                return result

    return None


def _extract_balanced(
    text: str, start: int, open_ch: str, close_ch: str
) -> dict | list | None:
    """Extract a brace-balanced substring starting at *start* and parse it."""
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            if in_string:
                escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    return json.loads(candidate)
                except (json.JSONDecodeError, ValueError):
                    return None

    return None
