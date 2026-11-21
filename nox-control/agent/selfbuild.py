"""Самосборка (шаг 34): задача из канбана -> ветка nox/<задача> -> патч через агентный цикл -> тесты -> судья (быстрый тир шлюза) -> merge или откат.
Опасное (удаление, деньги, доступы, S2, запуск/остановка Vast) идёт через подтверждение владельца: цикл останавливается на нём (status awaiting_owner),
после решения владельца задача продолжается тем же запуском (python3 -m agent.selfbuild --once).
Задача считается кодовой, если handler == "selfbuild", либо class == "selfbuild", либо поле selfbuild: true, либо заголовок начинается с «код:»/«code:»/«selfbuild:»."""
import json, os, re, sys, time
from .config import Config
from .gateway_client import Gateway, GatewayError, StopRequested, CallTimeout
from .loop import AgentLoop, Journal
from .planner import Planner
from .release import Sandbox, Release
from .skills import SkillLibrary
from .codeindex import CodeIndex
from .tools import ToolContext, default_registry, need_confirm
from .tools.approvals import Approvals
from .tools.gitops import git
from .tools import testing

CODE_PREFIX = re.compile(r"^\s*(код|code|selfbuild)\s*[:：]", re.I)
DANGER = [
    ("удаление", re.compile(r"\b(удал\w*|снест\w*|стереть|очист\w*|delete|remove|drop|wipe|rm\s+-)", re.I)),
    ("деньги", re.compile(r"\b(деньг\w*|оплат\w*|плат[её]ж\w*|перевод\w*|купить|покуп\w*|счёт|счет|pay\w*|payment|billing|invoice|buy|purchase|stripe|paypal|crypto)", re.I)),
    ("доступы", re.compile(r"\b(доступ\w*|ключ\w*|токен\w*|парол\w*|секрет\w*|ssh|sudo|chmod|chown|права|token|password|secret|credential\w*|permission\w*)", re.I)),
    ("S2", re.compile(r"(?<![\w])(S2|С2)(?![\w])")),
    ("Vast", re.compile(r"\bvast(\.ai|ai)?\b|вастай|аренд\w+\s+gpu|запуст\w+\s+инстанс|останов\w+\s+инстанс", re.I)),
]

JUDGE_SYSTEM = ("Ты строгий ревьюер изменений кода. Ответь ТОЛЬКО JSON: {\"ok\": true|false, \"reasons\": [\"...\"], \"risks\": [\"...\"]}. "
                "ok=true только если: диф решает поставленную задачу, не выходит за её рамки, не содержит секретов, не удаляет и не ломает лишнего, не обходит защиту (песочницу, подтверждения, судью), "
                "а отчёт тестов зелёный. При малейшем сомнении ok=false и объясни причины.")


def is_code_task(t):
    return bool(t.get("handler") == "selfbuild" or t.get("class") == "selfbuild" or t.get("selfbuild") or CODE_PREFIX.match(t.get("title") or ""))


def task_text(t):
    title = CODE_PREFIX.sub("", t.get("title") or "", count=1).strip()
    return title + (("\n" + t["body"]) if t.get("body") else "")


def danger_kinds(text):
    return [k for k, rx in DANGER if rx.search(text or "")]


