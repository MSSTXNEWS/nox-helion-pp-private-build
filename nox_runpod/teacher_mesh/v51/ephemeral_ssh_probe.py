"""Pinned, minimal Vast SSH-key transport for the NOX owner runner.

This implements only instance listing, per-instance SSH-key attach/list/detach.
It uses a fixed HTTPS origin, fixed instance scope, Bearer auth, no redirects,
bounded responses, and identity verification before and after detach.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import socket
import sys
import tempfile
import urllib.error
import urllib.request

API_BASE = "https://console.vast.ai/api/v0"
INSTANCE_ID = 60509551
MAX_RESPONSE_BYTES = 1024 * 1024
REQUEST_TIMEOUT_SECONDS = 20
RUNNER_ROOT = Path(os.environ.get("RUNNER_TEMP", tempfile.gettempdir())).resolve()
RUNNER = RUNNER_ROOT / "nox-v51-vast60509551-temp-ssh"
KEY = RUNNER / "owner-ssh-ed25519"
TRACK = RUNNER / "ssh-key-track.json"
_PUBLIC_KEY_RE = re.compile(r"^ssh-ed25519 ([A-Za-z0-9+/]+={0,2})(?: ([^\r\n]{0,100}))?$")
_ID_RE = re.compile(r"^[0-9]{1,20}$")
_ALLOWED_PATHS = (
    re.compile(r"^/instances/$"),
    re.compile(r"^/instances/60509551/ssh/?$"),
    re.compile(r"^/instances/60509551/ssh/[0-9]{1,20}/?$"),
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, new_url):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _valid_public_key(value: object) -> bool:
    if not isinstance(value, str) or len(value) > 700:
        return False
    match = _PUBLIC_KEY_RE.fullmatch(value)
    if not match:
        return False
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except (ValueError, base64.binascii.Error):
        return False
    return 32 <= len(raw) <= 256


def _canonical_path(path: object) -> str:
    if not isinstance(path, str) or not any(pattern.fullmatch(path) for pattern in _ALLOWED_PATHS):
        raise RuntimeError("HOLD_PROVIDER_REQUEST_SCOPE")
    if path == "/instances/":
        return path
    return path.rstrip("/")


def _open(request):
    return _OPENER.open(request, timeout=REQUEST_TIMEOUT_SECONDS)


def api(method: str, path: str, key: str, body=None):
    """Call one allowlisted Vast API route; never log the credential or body."""
    method = method.upper() if isinstance(method, str) else ""
    if method not in ("GET", "POST", "DELETE"):
        raise RuntimeError("HOLD_PROVIDER_REQUEST_SCOPE")
    path = _canonical_path(path)
    if not isinstance(key, str) or not key or len(key) > 4096 or "\r" in key or "\n" in key:
        raise RuntimeError("HOLD_OWNER_API_CREDENTIAL_UNAVAILABLE")
    if method == "GET" and body is not None:
        raise RuntimeError("HOLD_PROVIDER_REQUEST_SCOPE")
    if method == "DELETE" and body is not None:
        raise RuntimeError("HOLD_PROVIDER_REQUEST_SCOPE")
    if body is not None and not isinstance(body, dict):
        raise RuntimeError("HOLD_PROVIDER_REQUEST_SCOPE")

    data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        API_BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with _open(request) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError("HOLD_PROVIDER_HTTP_" + str(exc.code)) from None
    except (urllib.error.URLError, TimeoutError, socket.timeout, OSError):
        raise RuntimeError("HOLD_PROVIDER_TRANSPORT") from None
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RuntimeError("HOLD_PROVIDER_RESPONSE_SIZE")
    if not raw:
        return {}
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeError("HOLD_PROVIDER_RESPONSE") from None
    if not isinstance(value, (dict, list)):
        raise RuntimeError("HOLD_PROVIDER_RESPONSE")
    return value


def _ssh_key_rows(value):
    if not isinstance(value, dict):
        raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE")
    rows = value.get("ssh_keys")
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except json.JSONDecodeError:
            raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE") from None
    if not isinstance(rows, list):
        raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE")
    return rows


def match(key: str, public: str):
    """Return IDs only for keys whose public-key bytes exactly match."""
    if not _valid_public_key(public):
        raise RuntimeError("HOLD_PUBLIC_KEY_FORMAT")
    value = api("GET", f"/instances/{INSTANCE_ID}/ssh", key)
    ids = []
    for row in _ssh_key_rows(value):
        if not isinstance(row, dict) or row.get("public_key") != public:
            continue
        ident = row.get("id")
        if type(ident) is int and ident > 0:
            ids.append(ident)
        elif isinstance(ident, str) and _ID_RE.fullmatch(ident) and int(ident) > 0:
            ids.append(int(ident))
        else:
            raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE")
    return ids


def _remove_local_files():
    if RUNNER.is_symlink():
        return False
    if RUNNER.exists() and not RUNNER.is_dir():
        return False
    paths = (KEY, KEY.with_suffix(".pub"), RUNNER / "known_hosts",
             RUNNER / "owner-ssh.sock", TRACK)
    try:
        for path in paths:
            if path.parent != RUNNER or path.is_dir():
                return False
            if path.exists() or path.is_symlink():
                path.unlink()
        try:
            RUNNER.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            pass
    except OSError:
        return False
    return True


def cleanup():
    """Detach only the tracked temporary key, verify removal, then wipe local files."""
    if RUNNER.is_symlink() or (RUNNER.exists() and not RUNNER.is_dir()):
        return False
    if not TRACK.exists() and not TRACK.is_symlink():
        return _remove_local_files()
    if TRACK.is_symlink() or not TRACK.is_file():
        return False
    try:
        if TRACK.stat().st_size > 8192:
            return False
        record = json.loads(TRACK.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(record, dict) or not _valid_public_key(record.get("public")):
        return False
    public = record["public"]
    tracked = record.get("key_id")
    if tracked is not None and (type(tracked) is not int or tracked <= 0):
        return False

    token = os.environ.get("NOX2", "")
    if not token:
        return False
    try:
        found = match(token, public)
        if len(found) > 1:
            return False
        if tracked is None:
            target = found[0] if found else None
        else:
            if found and found != [tracked]:
                return False
            target = tracked if found else None
        if target is not None:
            result = api("DELETE", f"/instances/{INSTANCE_ID}/ssh/{target}", token)
            if isinstance(result, dict) and result and result.get("success") is not True:
                return False
            if match(token, public):
                return False
    except RuntimeError:
        return False
    return _remove_local_files()


def _main(argv):
    if argv != ["cleanup"]:
        return 2
    ok = cleanup()
    print("NOX_MAINT_CLEANUP=" + ("COMPLETE" if ok else "HOLD"), flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
