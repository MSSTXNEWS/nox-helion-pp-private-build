#!/usr/bin/env python3
"""R2/cycle_cli.py: команды шагов цикла саморазвития (их зовёт self_dev_cycle по умолчанию). Каждая печатает ПОСЛЕДНЕЙ строкой JSON-метрики шага.
inspect | growth | drain | stage | sleep-metrics | weakest | exam | growth-report | evolve | week-report | month-report | rotation | goals
Все функции cmd_* принимают state (корень /root/nox/state) и now, возвращают dict метрик; ошибки инфраструктуры - исключение (шаг помечается сбойным)."""
import argparse
import glob
import json
import os
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", ".."))
for _d in (_HERE, os.path.join(_ROOT, "COMMON"), os.path.join(_ROOT, "SLP"), os.path.join(_ROOT, "EMO"), os.path.join(_ROOT, "ACT"),
           os.path.join(_ROOT, "MIND", "M1_ARCH"), os.path.join(_ROOT, "MIND", "M2_SELFIMPROVE"), os.path.join(_ROOT, "MIND", "M3_CONSCIOUS"),
           os.path.join(_ROOT, "MIND", "M4_BENCH"), os.path.join(_ROOT, "MIND", "M5_GROWTH")):
    if os.path.isdir(_d) and _d not in sys.path:
        sys.path.append(_d)
import curiosity as CU
import sleep_feed as SF
import growth as GR
import mind_bench as MB

SEED_ANCHORS = os.path.join(_ROOT, "MIND", "M5_GROWTH", "anchors_seed.jsonl")


def paths(state):
    sd = os.path.join(state, "selfdev")
    os.makedirs(sd, exist_ok=True)
    return {"sd": sd, "growth": os.path.join(state, "growth"), "inbox": os.path.join(state, "growth_inbox.jsonl"), "bench": os.path.join(state, "mindbench"),
            "frozen": os.path.join(sd, "self_dev_frozen"), "ledger": os.path.join(sd, "gate_ledger.jsonl"), "reports": os.path.join(sd, "reports"),
            "proposals": os.path.join(sd, "proposals")}


def _dump(p, obj):
    os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def _jl(p):
    out = []
    try:
        with open(p, encoding="utf-8") as f:
            for l in f:
                try:
                    out.append(json.loads(l))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


# ---------------------------------------------------------------- Growth: единственный писатель growth.json
def make_growth(state, wire=False, clock=time.time):
    """wire=True: быстрая модель через fastq P3, drives через очередь FeedDrives (не пишем drives.json), gap_map. wire=False: только состояние (отчёты, сон)."""
    P = paths(state)
    if not wire:
        return GR.Growth(P["growth"], solver=lambda p: "", anchors_path=SEED_ANCHORS, clock=clock)
    import fastq
    fq = fastq.get()
    llm = fq.llm(fastq.P3)

    def solver(p):
        return fq.chat([{"role": "system", "content": GR.SOLVE_SYS}, {"role": "user", "content": p}], fastq.P3, max_tokens=300, temperature=0.3)
    hs = [GR.DrivesHooks(CU.FeedDrives(os.path.join(state, "drives.json")))]
    gm = os.path.join(state, "act", "gaps.json")
    if os.path.exists(gm):
        import gap_map
        hs.append(GR.GapHooks(gap_map.GapMap(gm, allow_hosts=())))
    return GR.Growth(P["growth"], solver, llm=llm, judge=GR.make_judge(llm), hooks=GR.Hooks(*hs), anchors_path=SEED_ANCHORS, clock=clock)


def cmd_drain(state, growth=None, now=None):
    g = growth or make_growth(state, wire=True)
    r = CU.GrowthInbox(paths(state)["inbox"]).drain(g, now)
    return {"ingest": r["ingest"], "lessons": r["lesson"], "lessons_failed": r["lesson_failed"], "errors": r["errors"]}