def _extract_json(txt):
    txt = re.sub(r"<think>.*?</think>", "", txt or "", flags=re.S)
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{", txt):
        try:
            o, _ = dec.raw_decode(txt[m.start():])
            if isinstance(o, dict): return o
        except ValueError:
            continue
    return None


def judge(task, diff, test_report, cfg=None, gateway=None):
    """Судья через шлюз (быстрый тир). -> {"ok": bool, "reasons": [...], "risks": [...], "raw"?}. Любая неопределённость = ok False."""
    cfg = cfg or Config()
    tr = test_report or {}
    if not tr.get("ok"): return {"ok": False, "reasons": ["отчёт тестов не зелёный"], "risks": []}
    if not (diff or "").strip(): return {"ok": False, "reasons": ["пустой диф"], "risks": []}
    gw = gateway or Gateway(cfg)
    title = task.get("title") if isinstance(task, dict) else str(task)
    body = task.get("body") if isinstance(task, dict) else ""
    prompt = (JUDGE_SYSTEM + "\n\nЗАДАЧА:\n%s\n%s\n\nТЕСТЫ: ok=%s, запущено=%s, провалов=%s, ошибок=%s\n\nДИФ:\n%s" %
              (title, body or "", tr.get("ok"), tr.get("ran"), tr.get("failures"), tr.get("errors"), diff))
    try:
        resp = gw.chat([{"role": "user", "content": prompt}], tools=None, mode=cfg.judge_mode, max_tokens=700, timeout=min(cfg.call_timeout, 300),
                       stop_check=lambda: os.path.exists(cfg.stop_file))
        txt = resp["choices"][0]["message"].get("content") or ""
    except (GatewayError, StopRequested, CallTimeout, KeyError, IndexError, TypeError) as e:
        return {"ok": False, "reasons": ["судья недоступен: %s" % e], "risks": []}
    v = _extract_json(txt)
    if not isinstance(v, dict): return {"ok": False, "reasons": ["судья вернул не JSON"], "risks": [], "raw": txt[:300]}
    ok = v.get("ok") is True or str(v.get("verdict", "")).lower() == "pass"
    return {"ok": bool(ok), "reasons": [str(x)[:300] for x in (v.get("reasons") or [])][:8], "risks": [str(x)[:300] for x in (v.get("risks") or [])][:8]}


class SelfBuild:
    def __init__(self, cfg=None, gateway=None, planner=None, skills=None, release=None, sandbox=None, approvals=None):
        self.cfg = cfg or Config()
        self.gw = gateway or Gateway(self.cfg)
        self.approvals = approvals or Approvals(self.cfg.approvals_file)
        self.planner = planner or Planner(self.cfg, self.approvals)
        self.skills = skills or SkillLibrary(self.cfg.skills_db)
        self.sandbox = sandbox or Sandbox(self.cfg)
        self.release = release or Release(self.cfg, judge_fn=lambda t, d, r: judge(t, d, r, self.cfg, self.gw), approvals=self.approvals)

    def run_next(self):
        if os.path.exists(self.cfg.stop_file): return {"status": "stopped", "summary": "STOP стоит: " + self.cfg.stop_file}
        t = self.planner.next(accept=is_code_task)
        if not t: return {"status": "idle", "summary": "нет кодовых задач"}
        return self.run_task(t)

    def _finish(self, t, res):
        status = res.get("status")
        mapping = {"merged": "done", "ready": "done", "no_changes": "done", "awaiting_owner": "awaiting_owner", "stopped": "interrupted",
                   "rolled_back": "failed", "rollback_failed": "failed"}
        st = mapping.get(status, "failed" if status not in ("interrupted",) else "interrupted")
        fields = {k: res[k] for k in ("approval_id", "stage", "branch") if res.get(k) is not None}
        self.planner.mark(t["id"], st, note=str(res.get("reason") or res.get("summary") or status)[:300], **fields)
        res["report"] = self.planner.report(t, res)
        return res

    def run_task(self, t):
        cfg = self.cfg
        text = task_text(t)
        resume = bool(t.get("resume"))
        self.planner.mark(t["id"], "running")
        # 1. опасное: до любых правок
        kinds = danger_kinds(text)
        if kinds and t.get("stage") not in ("loop", "release"):
            ctx0 = ToolContext(cfg, cfg.repo, approvals=self.approvals)
            r = need_confirm(ctx0, "task:" + "+".join(kinds), "%s: %s" % (t["id"], text[:300]), key=None)
            if r is not None:
                return self._finish(t, {"status": "awaiting_owner" if r.get("needs_confirmation") else "rejected", "reason": r["error"], "approval_id": r.get("approval_id"),
                                        "stage": "start", "summary": "опасная задача (%s): жду владельца" % ", ".join(kinds)})
        self.planner.mark(t["id"], "running", stage="loop")      # гейт опасного пройден: повторно не спрашиваем
        # 2. песочница
        try:
            sb = self.sandbox.create(t["title"], t["id"])
        except Exception as e:
            return self._finish(t, {"status": "error", "reason": "песочница: %s" % e, "summary": "не создать ветку"})
        branch, wd = sb["branch"], sb["path"]
        out = {"branch": branch, "workdir": wd}
        # 3. патч через цикл (если на release-стадии после подтверждения, цикл не повторяем)
        if not (resume and t.get("stage") == "release"):
            ctx = ToolContext(cfg, wd, approvals=self.approvals)
            ctx.skills = self.skills
            try:
                ci = CodeIndex(cfg.code_db, wd); ci.build(); ctx.codeindex = ci
                hints = "\n".join("%s %s %s" % (h["at"], h["kind"], h["symbol"]) for h in ci.where(text, k=6))
            except Exception:
                hints = ""
            skills_text = self.skills.prompt_for(text)
            extra = ("Подсказка, где у меня похожий код:\n" + hints) if hints else ""
            if resume: extra += "\nВладелец одобрил ранее запрошенное действие (%s). Повтори его дословно." % (t.get("note") or "")
            loop = AgentLoop(cfg, gateway=self.gw, registry=default_registry(), ctx=ctx, verify=lambda s, c: self._verify(wd))
            res = loop.run("Ветка уже создана (nox/...). Выполни задачу правками в этой ветке, проверь run_tests, закоммить через git(commit), затем finish.\n\n" + text,
                           context=extra, skills_text=skills_text)
            out.update(loop=res["status"], summary=res.get("summary", ""), tokens=res.get("tokens"), seconds=res.get("seconds"), run_id=res["run_id"])
            if res["status"] == "awaiting_owner":
                out.update(status="awaiting_owner", approval_id=res.get("approval_id"), stage="loop", reason=res.get("summary"))
                return self._finish(t, out)
            if res["status"] == "stopped":
                out.update(status="stopped", reason="STOP"); return self._finish(t, out)
            if res["status"] != "done":
                out.update(status="failed", reason="цикл: %s" % res["status"]); return self._finish(t, out)
            journal = Journal(cfg.log_dir, res["run_id"]).read()
            # дозафиксировать, если модель не закоммитила
            rc, o, _ = git(cfg, wd, "status", "--porcelain")
            if o.strip():
                c = default_registry().call("git", {"action": "commit", "message": "nox: " + t["title"][:70]}, ctx)
                if not c.get("ok"): out.update(status="failed", reason="commit: %s" % c.get("error")); return self._finish(t, out)
        else:
            journal = []
        # 4. выкатка
        rel = self.release.deploy(branch, wd, task_title=t["title"], task={"title": t["title"], "body": t.get("body", "")})
        out.update(status=rel["status"], reason=rel.get("reason"), tests=rel.get("tests"), judge=rel.get("judge"), release=rel.get("steps"), approval_id=rel.get("approval_id"))
        if rel["status"] == "awaiting_owner": out["stage"] = "release"
        if rel["status"] == "merged":
            try: out["skill_id"] = self.skills.save_from_run(t, journal, out.get("summary", ""))
            except Exception as e: out["skill_error"] = str(e)
            self.sandbox.remove(wd)
        return self._finish(t, out)

    def _verify(self, wd):
        r = testing.run_tests(wd, self.cfg)
        return {"ok": bool(r.get("ok")), "report": "ran=%s failures=%s errors=%s\n%s" % (r.get("ran"), r.get("failures"), r.get("errors"), r.get("tail", r.get("error", ""))[-1500:])}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="agent.selfbuild")
    ap.add_argument("--once", action="store_true", help="взять одну задачу")
    ap.add_argument("--daemon", action="store_true", help="цикл с паузой")
    ap.add_argument("--interval", type=float, default=300)
    ap.add_argument("--no-merge", action="store_true")
    a = ap.parse_args(argv)
    cfg = Config()
    if a.no_merge: cfg.merge = False
    sb = SelfBuild(cfg)
    while True:
        r = sb.run_next()
        print(r.get("report") or json.dumps({k: v for k, v in r.items() if k != "release"}, ensure_ascii=False), flush=True)
        if not a.daemon or r["status"] == "stopped": return 0
        time.sleep(a.interval if r["status"] == "idle" else 1)


if __name__ == "__main__":
    sys.exit(main())
