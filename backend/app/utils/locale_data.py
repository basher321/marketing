"""Worldwide reference data: countries, currencies, languages, timezones (SPEC-BE-072).

Built once at import from Babel (Unicode CLDR, the same data browsers use for
Intl) and pytz's country -> timezone table, so the settings page and the
backend validation share one source. Everything here is static for the
process lifetime; it is built on first use (about 1 second) and cached.

Mapping rules:
- Countries: CLDR two-letter territories, minus CLDR's non-country codes
  (EU, UN, ZZ, QO, pseudo-locales...). XK (Kosovo) is kept: it is
  user-assigned in ISO 3166 but universally used for Kosovo.
- Currencies: those legal tender today in at least one country (historic
  ones such as DEM are excluded). `decimals` is the ISO 4217 minor unit
  (JPY 0, USD 2, KWD 3).
- Money storage is NOT ISO minor units: every *_cents column holds
  amount x 100 for every currency (JPY 1,500 = 150000). format_money()
  divides by 100 and then shows the currency's own decimals.
- Languages: ISO 639-1 two-letter codes. A tag with a region or script
  (en-US, pt-BR, zh-Hant, es-419) is valid when its base language is.
- Timezones: the canonical IANA zones assigned to a country, plus UTC.
  Legacy aliases (US/Eastern, Asia/Calcutta, Etc/GMT+5...) are refused for
  new saves but still load.
"""
import re
import unicodedata
from functools import cache
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytz  # type: ignore[import-untyped]
from babel import Locale, UnknownLocaleError, localedata
from babel.numbers import get_currency_name, get_currency_precision, get_currency_symbol, get_territory_currencies

_EN = Locale("en")
# CLDR territory codes that are not countries (regions, pseudo-locales, unknown).
_NOT_COUNTRIES = {"AC", "CP", "CQ", "DG", "EA", "EU", "EZ", "IC", "QO", "TA", "UN", "XA", "XB", "ZZ"}
# pytz has no zone for Kosovo; it uses Belgrade time.
_EXTRA_TIMEZONES = {"XK": ["Europe/Belgrade"]}
_LANGUAGE_TAG = re.compile(r"^([a-z]{2})(?:-([A-Za-z]{4}|[A-Za-z]{2}|\d{3}))?$")


def _currencies_for(country: str) -> list[str]:
    return list(get_territory_currencies(country, date.today(), tender=True, non_tender=False))


def _likely_locale(country: str) -> Locale | None:
    try:
        return Locale.parse(f"und_{country}")
    except (UnknownLocaleError, ValueError):
        return None


def _symbol(code: str, home_countries: list[str]) -> str:
    """The short symbol people use ("৳", "₦", "$"), else the ISO code.

    English CLDR data gives "$", "€", "¥", "₹"... but only the code for many
    others (BDT, NGN). Then the home country's own locale is asked, and its
    symbol is used only when it is made of currency signs (so "৳" is taken,
    while an Arabic-letter symbol such as KWD's is not, and the code stays).
    """
    english = get_currency_symbol(code, "en")
    if english != code:
        return english
    for country in home_countries[:2]:  # each lookup loads a locale file
        loc = _likely_locale(country)
        local = loc.currency_symbols.get(code) if loc else None
        if local and all(unicodedata.category(ch) == "Sc" for ch in local):
            return local
    return code


@cache
def _build() -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, str]], list[str]]:
    countries: dict[str, dict[str, Any]] = {}
    users: dict[str, list[str]] = {}
    for code, name in _EN.territories.items():
        if not re.fullmatch(r"[A-Z]{2}", code) or code in _NOT_COUNTRIES:
            continue
        currencies = _currencies_for(code)
        for cur in currencies:
            users.setdefault(cur, []).append(code)
        countries[code] = {
            "code": code,
            "name": name,
            "currency": currencies[0] if currencies else None,
            "timezones": list(pytz.country_timezones.get(code, _EXTRA_TIMEZONES.get(code, []))),
        }
    currencies_out: dict[str, dict[str, Any]] = {}
    for cur, home in users.items():
        currencies_out[cur] = {
            "code": cur,
            "name": get_currency_name(cur, locale="en"),
            "symbol": _symbol(cur, home),
            "decimals": get_currency_precision(cur),
        }
    languages: dict[str, dict[str, str]] = {}
    with_data = set(localedata.locale_identifiers())
    for code, name in _EN.languages.items():
        if not re.fullmatch(r"[a-z]{2}", code):
            continue
        native = name
        if code in with_data:
            try:
                native = Locale.parse(code).get_display_name(code) or name
            except (UnknownLocaleError, ValueError):
                pass
        languages[code] = {"code": code, "name": name, "native_name": native}
    zones = sorted({z for zs in pytz.country_timezones.values() for z in zs} | {"UTC"})
    return countries, currencies_out, languages, zones


