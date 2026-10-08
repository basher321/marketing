"""Integration catalog and connection tests (SPEC-BE-052).

The catalog drives the Integrations page's forms: which fields each provider
needs and which are secret. `verify()` makes one cheap, read-only call to the
provider with the user's credentials to prove they work. It never logs
secrets; provider error text is cut to 300 characters.

Honest limit: a passing test proves the credentials, not that campaigns or
posts are published there - the publishing adapters are a later spec.

User-supplied hosts (Shopify domain, WooCommerce site, Salesforce instance,
SMTP host) must be public: https only for URLs, and a hostname that resolves
to no loopback / private / link-local address (server-side request forgery
guard).
"""
import ipaddress
import smtplib
import socket
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from app.integrations.meta_ads import graph_base

TIMEOUT_S = 10.0
ZOHO_DATA_CENTERS = ("com", "eu", "in", "com.au", "jp", "ca", "sa", "com.cn")


def _graph() -> str:
    # META_GRAPH_VERSION (SPEC-BE-054); was hard-coded to v19.0.
    return graph_base()


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    secret: bool = False
    required: bool = True
    help: str = ""


@dataclass(frozen=True)
class Provider:
    provider: str
    label: str
    category: str
    fields: tuple[Field, ...]
    docs_url: str


CATALOG: tuple[Provider, ...] = (
    Provider("meta_ads", "Meta Ads Manager", "Ads", (
        Field("access_token", "System user access token", secret=True, help="Business Settings › System users › Generate token (ads_read, ads_management)."),
        Field("ad_account_id", "Ad account ID", help="Numbers only, without the act_ prefix."),
        # Optional: needed to publish (SPEC-BE-054); "Connect with Facebook" fills them.
        Field("page_id", "Facebook Page ID", required=False, help="The Page the ads run as."),
        Field("instagram_id", "Instagram account ID", required=False, help="Needed to run on Instagram."),
        Field("pixel_id", "Meta Pixel ID", required=False, help="Needed for Conversions campaigns."),
    ), "https://developers.facebook.com/docs/marketing-api/system-users/"),
    Provider("tiktok_ads", "TikTok Ads", "Ads", (
        Field("access_token", "Access token", secret=True, help="TikTok for Business developer app › long-term access token."),
        Field("advertiser_id", "Advertiser ID"),
        Field("identity_id", "Identity ID", required=False, help="The TikTok identity your ads show as (used by AI campaigns)."),
    ), "https://business-api.tiktok.com/portal/docs"),
    # Google Ads also publishes YouTube ads (SPEC-BE-064).
    Provider("google_ads", "Google Ads (and YouTube)", "Ads", (
        Field("developer_token", "Developer token", secret=True, help="Google Ads API Center; Basic access or higher is needed to publish."),
        Field("client_id", "OAuth client ID"),
        Field("client_secret", "OAuth client secret", secret=True),
        Field("refresh_token", "OAuth refresh token", secret=True, help="From Google's OAuth consent with the adwords scope."),
        Field("customer_id", "Customer ID", help="10 digits, no dashes."),
        Field("login_customer_id", "Manager account ID", required=False, help="Only when access goes through a manager (MCC) account."),
    ), "https://developers.google.com/google-ads/api/docs/oauth/overview"),
    # SPEC-BE-065..068: the ad platforms added for the multi-platform Ad Manager.
    Provider("linkedin_ads", "LinkedIn Ads", "Ads", (
        Field("access_token", "Access token", secret=True, help="OAuth with rw_ads and r_ads_reporting."),
        Field("refresh_token", "Refresh token", secret=True, required=False, help="Used when the access token expires (60 days)."),
        Field("client_id", "Client ID", required=False),
        Field("client_secret", "Client secret", secret=True, required=False),
        Field("ad_account_id", "Ad account ID", help="Campaign Manager › account number."),
        Field("organization_urn", "Company Page (organization URN)", help="urn:li:organization:12345 — the Page your ads post as."),
    ), "https://learn.microsoft.com/linkedin/marketing/getting-started"),
    Provider("x_ads", "X Ads", "Ads", (
        Field("consumer_key", "API key (consumer key)"),
        Field("consumer_secret", "API key secret", secret=True),
        Field("access_token", "Access token", secret=True),
        Field("access_token_secret", "Access token secret", secret=True),
        Field("account_id", "Ads account ID"),
        Field("funding_instrument_id", "Funding source ID", required=False, help="Empty uses the account's first active funding source."),
    ), "https://docs.x.com/x-ads-api/getting-started"),
    Provider("snapchat_ads", "Snapchat Ads", "Ads", (
        Field("client_id", "OAuth client ID"),
        Field("client_secret", "OAuth client secret", secret=True),
        Field("refresh_token", "Refresh token", secret=True),
        Field("ad_account_id", "Ad account ID"),
        Field("public_profile_id", "Public profile ID", help="The brand profile your ads run from."),
    ), "https://developers.snap.com/api/marketing-api/Ads-API/authentication"),
    Provider("pinterest_ads", "Pinterest Ads", "Ads", (
        Field("access_token", "Access token", secret=True, help="Scopes: ads:read, ads:write, pins:read, pins:write, boards:read."),
        Field("refresh_token", "Refresh token", secret=True, required=False),
        Field("client_id", "App ID", required=False),
        Field("client_secret", "App secret", secret=True, required=False),
        Field("ad_account_id", "Ad account ID"),
        Field("board_id", "Default board ID", required=False, help="Where new Pins from AI campaigns are saved."),
    ), "https://developers.pinterest.com/docs/getting-started/set-up-authentication-and-authorization/"),
    # Organic publishing (SPEC-BE-075): the test runs the platform adapter's
    # check(), which also records the profile, permissions and limits.
    Provider("facebook", "Facebook Page", "Social", (
        Field("page_id", "Page ID"),
        Field("access_token", "Page access token", secret=True, help="Permissions: pages_manage_posts, pages_read_engagement."),
    ), "https://developers.facebook.com/docs/pages-api/"),
    Provider("instagram", "Instagram", "Social", (
        Field("ig_account_id", "Instagram business account ID"),
        Field("access_token", "Access token", secret=True, help="Permissions: instagram_basic, instagram_content_publish."),
    ), "https://developers.facebook.com/docs/instagram-platform/content-publishing/"),
    Provider("tiktok", "TikTok Business", "Social", (
        Field("access_token", "Access token", secret=True, help="Content Posting API scopes: video.publish (and video.list for results)."),
    ), "https://developers.tiktok.com/doc/content-posting-api-get-started"),
    Provider("linkedin", "LinkedIn Page", "Social", (
        Field("access_token", "Access token", secret=True, help="Scope w_organization_social (Community Management API)."),
        Field("organization_urn", "Company Page (organization URN)", help="urn:li:organization:12345"),
    ), "https://learn.microsoft.com/linkedin/marketing/community-management/shares/posts-api"),
    Provider("whatsapp", "WhatsApp Business", "Messaging", (
        Field("phone_number_id", "Phone number ID"),
        Field("access_token", "Access token", secret=True),
    ), "https://developers.facebook.com/docs/whatsapp/cloud-api/get-started"),
    Provider("smtp", "SMTP email", "Email", (
        Field("host", "SMTP host", help="e.g. smtp.gmail.com"),
        Field("port", "Port", help="587 (STARTTLS) or 465 (SSL)."),
        Field("username", "Username"),
        Field("password", "Password / app password", secret=True),
        Field("from_email", "From address"),
    ), "https://support.google.com/a/answer/176600"),
    Provider("sendgrid", "SendGrid", "Email", (
        Field("api_key", "API key", secret=True),
        Field("from_email", "From address"),
    ), "https://docs.sendgrid.com/ui/account-and-settings/api-keys"),
    Provider("shopify", "Shopify", "Commerce", (
        Field("shop_domain", "Shop domain", help="your-store.myshopify.com"),
        # Either a static Admin API token (older custom apps) or a Dev Dashboard
        # client ID + secret (stores created after 2026-01-01; 24-hour tokens),
        # SPEC-BE-058 decision 3. Scopes: read_shipping, write_shipping.
        Field("admin_token", "Admin API access token", secret=True, required=False, help="Older custom apps. Leave empty when using a client ID and secret."),
        Field("client_id", "Client ID", required=False, help="Dev Dashboard app (stores created after 2026-01-01)."),
        Field("client_secret", "Client secret", secret=True, required=False),
    ), "https://shopify.dev/docs/apps/auth/admin-app-access-tokens"),
    Provider("woocommerce", "WooCommerce", "Commerce", (
        Field("site_url", "Store URL", help="https://your-store.com"),
        Field("consumer_key", "Consumer key", secret=True),
        Field("consumer_secret", "Consumer secret", secret=True),
    ), "https://woocommerce.github.io/woocommerce-rest-api-docs/#authentication"),
    Provider("hubspot", "HubSpot CRM", "CRM", (
        Field("private_app_token", "Private app token", secret=True),
    ), "https://developers.hubspot.com/docs/api/private-apps"),
    Provider("zoho", "Zoho CRM", "CRM", (
        Field("client_id", "Client ID"),
        Field("client_secret", "Client secret", secret=True),
        Field("refresh_token", "Refresh token", secret=True),
        Field("dc", "Data center", help="com, eu, in, com.au, jp", required=False),
    ), "https://www.zoho.com/crm/developer/docs/api/v6/oauth-overview.html"),
    Provider("salesforce", "Salesforce", "CRM", (
        Field("instance_url", "Instance URL", help="https://your-domain.my.salesforce.com"),
        Field("client_id", "Consumer key"),
        Field("client_secret", "Consumer secret", secret=True),
        Field("refresh_token", "Refresh token", secret=True),
    ), "https://help.salesforce.com/s/articleView?id=sf.remoteaccess_oauth_refresh_token_flow.htm"),
)
BY_PROVIDER = {p.provider: p for p in CATALOG}
AD_PLATFORM_ADAPTERS = {"tiktok_ads": "tiktok_ads", "google_ads": "google_ads", "linkedin_ads": "linkedin_ads",
                        "x_ads": "x_ads", "snapchat_ads": "snapchat_ads", "pinterest_ads": "pinterest_ads"}