def cmd_growth(state, growth=None, now=None, max_tasks=None):
    g = growth or make_growth(state, wire=True)
    d = CU.GrowthInbox(paths(state)["inbox"]).drain(g, now)
    r = g.session(max_tasks, now)
    return {"n": r.get("n", 0), "passed": r.get("passed", 0), "assisted": r.get("assisted", 0), "failed": r.get("failed", 0), "reviews": r.get("reviews", 0),
            "new_pass": r.get("new_pass", 0), "stopped": r.get("stopped"), "skipped": r.get("skipped"), "inbox_ingest": d["ingest"], "levelups": len(r.get("levelups", []))}


def cmd_exam(state, growth=None, now=None, tag="auto"):
    g = growth or make_growth(state, wire=True)
    if tag == "auto":
        tag = ""
        try:
            import adapter_registry as AR
            tag = AR.load(AR.paths(None))["current"] or ""
        except Exception:
            pass
    r = g.run_exam(now, tag=tag)
    return {"overall": r.get("overall"), "n": r.get("n", 0), "tag": tag, "ok": r.get("ok", False)}


def cmd_growth_report(state, growth=None, now=None):
    g = growth or make_growth(state)
    r = g.growth_report(now)
    return {"slope_per_week": r.get("slope_per_week"), "t": r.get("t"), "gain": r.get("gain"), "verdict": r.get("verdict"), "exams": r.get("exams"),
            "assisted_share": r.get("assisted_share"), "frontier": r.get("frontier")}


# ---------------------------------------------------------------- замороженные наборы и сон
def frozen_texts(growth=None):
    out = []
    try:
        for t in MB.load_suite(None, None, "all")["tasks"]:
            out += [s["say"] for s in t["steps"]]
    except (OSError, ValueError, KeyError):
        pass
    if growth is not None:
        out += [t["prompt"] for t in growth.exam_tasks]
    return out


def cmd_stage(state, growth=None, now=None, since_hours=24, frozen=None):
    now = now or time.time()
    g = growth or make_growth(state)
    r = SF.stage_for_sleep(g, state, now - since_hours * 3600, frozen if frozen is not None else frozen_texts(g), now)
    ps = None
    pp = os.path.join(state, "predictive_self.json")
    if os.path.exists(pp):
        import predictive_self as PS
        ps = PS.PredictiveSelf(pp)
    tdir = os.environ.get("NOX_TRACE_DIR", os.path.join(state, "traces"))
    since = now - since_hours * 3600
    an = SF.annotate_feedback(state, ps, tdir, since, now)                     # исход/возражение у строк Создателя (анти-угодливость)
    pr = SF.stage_predictive(ps, state, since, frozen if frozen is not None else frozen_texts(g), tdir, now)   # export_training_rows -> сон
    return {"rows": r["rows"], "owner_rows": r["owner_rows"], "skipped_frozen": r["skipped_frozen"] + pr["skipped_frozen"], "duplicates": r["duplicates"],
            "predictive_rows": pr["rows"], "annotated": an["annotated"]}


def cmd_sleep_metrics(state, now=None):
    P = paths(state)
    out = {"mode": None, "accepted": None, "decision": None}
    runs = sorted(glob.glob(os.path.join(state, "sleep", "*", "state.json")))
    if runs:
        st = json.load(open(runs[-1], encoding="utf-8"))
        ds = st["stages"].get("dataset") or {}
        dc = st["stages"].get("decide") or {}
        out.update(mode=(ds.get("mode") or ds.get("stats", {}).get("mode")), accepted=dc.get("accepted"), adapter=dc.get("id"), pending_signature=bool(dc.get("pending_signature")),
                   aborted=st.get("aborted"), day=st.get("day"))
    try:
        lg = json.load(open(os.path.join(P["sd"], "last_gate.json"), encoding="utf-8"))
        out.update(decision=lg.get("decision"), bench_overall=lg.get("bench_overall"), bench_holdout=lg.get("bench_holdout"), gate_reasons=lg.get("reasons", [])[:4])
    except (OSError, ValueError):
        pass
    return out


# ---------------------------------------------------------------- инспектор
def bench_history(state):
    return MB.load_history(paths(state)["bench"])


