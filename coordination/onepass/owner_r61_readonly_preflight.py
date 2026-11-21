"""Owner-gated R6.1 preflight connection-gap report.

This deliberately does not SSH to the host: the only linked credential found in
source is NOX2, and the existing SSH helper attaches a temporary Vast SSH key.
That POST/DELETE is a control-plane mutation, forbidden for this read-only run.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import sys
from urllib.parse import urlsplit

INSTANCE_ID = 60509551
REPORT_PATH = os.environ.get("NOX_R61_REPORT_PATH", "nox-r61-preflight-hold.json")


def _safe_url(value: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 2048:
        raise ValueError("HOLD_ASSET_URL_BOUNDS")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("HOLD_ASSET_URL_CONTROL")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("HOLD_ASSET_URL_FORMAT")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("HOLD_ASSET_URL_CREDENTIALS")
    if parsed.query or parsed.fragment:
        raise ValueError("HOLD_ASSET_URL_QUERY_OR_FRAGMENT")
    if not parsed.path or not parsed.path.startswith("/"):
        raise ValueError("HOLD_ASSET_URL_PATH")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,253}", parsed.hostname):
        raise ValueError("HOLD_ASSET_URL_HOST")
    if not parsed.path.lower().endswith((".html", ".js", ".mjs", ".css")):
        raise ValueError("HOLD_ASSET_URL_NOT_STATIC_ASSET")
    return value


def _safe_path(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise ValueError("HOLD_" + field + "_BOUNDS")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("HOLD_" + field + "_CONTROL")
    path = PurePosixPath(value)
    if not path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError("HOLD_" + field + "_PATH")
    return value


def input_binding(asset_url: str, asset_path: str, proxy_path: str) -> str:
    record = json.dumps(
        {"asset_url": asset_url, "asset_path": asset_path, "proxy_path": proxy_path},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(record).hexdigest()


def make_report(asset_url: str, asset_path: str, proxy_path: str,
                control_plane_status: str) -> dict:
    url = _safe_url(asset_url)
    asset = _safe_path(asset_path, "ASSET_PATH")
    proxy = _safe_path(proxy_path, "PROXY_PATH")
    if control_plane_status not in ("running", "stopped", "unknown", "unavailable"):
        control_plane_status = "unknown"
    return {
        "schema": "nox-r61-owner-readonly-preflight/v1",
        "result": "HOLD_HOST_READ_CHANNEL_UNAVAILABLE_WITHOUT_MUTATION",
        "control_plane": {
            "provider": "Vast.ai",
            "instance_id": INSTANCE_ID,
            "read_only_status": control_plane_status,
        },
        "host_probe": "NOT_RUN",
        "connection_gap": (
            "NOX2 is the only linked credential visible in the existing owner "
            "workflow; host SSH through the existing helper requires temporary "
            "Vast SSH-key POST and DELETE. This workflow performs neither."
        ),
        "asset": {
            "url": url,
            "url_status": "NOT_PROBED",
            "served_sha256": "NOT_AVAILABLE",
            "local_sha256": "NOT_AVAILABLE",
            "path_input_sha256": hashlib.sha256(asset.encode("utf-8")).hexdigest(),
        },
        "proxy": {
            "route_sha256": "NOT_AVAILABLE",
            "path_input_sha256": hashlib.sha256(proxy.encode("utf-8")).hexdigest(),
        },
        "deployment_sha": "NOT_AVAILABLE",
        "processes": "NOT_AVAILABLE",
        "input_binding_sha256": input_binding(url, asset, proxy),
        "mutations_performed": False,
        "inference_performed": False,
    }


def _control_plane_status(token: str) -> str:
    if not token:
        return "unavailable"
    # The helper's GET /instances/ path is read-only. Do not call probe(): it
    # attaches an ephemeral SSH key with POST before opening the host channel.
    from nox_runpod.teacher_mesh.v51 import ephemeral_ssh_probe as ssh
    data = ssh.api("GET", "/instances/", token)
    rows = data.get("instances", data) if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return "unknown"
    row = next((item for item in rows
                if isinstance(item, dict) and str(item.get("id")) == str(INSTANCE_ID)), None)
    if row is None:
        return "unknown"
    status = row.get("actual_status")
    return status if status in ("running", "stopped") else "unknown"


def main() -> int:
    status = "unavailable"
    error = "HOLD_INPUT_OR_CONTROL_PLANE"
    try:
        asset_url = _safe_url(os.environ.get("NOX_R61_ASSET_URL", ""))
        asset_path = _safe_path(os.environ.get("NOX_R61_ASSET_PATH", ""), "ASSET_PATH")
        proxy_path = _safe_path(os.environ.get("NOX_R61_PROXY_PATH", ""), "PROXY_PATH")
        try:
            status = _control_plane_status(os.environ.get("NOX2", ""))
            error = "HOLD_HOST_READ_CHANNEL_UNAVAILABLE_WITHOUT_MUTATION"
        except Exception:
            # Never write exception text or API response contents to the artifact.
            status = "unavailable"
            error = "HOLD_VAST_CONTROL_PLANE_READ"
        report = make_report(asset_url, asset_path, proxy_path, status)
    except ValueError as exc:
        report = {
            "schema": "nox-r61-owner-readonly-preflight/v1",
            "result": str(exc),
            "host_probe": "NOT_RUN",
            "mutations_performed": False,
            "inference_performed": False,
        }
        error = str(exc)

    with open(REPORT_PATH, "w", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    os.chmod(REPORT_PATH, 0o600)
    print("NOX_R61_PREFLIGHT=" + error)
    print("NOX_R61_REPORT_WRITTEN=true")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
