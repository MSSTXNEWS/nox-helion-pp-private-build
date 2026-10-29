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

def pinned_ref(sha):
    if type(sha) is not str or re.fullmatch(r"[0-9a-f]{40}",sha) is None:
        raise ValueError("UNPINNED_GITLAB_SOURCE_REF")
    return urllib.parse.quote(sha,safe="")

def evaluate_live_evidence(result, handoff):
    """Independent fail-closed GitLab migration proof; never grants build consent."""
    problems = []
    def git_sha1(value):
        return type(value) is str and re.fullmatch(r"[0-9a-f]{40}", value) is not None
    def require(condition, code):
        if not condition:
            problems.append(code)
    history = handoff["history"]
    ci = handoff["ci"]
    required_files = history["migration_only_files"]
    required_parts = history["original_source_part_blobs"]
    require(result.get("project_visible") is True, "PROJECT_NOT_AUTHENTICATED")
    require(result.get("visibility") == "private", "PROJECT_PRIVACY_UNVERIFIED")
    require(git_sha1(result.get("live_gitlab_head")), "LIVE_HEAD_UNVERIFIED")
    require(git_sha1(result.get("migration_live_head")), "MIGRATION_HEAD_UNVERIFIED")
    require(type(result.get("access_level")) is int and
            result["access_level"] >= 20, "PROJECT_READ_PERMISSION_UNVERIFIED")
    require(result.get("migration_commit_preserved") is True,
            "HISTORIC_MIGRATION_COMMIT_MISSING")
    require(result.get("migration_head_stable") is True,
            "MIGRATION_HEAD_CHANGED_DURING_AUDIT")
    require(len({f["path"] for f in required_files}) == 27 and
            len(required_files) == 27, "HISTORIC_27_MANIFEST_INVALID")
    require(type(result.get("migration_unique_verified")) is int and
            result["migration_unique_verified"] == len(required_files) and
            not result.get("migration_unique_mismatches"),
            "MIGRATION_27_BLOB_MISMATCH")
    require(type(result.get("original_parts_verified")) is int and
            result["original_parts_verified"] == len(required_parts) and
            len(required_parts) == 3 and
            not result.get("original_parts_mismatches"),
            "ORIGINAL_3_PARTS_GIT_BLOB_MISMATCH")
    require(result.get("ci_git_blob") ==
            ci["historical_gitlab_ci_blob_sha1"], "CI_BLOB_DRIFT")
    require(result.get("entrypoint_git_blob") ==
            ci["historical_gitlab_entrypoint_blob_sha1"], "ENTRYPOINT_BLOB_DRIFT")
    # A runner is needed by future T12, not by T11 read-only migration history.
    # Preserve this operational finding without blocking authenticated 27+3 integrity.
    result["runner_available_for_future_T12"] = (
        result.get("windows_runner_proven_online") is True)
    result["evidence_errors"] = problems
    result["status"] = ("LIVE_MIGRATION_VERIFIED_NOT_SOURCE_READY" if not problems
                        else "LIVE_INSPECTED_INCOMPLETE")
    result["source_ready"] = False
    result["build_authorized"] = False
    return not problems

def main():
    parser = argparse.ArgumentParser(description="GitLab T11 read-only audit")
    parser.add_argument("--handoff", required=True, type=pathlib.Path)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    args = parser.parse_args()
    handoff = json.loads(args.handoff.read_text(encoding="utf-8"))
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
        "live_gitlab_head": None,
        "migration_live_head": None,
        "migration_commit_preserved": False,
        "migration_head_stable": False,
        "migration_unique_verified": 0,
        "migration_unique_total": len(handoff["history"]["migration_only_files"]),
        "migration_unique_mismatches": [],
        "original_parts_verified": 0,
        "original_parts_mismatches": [],
        "access_level": None,
        "permission_error": None,
        "evidence_errors": [],
        "source_ready": False,
        "build_authorized": False,
        "runners": [],
        "windows_runner_proven_online": False,
        "ci_git_blob": None,
        "entrypoint_git_blob": None,
        "mutations": 0,
        "pipeline_started": False
    }
    try:
        info = get("projects/" + project_id, token)
        if info.get("path_with_namespace") != project_path:
            raise ValueError("GitLab project namespace mismatch")
        result["project_visible"] = True
        result["visibility"] = info.get("visibility")
        result["default_branch"] = info.get("default_branch")
        pid = str(info["id"])
        try:
            actor = get("user", token)
            actor_id = actor.get("id")
            if type(actor_id) is not int or actor_id <= 0:
                raise ValueError("Authenticated GitLab user ID missing")
            member = get("projects/" + pid + "/members/all/" + str(actor_id), token)
            access = member.get("access_level")
            result["access_level"] = access if type(access) is int else None
        except (urllib.error.HTTPError, urllib.error.URLError, ValueError, KeyError) as ex:
            result["permission_error"] = type(ex).__name__

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
                query = pinned_ref(result["migration_live_head"])
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
                q = pinned_ref(result["migration_live_head"])
                try:
                    return get("projects/" + pid + "/repository/files/" + p +
                               "?ref=" + q, token).get("blob_id")
                except urllib.error.HTTPError:
                    return None
            for part in handoff["history"]["original_source_part_blobs"]:
                actual = observed_blob(part["path"])
                if actual == part["sha"]:
                    result["original_parts_verified"] += 1
                else:
                    result["original_parts_mismatches"].append({
                        "path": part["path"], "expected": part["sha"],
                        "observed": actual
                    })
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
        if result["migration_live_head"]:
            tip = get("projects/" + pid + "/repository/branches/" +
                      urllib.parse.quote(migration_ref, safe=""), token)
            result["migration_head_stable"] = (
                (tip.get("commit") or {}).get("id") ==
                result["migration_live_head"])
        evaluate_live_evidence(result, handoff)
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
    return 0 if result["status"] == "LIVE_MIGRATION_VERIFIED_NOT_SOURCE_READY" else 2

if __name__ == "__main__":
    sys.exit(main())
