"""Песочница правок и выкатка с откатом (шаг 33).
Правки своего кода только в git worktree на ветке nox/<задача>. Выкатка (merge в main живого репо) только если:
  1) run_tests зелёные в ветке, И 2) судья вернул ok, И 3) нет опасного (удаление файлов, защитные модули агента) без подтверждения владельца.
После merge проверяется health; при падении: автооткат (git revert -m 1), повторный запуск deploy-команды. STOP прерывает всё до merge; после merge STOP = откат."""
import os, shutil, subprocess, time, urllib.request, urllib.error, shlex, fnmatch
from .config import Config
from .tools import ToolContext, need_confirm
from .tools.approvals import Approvals
from .tools.gitops import git, slug
from .tools.files import BRANCH_RE
from .tools import testing


def now_stop(cfg):
    return os.path.exists(cfg.stop_file)


class Sandbox:
    """git worktree на ветке nox/<slug> рядом с живым репо. Основная ветка и живой каталог агентом не правятся."""

    def __init__(self, cfg):
        self.cfg = cfg

    def create(self, title, task_id=""):
        cfg = self.cfg
        name = slug(title or task_id)
        if task_id: name = (name[:30] + "-" + slug(task_id, 20)).strip("-.")
        branch, path = "nox/" + name, os.path.join(cfg.work_root, name)
        if not BRANCH_RE.match(branch): raise ValueError("недопустимое имя ветки " + branch)
        os.makedirs(cfg.work_root, exist_ok=True)
        if os.path.isdir(path):
            rc, o, _ = git(cfg, path, "rev-parse", "--abbrev-ref", "HEAD")
            if rc == 0 and o.strip() == branch: return {"branch": branch, "path": os.path.realpath(path), "reused": True}
            raise RuntimeError("каталог %s занят другой веткой" % path)
        rc, _, _ = git(cfg, cfg.repo, "rev-parse", "--verify", "--quiet", "refs/heads/" + branch)
        args = ["worktree", "add", path, branch] if rc == 0 else ["worktree", "add", "-b", branch, path, cfg.base_branch]
        rc, o, e = git(cfg, cfg.repo, *args)
        if rc != 0: raise RuntimeError("git worktree: " + (o + e).strip()[:300])
        return {"branch": branch, "path": os.path.realpath(path), "reused": False}

    def remove(self, path):
        git(self.cfg, self.cfg.repo, "worktree", "remove", "--force", path)
        shutil.rmtree(path, ignore_errors=True)
        git(self.cfg, self.cfg.repo, "worktree", "prune")


def changed_files(cfg, branch):
    """[(статус, путь)] ветка относительно base."""
    rc, o, e = git(cfg, cfg.repo, "diff", "--name-status", "%s...%s" % (cfg.base_branch, branch))
    out = []
    if rc == 0:
        for l in o.splitlines():
            p = l.split("\t")
            if len(p) >= 2: out.append((p[0][0], p[-1]))
    return out


def branch_diff(cfg, branch, limit=None):
    rc, o, e = git(cfg, cfg.repo, "diff", "%s...%s" % (cfg.base_branch, branch))
    return o if limit is None else o[:limit], len(o)


def http_health(cfg):
    try:
        with urllib.request.urlopen(urllib.request.Request(cfg.health_url), timeout=5) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


