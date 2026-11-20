#!/usr/bin/env python3
"""NOX integration gateway: bounded, credential-free-in-repository connectivity.

Credentials are read ONLY from environment or rclone config on the NOX host.
No arbitrary URLs, shell execution, or destructive API operations.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PROVIDERS = ("drive", "github", "gitlab", "notion", "vast")
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
REMOTE_PATTERN = re.compile(r"^[A-Za-z0-9_-]+:$")
PROJECT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+$")
TOKEN_KEYS = {
    "github": "NOX_GITHUB_TOKEN",
    "gitlab": "NOX_GITLAB_TOKEN",
    "notion": "NOX_NOTION_TOKEN",
    "vast": "NOX_VAST_API_KEY",
}
SAFE_TIMEOUT = 12


def clean_error(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return "http_" + str(exc.code)
    if isinstance(exc, subprocess.TimeoutExpired):
        return "timeout"
    if isinstance(exc, FileNotFoundError):
        return "tool_unavailable"
    return type(exc).__name__


def http_json(url, headers):
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=SAFE_TIMEOUT) as response:
        if response.status != 200:
            raise RuntimeError("upstream_status")
        return json.load(response)


def drive_status():
    remote = os.getenv("NOX_DRIVE_REMOTE", "noxdrive:")
    if not REMOTE_PATTERN.fullmatch(remote):
        return {"status": "configuration_error", "detail": "remote_must_be_name_colon"}
    if not shutil.which("rclone"):
        return {"status": "not_configured", "detail": "rclone_unavailable"}
    # Read-only listing; never output private Drive file names.
    p = subprocess.run(
        ["rclone", "lsjson", "--max-depth", "1", remote],
        capture_output=True, text=True, timeout=SAFE_TIMEOUT, check=False,
    )
    if p.returncode:
        return {"status": "unavailable", "detail": "rclone_listing_failed"}
    try:
        objects = json.loads(p.stdout)
        return {"status": "connected", "top_level_entries": len(objects)}
    except (ValueError, TypeError):
        return {"status": "unavailable", "detail": "invalid_rclone_response"}


def github_status():
    repo = os.getenv("NOX_GITHUB_REPOSITORY", "MSSTXNEWS/nox-helion-pp-private-build")
    if not REPO_PATTERN.fullmatch(repo):
        return {"status": "configuration_error", "detail": "invalid_repository"}
    token = os.getenv(TOKEN_KEYS["github"])
    if not token:
        return {"status": "not_configured", "detail": "missing_token"}
    url = "https://api.github.com/repos/" + repo
    data = http_json(url, {
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
        "User-Agent": "NOX-Integration-Gateway",
    })
    return {"status": "connected", "repository": data.get("full_name"),
            "private": data.get("private"), "push_permission": data.get("permissions", {}).get("push")}


def gitlab_status():
    # Fixed official host; do not accept an attacker-supplied endpoint.
    project = os.getenv("NOX_GITLAB_PROJECT", "")
    if not PROJECT_PATTERN.fullmatch(project):
        return {"status": "not_configured", "detail": "project_not_set"}
    token = os.getenv(TOKEN_KEYS["gitlab"])
    if not token:
        return {"status": "not_configured", "detail": "missing_token"}
    path = urllib.parse.quote(project, safe="")
    data = http_json("https://gitlab.com/api/v4/projects/" + path,
                     {"PRIVATE-TOKEN": token, "User-Agent": "NOX-Integration-Gateway"})
    return {"status": "connected", "project_id": data.get("id"),
            "visibility": data.get("visibility")}


def notion_status():
    token = os.getenv(TOKEN_KEYS["notion"])
    if not token:
        return {"status": "not_configured", "detail": "missing_token"}
    data = http_json("https://api.notion.com/v1/users/me", {
        "Authorization": "Bearer " + token, "Notion-Version": "2022-06-28",
        "User-Agent": "NOX-Integration-Gateway",
    })
    return {"status": "connected", "bot_id_present": bool(data.get("id"))}


def vast_status():
    token = os.getenv(TOKEN_KEYS["vast"])
    instance = os.getenv("NOX_VAST_INSTANCE_ID", "60509551")
    if not re.fullmatch(r"[0-9]{1,12}", instance):
        return {"status": "configuration_error", "detail": "invalid_instance_id"}
    if not token:
        return {"status": "not_configured", "detail": "missing_token"}
    data = http_json("https://console.vast.ai/api/v0/instances/" + instance + "/", {
        "Authorization": "Bearer " + token, "Accept": "application/json",
        "User-Agent": "NOX-Integration-Gateway",
    })
    obj = data.get("instances", data) if isinstance(data, dict) else {}
    if isinstance(obj, list):
        obj = next((x for x in obj if str(x.get("id")) == instance), {})
    return {"status": "connected", "instance_id": instance,
            "actual_status": obj.get("actual_status"),
            "gpu_count": obj.get("num_gpus")}


PROBES = {"drive": drive_status, "github": github_status,
          "gitlab": gitlab_status, "notion": notion_status, "vast": vast_status}


def main():
    p = argparse.ArgumentParser(description="NOX bounded integration gateway")
    p.add_argument("command", choices=("status",))
    p.add_argument("--provider", choices=("all",) + PROVIDERS, default="all")
    p.add_argument("--output", help="Optional JSON status file, atomic replace")
    args = p.parse_args()
    names = PROVIDERS if args.provider == "all" else (args.provider,)
    result = {"schema": "nox.integrations.status.v1",
              "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
              "providers": {}}
    for name in names:
        try:
            result["providers"][name] = PROBES[name]()
        except Exception as exc:
            result["providers"][name] = {"status": "unavailable", "detail": clean_error(exc)}
    payload = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output:
        dest = Path(args.output).resolve()
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_suffix(dest.suffix + ".tmp")
        if temp.exists():
            raise SystemExit("Temporary status path already exists")
        with temp.open("x", encoding="utf-8") as f:
            f.write(payload + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, dest)
    print(payload)
    if any(v["status"] == "configuration_error" for v in result["providers"].values()):
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