def countries() -> dict[str, dict[str, Any]]:
    return _build()[0]


def currencies() -> dict[str, dict[str, Any]]:
    return _build()[1]


def languages() -> dict[str, dict[str, str]]:
    return _build()[2]


def timezones() -> list[str]:
    return _build()[3]


@cache
def _timezone_set() -> frozenset[str]:
    return frozenset(timezones())


def utc_offset(zone: str, at: datetime | None = None) -> str:
    """Current offset of a zone as "+06:00" / "-03:30"."""
    offset = (at or datetime.now(timezone.utc)).astimezone(ZoneInfo(zone)).utcoffset()
    minutes = int(offset.total_seconds() // 60) if offset else 0
    sign = "+" if minutes >= 0 else "-"
    return f"{sign}{abs(minutes) // 60:02d}:{abs(minutes) % 60:02d}"


def locale_options() -> dict[str, Any]:
    """GET /tenants/locale-options payload (built per call: offsets follow DST)."""
    now = datetime.now(timezone.utc)
    zones = [{"name": z, "offset": utc_offset(z, now)} for z in timezones()]
    return {
        "countries": sorted(countries().values(), key=lambda c: c["name"]),
        "currencies": sorted(currencies().values(), key=lambda c: c["code"]),
        "languages": sorted(languages().values(), key=lambda lang: lang["name"]),
        "timezones": zones,
    }


def is_country(code: str) -> bool:
    return code in countries()


def is_currency(code: str) -> bool:
    return code in currencies()


def is_language(tag: str) -> bool:
    match = _LANGUAGE_TAG.match(tag)
    return match is not None and match.group(1) in languages()


def is_timezone(zone: str) -> bool:
    return zone in _timezone_set()


# Old IANA names that browsers (Chrome's ICU) still report, mapped to the
# current name in our list. Used for sign-up detection and error hints.
TIMEZONE_ALIASES = {
    "Asia/Calcutta": "Asia/Kolkata", "Asia/Katmandu": "Asia/Kathmandu", "Asia/Saigon": "Asia/Ho_Chi_Minh",
    "Asia/Rangoon": "Asia/Yangon", "Asia/Dacca": "Asia/Dhaka", "Asia/Ulan_Bator": "Asia/Ulaanbaatar",
    "Asia/Thimbu": "Asia/Thimphu", "Europe/Kiev": "Europe/Kyiv", "Atlantic/Faeroe": "Atlantic/Faroe",
    "America/Godthab": "America/Nuuk", "America/Buenos_Aires": "America/Argentina/Buenos_Aires",
    "America/Catamarca": "America/Argentina/Catamarca", "America/Cordoba": "America/Argentina/Cordoba",
    "America/Jujuy": "America/Argentina/Jujuy", "America/Mendoza": "America/Argentina/Mendoza",
    "America/Indianapolis": "America/Indiana/Indianapolis", "America/Louisville": "America/Kentucky/Louisville",
    "Pacific/Ponape": "Pacific/Pohnpei", "Pacific/Truk": "Pacific/Chuuk", "Pacific/Enderbury": "Pacific/Kanton",
    "Africa/Asmera": "Africa/Asmara", "Etc/UTC": "UTC", "Etc/GMT": "UTC", "GMT": "UTC",
    "US/Eastern": "America/New_York", "US/Central": "America/Chicago", "US/Mountain": "America/Denver",
    "US/Pacific": "America/Los_Angeles",
}


def canonical_timezone(zone: str | None) -> str | None:
    """A zone from our list for `zone` (old names mapped), or None if unusable."""
    if not zone:
        return None
    zone = zone.strip()
    if is_timezone(zone):
        return zone
    mapped = TIMEZONE_ALIASES.get(zone)
    return mapped if mapped and is_timezone(mapped) else None


def language_name(code: str) -> str | None:
    """English name of a language code ("sw" -> "Swahili"), or None."""
    entry = languages().get(code.lower().split("-")[0])
    return entry["name"] if entry else None


def format_money(cents: int | None, currency: str) -> str:
    """Human-readable amount from a *_cents value (amount x 100, every currency).

    The currency's own decimals are shown: 185000 BDT -> "৳1,850.00",
    150000 JPY -> "¥1,500", 185000 KWD -> "KWD 1,850.000". A symbol made of
    letters (or the bare code) is separated by a space.
    """
    code = (currency or "").strip().upper()
    info = currencies().get(code)
    decimals = info["decimals"] if info else 2
    symbol = info["symbol"] if info else code
    amount = (Decimal(cents or 0) / 100).quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    number = f"{abs(amount):,.{decimals}f}"
    if symbol and all(unicodedata.category(ch) == "Sc" or ch in "$" for ch in symbol[-1:]):
        return f"{sign}{symbol}{number}"
    return f"{sign}{symbol} {number}"
