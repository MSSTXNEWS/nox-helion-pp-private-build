#!/usr/bin/env python3
"""R2/self_dev_cycle.py: ЕДИНЫЙ планировщик цикла саморазвития NOX: день / ночь / неделя / месяц. Идемпотентный, с dry-run, STOP, заморозкой и тихими часами.

  ДЕНЬ   (каждый тик)   flush: любопытство ходов -> drives, внимание; inspect: раз в час проверка цепочек/регрессов (заморозка при аномалии);
                        growth: простой -> drain почтового ящика -> занятие growth (<= дневного потолка; вопросы Создателю не в тихие часы).
  НОЧЬ   (тихие часы)   drain -> stage (проверенное -> KTO, без замороженных наборов) -> contam -> sleep (SLP: KTO, fidelity, regress, затем gate_all: MIND-BENCH кандидата + contam + подпись -> принять/откатить) -> report.
                        Любой сбой = прерывание ночи, адаптер не меняется. Принят адаптер -> экзамен роста (тег адаптера).
  НЕДЕЛЯ (вс, не тихо)  exam -> bench_full (MIND-BENCH all, история РОСТ) -> weakest (слабейшая ось) -> evolve (стратегии/код по слабейшей оси; ворота gate_all) -> week_report.
  МЕСЯЦ  (1-е число)    growth_report -> holdout_rotation (ПРЕДЛОЖЕНИЕ, нужна подпись) -> goals (ПРЕДЛОЖЕНИЕ, нужна подпись) -> month_report.
Шаги - функции fn(ctx)->{"ok": bool, "metrics": {...}, ...}; метрики обязательны (см. Step.metrics), пропуск фиксируется. Состояние: state_dir/self_dev_state.json,
метрики: state_dir/self_dev_metrics.jsonl, заморозка: state_dir/self_dev_frozen (создаёт инспектор; снимает только Создатель удалением файла), STOP: state_dir/STOP.
Запуск: python3 self_dev_cycle.py tick [--dry-run] [--state DIR] [--now TS]   (cron раз в 5 минут)
"""
import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _d in (_HERE, os.path.join(_ROOT, "COMMON")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)
try:
    import quiet as _quiet
except Exception:
    _quiet = None
try:
    import statefile
except Exception:
    statefile = None

MSK = timezone(timedelta(hours=3))
PHASES = ("day", "night", "week", "month")


def in_quiet(ts):
    if _quiet is not None:
        return _quiet.in_quiet(ts)
    h = datetime.fromtimestamp(ts, MSK).hour          # запасной вариант: 23:00-08:00 МСК
    return h >= 23 or h < 8


def night_key(ts):
    d = datetime.fromtimestamp(ts, MSK)
    if d.hour < 12:                                    # ночь принадлежит дате начала окна
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def week_key(ts):
    y, w, _ = datetime.fromtimestamp(ts, MSK).isocalendar()
    return "%d-W%02d" % (y, w)


def month_key(ts):
    return datetime.fromtimestamp(ts, MSK).strftime("%Y-%m")


@dataclass
class Step:
    name: str
    phase: str
    fn: object
    metrics: tuple = ()            # ключи метрик, которые шаг ОБЯЗАН вернуть
    critical: bool = True          # сбой критичного шага прерывает фазу (ночь/неделя/месяц)


