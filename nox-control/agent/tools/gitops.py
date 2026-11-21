"""git для агента: ветка nox/<задача>, status, diff, commit, log, push только своих веток. Без shell, окружение чистое (+ токены из NOX_AGENT_GIT_PASS_ENV)."""
import os, re, subprocess
from . import Tool, err
from .files import BRANCH_RE, current_branch, DENY_NAMES, DENY_DIRS
import fnmatch

SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def slug(text, n=40):
    s = SLUG_RE.sub("-", (text or "").lower()).strip("-.")
    return (s or "task")[:n].strip("-.") or "task"


def git(cfg, cwd, *args, timeout=120):
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "GIT_TERMINAL_PROMPT": "0", "GIT_AUTHOR_NAME": "NOX agent", "GIT_AUTHOR_EMAIL": "nox-agent@localhost",
           "GIT_COMMITTER_NAME": "NOX agent", "GIT_COMMITTER_EMAIL": "nox-agent@localhost"}
    for k in cfg.git_pass_env:
        if k in os.environ: env[k] = os.environ[k]
    r = subprocess.run(["git", "-C", cwd] + list(args), capture_output=True, text=True, timeout=timeout, env=env)
    return r.returncode, r.stdout, r.stderr


def secret_path(rel):
    parts = rel.split("/")
    return any(x in DENY_DIRS and x != "__pycache__" for x in parts[:-1]) or any(fnmatch.fnmatch(parts[-1], p) for p in DENY_NAMES) or rel.endswith(".pyc")


def tool_git(a, ctx):
    cfg, wd, act = ctx.cfg, ctx.workdir, a["action"]
    br = current_branch(wd)
    if br is None: return err("рабочая папка не git-репозиторий")
    if act == "status":
        rc, o, e = git(cfg, wd, "status", "--short", "--branch")
        return {"ok": rc == 0, "branch": br, "status": o, "error": e.strip()[:300] or None}
    if act == "diff":
        base = a.get("base")
        if base and not re.fullmatch(r"[A-Za-z0-9_./~^@][A-Za-z0-9_./~^@-]*", base): return err("недопустимый base")
        args = ["diff", "--stat", "-p"] if not a.get("stat_only") else ["diff", "--stat"]
        if base: args.append(base + "...HEAD" if a.get("committed") else base)
        rc, o, e = git(cfg, wd, *args)
        lim = cfg.max_tool_output
        return {"ok": rc == 0, "branch": br, "diff": o[:lim], "truncated": len(o) > lim, "error": e.strip()[:300] or None}
    if act == "log":
        rc, o, e = git(cfg, wd, "log", "--oneline", "-n", "15")
        return {"ok": rc == 0, "log": o}
    if act == "branch":
        name = a.get("name") or ""
        if not name.startswith("nox/"): name = "nox/" + slug(name)
        if not BRANCH_RE.match(name): return err("имя ветки должно быть nox/<задача> (a-z, 0-9, ._-)")
        rc, o, e = git(cfg, wd, "checkout", "-b", name) if br != name else (0, "", "")
        if rc != 0:
            rc, o, e = git(cfg, wd, "checkout", name)
        return {"ok": rc == 0, "branch": name if rc == 0 else br, "error": e.strip()[:300] or None}
    if act == "commit":
        if not BRANCH_RE.match(br): return err("commit только в ветке nox/*; сейчас %r" % br, denied=True)
        msg = (a.get("message") or "").strip()
        if not msg: return err("нужен message")
        rc, o, e = git(cfg, wd, "status", "--porcelain")
        bad = [l[3:] for l in o.splitlines() if secret_path(l[3:].strip('"'))]
        if bad: return err("в изменениях секреты/служебное, commit отменён: " + ", ".join(bad[:5]), denied=True)
        rc, o, e = git(cfg, wd, "add", "-A")
        if rc != 0: return err("git add: " + e.strip()[:300])
        rc, o, e = git(cfg, wd, "commit", "-m", msg)
        if rc != 0: return err(("нечего коммитить" if "nothing to commit" in o + e else "git commit: " + (o + e).strip()[:300]))
        rc, sha, _ = git(cfg, wd, "rev-parse", "HEAD")
        return {"ok": True, "commit": sha.strip(), "branch": br}
    if act == "push":
        if not BRANCH_RE.match(br): return err("push только веток nox/*; сейчас %r" % br, denied=True)
        rc, o, e = git(cfg, wd, "push", "--set-upstream", cfg.remote, "HEAD:refs/heads/" + br, timeout=180)   # без --force
        return {"ok": rc == 0, "branch": br, "error": (o + e).strip()[:400] if rc else None}
    return err("неизвестное действие")


TOOLS = [Tool("git", "git в рабочей ветке: status, diff, log, branch (создать/перейти nox/<задача>), commit (git add -A + commit), push (только nox/*, без force).",
              {"type": "object", "properties": {"action": {"type": "string", "enum": ["status", "diff", "log", "branch", "commit", "push"]}, "name": {"type": "string"}, "message": {"type": "string"},
                                                "base": {"type": "string"}, "committed": {"type": "boolean"}, "stat_only": {"type": "boolean"}}, "required": ["action"]}, tool_git)]
