"""Abstract adapter interface for third-party platform integrations."""
from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Every concrete integration adapter implements this interface."""

    provider_name: str = "base"

    def __init__(self, credentials: dict[str, Any]):
        self.credentials = credentials

    @abstractmethod
    def test_connection(self) -> bool:
        """Return True if the stored credentials can authenticate successfully."""
        raise NotImplementedError

    @abstractmethod
    def fetch_account_info(self) -> dict[str, Any]:
        """Return basic account/profile info for display in the UI."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Ad platform adapter contract (SPEC-BE-062). Each of
# integrations/{tiktok,google,linkedin,x,snapchat,pinterest}_ads.py exposes
# these module-level functions once its spec (SPEC-BE-063..068) is built; the
# Ad Manager service checks for `publish` to know a platform is ready.
#
#   validate(conn, tree) -> list[issue]          platform rules + validate-only call
#   lookup(conn, kind, q) -> list[{id, name, type?, extra?}]
#   upload_media(conn, filename, content) -> {media_id, kind, name, thumbnail_url?}
#   publish(conn, tree, mode) -> {"campaign": id, "groups": {row_id: id},
#                                 "ads": {row_id: id}, "url": str | None}
#       Campaign first (paused), then groups, then ads; switched active at the
#       end when mode == "active". All-or-nothing: on any failure the adapter
#       deletes/archives what it created in reverse order, then raises
#       PlatformError.
#   set_status(conn, level, external_id, active) -> None
#   import_results(conn, since) -> list[daily metric rows]
#
# `conn` is integration_service.ad_platform_connection(): decrypted fields,
# never logged or returned to a client.
# ---------------------------------------------------------------------------
class PlatformError(Exception):
    """A platform call failed. `message` is safe to show (no secrets); `path`
    names the tree node (e.g. "groups[0].ads[1]"); `auth` marks a rejected or
    expired credential so the integration card can ask for a reconnect."""

    def __init__(self, message: str, status_code: int = 502, path: str | None = None, auth: bool = False):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.path = path
        self.auth = auth


# ---------------------------------------------------------------------------
# Shared helpers for the ad platform adapters (SPEC-BE-063..068).
# ---------------------------------------------------------------------------
import httpx  # noqa: E402 - kept next to the helpers that use it
import structlog  # noqa: E402

_log = structlog.get_logger(__name__)

# Sources whose analytics_events rows are ad results (SPEC-BE-056 for Meta,
# SPEC-BE-062 for the rest). Reports filter on this list, which keeps seeded
# demo rows ('demo-seed') out of CTR/ROAS.
AD_RESULT_SOURCES = ("meta", "tiktok", "google", "linkedin", "x", "snapchat", "pinterest")


def _default_client() -> httpx.Client:
    return httpx.Client(timeout=30.0, follow_redirects=False)


# Swappable in tests and by the dev fakes (httpx.MockTransport): every ad
# platform adapter makes its HTTP calls through this one factory.
client_factory = _default_client


def http(method: str, url: str, **kwargs: object) -> httpx.Response:
    """One HTTP call; network failures become a PlatformError (no secrets)."""
    try:
        with client_factory() as client:
            return client.request(method, url, **kwargs)  # type: ignore[arg-type]
    except httpx.TimeoutException:
        raise PlatformError("The platform didn't answer in time; try again.", 504) from None
    except httpx.HTTPError as exc:
        raise PlatformError(f"Couldn't reach the platform ({type(exc).__name__}).", 502) from None


def short(text: object, limit: int = 300) -> str:
    return " ".join(str(text).split())[:limit]


def micros(amount: object) -> int:
    """Major units (e.g. 12.5) -> micros (12_500_000), the unit Google, LinkedIn
    (for some fields), X, Snapchat and Pinterest use for money."""
    from decimal import ROUND_HALF_UP, Decimal

    return int((Decimal(str(amount)) * 1_000_000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def entries(targeting: dict[str, object], key: str) -> list[dict[str, object]]:
    value = targeting.get(key)
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def ids(targeting: dict[str, object], key: str) -> list[str]:
    return [str(e["id"]) for e in entries(targeting, key) if e.get("id")]


def issue(level: str, row_id: object, path: str, message: str, severity: str = "error") -> dict[str, object]:
    return {"level": level, "id": str(row_id) if row_id else None, "path": path, "message": message, "severity": severity}


def unresolved(tree: dict[str, object], keys: tuple[str, ...], label: str) -> list[dict[str, object]]:
    """Targeting entries typed while not connected (id None) must be picked
    from the platform's own list before publishing."""
    out: list[dict[str, object]] = []
    groups: list[dict[str, Any]] = tree["groups"]  # type: ignore[assignment]
    for gi, g in enumerate(groups):
        for key in keys:
            loose = [str(e.get("name")) for e in entries(g["targeting"], key) if not e.get("id")]
            if loose:
                out.append(issue("group", g["id"], f"groups[{gi}].targeting.{key}",
                                 f"Pick {', '.join(loose)} from {label}'s list ({key.replace('_', ' ')})."))
    return out


class Rollback:
    """Records what a publish created; on failure undoes it in reverse order.
    Cleanup errors are logged, never raised, so the original error surfaces."""

    def __init__(self, platform: str) -> None:
        self.platform = platform
        self.steps: list[tuple[str, object]] = []

    def add(self, what: str, undo: object) -> None:
        self.steps.append((what, undo))

    def run(self) -> None:
        for what, undo in reversed(self.steps):
            try:
                undo()  # type: ignore[operator]
            except Exception:  # noqa: BLE001 - best effort, the publish already failed
                _log.warning("ad_platform_cleanup_failed", platform=self.platform, object=what)