def cmd_inspect(state, now=None):
    """Цепочки журналов и тренд бенчмарка. Аномалия -> файл заморозки (учебные шаги ночи/недели/месяца не стартуют, пока Создатель не удалит файл)."""
    P, problems = paths(state), []
    try:
        import solver_policy as SP
        jp = os.path.join(state, "solver_journal.jsonl")
        if os.path.exists(jp) and not SP.read_journal(jp)[2]:
            problems.append("solver_journal: цепочка нарушена")
    except ImportError:
        pass
    try:
        import predictive_self as PS
        pp = os.path.join(state, "predictive_self.json")
        if os.path.exists(pp):
            ok, n, why = PS.PredictiveSelf(pp).verify_chain()
            if not ok:
                problems.append("predictive_self: " + why)
    except ImportError:
        pass
    dp = os.path.join(P["growth"], "growth_diary.jsonl")
    if os.path.exists(dp):
        ok, at = GR.Diary(dp).verify()
        if not ok:
            problems.append("growth_diary: разрыв на записи %s" % at)
    hist = [h for h in bench_history(state) if (h.get("splits") or {}).get("holdout") is not None]
    reg = None
    if len(hist) >= 2:
        c = MB.compare(hist[-1], hist[-2])
        o = c.get("overall") or {}
        if o.get("verdict") == "регресс":
            reg = o
            problems.append("MIND-BENCH: регресс holdout %+.3f [%.3f; %.3f] между двумя последними прогонами" % (o["delta"], o["lo"], o["hi"]))
    froze = 0
    if problems and not os.path.exists(P["frozen"]):
        with open(P["frozen"], "w", encoding="utf-8") as f:
            f.write("; ".join(problems)[:300])
        froze = 1
    return {"chains_ok": 0 if any("цепочк" in p or "разрыв" in p or "голова" in p for p in problems) else 1, "frozen": 1 if os.path.exists(P["frozen"]) else 0,
            "froze_now": froze, "problems": problems, "bench_runs": len(hist)}


# ---------------------------------------------------------------- неделя: слабейшая ось и evolve
def cmd_weakest(state, now=None):
    hist = bench_history(state)
    if not hist:
        return {"axis": None, "score": None, "reason": "нет прогонов MIND-BENCH"}
    rep = hist[-1]
    cand = [(a, v["score"]) for a, v in rep["axes"].items() if v.get("score") is not None and v.get("n_scored", 0) >= 3]
    if not cand:
        return {"axis": None, "score": None, "reason": "нет осей с n>=3"}
    a, s = min(cand, key=lambda x: x[1])
    _dump(os.path.join(paths(state)["sd"], "weakest_axis.json"), {"axis": a, "score": s, "ts": rep.get("ts"), "all": dict(cand)})
    return {"axis": a, "score": round(s, 4), "all": {k: round(v, 3) for k, v in cand}}


def run_evolve(state, loop, steps=3, kinds=("prompt", "strategy"), gate_checker=None, baseline=None):
    """loop: M2 EvolutionLoop (generator, evaluator, archive, champions уже собраны вызывающим). gate_checker - ворота gate_all внутри loop.gate. Возвращает метрики."""
    res = loop.run(steps, kinds=list(kinds), baseline=baseline)
    acc = [(k, r) for k, r in res if r.get("accepted")]
    for k, r in acc:        # MIND-10: принятый patch не применяем сами - карточка для agent/selfbuild (ветка nox/*, тесты, судья, release)
        cur = loop.champs.current("patch") if k == "patch" else None
        if cur:
            import evolve as EV
            import bench_evaluator as BE
            BE.queue_selfbuild(EV.Variant.from_json(cur["variant"]), r.get("verdict"), os.path.join(paths(state)["sd"], "selfbuild_queue.jsonl"))
    out = {"steps": steps, "accepted": len(acc), "kinds_accepted": [k for k, _ in acc],
           "coverage": loop.arch.coverage(), "log": len(loop.log)}
    _dump(os.path.join(paths(state)["sd"], "evolve_last.json"), {"t": time.time(), **{k: v for k, v in out.items() if k != "log"},
                                                                 "results": [(k, {kk: vv for kk, vv in r.items() if kk != "verdict"}) for k, r in res]})
    return out


