"""branch_pr: git branch/commit/push + GitHub REST (PR open, squash merge). stdlib urllib."""
import json
import os
import re
import urllib.error
import urllib.request
import registry as R

TRAILERS = "\n\nCo-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>\nClaude-Session: https://claude.ai/code/session_016FcEU5qWbMD9DzZter9mcS\n"
PR_FOOT = "\n\n\U0001F916 Generated with [Claude Code](https://claude.com/claude-code)"
REF = re.compile(r"^[A-Za-z0-9._/-]{1,100}$")


def _token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    r = R.run(["gh", "auth", "token"], timeout=15)
    return r["out"].strip() if r["rc"] == 0 else None


def _http(method, url, token, body=None):  # replaced by tests
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
                                          "Content-Type": "application/json", "User-Agent": "nox-selftools"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, {"message": e.read().decode("utf-8", "replace")[:300]}


@R.register("branch_pr", "write", {"properties": {
    "action": {"type": "string", "enum": ["status", "create_branch", "commit", "push", "open_pr", "merge_pr"]},
    "repo": {"type": "string", "description": "owner/name for GitHub actions"},
    "branch": {"type": "string"}, "base": {"type": "string", "default": "origin/main"},
    "message": {"type": "string"}, "paths": {"type": "array"}, "title": {"type": "string"},
    "body": {"type": "string"}, "head": {"type": "string"}, "pr": {"type": "integer"},
    "cwd": {"type": "string", "default": "."}}, "required": ["action"]},
    "git + gh REST: status/create_branch/commit(trailers)/push/open_pr/merge_pr(squash). dry_run default.",
    action_modes={"status": "read"})
def branch_pr(a):
    cwd = R.safe_path(a["cwd"], must_exist=True)
    act = a["action"]
    for k in ("branch", "head"):
        if a.get(k) and not REF.match(a[k]):
            return R.fail("bad ref in " + k)
    g = lambda *x: R.run(["git"] + list(x), cwd=cwd)
    if act == "status":
        return {"ok": True, "branch": g("rev-parse", "--abbrev-ref", "HEAD")["out"].strip(),
                "status": g("status", "--short")["out"].splitlines()[:200]}
    if act in ("create_branch", "commit", "push"):
        if act == "create_branch":
            cmds = [["git", "switch", "-c", a.get("branch") or "", a["base"]]] if a.get("branch") else None
        elif act == "commit":
            if not a.get("message"):
                return R.fail("message required")
            cmds = [["git", "add", "--"] + list(a.get("paths") or ["."]),
                    ["git", "commit", "-m", a["message"].rstrip() + TRAILERS]]
        else:
            cmds = [["git", "push", "-u", "origin", a.get("branch") or "HEAD"]]
        if not cmds:
            return R.fail("branch required")
        if a["dry_run"]:
            return {"ok": True, "dry_run": True, "would_run": cmds}
        outs = []
        for c in cmds:
            r = R.run(c, cwd=cwd, timeout=120)
            outs.append({"cmd": c[:4], "rc": r["rc"], "err": r["err"][-300:]})
            if r["rc"] != 0:
                return {"ok": False, "error": "git failed", "steps": outs}
        return {"ok": True, "steps": outs}
    # GitHub REST
    if not a.get("repo") or not re.match(r"^[\w.-]+/[\w.-]+$", a["repo"]):
        return R.fail("repo owner/name required")
    if act == "open_pr":
        if not (a.get("head") and a.get("title")):
            return R.fail("head and title required")
        payload = {"title": a["title"], "head": a["head"], "base": a.get("base", "main").replace("origin/", ""),
                   "body": (a.get("body") or "").rstrip() + PR_FOOT}
        call = ("POST", "https://api.github.com/repos/%s/pulls" % a["repo"], payload)
    else:
        if not a.get("pr"):
            return R.fail("pr number required")
        call = ("PUT", "https://api.github.com/repos/%s/pulls/%d/merge" % (a["repo"], a["pr"]), {"merge_method": "squash"})
    if a["dry_run"]:
        return {"ok": True, "dry_run": True, "would_call": list(call[:2]), "payload": call[2]}
    tok = _token()
    if not tok:
        return R.blocked("no GitHub token", "set GH_TOKEN or run `gh auth login`")
    code, data = _http(call[0], call[1], tok, call[2])
    ok = code in (200, 201)
    return {"ok": ok, "http": code, "number": data.get("number"), "url": data.get("html_url"),
            "merged": data.get("merged"), "message": None if ok else data.get("message")}
