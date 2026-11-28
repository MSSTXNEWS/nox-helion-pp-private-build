#!/usr/bin/env python3
"""NOX сон по канону v5 гл. 5 (чистый код, без LLM). Окно 02:00-05:00 МСК, как у agent/nox_agents/sleep.py (тот собирает пары обучения; здесь его файлы НЕ меняются, sleep_cursor только читается).
NREM (с 02:00): replay эпизодов state/core/episodes.jsonl по весу (ошибка x аффект x новизна x значимость x свежесть) -> уроки (nrem_lessons.jsonl) и концепты-кластеры (nrem_concepts.json), строка в dream.jsonl (phase=NREM).
REM (с 03:00): рекомбинация двух эпизодов из разных источников -> 1-2 гипотезы со статусом «не проверено» (rem_hypotheses.jsonl) -> утренняя мысль (morning_thought.json, ключ в self_now.json, строка dream.jsonl phase=REM).
Забывание не делается здесь: им занимается поток №10 (память). Читает веса из nrem_lessons.jsonl/episodes; ничего не удаляет."""
import os, sys, json, math, time, hashlib, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C
WINDOW = (2, 5)
def in_window(now): h = C.msk_hour(now); return WINDOW[0] <= h < WINDOW[1]
def _is_err(e):
    if e.get("kind") in ("veto",): return 1.0
    c = e.get("content")
    if isinstance(c, dict):
        for k, v in c.items():
            if any(s in str(k).lower() for s in ("error", "err", "fail", "exception")) and v not in (0, False, None, "", "none"): return 1.0
            if k == "ok" and v is False: return 1.0
    return 0.3
def _aff(e):
    a = e.get("affect")
    if isinstance(a, (int, float)): return min(1.0, abs(float(a)))
    if isinstance(a, dict):
        v = [abs(x) for x in a.values() if isinstance(x, (int, float))]
        return min(1.0, max(v)) if v else 0.3
    return 0.3
def weigh(eps, now):
    """Вес эпизода = (0.2+ошибка) x (0.5+аффект) x новизна x значимость x свежесть(полураспад 24 ч)."""
    cnt = {}
    for e in eps: cnt[(e.get("src"), e.get("kind"))] = cnt.get((e.get("src"), e.get("kind")), 0) + 1
    out = []
    for e in eps:
        t = C.parse_ts(e.get("t")) or now; age_h = max(0.0, (now - t) / 3600.0)
        nov = 1.0 / (1.0 + math.log1p(cnt[(e.get("src"), e.get("kind"))]))
        w = (0.2 + _is_err(e)) * (0.5 + _aff(e)) * nov * max(0.05, float(e.get("salience") or 0.05)) * 0.5 ** (age_h / 24.0)
        out.append((w, e))
    out.sort(key=lambda x: -x[0]); return out
def _keys(e): return frozenset((e.get("content") or {}).keys()) if isinstance(e.get("content"), dict) else frozenset()
def load_eps(r, now, hours=48):
    L = C.jl_tail(C.S(r) + "/episodes.jsonl", 8000, maxbytes=8_000_000)
    return [e for e in L if e.get("id") and now - (C.parse_ts(e.get("t")) or 0) <= hours * 3600]
def pairs_written(r):
    d = C.load_json(r + "/state/agents/sleep_cursor.json", {}) or {}
    return d.get("written")
def _dream(r, now, text, themes, phase, extra=None):
    rec = {"ts": C.iso_z(now), "msk": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now + 10800)) + " МСК", "dream": text, "themes": themes[:6], "phase": phase}
    rec.update(extra or {}); C.jl_append(C.M(r) + "/dream.jsonl", rec)
def nrem(r, now, topk=60):
    eps = load_eps(r, now); W = weigh(eps, now)[:topk]
    groups = {}
    for w, e in W: groups.setdefault((e.get("src"), e.get("kind")), []).append((w, e))
    lessons = []
    for (src, kind), g in sorted(groups.items(), key=lambda kv: -sum(w for w, _ in kv[1])):
        errs = sum(1 for _, e in g if _is_err(e) >= 1.0)
        if len(g) < 2 and not errs: continue
        if errs and errs / len(g) > 0.5: concl = "требует внимания: найти причину повторных сбоев"
        elif len(g) >= 20: concl = "рутина: сжать в сводку, сырое не хранить дольше нужного"
        else: concl = "редкий сигнал: сохранить как есть"
        lid = "les_" + hashlib.sha1(("%s|%s|%s" % (src, kind, C.iso_z(now)[:10])).encode()).hexdigest()[:10]
        lessons.append({"id": lid, "ts": C.iso_z(now), "text": "За 48 ч «%s/%s» повторилось %d раз(а) в отборе replay, вес %.2f, сбоев %d. Вывод: %s." % (src, kind, len(g), sum(w for w, _ in g), errs, concl),
                        "evidence": [e["id"] for _, e in g[:6]], "weight": round(sum(w for w, _ in g), 4), "status": "черновик (код, без проверки)", "source": "nrem"})
        if len(lessons) >= 5: break
    for l in lessons: C.jl_append(C.M(r) + "/nrem_lessons.jsonl", l)
    cl = []
    for w, e in W:
        k = _keys(e)
        if not k: continue
        for c in cl:
            if len(k & c["keys"]) / len(k | c["keys"]) >= 0.6: c["members"].append(e["id"]); c["keys"] = c["keys"] | k if len(c["members"]) < 3 else c["keys"]; break
        else: cl.append({"keys": set(k), "members": [e["id"]]})
    cl = [c for c in sorted(cl, key=lambda c: -len(c["members"])) if len(c["members"]) >= 2][:5]
    concepts = [{"id": "con_" + hashlib.sha1("|".join(sorted(c["keys"])).encode()).hexdigest()[:10], "keys": sorted(c["keys"])[:12], "size": len(c["members"]), "members": c["members"][:8]} for c in cl]
    C.atomic_json(C.M(r) + "/nrem_concepts.json", {"ts": C.iso_z(now), "n": len(concepts), "concepts": concepts})
    pw = pairs_written(r)
    text = "Консолидирую память: в повторе %d эпизодов, %d уроков, %d концептов%s." % (len(W), len(lessons), len(concepts), (", пар обучения за ночь собрано %s" % pw) if pw is not None else "")
    _dream(r, now, text, ["%s/%s" % k for k in list(groups)[:6]], "NREM", {"lessons": [l["id"] for l in lessons], "concepts": [c["id"] for c in concepts], "replayed": len(W)})
    return {"replayed": len(W), "lessons": len(lessons), "concepts": len(concepts), "episodes_in_window": len(eps)}
