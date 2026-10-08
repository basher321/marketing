"""Media storage backends (SPEC-BE-074).

`get_storage()` returns the backend chosen by STORAGE_PROVIDER:
- local : files under MEDIA_ROOT (default backend/media/), served to the
          outside world only through the signed /media/f/{token} route.
- s3    : any S3-compatible bucket (AWS, R2, MinIO...) signed with SigV4 over
          httpx (no SDK). Path-style URLs: {STORAGE_ENDPOINT}/{bucket}/{key}.
          `presign_get()` gives platforms (Instagram, TikTok pull) a public
          https URL straight from the bucket.

Keys are "<tenant_id>/<media_id>.<ext>"; callers never build paths themselves.
Credentials are never logged.
"""
import datetime as dt
import hashlib
import hmac
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import structlog

from app.config import get_settings
from app.integrations.base_adapter import PlatformError, http

logger = structlog.get_logger(__name__)

CHUNK = 1024 * 1024


class Storage(Protocol):
    name: str

    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def open_range(self, key: str, start: int, end: int) -> Iterator[bytes]: ...
    def delete(self, key: str) -> None: ...
    def presign_get(self, key: str, ttl_s: int) -> str | None: ...


class StorageError(Exception):
    pass


class LocalStorage:
    name = "local"

    def __init__(self, root: str) -> None:
        base = Path(root)
        if not base.is_absolute():
            base = Path(__file__).resolve().parents[2] / base  # relative to backend/
        self.root = base

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise StorageError("Invalid storage key.")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def get(self, key: str) -> bytes:
        try:
            return self._path(key).read_bytes()
        except FileNotFoundError:
            raise StorageError("The file is missing from storage.") from None

    def open_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        path = self._path(key)
        if not path.exists():
            raise StorageError("The file is missing from storage.")

        def gen() -> Iterator[bytes]:
            with path.open("rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(CHUNK, left))
                    if not chunk:
                        break
                    left -= len(chunk)
                    yield chunk

        return gen()

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass

    def presign_get(self, key: str, ttl_s: int) -> str | None:
        return None  # served by the backend's own signed route


# ---------------------------------------------------------------------------
# S3 (SigV4)
# ---------------------------------------------------------------------------
def _hmac(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def _uri(path: str) -> str:
    return quote(path, safe="/-_.~")


class S3Storage:
    name = "s3"

    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str,
                 clock: "type[dt.datetime] | None" = None) -> None:
        if not endpoint.startswith("https://") and not endpoint.startswith("http://"):
            raise StorageError("STORAGE_ENDPOINT must be an http(s) URL for S3 storage.")
        self.endpoint = endpoint.rstrip("/")
        self.host = self.endpoint.split("://", 1)[1]
        self.bucket = bucket
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self._clock = clock or dt.datetime

    def _now(self) -> dt.datetime:
        return self._clock.now(dt.timezone.utc)

    def _signing_key(self, day: str) -> bytes:
        k = _hmac(("AWS4" + self.secret_key).encode(), day)
        k = _hmac(k, self.region)
        k = _hmac(k, "s3")
        return _hmac(k, "aws4_request")

    def _path(self, key: str) -> str:
        return f"/{self.bucket}/{key}"

    def _signed_headers(self, method: str, key: str, payload_hash: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        now = self._now()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        day = now.strftime("%Y%m%d")
        headers = {"host": self.host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date, **(extra or {})}
        names = sorted(h.lower() for h in headers)
        canonical_headers = "".join(f"{n}:{str(headers[n]).strip()}\n" for n in names)
        signed = ";".join(names)
        canonical = "\n".join([method, _uri(self._path(key)), "", canonical_headers, signed, payload_hash])
        scope = f"{day}/{self.region}/s3/aws4_request"
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        sig = hmac.new(self._signing_key(day), to_sign.encode(), hashlib.sha256).hexdigest()
        headers["Authorization"] = f"AWS4-HMAC-SHA256 Credential={self.access_key}/{scope}, SignedHeaders={signed}, Signature={sig}"
        headers.pop("host")
        return headers

    def _call(self, method: str, key: str, data: bytes = b"", extra: dict[str, str] | None = None) -> bytes:
        payload_hash = hashlib.sha256(data).hexdigest()
        headers = self._signed_headers(method, key, payload_hash, extra)
        try:
            resp = http(method, self.endpoint + _uri(self._path(key)), headers=headers, content=data if data else None, timeout=300.0)
        except PlatformError as exc:
            raise StorageError(f"Storage unreachable: {exc.message}") from None
        if resp.status_code == 404:
            raise StorageError("The file is missing from storage.")
        if resp.status_code >= 300:
            raise StorageError(f"Storage answered HTTP {resp.status_code}.")
        return resp.content

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self._call("PUT", key, data, {"content-type": content_type})

    def get(self, key: str) -> bytes:
        return self._call("GET", key)

    def open_range(self, key: str, start: int, end: int) -> Iterator[bytes]:
        data = self._call("GET", key, extra={"range": f"bytes={start}-{end}"})
        return iter([data])

    def delete(self, key: str) -> None:
        try:
            self._call("DELETE", key)
        except StorageError:
            logger.warning("storage_delete_failed", backend="s3")

    def presign_get(self, key: str, ttl_s: int) -> str | None:
        now = self._now()
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        day = now.strftime("%Y%m%d")
        scope = f"{day}/{self.region}/s3/aws4_request"
        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
            "X-Amz-Credential": f"{self.access_key}/{scope}",
            "X-Amz-Date": amz_date,
            "X-Amz-Expires": str(min(ttl_s, 7 * 24 * 3600)),
            "X-Amz-SignedHeaders": "host",
        }
        query = "&".join(f"{quote(k, safe='-_.~')}={quote(v, safe='-_.~')}" for k, v in sorted(params.items()))
        canonical = "\n".join(["GET", _uri(self._path(key)), query, f"host:{self.host}\n", "host", "UNSIGNED-PAYLOAD"])
        to_sign = "\n".join(["AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical.encode()).hexdigest()])
        sig = hmac.new(self._signing_key(day), to_sign.encode(), hashlib.sha256).hexdigest()
        return f"{self.endpoint}{_uri(self._path(key))}?{query}&X-Amz-Signature={sig}"


def get_storage() -> Storage:
    s = get_settings()
    if s.STORAGE_PROVIDER == "s3":
        secret = s.STORAGE_SECRET_KEY.get_secret_value()
        if not s.STORAGE_ENDPOINT or "changeme" in (s.STORAGE_ACCESS_KEY, secret):
            raise StorageError("S3 storage isn't configured: set STORAGE_ENDPOINT, STORAGE_ACCESS_KEY and STORAGE_SECRET_KEY.")
        return S3Storage(s.STORAGE_ENDPOINT, s.STORAGE_BUCKET, s.STORAGE_ACCESS_KEY, secret, s.STORAGE_REGION)
    return LocalStorage(s.MEDIA_ROOT)