def _cmd_evaluator(cmd):
    """Внешняя команда NOX_EVOLVE_CMD (переопределение): stdin {variant, tasks} -> stdout последней строкой {task_id: score}."""
    import subprocess

    def evaluator(v, ts):
        r = subprocess.run(cmd, shell=True, input=json.dumps({"variant": v.to_json(), "tasks": [t["id"] for t in ts]}), capture_output=True, text=True, timeout=7200)
        return json.loads(r.stdout.strip().splitlines()[-1])
    return evaluator


def _fast_alive(url, timeout=3.0):
    import urllib.request
    try:
        urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout).read()
        return True
    except Exception:
        try:
            urllib.request.urlopen(url.rstrip("/") + "/props", timeout=timeout).read()
            return True
        except Exception:
            return False


def cmd_evolve(state, now=None, evaluator=None, generator=None):
    """MIND-10: боевой evolve. Evaluator по умолчанию = MIND-BENCH на временном ядре (M4_BENCH/bench_evaluator.BenchEvaluator: вариант применяется только к временному ядру,
    holdout бенчмарка не используется). NOX_EVOLVE_CMD (внешняя команда) переопределяет; NOX_EVOLVE_BENCH=0 выключает шаг; быстрая модель недоступна -> шаг честно пропущен.
    Виды: NOX_EVOLVE_KINDS=prompt,strategy[,patch] (patch нужен NOX_EVOLVE_REPO - корень пакета; принятый patch -> очередь selfbuild_queue.jsonl, не применяется здесь).
    Принятие кода/стратегии проходит gate_all (подпись Создателя): без подписи чемпион не меняется, но прогон и лог остаются."""
    if os.environ.get("NOX_EVOLVE_BENCH") == "0" and not os.environ.get("NOX_EVOLVE_CMD") and evaluator is None:
        return {"steps": 0, "accepted": 0, "skipped": "NOX_EVOLVE_BENCH=0: шаг выключен"}
    import evolve as EV
    import gate_all as GA
    sd = paths(state)["sd"]
    wk = json.load(open(os.path.join(sd, "weakest_axis.json"), encoding="utf-8")) if os.path.exists(os.path.join(sd, "weakest_axis.json")) else {}
    tasks = [{"id": t["id"]} for t in MB.load_suite(None, None, "dev")["tasks"] if not wk.get("axis") or t["axis"] == wk["axis"]]
    kinds = tuple(k for k in os.environ.get("NOX_EVOLVE_KINDS", "prompt,strategy").split(",") if k in EV.KINDS) or ("prompt", "strategy")
    sandbox = None
    if evaluator is None:
        if os.environ.get("NOX_EVOLVE_CMD"):
            evaluator = _cmd_evaluator(os.environ["NOX_EVOLVE_CMD"])
        else:
            import bench_evaluator as BE
            fast = os.environ.get("NOX_FAST_URL", "http://127.0.0.1:8083")
            if not _fast_alive(fast):
                return {"steps": 0, "accepted": 0, "skipped": "быстрая модель %s не отвечает: evaluator (временное ядро) поднять нельзя" % fast}
            repo = os.environ.get("NOX_EVOLVE_REPO")
            evaluator = BE.BenchEvaluator(suite=MB.load_suite(None, None, "dev"), fast_url=fast, glm_url=os.environ.get("NOX_GLM_URL"), patch_repo=repo)
            if "patch" in kinds:
                if not repo:
                    kinds = tuple(k for k in kinds if k != "patch")
                else:
                    sandbox = EV.PatchSandbox(repo, os.environ.get("NOX_EVOLVE_TESTCMD", "python3 -m unittest discover -s BRAIN -p 'test_*.py'"))
    if generator is None:
        import fastq
        generator = EV.LLMGenerator(fastq.get().llm(fastq.P3), kinds=kinds)
    check = lambda: {"pass": False, "decision": "pending_signature", "reasons": [], "needs_signature": ["evolve: принятие кода/стратегии подтверждает Создатель"]}
    loop = EV.EvolutionLoop(generator, evaluator, tasks, EV.Archive(os.path.join(sd, "archive.jsonl")), EV.Champions(os.path.join(sd, "champions.json")),
                            gate=GA.evolve_gate(check), sandbox=sandbox, stop_file=os.path.join(state, "STOP"))
    baseline = {"prompt": EV.Variant("prompt", "", note="текущая душа"), "strategy": EV.Variant("strategy", "{}", note="текущие параметры")}
    out = run_evolve(state, loop, steps=int(os.environ.get("NOX_EVOLVE_STEPS", "3")), kinds=kinds, baseline=baseline)
    errs = [e for e in loop.log if isinstance(e, dict) and e.get("evaluator_error")]
    if errs:
        out["evaluator_errors"] = len(errs)
        out["first_evaluator_error"] = errs[0]["evaluator_error"]
    return out


