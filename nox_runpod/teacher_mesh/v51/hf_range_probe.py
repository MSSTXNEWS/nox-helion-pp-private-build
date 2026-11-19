"""Sanitized, read-only HEAD + one-byte Range probe for immutable HF pins.

The production allowlist below is taken from Hugging Face's expanded repository
tree API at the exact immutable revision. No user supplied metadata is trusted.
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
_REVISION = "65d53bc8be65123e255ff02f3ded958b6dbf54fd"
_REPO = "ISTA-DASLab/DeepSeek-V4.1-Flash-1017-GSQ-RCO-GGUF"


def _pin(path: str, size: int, sha256: str) -> dict:
    return {
        "revision": _REVISION,
        "path": path,
        "url": f"https://huggingface.co/{_REPO}/resolve/{_REVISION}/{path}",
        "bytes": size,
        "sha256": sha256,
    }


# HF expanded repository tree metadata (expand=true) at _REVISION.
# The IQ2_XXS backbone is shards 1-5; shard 00005 is included exactly once
# because it is already present in the coldpack. Engram is a single shared file.
PINNED_SOURCES = (
    _pin("DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00001-of-00006.gguf",
         5780704, "f356f198561f56df36f7ab92d7238a926646d76de992c34f15bcb939a5f529b9"),
    _pin("DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00002-of-00006.gguf",
         39535781184, "25af3785ccf925f54137e1ead4c481a8952315dc0b1af6519a99407f67bce8f3"),
    _pin("DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00003-of-00006.gguf",
         39736712000, "8168d0998fc494def2e1952d83c131425a108660aae9d29190f5a8670ab62b48"),
    _pin("DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00004-of-00006.gguf",
         39036908384, "9eb9b4de1968f150dfc207eb31c27be9cd9b5666a9a6246bde8a22b184b4bee0"),
    _pin("DeepSeek-V4.1-Flash-1017-GSQ-RCO-IQ2_XXS-00005-of-00006.gguf",
         19923784832, "7e35f6b4e6fc46f6c4b152b593d84d683c5ece695ae6ad734f556198c041bec1"),
    _pin("DeepSeek-V4.1-Flash-Engram-IQ4_NL.gguf",
         110595290816, "3dac4c54893ad7aa89103c0028500eadc78e74112cef3a2930a97e67dc9fb4f3"),
)


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


def _resolve_pin(supplied: dict) -> dict:
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
