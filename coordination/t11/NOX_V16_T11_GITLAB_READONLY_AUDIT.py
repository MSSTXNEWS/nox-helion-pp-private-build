#!/usr/bin/env python3
"""Read-only GitLab evidence collection for NOX T11. Only HTTPS GET requests.
Run locally with a GitLab read_api-scoped token in NOX_GITLAB_READ_API_TOKEN.
Never pass tokens on CLI or upload them; this writes sanitized metadata only.
No pipeline, CI lint POST, git push, repository import, or source modifications.
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = "https://gitlab.com/api/v4/"
EXPECTED_PROJECT = "s-grouptwet/nox-helion-pp-private-build"

def get(path, token):
    req = urllib.request.Request(ROOT + path, headers={
        "PRIVATE-TOKEN": token, "Accept": "application/json"
    }, method="GET")
    with urllib.request.urlopen(req, timeout=30) as stream:
        return json.loads(stream.read().decode("utf-8"))

def pages(path, token):
    records = []
    for n in range(1, 101):
        delim = "&" if "?" in path else "?"
        block = get(path + delim + "per_page=100&page=" + str(n), token)
        if not isinstance(block, list):
            raise ValueError("Expected GitLab paginated list")
        records.extend(block)
        if len(block) < 100:
            return records
    raise ValueError("GitLab pagination cap hit; not verified complete")

def evidence_readback_valid(result):
    """Only authenticated, permission-proven live GitLab HEADs pass this read-only gate."""
    def sha1(value):
        return isinstance(value, str) and len(value) == 40 and all(c in '0123456789abcdef' for c in value)
    return (result.get('authenticated_identity_verified') is True
            and result.get('project_visible') is True
            and result.get('project_path') == EXPECTED_PROJECT
            and result.get('effective_access_level') in (10, 15, 20, 25, 30, 40, 50)
            and sha1(result.get('live_gitlab_head'))
            and sha1(result.get('migration_live_head')))

EXPECTED_MIGRATION_REF = "migration/nox-v16-gitlab-free-20261028-r01"

def verified_handoff_layout(raw):
    """Accept existing T11 R12 history as READ-ONLY inventory; never authorize CI."""
    if not isinstance(raw, dict):
        raise ValueError("T11 handoff must be a JSON object")
    if raw.get("schema") == "NOX_FIN_ZAGR_V16_T11_GITLAB_FREE_SOURCE_HANDOFF_V1":
        target, verified = raw["gitlab_target"], raw["github_verified"]
        url = urllib.parse.urlsplit(target["url"])
        if (url.scheme, url.netloc, url.path.strip("/"), url.query, url.fragment) != ("https", "gitlab.com", EXPECTED_PROJECT, "", ""):
            raise ValueError("Unexpected GitLab project URL")
        handoff = {
            "gitlab": {"path": EXPECTED_PROJECT, "historical_migration_branch": verified["historical_migration_ref"]},
            "history": {"migration_github_commit": verified["historical_migration_head_sha1"], "migration_only_files": verified["migration_only_files"]},
            "ci": {"default_windows_runner_tag": target["historic_runner_tag"]}
        }
    elif all(k in raw for k in ("gitlab", "history", "ci")):
        handoff = raw
    else:
        raise ValueError("Unrecognized T11 handoff schema")
    files = handoff["history"]["migration_only_files"]
    if not isinstance(files, list) or len(files) != 27:
        raise ValueError("Expected exactly 27 unique migration files")
    paths = set()
    for item in files:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"] or item["path"] in paths:
            raise ValueError("Missing or duplicate migration file path")
        paths.add(item["path"])
        if not isinstance(item.get("git_blob_sha1"), str) or re.fullmatch(r"[0-9a-f]{40}", item["git_blob_sha1"]) is None:
            raise ValueError("Invalid migration blob SHA")
    if (handoff["gitlab"]["path"] != EXPECTED_PROJECT or
            handoff["gitlab"]["historical_migration_branch"] != EXPECTED_MIGRATION_REF or
            not isinstance(handoff["history"]["migration_github_commit"], str) or
            re.fullmatch(r"[0-9a-f]{40}", handoff["history"]["migration_github_commit"]) is None or
            not isinstance(handoff["ci"]["default_windows_runner_tag"], str) or
            not handoff["ci"]["default_windows_runner_tag"]):
        raise ValueError("T11 historical ref, commit or runner tag invalid")
    return handoff

def main():
    parser = argparse.ArgumentParser(description="GitLab T11 read-only audit")
    parser.add_argument("--handoff", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    try:
        handoff = verified_handoff_layout(json.loads(args.handoff.read_text(encoding="utf-8")))
    except (KeyError, TypeError, ValueError) as ex:
        raise SystemExit("T11_HANDOFF_SCHEMA_HOLD: " + type(ex).__name__) from None
    token = os.environ.get("NOX_GITLAB_READ_API_TOKEN")
    if not token:
        raise SystemExit("GITLAB_ACCESS_HOLD: set NOX_GITLAB_READ_API_TOKEN locally; do not paste token into chat")
    project_path = handoff["gitlab"]["path"]
    if project_path != EXPECTED_PROJECT:
        raise SystemExit("Wrong GitLab project path")
    project_id = urllib.parse.quote(project_path, safe="")
    result = {
        "schema": "NOX_V16_T11_GITLAB_LIVE_READONLY_PROOF_V1",
        "project_path": project_path,
        "status": "GITLAB_ACCESS_HOLD",
        "project_visible": False,
        "authenticated_identity_verified": False,
        "effective_access_level": None,
        "permissions_readback": "NOT_VERIFIED",
        "gitlab_ready": False,
        "live_gitlab_head": None,
        "migration_live_head": None,
        "migration_commit_preserved": False,
        "migration_unique_verified": 0,
        "migration_unique_total": len(handoff["history"]["migration_only_files"]),
        "migration_unique_mismatches": [],
        "runners": [],
        "windows_runner_proven_online": False,
        "ci_git_blob": None,
        "entrypoint_git_blob": None,
        "mutations": 0,
        "pipeline_started": False
    }
    try:
        principal = get("user", token)
        if not isinstance(principal, dict) or not isinstance(principal.get("id"), int):
            raise ValueError("Authenticated GitLab identity not verified")
        result["authenticated_identity_verified"] = True
        info = get("projects/" + project_id, token)
        if info.get("path_with_namespace") != project_path:
            raise ValueError("GitLab project namespace mismatch")
        result["project_visible"] = True
        result["visibility"] = info.get("visibility")
        result["default_branch"] = info.get("default_branch")
        pid = str(info["id"])
        permissions = info.get("permissions") or {}
        levels = [(permissions.get(kind) or {}).get("access_level")
                  for kind in ("project_access", "group_access")]
        levels = [level for level in levels if type(level) is int]
        if not levels:
            try:
                member = get("projects/" + pid + "/members/all/" + str(principal["id"]), token)
                if type(member.get("access_level")) is int:
                    levels.append(member["access_level"])
            except urllib.error.HTTPError as ex:
                result["permissions_read_error"] = "HTTP_" + str(ex.code)
        if levels:
            result["effective_access_level"] = max(levels)
            result["permissions_readback"] = "VERIFIED_LEVEL"
        # Do not emit the principal identity, access token, or API exception content.
        branches = pages("projects/" + pid + "/repository/branches", token)
        result["branches"] = [
            {"name": b.get("name"), "sha": (b.get("commit") or {}).get("id"),
             "protected": b.get("protected")} for b in branches
        ]
        branch_dict = {b["name"]: b["sha"] for b in result["branches"]}
        result["live_gitlab_head"] = branch_dict.get(info.get("default_branch"))
        migration_ref = handoff["gitlab"]["historical_migration_branch"]
        result["migration_live_head"] = branch_dict.get(migration_ref)
        try:
            get("projects/" + pid + "/repository/commits/" +
                handoff["history"]["migration_github_commit"], token)
            result["migration_commit_preserved"] = True
        except urllib.error.HTTPError:
            result["migration_commit_preserved"] = False

        if result["migration_live_head"]:
            for f in handoff["history"]["migration_only_files"]:
                code = urllib.parse.quote(f["path"], safe="")
                query = urllib.parse.quote(migration_ref, safe="")
                try:
                    remote = get("projects/" + pid + "/repository/files/" + code +
                                 "?ref=" + query, token)
                    actual = remote.get("blob_id")
                except urllib.error.HTTPError as ex:
                    actual = "HTTP_" + str(ex.code)
                if actual == f["git_blob_sha1"]:
                    result["migration_unique_verified"] += 1
                else:
                    result["migration_unique_mismatches"].append({
                        "path": f["path"], "expected": f["git_blob_sha1"],
                        "observed": actual
                    })
            def observed_blob(path):
                p = urllib.parse.quote(path, safe="")
                q = urllib.parse.quote(migration_ref, safe="")
                try:
                    return get("projects/" + pid + "/repository/files/" + p +
                               "?ref=" + q, token).get("blob_id")
                except urllib.error.HTTPError:
                    return None
            result["ci_git_blob"] = observed_blob(".gitlab-ci.yml")
            result["entrypoint_git_blob"] = observed_blob(
                "coordination/e06/gitlab_windows_entrypoint.ps1")
        try:
            runners = pages("projects/" + pid + "/runners", token)
            result["runners"] = [{
                "id": r.get("id"), "status": r.get("status"),
                "paused": r.get("paused"), "runner_type": r.get("runner_type"),
                "tags": r.get("tag_list") or []
            } for r in runners]
            result["windows_runner_proven_online"] = any(
                r["status"] == "online" and not r["paused"] and
                handoff["ci"]["default_windows_runner_tag"] in r["tags"]
                for r in result["runners"])
        except urllib.error.HTTPError as ex:
            result["runners_error"] = "HTTP_" + str(ex.code)
        if evidence_readback_valid(result):
            result["status"] = "LIVE_INSPECTED_NOT_BUILD_READY"
        else:
            result["status"] = "GITLAB_ACCESS_HOLD"
            result["hold_reason"] = "AUTHENTICATED_HEAD_OR_PROJECT_RIGHTS_NOT_VERIFIED"
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError) as ex:
        result["read_error_type"] = type(ex).__name__
        result["status"] = "GITLAB_ACCESS_HOLD"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"],
        "project_visible": result["project_visible"],
        "live_gitlab_head": result["live_gitlab_head"],
        "migration_unique_verified": result["migration_unique_verified"],
        "migration_unique_total": result["migration_unique_total"],
        "windows_runner_proven_online": result["windows_runner_proven_online"],
        "audit_file": str(args.out)
    }, ensure_ascii=False))
    return 0 if result["status"] == "LIVE_INSPECTED_NOT_BUILD_READY" else 2

if __name__ == "__main__":
    sys.exit(main())