class Scheduler:
    def __init__(self, state_dir, steps, clock=time.time, idle=None, growth_period_s=1500.0, flush_period_s=3600.0, inspect_period_s=3600.0,
                 week_weekday=6, month_day=1, max_retries=2, quiet_fn=None, ctx=None):
        """steps: {имя: Step}. idle() -> bool (чат свободен). week_weekday: 0=пн..6=вс (МСК)."""
        self.dir, self.steps, self.clock = state_dir, steps, clock
        self.idle = idle or (lambda: True)
        self.gp, self.fp, self.ip = growth_period_s, flush_period_s, inspect_period_s
        self.wd, self.md, self.max_retries = week_weekday, month_day, max_retries
        self.quiet = quiet_fn or in_quiet
        self.ctx = ctx if ctx is not None else {}
        os.makedirs(state_dir, exist_ok=True)
        self.p_state = os.path.join(state_dir, "self_dev_state.json")
        self.p_metrics = os.path.join(state_dir, "self_dev_metrics.jsonl")
        self.p_frozen = os.path.join(state_dir, "self_dev_frozen")
        self.p_stop = os.path.join(state_dir, "STOP")

    # ---------- состояние
    def load(self):
        try:
            with open(self.p_state, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
        for k in ("day", "night", "week", "month"):
            st.setdefault(k, {})
        return st

    def save(self, st):
        if statefile:
            statefile.save(self.p_state, st)
        else:
            with open(self.p_state, "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False)

    def frozen(self):
        try:
            with open(self.p_frozen, encoding="utf-8") as f:
                return f.read().strip() or "frozen"
        except OSError:
            return None

    def freeze(self, why):
        with open(self.p_frozen, "w", encoding="utf-8") as f:
            f.write(why[:300])

    def stopped(self):
        return os.path.exists(self.p_stop) or bool(os.environ.get("NOX_STOP_FILE") and os.path.exists(os.environ["NOX_STOP_FILE"]))

    # ---------- план
    def _seq(self, phase, names):
        return [n for n in names if n in self.steps]

    def plan(self, now=None, st=None):
        """-> список {phase, key, steps, why}. Чистая функция состояния и времени: ничего не выполняет."""
        now = self.clock() if now is None else now
        st = st if st is not None else self.load()
        out = []
        if self.stopped():
            return [{"phase": "stop", "key": "", "steps": [], "why": "STOP"}]
        fz = self.frozen()
        d = st["day"]
        quiet = self.quiet(now)
        dt = datetime.fromtimestamp(now, MSK)
        # ДЕНЬ: flush/inspect можно всегда (в т.ч. при заморозке: инспектор и поток данных безопасны)
        due = []
        if now - d.get("flush", 0) >= self.fp:
            due.append("flush")
        if now - d.get("inspect", 0) >= self.ip:
            due.append("inspect")
        if due:
            out.append({"phase": "day", "key": "tick", "steps": self._seq("day", due), "why": "периодические"})
        if fz:
            out.append({"phase": "frozen", "key": "", "steps": [], "why": "заморожено: " + fz})
            return out
        if now - d.get("growth", 0) >= self.gp and self.idle():
            out.append({"phase": "day", "key": "growth", "steps": self._seq("day", ["drain", "growth"]), "why": "простой -> занятие роста%s" % (" (тихие часы: без вопросов Создателю)" if quiet else "")})
        # НОЧЬ
        nk = night_key(now)
        ns = st["night"].get(nk, {})
        if quiet and not ns.get("complete") and ns.get("fails", 0) <= self.max_retries and self.idle():
            todo = [s for s in self._seq("night", ["n_drain", "n_stage", "n_contam", "n_sleep", "n_report"]) if s not in ns.get("done", [])]
            if todo:
                out.append({"phase": "night", "key": nk, "steps": todo, "why": "тихие часы, ночь не завершена"})
        # НЕДЕЛЯ
        wk = week_key(now)
        ws = st["week"].get(wk, {})
        if not quiet and dt.weekday() == self.wd and not ws.get("complete") and ws.get("fails", 0) <= self.max_retries and self.idle():
            todo = [s for s in self._seq("week", ["w_exam", "w_bench", "w_weakest", "w_evolve", "w_report"]) if s not in ws.get("done", [])]
            if todo:
                out.append({"phase": "week", "key": wk, "steps": todo, "why": "воскресенье, экзамен и evolve по слабейшей оси"})
        # МЕСЯЦ
        mk = month_key(now)
        ms = st["month"].get(mk, {})
        if not quiet and dt.day >= self.md and not ms.get("complete") and ms.get("fails", 0) <= self.max_retries and self.idle():
            todo = [s for s in self._seq("month", ["m_growth", "m_rotation", "m_goals", "m_report"]) if s not in ms.get("done", [])]
            if todo:
                out.append({"phase": "month", "key": mk, "steps": todo, "why": "новый месяц: отчёт роста и цели"})
        return out

    # ---------- выполнение
    def _metric(self, now, phase, key, step, rec):
        line = json.dumps({"t": now, "phase": phase, "key": key, "step": step, **rec}, ensure_ascii=False)
        if statefile:
            statefile.append_line(self.p_metrics, line)
        else:
            with open(self.p_metrics, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def _run_step(self, now, phase, key, name, ctx):
        s = self.steps[name]
        t0 = time.monotonic()
        try:
            r = s.fn(ctx) or {}
            ok = bool(r.get("ok", True))
        except Exception as e:
            r, ok = {"error": "%s: %s" % (type(e).__name__, e)}, False
        m = dict(r.get("metrics") or {})
        missing = [k for k in s.metrics if k not in m] if ok and not r.get("skipped") else []
        rec = {"ok": ok, "ms": int((time.monotonic() - t0) * 1000), "metrics": m}
        if r.get("skipped"):
            rec["skipped"] = r["skipped"]
        if missing:
            rec["missing_metrics"] = missing
        if r.get("error"):
            rec["error"] = r["error"]
        self._metric(now, phase, key, name, rec)
        ctx.update({k: v for k, v in r.items() if k not in ("metrics", "ok", "error", "skipped")})
        return ok, rec, bool(r.get("abort"))

    def tick(self, now=None, dry_run=False):
        now = self.clock() if now is None else now
        st = self.load()
        plan = self.plan(now, st)
        rep = {"now": now, "dry_run": dry_run, "plan": plan, "ran": [], "failed": [], "deferred": []}
        if dry_run:
            rep["would_run"] = [s for p in plan for s in p["steps"]]
            return rep
        for p in plan:
            ph, key = p["phase"], p["key"]
            if ph in ("stop", "frozen") or not p["steps"]:
                continue
            ctx = self.ctx
            ctx["now"], ctx["quiet"], ctx["key"] = now, self.quiet(now), key
            if ph == "day":
                for name in p["steps"]:
                    ok, rec, _ = self._run_step(now, ph, key, name, ctx)
                    rep["ran" if ok else "failed"].append(name)
                    if name in ("flush", "inspect", "growth"):
                        st["day"][name] = now
                    if name == "inspect" and ctx.get("freeze"):
                        self.freeze(str(ctx.pop("freeze")))
                        rep["frozen"] = self.frozen()
                continue
            ps = st[ph].setdefault(key, {"done": [], "fails": 0})
            for name in p["steps"]:
                ok, rec, abort = self._run_step(now, ph, key, name, ctx)
                if ok:
                    ps["done"].append(name)
                    rep["ran"].append(name)
                    if abort:
                        ps["aborted"] = ctx.pop("abort", name)
                        ps["complete"] = True       # осознанное завершение (напр. «нет данных для сна»): повторов нет
                        break
                else:
                    rep["failed"].append(name)
                    if self.steps[name].critical:
                        ps["fails"] += 1
                        ps["last_error"] = {"step": name, "error": rec.get("error", "")[:200]}
                        break
            else:
                ps["complete"] = True
            if ph == "night" and ctx.get("accepted") and "w_exam" in self.steps and not ps.get("exam_after"):
                ok, rec, _ = self._run_step(now, "night", key, "w_exam", ctx)
                ps["exam_after"] = True
                rep["ran" if ok else "failed"].append("w_exam@adapter")
            self.save(st)
        self.save(st)
        return rep

    def report(self, since=0):
        """Сводка метрик цикла из журнала: по шагам последнее значение."""
        last = {}
        try:
            with open(self.p_metrics, encoding="utf-8") as f:
                for l in f:
                    try:
                        r = json.loads(l)
                    except ValueError:
                        continue
                    if r["t"] >= since:
                        last[r["step"]] = r
        except OSError:
            pass
        return last


# ============================================================ шаги по умолчанию (боевая проводка; в тестах подменяются)
def default_steps(cfg):
    """cfg: {state, root, cmd}. Шаги - внешние команды (cycle_cli/SLP/mind_bench); метрики берутся из последней JSON-строки stdout.
    Любопытство (flush) шлёт само ядро (MindBridge.on_turn), поэтому шага flush в cron нет; он нужен только встроенному планировщику (регистрируется вручную)."""
    import subprocess
    st = cfg["state"]

    def sh(key, timeout=7200):
        def run(ctx):
            cmd = cfg["cmd"].get(key)
            if not cmd:
                return {"ok": True, "skipped": "команда %s не задана" % key, "metrics": {}}
            r = subprocess.run(cmd.format(state=st, root=cfg.get("root", _ROOT), now=int(ctx.get("now", time.time()))), shell=True, capture_output=True, text=True, timeout=timeout)
            m = {}
            for l in reversed((r.stdout or "").strip().splitlines()):
                try:
                    m = json.loads(l)
                    break
                except ValueError:
                    continue
            m = m if isinstance(m, dict) else {}
            out = {"ok": r.returncode == 0, "metrics": m, "error": (r.stderr or r.stdout or "")[-200:] if r.returncode else ""}
            if m.get("problems") and key == "inspect" and m.get("frozen"):
                out["freeze"] = "; ".join(m["problems"])[:300]
            return out
        return run

    S = {}

    def add(name, phase, key, metrics, critical=True):
        S[name] = Step(name, phase, sh(key), tuple(metrics), critical)
    add("inspect", "day", "inspect", ("chains_ok", "frozen"), False)
    add("drain", "day", "drain", ("ingest", "lessons"), False)
    add("growth", "day", "growth", ("n", "passed", "assisted", "failed"), False)
    add("n_drain", "night", "drain", ("ingest", "lessons"))
    add("n_stage", "night", "stage", ("rows", "skipped_frozen"))
    add("n_contam", "night", "contam", ("holdout_hits",))
    add("n_sleep", "night", "sleep", ("mode", "accepted", "decision"))
    add("n_report", "night", "report", (), False)
    add("w_exam", "week", "exam", ("overall", "n"))
    add("w_bench", "week", "bench_full", ("overall",))
    add("w_weakest", "week", "weakest", ("axis", "score"))
    add("w_evolve", "week", "evolve", ("steps", "accepted"))
    add("w_report", "week", "week_report", ("report",), False)
    add("m_growth", "month", "growth_report", ("slope_per_week", "verdict"))
    add("m_rotation", "month", "rotation", ("proposed",), False)
    add("m_goals", "month", "goals", ("proposed",), False)
    add("m_report", "month", "month_report", ("report",), False)
    return S


_CLI = "python3 {root}/MIND/R2/cycle_cli.py %s --state {state}"
DEFAULT_CMD = {
    "inspect": _CLI % "inspect", "drain": _CLI % "drain", "growth": _CLI % "growth", "stage": _CLI % "stage",
    "contam": "python3 {root}/MIND/M4_BENCH/mind_bench.py contam --train {state}/feedback.jsonl",
    "sleep": "NOX_STATE={state} NOX_SLP_HOOKS=slp_night_hooks:Hooks PYTHONPATH={root}/MIND/R2 python3 {root}/SLP/sleep_cycle.py run --state {state} >/dev/null && " + _CLI % "sleep-metrics",
    "report": _CLI % "sleep-metrics",
    "exam": _CLI % "exam",
    "bench_full": "python3 {root}/MIND/M4_BENCH/mind_bench.py run --split all --history-dir {state}/mindbench --out {state}/selfdev/bench_last.json >/dev/null; " + _CLI % "bench-summary",
    "weakest": _CLI % "weakest", "evolve": _CLI % "evolve", "week_report": _CLI % "week-report",
    "growth_report": _CLI % "growth-report", "rotation": _CLI % "rotation", "goals": _CLI % "goals", "month_report": _CLI % "month-report",
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["tick", "plan", "report"])
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--now", type=float)
    ap.add_argument("--config", help="json: {cmd:{...}} переопределение команд")
    a = ap.parse_args(argv)
    cfg = {"state": a.state, "root": _ROOT, "cmd": dict(DEFAULT_CMD)}
    if a.config:
        with open(a.config, encoding="utf-8") as f:
            cfg["cmd"].update(json.load(f).get("cmd", {}))
    sch = Scheduler(os.path.join(a.state, "selfdev"), default_steps(cfg))
    if a.cmd == "report":
        print(json.dumps(sch.report(), ensure_ascii=False, indent=1))
        return 0
    rep = sch.tick(a.now, dry_run=a.dry_run or a.cmd == "plan")
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 1 if rep["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