SOCIAL_PROVIDERS = ("facebook", "instagram", "tiktok", "linkedin")


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    message: str
    account_name: str | None = None
    # Social accounts only (SPEC-BE-075): handle, avatar, permissions, limits.
    profile: dict[str, Any] | None = None


class VerifyError(Exception):
    pass


# Swappable in tests (httpx.MockTransport) so no real third-party call is made.
def _default_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_S, follow_redirects=False)


client_factory: Callable[[], httpx.Client] = _default_client


def _short(text: object) -> str:
    return " ".join(str(text).split())[:300]


def _require_public_host(host: str) -> None:
    host = (host or "").strip().lower()
    if not host or host == "localhost" or host.endswith(".localhost"):
        raise VerifyError("Use a public hostname (localhost isn't allowed).")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise VerifyError(f"Can't resolve host {host}.") from None
    for info in infos:
        addr = ipaddress.ip_address(info[4][0])
        if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast:
            raise VerifyError("That host points to a private or local network address.")


def _public_https_base(url: str) -> str:
    raw = url.strip()
    if "://" not in raw:
        raw = "https://" + raw
    parsed = urlparse(raw)
    if parsed.scheme != "https" or not parsed.hostname:
        raise VerifyError("Use an https:// address.")
    _require_public_host(parsed.hostname)
    return f"https://{parsed.netloc}"


