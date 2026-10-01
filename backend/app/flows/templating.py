"""Fills {{ key }} / {{ key.sub }} placeholders from the call state."""

import re
from collections.abc import Callable
from typing import Any

from app.flows.validator import PLACEHOLDER


def render(text: str, state: dict[str, Any], escape: Callable[[str], str] | None = None) -> str:
    """Fill placeholders from state; missing keys render empty.

    escape: applied to each filled value, e.g. URL-quoting for addresses or JSON-escaping for
    request bodies, so a caller's words can't change the structure around them.
    """

    def substitute(match: re.Match) -> str:
        current: Any = state
        for part in match.group(0).strip("{} \t").split("."):
            if not isinstance(current, dict) or part not in current:
                return ""
            current = current[part]
        value = "" if current is None else str(current)
        return escape(value) if escape else value

    return PLACEHOLDER.sub(substitute, text)
