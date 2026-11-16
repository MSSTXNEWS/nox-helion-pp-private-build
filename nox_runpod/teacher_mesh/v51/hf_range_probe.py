"""Sanitized, read-only HEAD + exactly one-byte Range probe for pinned public HF URLs.

This is an opt-in source contract. It does not write files, print URLs, or send auth.
The SHA256 field is a manifest pin, not a digest computed from one byte.
"""
from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request


class ProbeHold(RuntimeError):
    pass


_SHA256 = re.compile(r"[a-f0-9]{64}")


def _public_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower()
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443)
            or not (host == "huggingface.co" or host.endswith(".huggingface.co")
                    or host.endswith(".hf.co"))):
        raise ProbeHold("PUBLIC_HF_REDIRECT_SCOPE")
    return url


class _Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _strong_etag(value: str) -> bool:
    return bool(value and not value.startswith("W/") and len(value) <= 256
                and not any(ord(ch) < 32 for ch in value))


def _headers(response, start: int, length: int, total: int, etag: str) -> None:
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
    """HEAD metadata, then GET Range bytes=0-0; return only non-secret metadata."""
    total = file.get("bytes")
    source_sha = file.get("sha256")
    if (type(total) is not int or total <= 0
            or not isinstance(source_sha, str) or not _SHA256.fullmatch(source_sha)):
        raise ProbeHold("PINNED_SOURCE_METADATA_INVALID")

    url = _public_url(file.get("url", ""))
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
        _headers(response, 0, 1, total, etag)
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