def _json_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return _short(resp.text) or f"HTTP {resp.status_code}"
    if isinstance(body, dict):
        err = body.get("error")
        if isinstance(err, dict):
            return _short(err.get("message") or err)
        for key in ("error_description", "message", "error", "errors", "msg"):
            if body.get(key):
                return _short(body[key])
    return _short(body)


def _get(url: str, **kwargs: Any) -> httpx.Response:
    with client_factory() as client:
        return client.get(url, **kwargs)


def _post(url: str, **kwargs: Any) -> httpx.Response:
    with client_factory() as client:
        return client.post(url, **kwargs)


def _ok_or_error(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        raise VerifyError(f"{resp.status_code}: {_json_error(resp)}")


def _graph_object(object_id: str, token: str, fields: str) -> dict[str, Any]:
    resp = _get(f"{_graph()}/{object_id}", params={"fields": fields, "access_token": token})
    _ok_or_error(resp)
    return resp.json()


def _oauth_refresh(url: str, f: dict[str, str]) -> None:
    resp = _post(url, data={"grant_type": "refresh_token", "client_id": f["client_id"], "client_secret": f["client_secret"], "refresh_token": f["refresh_token"]})
    _ok_or_error(resp)
    if "access_token" not in resp.json():
        raise VerifyError(_json_error(resp))


def _check(provider: str, f: dict[str, str]) -> str | None:
    """Run the provider's test call; return an account name when the API gives one."""
    if provider == "meta_ads":
        me = _graph_object("me", f["access_token"], "name")
        acct = _graph_object(f"act_{f['ad_account_id'].removeprefix('act_')}", f["access_token"], "name")
        page_id = (f.get("page_id") or "").strip()
        if page_id:
            # Ad sets send it as promoted_object[page_id]; a wrong ID (a profile,
            # another business's Page, or a Page not assigned to the system user)
            # only failed at publish time with "#100 must be a valid page ID".
            try:
                _graph_object(page_id, f["access_token"], "name")
            except VerifyError as exc:
                raise VerifyError(
                    f"Facebook Page ID {page_id} can't be used with this token ({exc}). Use the "
                    "Page's own ID and assign that Page to the system user in Business Settings."
                ) from None
        return acct.get("name") or me.get("name")
    if provider == "whatsapp":
        return _graph_object(f["phone_number_id"], f["access_token"], "display_phone_number,verified_name").get("verified_name")
    if provider in AD_PLATFORM_ADAPTERS:
        # The ad platform's own adapter (SPEC-BE-063..068) reads the account,
        # so the connection test and publishing share one implementation.
        import importlib

        from app.integrations.base_adapter import PlatformError

        adapter = importlib.import_module(f"app.integrations.{AD_PLATFORM_ADAPTERS[provider]}")
        try:
            account = adapter.verify_account(f)
        except PlatformError as exc:
            raise VerifyError(exc.message) from None
        return account.get("name")
    if provider == "zoho":
        # Allow-listed: the value becomes part of the hostname.
        dc = (f.get("dc") or "com").strip().lstrip(".").lower() or "com"
        if dc not in ZOHO_DATA_CENTERS:
            raise VerifyError(f"Data center must be one of: {', '.join(ZOHO_DATA_CENTERS)}.")
        _oauth_refresh(f"https://accounts.zoho.{dc}/oauth/v2/token", f)
        return None
    if provider == "salesforce":
        _oauth_refresh(f"{_public_https_base(f['instance_url'])}/services/oauth2/token", f)
        return None
    if provider == "sendgrid":
        resp = _get("https://api.sendgrid.com/v3/scopes", headers={"Authorization": f"Bearer {f['api_key']}"})
        _ok_or_error(resp)
        return None
    if provider == "shopify":
        from app.config import get_settings
        from app.integrations import shopify

        base = _public_https_base(f["shop_domain"])
        try:
            token = shopify.access_token(f)
        except shopify.ShopifyError as exc:
            raise VerifyError(exc.message) from None
        version = get_settings().SHOPIFY_API_VERSION
        resp = _get(f"{base}/admin/api/{version}/shop.json", headers={"X-Shopify-Access-Token": token})
        _ok_or_error(resp)
        return (resp.json().get("shop") or {}).get("name")
    if provider == "woocommerce":
        base = _public_https_base(f["site_url"])
        resp = _get(f"{base}/wp-json/wc/v3/system_status", auth=(f["consumer_key"], f["consumer_secret"]))
        _ok_or_error(resp)
        return ((resp.json().get("environment") or {}).get("site_url")) or None
    if provider == "hubspot":
        resp = _get("https://api.hubapi.com/crm/v3/objects/contacts", params={"limit": 1}, headers={"Authorization": f"Bearer {f['private_app_token']}"})
        _ok_or_error(resp)
        return None
    if provider == "smtp":
        _require_public_host(f["host"])
        try:
            port = int(f["port"])
        except ValueError:
            raise VerifyError("Port must be a number.") from None
        smtp_cls = smtplib.SMTP_SSL if port == 465 else smtplib.SMTP
        with smtp_cls(f["host"].strip(), port, timeout=TIMEOUT_S) as smtp:
            if port != 465:
                smtp.starttls()
            smtp.login(f["username"], f["password"])
        return f.get("from_email") or f["username"]
    raise VerifyError(f"No test available for {provider}.")


def _social(provider: str, fields: dict[str, str]) -> VerifyResult:
    from app.integrations.social_base import SocialError, adapter

    try:
        profile = adapter(provider).check(fields)
    except SocialError as exc:
        return VerifyResult(False, _short(exc.message))
    missing = profile.get("missing_permissions") or []
    message = f"Connected, but missing permissions: {', '.join(missing)}." if missing else "Connection verified."
    return VerifyResult(True, message, profile.get("account_name"), profile)


def verify(provider: str, fields: dict[str, str]) -> VerifyResult:
    try:
        if provider in SOCIAL_PROVIDERS:
            return _social(provider, fields)
        name = _check(provider, fields)
        return VerifyResult(True, "Connection verified.", name)
    except VerifyError as exc:
        return VerifyResult(False, _short(str(exc)))
    except httpx.TimeoutException:
        return VerifyResult(False, "The provider didn't answer within 10 seconds.")
    except httpx.HTTPError as exc:
        return VerifyResult(False, _short(f"Couldn't reach the provider ({type(exc).__name__})."))
    except smtplib.SMTPAuthenticationError:
        return VerifyResult(False, "SMTP login failed: wrong username or password.")
    except (smtplib.SMTPException, OSError) as exc:
        return VerifyResult(False, _short(f"SMTP error: {exc}"))
    except (KeyError, ValueError, TypeError) as exc:
        return VerifyResult(False, _short(f"Unexpected response from the provider ({type(exc).__name__})."))