class Release:
    def __init__(self, cfg=None, tests_fn=None, judge_fn=None, health_fn=None, deploy_fn=None, approvals=None, sleep=time.sleep):
        self.cfg = cfg or Config()
        self.tests_fn = tests_fn or (lambda wd: testing.run_tests(wd, self.cfg))
        self.judge_fn = judge_fn
        self.health_fn = health_fn or (lambda: http_health(self.cfg))
        self.deploy_fn = deploy_fn or self._deploy_cmd
        self.approvals = approvals or Approvals(self.cfg.approvals_file)
        self.sleep = sleep
        self.log = []

    def _note(self, step, **kw):
        self.log.append(dict(step=step, **kw))

    def _deploy_cmd(self):
        if not self.cfg.deploy_cmd: return {"ok": True, "skipped": True}
        try:
            r = subprocess.run(shlex.split(self.cfg.deploy_cmd), cwd=self.cfg.repo, capture_output=True, text=True, timeout=300)
            return {"ok": r.returncode == 0, "output": (r.stdout + r.stderr)[-500:]}
        except Exception as e:
            return {"ok": False, "output": str(e)}

    def _res(self, status, **kw):
        return dict(status=status, steps=self.log, **kw)

    def needs_owner(self, branch):
        """Список причин, по которым merge требует подтверждения: удаление файлов, правка защитных модулей."""
        reasons = []
        for st, path in changed_files(self.cfg, branch):
            if st == "D": reasons.append("удаление файла " + path)
            if any(fnmatch.fnmatch(path, pat) for pat in self.cfg.protected): reasons.append("правка защитного модуля " + path)
        return reasons

    def deploy(self, branch, workdir, task_title="", task=None):
        cfg = self.cfg
        if not BRANCH_RE.match(branch): return self._res("refused", reason="выкатываются только ветки nox/*")
        if now_stop(cfg): return self._res("stopped", reason="STOP до выкатки")
        rc, o, _ = git(cfg, workdir, "status", "--porcelain")
        if o.strip(): return self._res("refused", reason="в рабочей ветке есть незакоммиченные изменения")
        # 1. тесты
        t = self.tests_fn(workdir)
        self._note("tests", ok=bool(t.get("ok")), ran=t.get("ran"), failures=t.get("failures"), errors=t.get("errors"))
        if not t.get("ok"): return self._res("rejected", reason="тесты не зелёные", tests=t)
        # 2. судья
        diff, total = branch_diff(cfg, branch, cfg.judge_max_diff)
        if not diff.strip(): return self._res("no_changes", reason="ветка не отличается от %s" % cfg.base_branch)
        if total > cfg.judge_max_diff: return self._res("rejected", reason="диф %d симв. больше лимита судьи %d: разбей задачу" % (total, cfg.judge_max_diff), tests=t)
        if self.judge_fn is None: return self._res("rejected", reason="судья не задан (выкатка без судьи запрещена)", tests=t)
        try: verdict = self.judge_fn(task or {"title": task_title}, diff, t)
        except Exception as e: verdict = {"ok": False, "reasons": ["судья упал: %s" % e]}
        self._note("judge", ok=bool(verdict.get("ok")), reasons=verdict.get("reasons"))
        if verdict.get("ok") is not True: return self._res("rejected", reason="судья не одобрил", judge=verdict, tests=t)
        # 3. опасное
        reasons = self.needs_owner(branch)
        if reasons:
            ctx = ToolContext(cfg, workdir, approvals=self.approvals)
            r = need_confirm(ctx, "merge", "ветка %s: %s" % (branch, "; ".join(reasons)))
            if r is not None:
                return self._res("awaiting_owner" if r.get("needs_confirmation") else "rejected", reason=r["error"], approval_id=r.get("approval_id"), danger=reasons)
        if not cfg.merge: return self._res("ready", reason="NOX_AGENT_MERGE=0: влить вручную", branch=branch)
        # 4. живой репо
        rc, cur, _ = git(cfg, cfg.repo, "rev-parse", "--abbrev-ref", "HEAD")
        if cur.strip() != cfg.base_branch: return self._res("refused", reason="живой репо на ветке %r, не %s" % (cur.strip(), cfg.base_branch))
        rc, o, _ = git(cfg, cfg.repo, "status", "--porcelain", "--untracked-files=no")
        if o.strip(): return self._res("refused", reason="живой репо с незакоммиченными правками")
        if not self.health_fn(): return self._res("refused", reason="health до выкатки уже красный: откат нельзя отнести к этой выкатке")
        if now_stop(cfg): return self._res("stopped", reason="STOP перед merge")
        rc, pre, _ = git(cfg, cfg.repo, "rev-parse", "HEAD"); pre = pre.strip()
        rc, o, e = git(cfg, cfg.repo, "merge", "--no-ff", "-m", "nox: %s (%s)" % (task_title or branch, branch), branch)
        if rc != 0:
            git(cfg, cfg.repo, "merge", "--abort")
            return self._res("merge_failed", reason=(o + e).strip()[:300])
        rc, merged, _ = git(cfg, cfg.repo, "rev-parse", "HEAD"); merged = merged.strip()
        self._note("merged", pre=pre, merge=merged)
        # 5. выкатка + health
        d = self.deploy_fn()
        self._note("deploy", ok=bool(d.get("ok")), out=d.get("output"))
        healthy, why = bool(d.get("ok")), "deploy-команда упала" if not d.get("ok") else ""
        if healthy:
            for i in range(max(cfg.health_checks, 1)):
                if i: self.sleep(cfg.health_interval)
                if now_stop(cfg): healthy, why = False, "STOP после merge: откат непроверенной выкатки"; break
                if not self.health_fn(): healthy, why = False, "health упал (проверка %d)" % (i + 1); break
        self._note("health", ok=healthy, why=why)
        if healthy: return self._res("merged", merge=merged, pre=pre, branch=branch, judge=verdict, tests=t)
        rb = self.rollback(merged, pre)
        return self._res("rolled_back" if rb["ok"] else "rollback_failed", reason=why, rollback=rb, merge=merged, pre=pre)

    def rollback(self, merged, pre):
        cfg = self.cfg
        rc, head, _ = git(cfg, cfg.repo, "rev-parse", "HEAD")
        if head.strip() == merged:
            rc, o, e = git(cfg, cfg.repo, "reset", "--hard", pre)       # наш merge последний: возвращаем указатель на точный pre-sha
            how = "reset"
        else:
            rc, o, e = git(cfg, cfg.repo, "revert", "-m", "1", "--no-edit", merged)   # поверх уже есть чужие коммиты: сохраняем историю
            how = "revert"
            if rc != 0: git(cfg, cfg.repo, "revert", "--abort")
        ok = rc == 0
        d = self.deploy_fn() if ok else {"ok": False}
        self._note("rollback", how=how, ok=ok, redeploy=d.get("ok"))
        return {"ok": ok, "how": how, "redeploy_ok": d.get("ok"), "error": None if ok else (o + e).strip()[:300]}
