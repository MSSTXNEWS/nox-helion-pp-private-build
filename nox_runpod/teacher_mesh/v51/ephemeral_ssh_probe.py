"""Pinned, minimal Vast SSH-key transport for the NOX owner runner.

This implements exact owner-scoped instance lookup and per-instance SSH-key
attach/list/detach. It uses a fixed HTTPS origin, fixed instance scope, Bearer
auth, no redirects, bounded responses, and identity verification before and
after detach.
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
# Exact current official Vast CLI source for show_instance() owner-scoped GET.
VAST_CLI_REFERENCE_SHA = "b0eab2968b832d62b55fd07b29e26449e3408d7e"
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
    re.compile(r"^/instances/60509551/?$"),
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
    if path == f"/instances/{INSTANCE_ID}":
        allowed = method == "GET" and body is None
    elif path == f"/instances/{INSTANCE_ID}/ssh":
        allowed = (
            (method == "GET" and body is None)
            or (method == "POST" and isinstance(body, dict)
                and set(body) == {"ssh_key"} and _valid_public_key(body.get("ssh_key")))
        )
    else:
        allowed = (
            method == "DELETE" and body is None
            and bool(re.fullmatch(rf"/instances/{INSTANCE_ID}/ssh/[0-9]{{1,20}}", path))
        )
    if not allowed:
        raise RuntimeError("HOLD_PROVIDER_REQUEST_SCOPE")

    data = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
    url = (API_BASE + path + "/?owner=me"
           if path == f"/instances/{INSTANCE_ID}" else API_BASE + path + "/")
    request = urllib.request.Request(
        url,
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


def _instance_ssh_key_identities(key: str):
    """Read the entire fixed-instance key list and validate every row's identity."""
    value = api("GET", f"/instances/{INSTANCE_ID}/ssh", key)
    identities = []
    for row in _ssh_key_rows(value):
        if not isinstance(row, dict):
            raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE")
        ident = row.get("id")
        if type(ident) is int and ident > 0:
            ident = int(ident)
        elif isinstance(ident, str) and _ID_RE.fullmatch(ident) and int(ident) > 0:
            ident = int(ident)
        else:
            raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE")
        public = row.get("public_key")
        if (not isinstance(public, str) or not public or len(public) > 4096
                or "\r" in public or "\n" in public):
            raise RuntimeError("HOLD_PROVIDER_SSH_RESPONSE")
        identities.append((ident, public))
    return identities


def match(key: str, public: str):
    """Return IDs only for keys whose public-key bytes exactly match."""
    if not _valid_public_key(public):
        raise RuntimeError("HOLD_PUBLIC_KEY_FORMAT")
    return [ident for ident, row_public in _instance_ssh_key_identities(key)
            if row_public == public]


def _remove_local_files():
    """Remove only this runner's temporary files and verify key absence."""
    if RUNNER.is_symlink() or (RUNNER.exists() and not RUNNER.is_dir()):
        return False, "HOLD_UNLINK"
    key_existed = KEY.exists()
    paths = (KEY, KEY.with_suffix(".pub"), RUNNER / "known_hosts",
             RUNNER / "owner-ssh.sock", TRACK)
    try:
        for path in paths:
            if path.parent != RUNNER or path.is_symlink() or path.is_dir():
                return False, "HOLD_UNLINK"
            if path.exists():
                path.unlink()
        if any(path.exists() or path.is_symlink() for path in paths):
            return False, "HOLD_UNLINK"
        if KEY.exists() or KEY.is_symlink():
            return False, "HOLD_UNLINK"
        try:
            RUNNER.rmdir()
        except FileNotFoundError:
            pass
        except OSError:
            pass
        return True, "REMOVED_AND_VERIFIED" if key_existed else "ABSENT_AND_VERIFIED"
    except OSError:
        return False, "HOLD_UNLINK"


