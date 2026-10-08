"""XSS/injection sanitization for free-text user input."""
import html
import re

_SCRIPT_TAG_RE = re.compile(r"<\s*script.*?>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)


def sanitize_text(value: str) -> str:
    without_scripts = _SCRIPT_TAG_RE.sub("", value)
    return html.escape(without_scripts, quote=False)
