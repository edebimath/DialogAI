"""Tags decide which callers a knowledge-base entry is for.

An entry without tags is for everyone. A tagged entry is used only when the caller has at least
one of its tags. Tags are compared in a normalized form: trimmed, single-spaced, Turkish
lowercase ("Mevcut Müşteri" == "mevcut müşteri").
"""

import re

MAX_TAG_LENGTH = 64


def normalize_tag(tag: str) -> str:
    text = re.sub(r"\s+", " ", tag).strip()
    # str.lower() maps "I" to "i" and "İ" to "i̇"; Turkish wants "ı" and "i".
    return text.replace("I", "ı").replace("İ", "i").lower()[:MAX_TAG_LENGTH]


def normalize_tags(tags: list[str]) -> list[str]:
    """Normalized, without empties or duplicates, in the given order."""
    seen: dict[str, None] = {}
    for tag in tags:
        if normalized := normalize_tag(tag):
            seen.setdefault(normalized, None)
    return list(seen)


def parse_tags(text: str) -> list[str]:
    """Tags from a comma-separated text, e.g. a flow's rendered "Arayan etiketleri"."""
    return normalize_tags(text.split(","))


def visible_to(entry_tags: list[str], caller_tags: list[str] | None) -> bool:
    """The rule the search applies in SQL, for tests and the UI's explanations."""
    if caller_tags is None or not entry_tags:
        return True
    return bool(set(entry_tags) & set(caller_tags))
