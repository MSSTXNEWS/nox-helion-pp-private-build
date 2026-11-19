"""GitHub REST HTTPS mailbox for the existing NOX OneHost callback bridge.

Requires explicit repository-scoped credential for WRITE receipts. Can read
a public repository without a token; request HMAC still gates execution.
GitHub is only transport, never a trusted executable command source.
"""
from __future__ import annotations
import base64
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from typing import Any

from .onehost_bridge import INBOX_SCHEMA, RECEIPT_SCHEMA, SIG_RE, canon

REPO = "MSSTXNEWS/nox-helion-pp-private-build"
BRANCH = "feature/nox-v38-synaptic-brain-20261114"
INBOX = "coordination/bridge/NOX_BRIDGE_INBOX.json"
RECEIPTS = "coordination/bridge/NOX_BRIDGE_RECEIPTS.json"
MAX_FILE = 65536
MAX_LEDGER = 96
API_ROOT = "https://api.github.com/repos/" + REPO + "/contents/"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GitHubHTTPSMailbox:
    def __init__(self, *, token: str | None = None, branch: str = BRANCH,
                 opener: Any = None):
        if branch != BRANCH:
            raise ValueError("HOLD_UNPINNED_BRANCH")
        if token is not None and (not isinstance(token, str)
                                  or len(token) < 12
                                  or any(c.isspace() for c in token)):
            raise ValueError("HOLD_GITHUB_TOKEN_FORMAT")
        self.token = token
        self.branch = branch
        self.opener = opener or urllib.request.build_opener(
            _NoRedirect(), urllib.request.HTTPSHandler(
                context=ssl.create_default_context()))

    def _send(self, path: str, *, method: str = "GET",
              payload: Mapping[str, Any] | None = None) -> dict:
        if path not in (INBOX, RECEIPTS):
            raise ValueError("HOLD_UNRECOGNIZED_PATH")
        if method not in ("GET", "PUT"):
            raise ValueError("HOLD_METHOD")
        if method == "PUT" and not self.token:
            raise ValueError("HOLD_WRITER_CREDENTIAL")
        url = API_ROOT + path
        if method == "GET":
            url += "?ref=" + urllib.parse.quote(self.branch, safe="")
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "NOX-OneHost-Bridge/49",
        }
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        raw = None
        if payload is not None:
            raw = canon(payload)
            if len(raw) > MAX_FILE * 3:
                raise ValueError("HOLD_WRITE_TOO_LARGE")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=raw, headers=headers, method=method)
        # No redirects: do not send GitHub bearer tokens to arbitrary domains.
        with self.opener.open(request, timeout=15) as response:
            raw_response = response.read(MAX_FILE * 4 + 1)
        if len(raw_response) > MAX_FILE * 4:
            raise ValueError("HOLD_GITHUB_RESPONSE_TOO_LARGE")
        parsed = json.loads(raw_response)
        if not isinstance(parsed, dict):
            raise ValueError("HOLD_GITHUB_RESPONSE")
        return parsed

    def _file(self, path: str) -> tuple[dict, str]:
        metadata = self._send(path)
        if metadata.get("type") != "file" or metadata.get("encoding") != "base64":
            raise ValueError("HOLD_UNEXPECTED_GITHUB_OBJECT")
        sha = metadata.get("sha")
        if not isinstance(sha, str) or len(sha) != 40:
            raise ValueError("HOLD_GITHUB_BLOB_SHA")
        encoded = metadata.get("content")
        if not isinstance(encoded, str) or len(encoded) > MAX_FILE * 2:
            raise ValueError("HOLD_GITHUB_CONTENT_SIZE")
        raw = base64.b64decode(encoded, validate=False)
        if len(raw) > MAX_FILE:
            raise ValueError("HOLD_BRIDGE_FILE_SIZE")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("HOLD_BRIDGE_FILE_SCHEMA")
        return parsed, sha

    def read_inbox(self) -> dict:
        inbox, _ = self._file(INBOX)
        if inbox.get("schema") != INBOX_SCHEMA or inbox.get("instance_id") != 60509551:
            raise ValueError("HOLD_INBOX_SCHEMA_OR_INSTANCE")
        return inbox

    def publish(self, receipt: Mapping[str, Any]) -> bool:
        """Append minimal private-free receipt with a single optimistic CAS write."""
        if receipt.get("schema") != RECEIPT_SCHEMA:
            return False
        # Strict output schema; never write native data, token, paths or memory.
        safe_keys = {
            "schema", "request_id", "action", "request_sha256",
            "state", "performed", "native_readback", "independent_verified",
            "data_sha256", "s03_durable", "receipt_signature",
        }
        if set(receipt) - safe_keys:
            return False
        if "request_id" not in receipt or not isinstance(receipt["request_id"], str):
            return False
        if not isinstance(receipt.get("receipt_signature"), str) or not SIG_RE.fullmatch(receipt["receipt_signature"]):
            return False
        ledger, blob_sha = self._file(RECEIPTS)
        if ledger.get("schema") != "NOX_ONEHOST_BRIDGE_RECEIPTS_V1":
            return False
        records = ledger.get("receipts")
        if not isinstance(records, list) or len(records) >= MAX_LEDGER:
            return False
        if any(isinstance(r, dict) and r.get("request_id") == receipt["request_id"]
               for r in records):
            # Already published; idempotent, not a fresh native execution proof.
            return True
        records.append(dict(receipt))
        raw = canon(ledger)
        if len(raw) > MAX_FILE:
            return False
        data = {
            "message": "NOX V49 bridge: bounded signed read receipt",
            "content": base64.b64encode(raw).decode("ascii"),
            "sha": blob_sha,
            "branch": self.branch,
        }
        response = self._send(RECEIPTS, method="PUT", payload=data)
        if not isinstance(response.get("commit"), dict):
            return False
        # New snapshot may be overwritten by concurrent writers: GitHub's
        # expected blob SHA rejects races (409/422); never retry blind.
        return True


def poll_existing_onehost(bridge, *, github_token: str | None = None) -> dict:
    """Exactly one poll, called by existing OneHost scheduler; no new daemon."""
    try:
        mailbox = GitHubHTTPSMailbox(token=github_token)
        return bridge.poll_once(mailbox.read_inbox(), mailbox.publish)
    except Exception:
        # Corrupt response, TLS error or failed write must never crash OneHost.
        # The native S03 claim remains the source of truth after uncertain writes.
        return {"state": "HOLD_HTTPS_BRIDGE_TRANSPORT", "published": 0,
                "native_queue_registered": 0, "may_have_processed": True}