def _shared(a, b):
    ca, cb = (a.get("content") if isinstance(a.get("content"), dict) else {}), (b.get("content") if isinstance(b.get("content"), dict) else {})
    ks = sorted(set(ca) & set(cb)); same = [k for k in ks if isinstance(ca[k], (int, float, str, bool)) and ca[k] == cb[k] and str(ca[k]) not in ("", "0")]
    if same: return "совпадающие значения полей " + ", ".join(same[:3])
    if ks: return "общие поля " + ", ".join(ks[:3])
    dtm = abs((C.parse_ts(a.get("t")) or 0) - (C.parse_ts(b.get("t")) or 0)) / 60.0
    return "близость во времени (%.0f мин)" % dtm
def rem(r, now, n_hyp=2):
    eps = load_eps(r, now, hours=72); W = weigh(eps, now)
    if len(W) < 2: return {"hypotheses": 0}
    rnd = random.Random(C.iso_z(now)[:10]); top = [e for _, e in W[:15]]; pool = [e for _, e in W[:200]]
    hyps = []
    for _ in range(n_hyp * 4):
        if len(hyps) >= n_hyp: break
        a = rnd.choice(top); cand = [e for e in pool if e.get("src") != a.get("src") and e["id"] != a["id"]]
        if not cand: continue
        b = rnd.choice(cand)
        if any({a["id"], b["id"]} == set(h["evidence"]) for h in hyps): continue
        sh = _shared(a, b)
        hid = "hyp_" + hashlib.sha1((a["id"] + b["id"] + C.iso_z(now)[:10]).encode()).hexdigest()[:10]
        hyps.append({"id": hid, "ts": C.iso_z(now), "text": "Гипотеза (не проверено): события «%s/%s» и «%s/%s» могут быть связаны через %s. Проверка: если связь реальна, она повторится в ближайшие сутки." % (a.get("src"), a.get("kind"), b.get("src"), b.get("kind"), sh),
                     "evidence": [a["id"], b["id"]], "status": "не проверено", "source": "rem"})
    for h in hyps: C.jl_append(C.M(r) + "/rem_hypotheses.jsonl", h)
    if not hyps: return {"hypotheses": 0}
    mt = {"ts": C.iso_z(now), "text": "Ночью заметил одну вещь (не проверено): " + hyps[0]["text"].split("Гипотеза (не проверено): ", 1)[1], "hypotheses": [h["id"] for h in hyps], "status": "не проверено"}
    C.atomic_json(C.M(r) + "/morning_thought.json", mt)
    _dream(r, now, "Увидел во сне связь, не проверено: " + hyps[0]["text"].split("Гипотеза (не проверено): ", 1)[1][:200], ["rem"], "REM", {"hypotheses": [h["id"] for h in hyps], "status": "не проверено"})
    sn = C.S(r) + "/self_now.json"; cur = C.load_json(sn, None)
    if isinstance(cur, dict): cur["morning_thought"] = {"text": mt["text"], "ts": mt["ts"], "status": "не проверено", "hypotheses": mt["hypotheses"]}; C.atomic_json(sn, cur)
    return {"hypotheses": len(hyps)}
def run(r, now):
    return {"nrem": nrem(r, now), "rem": rem(r, now)}
def maybe_run(r, now=None):
    now = now if now is not None else time.time()
    if not in_window(now): return None
    sp = C.M(r) + "/organism_sleep.json"; st = C.load_json(sp, {}) or {}; day = time.strftime("%Y-%m-%d", time.gmtime(now + 10800)); res = {"ran": False}
    if st.get("nrem_day") != day and C.msk_hour(now) >= 2:
        res["nrem"] = nrem(r, now); st["nrem_day"] = day; res["ran"] = True
    if st.get("rem_day") != day and st.get("nrem_day") == day and C.msk_hour(now) >= 3:
        res["rem"] = rem(r, now); st["rem_day"] = day; res["ran"] = True
    if res["ran"]: C.atomic_json(sp, st)
    return res
if __name__ == "__main__":
    print(json.dumps(run(C.root(), time.time()), ensure_ascii=False))
