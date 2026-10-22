"""Phone numbers to E.164 (SPEC-BE-108 FR3)."""
import phonenumbers


def normalize(raw: str | None, country: str | None = None) -> str | None:
    """E.164 ("+8801712345678") or None when the input isn't a valid number.

    `country` (ISO 3166 alpha-2, the company's country) is the default region for
    numbers written without a country code, e.g. "01712345678" in Bangladesh."""
    if not raw or not raw.strip():
        return None
    try:
        parsed = phonenumbers.parse(raw.strip(), (country or "").upper() or None)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def digits(raw: str | None) -> str:
    return "".join(ch for ch in raw or "" if ch.isdigit())
