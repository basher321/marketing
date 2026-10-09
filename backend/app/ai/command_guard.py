"""Faithfulness guard for Command Chat plans (SPEC-BE-085).

Runs on the model's raw actions *before* schema validation, so that a plan
does what the user typed and nothing else:

- scope (FR3): a non-read step whose request words don't appear in what the
  user typed is left out;
- provenance (FR2): a value the user's words don't support is removed. A
  removed required param then becomes the usual fixed-template question
  (command_actions.question_for); a removed optional param falls back to its
  default and is listed in the reply.

Evidence (FR1) is only text the user typed. AI-written text and context data
never count, with two exceptions: ids must appear in the planner context sent
to the model (or in the user's text), and SKUs must exist for the tenant.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from typing import Any

from app.ai import command_actions as ca

# ---------------------------------------------------------------------------
# Numbers
# ---------------------------------------------------------------------------
_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "hundred": 100,
}
_SCALES = {"k": 1000, "thousand": 1000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "million": 1_000_000}
_NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(?:\s*(k|thousand|lakhs?|lac|million)\b)?", re.IGNORECASE)
_COUNT = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"
_DURATION = re.compile(rf"\b{_COUNT}\s*-?\s*(weeks?|months?)\b", re.IGNORECASE)
_TOLERANCE = Decimal("0.005")


def _normalize(text: str) -> str:
    return text.translate(_BN_DIGITS)


def _count_value(word: str) -> int | None:
    word = word.lower()
    if word.isdigit():
        return int(word)
    if word in ("a", "an"):
        return 1
    return _NUMBER_WORDS.get(word)


def numbers_in(text: str) -> set[Decimal]:
    """Every number written in the text: digits (Bengali digits too), 1,500,
    1.5k, 2 lakh, and the number words one-twenty, thirty, forty, fifty,
    hundred."""
    text = _normalize(text)
    found: set[Decimal] = set()
    for m in _NUMBER.finditer(text):
        raw = m.group(1).rstrip(",").replace(",", "")
        try:
            value = Decimal(raw)
        except InvalidOperation:
            continue
        if m.group(2):
            value *= _SCALES[m.group(2).lower()]
        found.add(value)
    for word in re.findall(r"[a-z]+", text.lower()):
        if word in _NUMBER_WORDS:
            found.add(Decimal(_NUMBER_WORDS[word]))
    return found


def _day_counts(text: str, numbers: set[Decimal]) -> set[Decimal]:
    # A duration in days: any written number, weeks x 7, a fortnight = 14,
    # a month = 28-31 days, N months = 30 x N.
    counts = set(numbers)
    for m in _DURATION.finditer(_normalize(text)):
        n = _count_value(m.group(1))
        if not n:
            continue
        if m.group(2).lower().startswith("week"):
            counts.add(Decimal(7 * n))
        elif n == 1:
            counts.update(Decimal(d) for d in (28, 29, 30, 31))
        else:
            counts.add(Decimal(30 * n))
    if re.search(r"\bfortnight\b", text, re.IGNORECASE):
        counts.add(Decimal(14))
    return counts


def _as_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        return None


def _number_ok(value: Decimal, numbers: set[Decimal]) -> bool:
    return any(abs(value - n) < _TOLERANCE for n in numbers)


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------
# Common names CLDR doesn't use (CLDR names come from utils/locale_data).
_COUNTRY_ALIASES: dict[str, tuple[str, ...]] = {
    "US": ("usa", "u.s.", "u.s.a.", "america", "united states of america"),
    "GB": ("uk", "u.k.", "britain", "great britain", "england", "scotland", "wales"),
    "AE": ("uae", "u.a.e.", "emirates"),
    "BD": ("বাংলাদেশ",),
    "KR": ("south korea",),
    "CZ": ("czech republic",),
    "TR": ("turkey",),
    "NL": ("holland",),
}
# Country names that are also everyday words or US states; never read from a
# brief or an ad location (FR10), only from a Command Chat message.
AMBIGUOUS_COUNTRY_NAMES = {"TD", "JO", "GE", "TR"}


@lru_cache(maxsize=1)
def _country_names() -> tuple[tuple[str, str], ...]:
    from app.utils import locale_data

    pairs: list[tuple[str, str]] = []
    for code, info in locale_data.countries().items():
        name = str(info.get("name") or "")
        variants = {name, re.sub(r"\s*\(.*?\)", "", name), name.replace(" SAR China", "")}
        pairs.extend((code, v.strip()) for v in variants if v.strip())
    for code, aliases in _COUNTRY_ALIASES.items():
        pairs.extend((code, a) for a in aliases)
    return tuple(pairs)


def country_codes_in(text: str, case_sensitive: bool = False, exclude: set[str] | frozenset[str] = frozenset()) -> set[str]:
    """ISO codes of the countries whose name (or a listed alias) appears in
    the text as a whole word."""
    flags = 0 if case_sensitive else re.IGNORECASE
    found: set[str] = set()
    for code, name in _country_names():
        if code in exclude or code in found:
            continue
        if case_sensitive and name.islower():
            continue  # lowercase aliases ("usa", "uk") only match case-insensitively
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, flags):
            found.add(code)
    return found


# ---------------------------------------------------------------------------
# URLs, dates, times
# ---------------------------------------------------------------------------
_URL = re.compile(r"(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)+(?::\d+)?(?:/[^\s<>\"'\]]*)?", re.IGNORECASE)


def _norm_url(url: str) -> str:
    url = url.strip().rstrip(".,;:!?)").lower()
    url = re.sub(r"^https?://", "", url)
    return re.sub(r"^www\.", "", url).rstrip("/")


_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4, "april": 4, "may": 5,
    "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}
_WEEKDAYS = {
    "monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "tues": 1, "wednesday": 2, "wed": 2, "thursday": 3, "thu": 3,
    "thurs": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5, "sunday": 6, "sun": 6,
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_WEEKDAY_RE = "|".join(sorted(_WEEKDAYS, key=len, reverse=True))


def _safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def _upcoming(today: dt.date, month: int, day: int, year: int | None) -> dt.date | None:
    if year is not None:
        return _safe_date(year if year > 99 else 2000 + year, month, day)
    found = _safe_date(today.year, month, day)
    if found is not None and found < today:
        found = _safe_date(today.year + 1, month, day)
    return found


def dates_in(text: str, today: dt.date) -> set[dt.date]:
    """Dates the text names, resolved against the company-local `today`."""
    text = _normalize(text)
    low = text.lower()
    found: set[dt.date] = set()

    def add(value: dt.date | None) -> None:
        if value is not None:
            found.add(value)

    for y, m, d in re.findall(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        add(_safe_date(int(y), int(m), int(d)))
    for a, b, y in re.findall(r"\b(\d{1,2})[/.](\d{1,2})(?:[/.](\d{2,4}))?\b", text):
        year = int(y) if y else None
        add(_upcoming(today, int(b), int(a), year))  # day/month
        add(_upcoming(today, int(a), int(b), year))  # month/day
    for d, mon, y in re.findall(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MONTH_RE})\.?\b(?:,?\s*(\d{{4}}))?", low):
        add(_upcoming(today, _MONTHS[mon], int(d), int(y) if y else None))
    for mon, d, y in re.findall(rf"\b({_MONTH_RE})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s*(\d{{4}}))?", low):
        add(_upcoming(today, _MONTHS[mon], int(d), int(y) if y else None))
    if re.search(r"\b(today|tonight)\b|আজ", low):
        add(today)
    if re.search(r"\btomorrow\b|আগামীকাল|কাল", low):
        add(today + dt.timedelta(days=1))
    if re.search(r"\bday after tomorrow\b|পরশু", low):
        add(today + dt.timedelta(days=2))
    for name in re.findall(rf"\b({_WEEKDAY_RE})s?\b", low):
        ahead = (_WEEKDAYS[name] - today.weekday()) % 7
        add(today + dt.timedelta(days=ahead))
        add(today + dt.timedelta(days=ahead + 7))
    for n in re.findall(rf"\b(?:in|after)\s+{_COUNT}\s+days?\b|\b{_COUNT}\s+days?\s+from\s+(?:now|today)\b", low):
        value = _count_value(next(x for x in n if x)) if isinstance(n, tuple) else _count_value(n)
        if value:
            add(today + dt.timedelta(days=value))
    # "Over the next N days" starts tomorrow (the planner's rule, SPEC-BE-078).
    if re.search(r"\b(?:next|coming|following)\s+(?:\d+|[a-z]+)\s+days?\b", low):
        add(today + dt.timedelta(days=1))
    if re.search(r"\bnext week\b", low):
        add(today + dt.timedelta(days=7))
        add(today + dt.timedelta(days=7 - today.weekday()))
    if re.search(r"\bweekend\b", low):
        ahead = (5 - today.weekday()) % 7
        add(today + dt.timedelta(days=ahead))
        add(today + dt.timedelta(days=ahead + 1))
    if re.search(r"\b(?:end of (?:the |this )?month|month[- ]end)\b", low):
        first_next = (today.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        add(first_next - dt.timedelta(days=1))
    if re.search(r"\bnext month\b", low):
        add((today.replace(day=1) + dt.timedelta(days=32)).replace(day=1))
    return found


def times_in(text: str) -> set[str]:
    """Times of day ("HH:MM") the text names. A bare hour without am/pm counts
    as either half of the day."""
    text = _normalize(text)
    low = text.lower()
    found: set[str] = set()

    def add(hour: int, minute: int = 0) -> None:
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            found.add(f"{hour:02d}:{minute:02d}")

    def both(hour: int, minute: int = 0) -> None:
        if 1 <= hour <= 12:
            add(hour % 12, minute)
            add(hour % 12 + 12, minute)

    for h, mi, half in re.findall(r"\b(\d{1,2})(?:[:.](\d{2}))?\s*(a\.?m\.?|p\.?m\.?)(?!\w)", low):
        hour, minute = int(h), int(mi or 0)
        if 1 <= hour <= 12:
            add(hour % 12 + (12 if half.startswith("p") else 0), minute)
    for h, mi in re.findall(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", low):
        add(int(h), int(mi))
        if 1 <= int(h) <= 11:
            add(int(h) + 12, int(mi))
    for h in re.findall(r"\bat\s+(\d{1,2})\b(?![:.]\d|\s*(?:%|days?|a\.?m|p\.?m))", low):
        both(int(h))
    for h in re.findall(r"\b(\d{1,2})\s*o'?clock\b", low):
        both(int(h))
    for h in re.findall(r"(\d{1,2})\s*টা", low):
        both(int(h))
    if re.search(r"\b(noon|midday)\b", low):
        add(12)
    if re.search(r"\bmidnight\b", low):
        add(0)
    return found


_FEMALE = re.compile(r"\b(women|woman|female|females|ladies|lady|girls|mothers|moms|mums)\b|মহিলা|নারী", re.IGNORECASE)
_MALE = re.compile(r"\b(men|man|male|males|gentlemen|guys|boys|fathers|dads)\b|পুরুষ", re.IGNORECASE)
_FREE = re.compile(r"\bfree\b|ফ্রি|বিনামূল্যে", re.IGNORECASE)
_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


@dataclass
class Evidence:
    text: str
    lower: str
    numbers: set[Decimal]
    day_counts: set[Decimal]
    dates: set[dt.date]
    times: set[str]
    urls: set[str]
    countries: set[str]
    capital_codes: set[str]
    free: bool


def build_evidence(text: str, today: dt.date) -> Evidence:
    numbers = numbers_in(text)
    return Evidence(
        text=text,
        lower=text.lower(),
        numbers=numbers,
        day_counts=_day_counts(text, numbers),
        dates=dates_in(text, today),
        times=times_in(text),
        urls={_norm_url(u) for u in _URL.findall(text)},
        countries=country_codes_in(text),
        capital_codes=set(re.findall(r"\b[A-Z]{2}\b", text)),
        free=bool(_FREE.search(text)),
    )


# ---------------------------------------------------------------------------
# Scope (FR3): the words that ask for each non-read action
# ---------------------------------------------------------------------------
_PUBLISH = r"publish|launch|go live|run|start|activate|turn (?:it |them )?on|live|চালু|লঞ্চ|প্রকাশ"
_SHIPPING = r"shipping|ship|delivery|deliver|courier|zone|rate|method|pickup|ডেলিভারি|শিপিং"
_SCOPE: dict[str, str] = {
    "adjust_inventory": r"stock|inventory|on hand|on-hand|units|restock|quantity|qty|স্টক",
    "create_pricing_rule": r"discount|price|pricing|sale|off|offer|promo|deal|cheaper|markdown|ছাড়|দাম|ডিসকাউন্ট",
    "update_product": r"archive|unarchive|activate|deactivate|draft|rename|title|status|unpublish|publish|hide|unhide|out of stock|in stock|restore",
    "create_shipping_zone": _SHIPPING,
    "add_shipping_rate": _SHIPPING,
    "update_shipping_rate": _SHIPPING + r"|price|cost|fee|charge|change|update",
    "set_free_shipping_threshold": r"free|threshold|ফ্রি",
    "enable_shipping_rate": r"enable|turn (?:it |them )?on|activate|switch on|reactivate|চালু",
    "disable_shipping_rate": r"disable|turn (?:it |them )?off|deactivate|switch off|stop|pause|বন্ধ",
    "sync_shipping": r"sync|import|refresh|pull|fetch|reload",
    "generate_content": r"copy|caption|headline|text|creative|write|draft|ad|ads|slogan|tagline|লিখ",
    "create_ai_campaign": r"campaign|ad|ads|advert|promot|boost|marketing|ক্যাম্পেইন|বিজ্ঞাপন",
    "create_organic_posts": r"post|content|caption|write|draft|create|publish|share|reel|story|পোস্ট|কনটেন্ট",
    "create_organic_post": r"post|content|caption|write|draft|create|publish|share|reel|story|পোস্ট|কনটেন্ট",
    # SPEC-BE-092: naming the tool ("nano banana", "google flow", "veo", "sora") is a request too.
    "generate_photo": r"photo|image|picture|pic|visual|graphic|banner|poster|nano ?banana|ছবি",
    "generate_video": r"video|clip|reel|animation|google flow|veo|sora|ভিডিও",
    "regenerate_organic_copy": r"rewrite|regenerate|redo|rephrase|change|new caption|another|different|edit|improve|shorter|longer|caption|text|hashtag|title|cta|fix",
    # Writing posts is not a request to schedule them: scheduling needs a
    # scheduling word, a time/day, or "post it/them ...".
    "schedule_organic_posts": (
        r"schedule|publish|go live|queue|post (?:it|them|this|these|those|on|to|at|every|daily|tomorrow|today|tonight)"
        r"|share (?:it|them|on|to)|put (?:it|them) out|send (?:it|them) out|at \d|tomorrow|tonight|today|every day|daily"
        r"|(?:next|coming|following) (?:\d+|[a-z]+) days|শিডিউল|প্রকাশ|পোস্ট কর"
    ),
    "publish_organic_now": r"publish|post (?:it|this|that|them) now|go live|now|immediately|right away|প্রকাশ",
    "cancel_organic_post": r"cancel|delete|remove|stop|unschedule|বাতিল",
    "reschedule_organic_post": r"reschedule|move|postpone|delay|push|change the (?:time|date|day)|shift|earlier|later",
    "create_meta_campaign_draft": r"campaign|ad|ads|advert|promot|boost|meta|facebook|instagram|ক্যাম্পেইন|বিজ্ঞাপন",
    "publish_meta_campaign": _PUBLISH,
    "publish_zernio_campaign": r"campaign|ad|ads|advert|promot|boost|meta|facebook|instagram|zernio|ক্যাম্পেইন|বিজ্ঞাপন",
    "launch_campaign": _PUBLISH,
    "pause_meta": r"pause|stop|turn (?:it |them )?off|halt|suspend|disable|বন্ধ",
    "resume_meta": r"resume|restart|unpause|turn (?:it |them )?back on|reactivate|re-enable|continue|start again|চালু",
    "update_meta_budget": r"budget|spend|increase|decrease|raise|lower|reduce|double|halve|বাজেট",
    "create_workflow": r"workflow|automation|automate|automatically|whenever|every time|each time|when|if|rule|trigger|alert me|notify me|remind",
    "update_workflow": r"workflow|automation|rule|change|edit|update|modify|adjust",
    "enable_workflow": r"enable|turn (?:it |this |that )?on|activate|switch on|start|go live|চালু",
    "disable_workflow": r"disable|turn (?:it |this |that )?off|deactivate|switch off|stop|pause|বন্ধ",
    "run_workflow": r"run|execute|trigger|test|fire|start",
    "notify_owner": r"notify|tell|alert|inform|message|let (?:me|the owner|owner)|ping|email me|জানা",
    "create_task": r"task|todo|to-do|to do|remind|assign|purchase order|po\b|follow up|follow-up",
    "call_webhook": r"webhook|call|post to|send to|hit|ping",
}
_SCOPE_RE = {k: re.compile(rf"(?<!\w)(?:{v})", re.IGNORECASE) for k, v in _SCOPE.items()}


def requested(action_type: str, evidence: Evidence) -> bool:
    pattern = _SCOPE_RE.get(action_type)
    return True if pattern is None else bool(pattern.search(evidence.text))


# ---------------------------------------------------------------------------
# Provenance (FR2)
# ---------------------------------------------------------------------------
_NUMBER_PARAMS = {
    "budget", "value", "threshold", "rate", "free_over", "new_on_hand", "count", "duration_days", "duration_s",
    "age_min", "age_max", "sla_days_min", "sla_days_max",
}
_COUNTRY_PARAMS = {"countries", "country_codes"}
_URL_PARAMS = {"destination_url", "landing_url", "url", "link_url"}
_DATE_PARAMS = {"start_date", "end_date", "date"}
_SKU_PARAMS = {"sku", "skus", "product_skus"}

_KEEP = object()  # "the value is supported, keep it as it is"


@dataclass
class GuardResult:
    actions: list[Any]
    not_requested: dict[int, str] = field(default_factory=dict)  # position -> step label
    left_out: list[dict[str, Any]] = field(default_factory=list)  # {"index", "field", "label"}


def _is_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(ca.REF_RE.match(value))


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def _date_value(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        return None


class _Checker:
    def __init__(self, ctx: ca.ExecContext, ev: Evidence, context_text: str, context: dict[str, Any]) -> None:
        self.ctx = ctx
        self.ev = ev
        self.context_text = context_text.lower()
        self.stock = {str(p.get("sku", "")).lower(): p.get("stock") for p in context.get("products") or []}
        self.zernio_accounts = list(((context.get("zernio_ads") or {}).get("ad_accounts")) or [])
        self._skus: dict[str, str] | None = None

    def tenant_skus(self) -> dict[str, str]:
        if self._skus is None:
            from app.models.product import Product

            rows = (
                self.ctx.db.query(Product.sku)
                .filter(Product.tenant_id == self.ctx.tenant_id, Product.deleted_at.is_(None))
                .all()
            )
            self._skus = {str(sku).lower(): str(sku) for (sku,) in rows}
        return self._skus

    def number(self, name: str, value: Any, params: dict[str, Any]) -> bool:
        num = _as_decimal(value)
        if num is None:
            return True  # not a number: the schema check reports it
        if name == "count" and num == 1:
            return True
        if name == "rate" and num == 0 and self.ev.free:
            return True
        pool = self.ev.day_counts if name == "duration_days" else self.ev.numbers
        if _number_ok(num, pool):
            return True
        if name == "new_on_hand":
            # "Add 10 units of SKU-1" = current stock + 10 (stock from the context).
            stock = self.stock.get(str(params.get("sku", "")).lower())
            if isinstance(stock, int):
                return any(abs(num - (stock + sign * n)) < _TOLERANCE for n in self.ev.numbers for sign in (1, -1))
        return False

    def countries(self, value: Any) -> bool:
        codes = [value] if isinstance(value, str) else value if isinstance(value, list) else []
        for code in codes:
            if not isinstance(code, str):
                return True  # the schema check reports it
            upper = code.upper()
            if upper not in self.ev.countries and upper not in self.ev.capital_codes:
                return False
        return True

    def url(self, value: Any) -> bool:
        return not isinstance(value, str) or _norm_url(value) in self.ev.urls

    def date(self, name: str, value: Any) -> bool:
        day = _date_value(value)
        if day is None:
            return True  # not a date: the schema check reports it
        if day in self.ev.dates:
            return True
        if name == "end_date":
            # "For 7 days from tomorrow": a start date plus N-1 or N days.
            for start in self.ev.dates:
                gap = (day - start).days
                if gap > 0 and any(Decimal(gap) == n or Decimal(gap + 1) == n for n in self.ev.day_counts):
                    return True
        return False

    def time(self, value: Any) -> bool:
        return not isinstance(value, str) or value in self.ev.times

    def genders(self, value: Any) -> bool:
        if value == "female":
            return bool(_FEMALE.search(self.ev.text))
        if value == "male":
            return bool(_MALE.search(self.ev.text))
        return True

    def timezone(self, value: Any) -> bool:
        if not isinstance(value, str):
            return True
        zone = value.lower()
        if zone in ("utc", "etc/utc", "gmt", "etc/gmt"):
            return bool(re.search(r"\b(utc|gmt)\b", self.ev.lower))
        city = zone.split("/")[-1].replace("_", " ")
        return zone in self.ev.lower or city in self.ev.lower

    def ids(self, value: Any) -> bool:
        for s in _strings(value):
            if _ID.match(s) and not _is_ref(s):
                low = s.lower()
                if low not in self.context_text and low not in self.ev.lower:
                    return False
        return True

    def ad_account(self, value: Any) -> bool:
        """SPEC-BE-090: a Zernio ad account from the context, kept only when it's the
        only one or the user named it (its id, or a distinctive word of its name)."""
        match = next((a for a in self.zernio_accounts if a.get("id") == value), None)
        if match is None:
            return False
        if len(self.zernio_accounts) == 1 or str(value).lower() in self.ev.lower:
            return True
        words = set(re.findall(r"[^\W\d_]{3,}", str(match.get("name") or "").lower())) - {"account", "ads", "the"}
        return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", self.ev.lower) for w in words)

    def skus(self, value: Any) -> Any:
        """_KEEP, False (unknown SKU), or the value with the stored spelling."""
        known = self.tenant_skus()
        items = [value] if isinstance(value, str) else value if isinstance(value, list) else None
        if items is None:
            return _KEEP
        fixed: list[Any] = []
        for item in items:
            if not isinstance(item, str) or _is_ref(item):
                fixed.append(item)
                continue
            stored = known.get(item.strip().lower())
            if stored is None:
                return False
            fixed.append(stored)
        if fixed == items:
            return _KEEP
        return fixed[0] if isinstance(value, str) else fixed

    def check(self, name: str, value: Any, params: dict[str, Any]) -> Any:
        """_KEEP, False (unsupported: remove it) or a replacement value."""
        if _is_ref(value):
            return _KEEP
        if not self.ids(value):
            return False
        if name == "ad_account_id":
            return _KEEP if self.ad_account(value) else False
        if name in _NUMBER_PARAMS:
            return _KEEP if self.number(name, value, params) else False
        if name in _COUNTRY_PARAMS:
            return _KEEP if self.countries(value) else False
        if name in _URL_PARAMS:
            return _KEEP if self.url(value) else False
        if name in _DATE_PARAMS:
            return _KEEP if self.date(name, value) else False
        if name == "time_local":
            return _KEEP if self.time(value) else False
        if name == "genders":
            return _KEEP if self.genders(value) else False
        if name == "timezone":
            return _KEEP if self.timezone(value) else False
        if name in _SKU_PARAMS:
            return self.skus(value)
        if name == "trigger_config" and isinstance(value, dict) and "threshold" in value:
            # "Below 10" is threshold 9: the trigger fires at or below it.
            num = _as_decimal(value["threshold"])
            if num is not None and not _number_ok(num, self.ev.numbers) and not _number_ok(num + 1, self.ev.numbers):
                return {k: v for k, v in value.items() if k != "threshold"}
        return _KEEP


def guard_actions(
    ctx: ca.ExecContext,
    raw_actions: list[Any],
    evidence: str,
    context_text: str,
    context: dict[str, Any],
    today: dt.date,
) -> GuardResult:
    """Returns the raw actions with unsupported values removed, the steps the
    user didn't ask for, and the optional values that were left out."""
    ev = build_evidence(evidence, today)
    checker = _Checker(ctx, ev, context_text, context)
    result = GuardResult(actions=[])
    for position, item in enumerate(raw_actions, start=1):
        action = ca.resolve(item["type"]) if isinstance(item, dict) and isinstance(item.get("type"), str) else None
        if action is None:
            result.actions.append(item)  # validate_actions reports it
            continue
        if action.risk != "read" and not requested(action.type, ev):
            result.not_requested[position] = action.label
        params = item.get("params")
        if not isinstance(params, dict):
            result.actions.append(item)
            continue
        kept: dict[str, Any] = {}
        for name, value in params.items():
            verdict = checker.check(name, value, params)
            if verdict is _KEEP:
                kept[name] = value
                continue
            if verdict is not False:
                kept[name] = verdict  # corrected (SKU spelling) or trimmed (workflow threshold)
                continue
            spec = action.params.model_fields.get(name)
            if spec is not None and not spec.is_required():
                if value == spec.default:
                    kept[name] = value  # the default anyway: nothing was invented
                    continue
                result.left_out.append({"index": position, "field": name, "label": action.label})
            # A removed required param becomes the fixed-template question.
        result.actions.append({**item, "params": kept})
    return result