def cleanup_with_receipt():
    """Detach only the exact tracked remote key, then verify local cleanup separately."""
    if RUNNER.is_symlink() or (RUNNER.exists() and not RUNNER.is_dir()):
        return False, "HOLD", "HOLD_UNLINK"
    if not TRACK.exists() and not TRACK.is_symlink():
        _local_ok, local_status = _remove_local_files()
        # Local cleanup cannot prove which remote key, if any, belongs to this run.
        return False, "NO_TRACKED_REMOTE_KEY", local_status
    if TRACK.is_symlink() or not TRACK.is_file():
        return False, "HOLD", "HOLD_UNLINK"
    try:
        if TRACK.stat().st_size > 8192:
            return False, "HOLD", "HOLD_UNLINK"
        record = json.loads(TRACK.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False, "HOLD", "HOLD_UNLINK"
    if not isinstance(record, dict) or not _valid_public_key(record.get("public")):
        return False, "HOLD", "HOLD_UNLINK"
    public = record["public"]
    tracked = record.get("key_id")
    if tracked is not None and (type(tracked) is not int or tracked <= 0):
        return False, "HOLD", "HOLD_UNLINK"

    token = os.environ.get("NOX2", "")
    if not token:
        return False, "HOLD", "HOLD_UNLINK"
    remote_status = "HOLD"
    try:
        identities = _instance_ssh_key_identities(token)
        exact_ids = [ident for ident, row_public in identities if row_public == public]
        if len(exact_ids) > 1:
            return False, "HOLD", "HOLD_UNLINK"

        if tracked is None:
            target = exact_ids[0] if exact_ids else None
        else:
            tracked_rows = [(ident, row_public) for ident, row_public in identities
                            if ident == tracked]
            if len(tracked_rows) > 1:
                return False, "HOLD", "HOLD_UNLINK"
            if tracked_rows:
                # An ID is deletable only when the current fixed-instance row
                # still holds the exact public-key bytes from this run.
                if tracked_rows != [(tracked, public)] or exact_ids != [tracked]:
                    return False, "HOLD", "HOLD_UNLINK"
                target = tracked
            else:
                # If the same key has moved to another ID, or the tracked ID
                # still exists under another key, the record is ambiguous.
                if exact_ids:
                    return False, "HOLD", "HOLD_UNLINK"
                target = None

        if target is None:
            remote_status = "ALREADY_ABSENT_VERIFIED"
        else:
            target_rows = [(ident, row_public) for ident, row_public in identities
                           if ident == target]
            if target_rows != [(target, public)]:
                return False, "HOLD", "HOLD_UNLINK"
            result = api("DELETE", f"/instances/{INSTANCE_ID}/ssh/{target}", token)
            if isinstance(result, dict) and result and result.get("success") is not True:
                return False, "HOLD", "HOLD_UNLINK"
            after = _instance_ssh_key_identities(token)
            if (any(ident == target or row_public == public
                    for ident, row_public in after)):
                return False, "HOLD", "HOLD_UNLINK"
            remote_status = "DETACHED_AND_VERIFIED"
    except RuntimeError:
        return False, "HOLD", "HOLD_UNLINK"

    local_ok, local_status = _remove_local_files()
    complete = local_ok and remote_status in (
        "DETACHED_AND_VERIFIED", "ALREADY_ABSENT_VERIFIED")
    return complete, remote_status, local_status


def cleanup():
    """Compatibility wrapper; inspect cleanup_with_receipt for separate outcomes."""
    ok, _remote_status, _local_status = cleanup_with_receipt()
    return ok


def _main(argv):
    if argv != ["cleanup"]:
        return 2
    ok, remote_status, local_status = cleanup_with_receipt()
    print("TEMP_SSH_REMOTE_KEY=" + remote_status, flush=True)
    print("TEMP_SSH_LOCAL_KEY=" + (
        local_status
    ), flush=True)
    print("NOX_MAINT_CLEANUP=" + ("COMPLETE" if ok else "HOLD"), flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
