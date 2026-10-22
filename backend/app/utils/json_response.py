"""The app's default JSON response: every float rounded to two decimal places.

The number rule (user request, 2026-10-22): any value with a fraction is sent
with at most two digits after the point (ROAS 3.4567 -> 3.46, KWD 1.255 ->
1.26); the frontend then shows exactly two (lib/format/number.ts). Whole
numbers and ints are untouched. Map coordinates keep full precision, since two
places would move a pin by up to a kilometre.
"""

from typing import Any

from fastapi.responses import JSONResponse

# Keys whose float values are exempt from rounding.
_KEEP_PRECISION = frozenset({"latitude", "longitude", "lat", "lng"})


def round_floats(value: Any, key: str | None = None) -> Any:
    if isinstance(value, float):
        return value if key in _KEEP_PRECISION else round(value, 2)
    if isinstance(value, dict):
        return {k: round_floats(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [round_floats(v, key) for v in value]
    return value


class RoundedJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return super().render(round_floats(content))
