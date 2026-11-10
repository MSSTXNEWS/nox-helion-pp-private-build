#!/usr/bin/env python3
"""Read-only GitHub Actions failure triage for NOX V16.

Never converts a job failure without step logs into a product regression.
Requires GITHUB_TOKEN (read-only Actions permission). Stdlib only.
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"


def api_get(path, token):
    req = urllib.request.Request(
        API + path,
        headers={"Authorization": "Bearer " + token,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "nox-v16-ci-triage"})
    with urllib.request.urlopen(req, timeout=15) as response:
        return json.load(response)


def diagnose_run(repo, run_id, token):
    run = api_get(f"/repos/{repo}/actions/runs/{run_id}", token)
    jobs = api_get(f"/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100", token)
    if jobs.get("total_count", 0) > len(jobs.get("jobs", [])):
        raise ValueError("PAGINATION_REQUIRED: cannot assert all jobs were checked")
    classifications = []
    for job in jobs.get("jobs", []):
        steps = job.get("steps") or []
        failed = [s for s in steps if s.get("conclusion") in ("failure", "timed_out")]
        if job.get("conclusion") == "failure" and not steps:
            status = "NO_STEPS_CAUSE_UNKNOWN"
        elif failed:
            status = "FAILED_STEPS_PRESENT_INSPECT_LOGS"
        elif job.get("conclusion") == "success":
            status = "JOB_SUCCESS"
        else:
            status = "NON_SUCCESS_UNCLASSIFIED"
        classifications.append({
            "id": job.get("id"), "name": job.get("name"),
            "conclusion": job.get("conclusion"),
            "classification": status,
            "failed_steps": [{"name": s.get("name"), "number": s.get("number")}
                             for s in failed],
            "runner_name": job.get("runner_name"),
            "runner_group_name": job.get("runner_group_name")})
    return {"run_id": run_id, "head_sha": run.get("head_sha"),
            "event": run.get("event"), "conclusion": run.get("conclusion"),
            "jobs": classifications, "source_ready": False,
            "independent_qa_accepted": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="MSSTXNEWS/nox-helion-pp-private-build")
    parser.add_argument("--head", required=True, help="Exact frozen commit SHA")
    parser.add_argument("--runs", type=int, nargs="+", required=True,
                        help="Run IDs verified for the exact --head; no stale defaults")
    a = parser.parse_args()
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        parser.error("GITHUB_TOKEN with read-only Actions permission required")
    if len(a.head) != 40 or any(c not in "0123456789abcdef" for c in a.head):
        parser.error("--head must be full lowercase 40-character SHA")
    try:
        results = [diagnose_run(a.repo, run_id, token) for run_id in a.runs]
    except (urllib.error.URLError, ValueError, KeyError) as exc:
        print(json.dumps({"status": "DIAGNOSTIC_ERROR", "error": str(exc)}))
        return 2
    if any(r["head_sha"] != a.head for r in results):
        print(json.dumps({"status": "HEAD_MISMATCH", "results": results}, indent=2))
        return 3
    print(json.dumps({"status": "DIAGNOSTIC_ONLY", "head": a.head,
                      "results": results}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