# ---------------------------------------------------------------- отчёты и предложения (подпись Создателя)
def _write_report(P, name, text):
    os.makedirs(P["reports"], exist_ok=True)
    p = os.path.join(P["reports"], name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    return p


def _gate_counts(ledger, since):
    c = {}
    for r in _jl(ledger):
        if r.get("t", 0) >= since:
            c[r["decision"]] = c.get(r["decision"], 0) + 1
    return c


def cmd_week_report(state, growth=None, now=None):
    from self_dev_cycle import week_key
    now = now or time.time()
    P = paths(state)
    g = growth or make_growth(state)
    gr = g.growth_report(now)
    hist = bench_history(state)
    L = ["Отчёт недели %s." % week_key(now)]
    L.append("Экзамен роста: вердикт %s, наклон %s в неделю (экзаменов %s)." % (gr.get("verdict"), gr.get("slope_per_week"), gr.get("exams")))
    if len(hist) >= 2:
        c = MB.compare(hist[-1], hist[-2])
        o = c.get("overall") or {}
        L.append("MIND-BENCH против прошлого прогона: %s (%+.3f)." % (o.get("verdict", "н/д"), o.get("delta", 0.0)))
        for a, v in c["axes"].items():
            if v["verdict"] != "шум/без изменений":
                L.append("  ось %s: %s %+.3f" % (a, v["verdict"], v["delta"]))
    else:
        L.append("MIND-BENCH: меньше двух прогонов, сравнение недоступно.")
    wk = os.path.join(P["sd"], "weakest_axis.json")
    if os.path.exists(wk):
        w = json.load(open(wk, encoding="utf-8"))
        L.append("Слабейшая ось: %s (%.2f)." % (w["axis"], w["score"]))
    gc = _gate_counts(P["ledger"], now - 7 * 86400)
    L.append("Ворота за неделю: " + (", ".join("%s=%d" % kv for kv in sorted(gc.items())) or "решений не было") + ".")
    p = _write_report(P, "week_%s.md" % week_key(now), "\n".join(L))
    return {"report": p, "bench_runs": len(hist), "verdict": gr.get("verdict")}


def cmd_month_report(state, growth=None, now=None):
    from self_dev_cycle import month_key
    now = now or time.time()
    P = paths(state)
    g = growth or make_growth(state)
    gr = g.growth_report(now)
    hist = bench_history(state)
    L = ["Отчёт роста за месяц %s." % month_key(now)]
    L.append("Экзамен: вердикт %s, наклон %s/нед, прирост %s, самостоятельность: доля с подсказкой %s." % (gr.get("verdict"), gr.get("slope_per_week"), gr.get("gain"), gr.get("assisted_share")))
    if hist:
        gw = MB.compute_growth(hist[-1], hist, 30.0, hist[-1].get("ts"))
        L.append("РОСТ на скрытом holdout (30 сут): %s." % (("%s, %+.3f [%.3f; %.3f], n=%d" % (gw["verdict"], gw["delta"], gw["lo"], gw["hi"], gw["n"])) if gw.get("available") else "недоступен: " + gw.get("why", "")))
    gc = _gate_counts(P["ledger"], now - 30 * 86400)
    L.append("Решения ворот за месяц: " + (", ".join("%s=%d" % kv for kv in sorted(gc.items())) or "нет") + ".")
    L.append("Предложения (ротация holdout, цели) лежат в %s и вступают в силу только после подписи Создателя." % P["proposals"])
    p = _write_report(P, "month_%s.md" % month_key(now), "\n".join(L))
    return {"report": p, "verdict": gr.get("verdict"), "bench_runs": len(hist)}


def _proposal(P, name, body):
    import gate_all as GA
    body = dict(body)
    body["sha"] = GA.meta_sha(name, body["kind"], body.get("meta"))
    body["needs_signature"] = True
    _dump(os.path.join(P["proposals"], name + ".json"), body)
    return body


def cmd_rotation(state, now=None):
    """Ротация 20% holdout раз в месяц - только ПРЕДЛОЖЕНИЕ с манифестом (хеши, без текстов). Новые задания делает приватный генератор владельца бенча; смена набора = подпись Создателя."""
    from self_dev_cycle import month_key
    now = now or time.time()
    P = paths(state)
    try:
        suite = MB.load_suite(None, None, "holdout")
    except (OSError, ValueError):
        return {"proposed": 0, "reason": "holdout недоступен"}
    ids = sorted(t["id"] for t in suite["tasks"])
    k = max(1, len(ids) // 5)
    drop = sorted(ids, key=lambda i: MB.task_hash(next(t for t in suite["tasks"] if t["id"] == i)))[:k]
    _proposal(P, "holdout_rotation_" + month_key(now), {"kind": "value", "meta": {"changes_frozen_set": True}, "version": suite["version"], "n": len(ids),
                                                         "rotate_out_ids": drop, "action": "заменить заданиями приватного генератора, поднять версию набора"})
    return {"proposed": 1, "rotate_n": k}


def cmd_goals(state, growth=None, now=None):
    from self_dev_cycle import month_key
    now = now or time.time()
    P = paths(state)
    g = growth or make_growth(state)
    hist = bench_history(state)
    goals = []
    if hist:
        ax = sorted([(v["score"], a) for a, v in hist[-1]["axes"].items() if v.get("score") is not None])[:2]
        goals += [{"type": "bench_axis", "axis": a, "from": round(s, 3), "target": round(min(1.0, s + 0.1), 3)} for s, a in ax]
    need = sorted(g.lp_table(), key=lambda r: -r["need"])[:2]
    goals += [{"type": "growth_area", "area": r["area"], "mastered": r["mastered"]} for r in need]
    _proposal(P, "goals_" + month_key(now), {"kind": "genome_rule", "meta": {}, "goals": goals, "note": "цели на месяц: слабейшие оси и области роста"})
    return {"proposed": len(goals)}


def cmd_bench_summary(state, now=None):
    p = os.path.join(paths(state)["sd"], "bench_last.json")
    r = json.load(open(p, encoding="utf-8"))
    return {"overall": r.get("overall"), "holdout": (r.get("splits") or {}).get("holdout"), "growth": (r.get("growth") or {}).get("verdict"),
            "coverage": r.get("coverage")}


COMMANDS = {"bench-summary": cmd_bench_summary, "inspect": cmd_inspect, "growth": cmd_growth, "drain": cmd_drain, "stage": cmd_stage, "sleep-metrics": cmd_sleep_metrics, "weakest": cmd_weakest,
            "exam": cmd_exam, "growth-report": cmd_growth_report, "evolve": cmd_evolve, "week-report": cmd_week_report, "month-report": cmd_month_report,
            "rotation": cmd_rotation, "goals": cmd_goals}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cmd", choices=sorted(COMMANDS))
    ap.add_argument("--state", default=os.environ.get("NOX_STATE", "/root/nox/state"))
    ap.add_argument("--now", type=float)
    a = ap.parse_args(argv)
    try:
        r = COMMANDS[a.cmd](a.state, now=a.now)
    except ImportError as e:
        print(json.dumps({"error": "нет модуля проводки: %s" % e}, ensure_ascii=False))
        return 2
    print(json.dumps(r, ensure_ascii=False))
    return 1 if (a.cmd == "contam" and r.get("holdout_hits")) else 0


if __name__ == "__main__":
    sys.exit(main())
