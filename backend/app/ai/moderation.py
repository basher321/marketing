"""Content safety and moderation pass (structural stub)."""
import re
from collections.abc import Sequence

_BLOCKED_TERMS = {"scam", "illegal"}


def moderate_text(text: str, extra_blocked_terms: Sequence[str] = ()) -> tuple[bool, list[str]]:
    # Returns (passed, matched_terms). Blocked terms are the built-in list plus
    # any caller-supplied terms (SPEC-BE-027 passes the tenant's
    # brand_settings.forbidden_terms). Matching is case-insensitive on whole
    # words/phrases (\b boundaries), so "scampi" does not match "scam".
    terms = {t.strip().lower() for t in (*_BLOCKED_TERMS, *extra_blocked_terms) if t.strip()}
    hits = sorted(
        term for term in terms if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE)
    )
    return (len(hits) == 0, hits)
