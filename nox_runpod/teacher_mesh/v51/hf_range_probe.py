"""Sanitized, read-only HEAD + exactly one-byte Range probe for pinned HF sources.

No complete DeepSeek URL/revision/path/size/SHA allowlist is checked in on this
branch, so the production allowlist is intentionally empty and network access
fails closed with PIN_METADATA_UNAVAILABLE. Offline tests may inject a synthetic
fixture pin; that is not a model pin and cannot enable a production request.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request


class ProbeHold(RuntimeError):
    pass


_SHA256 = re.compile(r"[a-f0-9]{64}")
_PIN_FIELDS = ("revision", "path", "url", "bytes", "sha256")

# No complete trusted per-file allowlist is checked in. Do not populate from
# caller input, environment variables, an unverified Library item, or runtime
# network metadata.
PINNED_SOURCES = ()


def _public_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not (host == "huggingface.co" or host.endswith(".huggingface.co")
                    or host.endswith(".hf.co")):
        raise ProbeHold("PUBLIC_HF_REDIRECT_SCOPE")
    return url


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _resolve_pin(supplied: dict) -> dict:
    if not PINNED_SOURCES:
        raise ProbeHold("PIN_METADATA_UNAVAILABLE")
    if not isinstance(supplied, dict):
        raise ProbeHold("PIN_METADATA_MISMATCH")
    matches = []
    for row in PINNED_SOURCES:
        if (isinstance(row, dict)
                and type(row.get("bytes")) is int and row["bytes"] > 0
                and isinstance(row.get("sha256"), str) and _SHA256.fullmatch(row["sha256"])
                and isinstance(row.get("revision"), str) and row["revision"]
                and isinstance(row.get("path"), str) and row["path"]
                and isinstance(row.get("url"), str)):
            if all(supplied.get(key) == row[key] for key in _PIN_FIELDS):
                matches.append(row)
    if len(matches) != 1:
        raise ProbeHold("PIN_METADATA_MISMATCH")
    return matches[0]


def _strong_etag(value: str) -> bool:
    return bool(value and not value.startswith("W/") and len(value) <= 256
                and not any(ord(ch) < 32 for ch in value))


def _validate_range_headers(response, start: int, length: int, total: int, etag: str) -> None:
    observed = response.headers.get("ETag", "")
    if (response.status != 206
            or response.headers.get("Content-Range") != f"bytes {start}-{start + length - 1}/{total}"
            or response.headers.get("Content-Length") != str(length)
            or response.headers.get("Content-Encoding", "identity").lower() != "identity"):
        raise ProbeHold("RANGE_STATUS_LENGTH_OR_TOTAL_MISMATCH")
    if not _strong_etag(observed) or observed != etag:
        raise ProbeHold("STRONG_ETAG_MISSING_OR_CHANGED")


def _open_sanitized(client, request):
    try:
        return client.open(request, timeout=20)
    except urllib.error.HTTPError as exc:
        raise ProbeHold("HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ProbeHold("NETWORK_ERROR") from None


def probe_one_byte(file: dict, opener=None) -> dict:
    """Resolve an exact checked-in pin, then HEAD + GET Range bytes=0-0."""
    pin = _resolve_pin(file)
    total = pin["bytes"]
    source_sha = pin["sha256"]
    url = _public_url(pin["url"])
    client = opener or urllib.request.build_opener(_Redirect())

    head = urllib.request.Request(url, headers={"Accept-Encoding": "identity"}, method="HEAD")
    with _open_sanitized(client, head) as response:
        etag = response.headers.get("ETag", "")
        if (response.status != 200
                or response.headers.get("Content-Length") != str(total)
                or response.headers.get("Content-Encoding", "identity").lower() != "identity"
                or not _strong_etag(etag)):
            raise ProbeHold("HEAD_METADATA_MISMATCH")

    ranged = urllib.request.Request(
        url, headers={"Range": "bytes=0-0", "Accept-Encoding": "identity", "If-Range": etag})
    with _open_sanitized(client, ranged) as response:
        _validate_range_headers(response, 0, 1, total, etag)
        if len(response.read(2)) != 1:
            raise ProbeHold("RANGE_PROBE_BODY_NOT_ONE_BYTE")

    return {
        "head_status": 200,
        "range_status": 206,
        "content_range": f"bytes 0-0/{total}",
        "content_length": 1,
        "bytes_read": 1,
        "strong_etag_match": True,
        "source_bytes": total,
        "source_sha256": source_sha,
    }
