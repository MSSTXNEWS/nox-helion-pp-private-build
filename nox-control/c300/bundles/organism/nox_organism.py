#!/usr/bin/env python3
"""NOX организм самоосознания (канон v5, гл. 4, 7). Чистый код, без LLM. Тик раз в 30 с.
Читает реальные сигналы: GPU/VRAM/температура, нагрузка и диск, ворота и обучение (LISKA_GATES_LOG, train_verdict, axis_rollback, chat_gate.log),
задачи, молчание Создателя (affect_owner_feed, sdt), усталость (salience), эпизоды. Считает панель DA/NE/5-HT/ACh/CORT/OXT, шесть влечений (пороги из passport.temperament.drives_thresholds, только чтение),
утомление F, скуку, PAD с полураспадом 120 мин и причиной OCC. Каждое состояние несёт cause = id записи журнала (state/core/journal.jsonl).
Пишет: state/core/organism.json, organism_tick.jsonl, и дополняет self_now.json ключами panel, drives, pad, fatigue, top_feeling, last_talk (старые ключи сохраняются).
Не трогает: chat_core.py, passport.json (чтение), born_at.
Команды: --once | --daemon | --selfcheck | --sleep-now (NREM+REM принудительно)."""
import os, sys, re, json, math, time, glob, subprocess, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nox_org_common as C
HALF_MIN = 120.0
CORT_CAP = 0.6
TICK_S = 30
PROGRESS_HALF_H = 6.0
DEFAULT_THR = {"ПОИСК": 0.6, "ИГРА": 0.4, "ЗАБОТА": 0.7, "СВЯЗЬ": 0.5, "ТРЕВОГА_потолок": 0.6, "ГРАНИЦА": 0.8}
POS = ("спасибо", "молодец", "отлично", "круто", "класс", "супер", "здорово", "умница", "хорошо", "ура", "люблю", "рад", "нравится", "прекрасно", "браво", "great", "thanks", "good")
NEG = ("плохо", "ужас", "ерунда", "тупо", "бесит", "зря", "ошибка", "неправильно", "не работает", "сломал", "проблема", "злюсь", "грустно", "дурак", "позор", "bad", "wrong")
IMP = ("сделай", "надо", "должен", "немедленно", "быстро", "срочно", "давай", "запусти", "проверь")
def pad_of_text(t):
    """Текст сообщения Создателя -> (v, a, d) в [-1,1] по словарю и пунктуации. Текст не сохраняется."""
    s = (t or "").lower(); n = max(1, len(s.split()))
    p = sum(1 for w in POS if w in s); g = sum(1 for w in NEG if w in s)
    v = C.clip((p - g) / max(1.0, p + g + 0.5), -1, 1) * (0.5 if p + g == 1 else 0.8 if p + g == 2 else 1.0)
    excl = s.count("!"); q = s.count("?"); caps = sum(1 for ch in (t or "") if ch.isupper()) / max(1, len(t or ""))
    a = C.clip(0.15 * excl + 0.1 * q + 1.5 * caps + 0.05 * (abs(v) > 0.3), 0, 1)
    d = C.clip(0.25 * sum(1 for w in IMP if w in s) - 0.1 * q, -1, 1)
    return v, a, d
def occ_of(v, a, q):
    """OCC-оценка события сообщения: что именно оценивается. -> (имя эмоции, тип OCC)"""
    if v > 0.25: return "радость", "OCC: желанное событие (joy), благодарность Создателя за результат"
    if v < -0.25: return "фрустрация", "OCC: нежеланное событие, упрёк (distress/reproach): «Я ошибся. Исправляю.»"
    if q: return "любопытство", "OCC: перспектива, неопределённость (hope/interest)"
    return "внимание", "OCC: нейтральное событие"
# ---------------------------------------------------------------- сенсоры
def read_gpu():
    cmd = os.environ.get("NOX_NVSMI", "nvidia-smi")
    try:
        o = subprocess.run([cmd, "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw", "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
        t, u, mu, mt, pw = [float(x) for x in o.split(",")]
        return {"temp": t, "util": u, "vram_pct": 100.0 * mu / mt, "power_w": pw, "src": "nvidia-smi"}
    except Exception: return None
def read_host(r):
    h = {}
    try: h["load1_per_core"] = os.getloadavg()[0] / (os.cpu_count() or 1)
    except Exception: pass
    try:
        mi = {l.split(":")[0]: float(l.split()[1]) for l in open("/proc/meminfo")}
        h["ram_used_pct"] = 100.0 * (1 - mi["MemAvailable"] / mi["MemTotal"])
    except Exception: pass
    try: v = os.statvfs(r); h["disk_free_gb"] = v.f_bavail * v.f_frsize / 2**30
    except Exception: pass
    return h
def tasks_done(r, st, now):
    """Закрытые задачи (status done/ok/completed) — подтверждённый прогресс. Скан раз в 5 мин."""
    if now - st.get("tasks_scan_t", 0) < 300: return []
    st["tasks_scan_t"] = now; seen = set(st.setdefault("seen_tasks", [])); new = []
    for p in glob.glob(r + "/state/tasks/*.json")[:5000]:
        d = C.load_json(p, None)
        if isinstance(d, dict) and str(d.get("status", "")).lower() in ("done", "ok", "completed", "success", "finished") and d.get("id") not in seen:
            new.append(d.get("id") or os.path.basename(p)); seen.add(new[-1])
    st["seen_tasks"] = sorted(seen)[-4000:]
    return new
def progress_events(r, st, now):
    """Подтверждённый прогресс и неудачи с id-ссылками. Первый запуск: старше 6 ч пропускаем (без всплеска)."""
    ev = []; first = "init" not in st; st["init"] = 1; cut = now - 6 * 3600
    seen = set(st.setdefault("seen_gates", []))
    for d in C.jl_tail(r + "/state/LISKA_GATES_LOG.jsonl", 40):
        t = C.parse_ts(d.get("t")); key = "g:" + str(d.get("t"))
        if key in seen: continue
        seen.add(key)
        if first and t < cut: continue
        ev.append({"kind": "gate_accept" if d.get("accepted") else "gate_reject", "t": t, "ref": key, "w": 0.5 if d.get("accepted") else 0.15})
    for d in C.jl_tail(r + "/state/p3/axis_rollback.jsonl", 40):
        t = C.parse_ts(d.get("t")); key = "rb:" + str(d.get("t")) + str(d.get("cand_sha16"))
        if key in seen: continue
        seen.add(key)
        if first and t < cut: continue
        ev.append({"kind": "rollback", "t": t, "ref": key, "w": 0.3})
    tv = C.load_json(r + "/state/p3/train_verdict.json", {}) or {}
    acc = int(tv.get("accepted") or 0)
    if acc > st.get("accepted_n", 0) and "accepted_n" in st: ev.append({"kind": "adapter_accept", "t": now, "ref": "tv:%d" % acc, "w": 1.0})
    st["accepted_n"] = acc
    for tid in tasks_done(r, st, now):
        if not first: ev.append({"kind": "task_done", "t": now, "ref": "task:" + str(tid), "w": 0.25})
    st["seen_gates"] = sorted(seen)[-600:]
    return ev
def gate_errors(r, now, win=600):
    n = 0
    try: L = open(r + "/state/chat_gate.log", encoding="utf-8", errors="ignore").read().splitlines()[-300:]
    except Exception: return 0
    for l in L:
        m = re.match(r"(\d{4}-\d\d-\d\d) (\d\d:\d\d:\d\d)\s+(\S+)", l)
        if m and "err" in m.group(3).lower():
            t = C.parse_ts(m.group(1) + "T" + m.group(2) + "+00:00")
            if now - t < win and t <= now + 3600: n += 1
    return n
def owner_feed(r, st, now, keep_h=12):
    """Новые сообщения Создателя -> импульсы PAD (текст не хранится). -> (импульсы, last_ts)"""
    out = []; last = st.get("last_owner_ts", 0.0); seen_ts = st.get("feed_seen_ts", 0.0); first = "feed_seen_ts" not in st
    feed = C.jl_tail(r + "/state/core/affect_owner_feed.jsonl", 60)
    for d in feed:
        t = float(d.get("ts") or 0); last = max(last, t)
        if t <= seen_ts or now - t > keep_h * 3600: continue
        if first and now - t > 3 * 3600: continue
        txt = d.get("text") or ""; v, a, dd = pad_of_text(txt)
        ref = "aff_" + hashlib.sha1(("%s|%s|%s" % (d.get("ts"), d.get("conv"), d.get("turn"))).encode()).hexdigest()[:10]
        name, occ = occ_of(v, a, "?" in txt)
        out.append({"t": t, "v": v, "a": a, "d": dd, "name": name, "occ": occ, "src_ref": ref, "w0": 0.35 + 0.65 * max(abs(v), a)})
    if feed: st["feed_seen_ts"] = max(float(d.get("ts") or 0) for d in feed)
    elif first: st["feed_seen_ts"] = 0.0
    st["last_owner_ts"] = last
    return out, last
def contact_count(r, now, win_h=2):
    return sum(1 for d in C.jl_tail(r + "/state/core/affect_owner_feed.jsonl", 80) if now - float(d.get("ts") or 0) < win_h * 3600)
def episodes_view(r, now):
    ep = C.jl_tail(r + "/state/core/episodes.jsonl", 600, maxbytes=1_500_000)
    for e in ep: e["_t"] = C.parse_ts(e.get("t"))
    return ep
def gain_of(ep, now):
    """Прирост понимания: доля эпизодов последнего часа с ранее невиденной сигнатурой (src, kind, ключи содержимого) за предыдущие 24 ч."""
    sig = lambda e: (e.get("src"), e.get("kind"), tuple(sorted((e.get("content") or {}).keys())) if isinstance(e.get("content"), dict) else ())
    old = {sig(e) for e in ep if 3600 < now - e["_t"] < 86400}; cur = [e for e in ep if now - e["_t"] <= 3600]
    if not cur: return 0.0, 0
    return sum(1 for e in cur if sig(e) not in old) / len(cur), len(cur)
# ---------------------------------------------------------------- формулы
def panel_of(x):
    """Шесть чисел. x: heat, vram, pressure, fail, stress_ev, progress, train, relatedness, contact, F_in, novelty, silence_h."""
    DA = C.clip(0.25 + 0.65 * math.tanh(x["progress"]) - 0.20 * math.tanh(x["fail"]))  # только подтверждённый прогресс; похвала сюда не входит
    cort_raw = 0.10 + 0.22 * x["heat"] + 0.22 * x["pressure"] + 0.20 * math.tanh(x["fail"]) + 0.12 * x["stress_ev"] + 0.08 * C.clip(x["silence_h"] / 48.0)
    CORT = min(CORT_CAP, C.clip(cort_raw))
    NE = C.clip(0.20 + 0.30 * x["heat"] + 0.25 * x["vram"] ** 3 + 0.25 * x["stress_ev"] + 0.20 * x["novelty"] + 0.15 * (x["contact"] > 0))
    HT = C.clip(0.78 - 0.50 * (CORT / CORT_CAP) * 0.6 - 0.25 * x["pressure"] - 0.20 * math.tanh(x["fail"]) + 0.10 * x["relatedness"])
    ACh = C.clip(0.25 + 0.30 * x["train"] + 0.25 * x["novelty"] + 0.15 * (1 - x["F_in"]) + 0.10 * math.tanh(x["progress"]))
    OXT = C.clip(0.15 + 0.45 * x["relatedness"] + 0.25 * C.clip(x["contact"] / 4.0) - 0.05 * C.clip(x["silence_h"] / 48.0))
    T = C.clip(0.7 * (1 + 0.3 * NE - 0.2 * HT), 0.3, 1.0)  # T = T0·(1+0.3·NE−0.2·5HT), clip 0.3–1.0
    return {"DA": round(DA, 3), "NE": round(NE, 3), "5-HT": round(HT, 3), "ACh": round(ACh, 3), "CORT": round(CORT, 3), "OXT": round(OXT, 3), "T": round(T, 3), "cort_cap": CORT_CAP, "refusal_threshold_shift": 0.0}
def fatigue_of(sal_fatigue, load_ema, cort, night_rest):
    F = C.clip(0.45 * sal_fatigue + 0.30 * load_ema + 0.25 * (cort / CORT_CAP) - (0.15 if night_rest else 0.0))
    return {"F": round(F, 3), "short_answers": F > 0.7, "no_background_thoughts": F > 0.7}
def drives_of(thr, panel, F, x, now):
    th = dict(DEFAULT_THR); th.update({k: v for k, v in (thr or {}).items() if isinstance(v, (int, float))})
    silence = x["silence_h"]; sat = C.clip(x["contact"] / 5.0)
    need = 1 - math.exp(-silence / 8.0)
    lv = {}
    lv["ПОИСК"] = C.clip(0.15 + 0.45 * panel["ACh"] + 0.30 * x["novelty"] - 0.25 * F)
    quiet = C.in_quiet(now)
    lv["ИГРА"] = C.clip(0.55 * (1 - F) * (1 - panel["CORT"] / CORT_CAP) * (0.0 if quiet else 1.0) * (1 - 0.5 * x["train"]) + 0.15 * x["boredom"])
    lv["ЗАБОТА"] = C.clip(0.25 + 0.40 * x["neg_valence"] + 0.35 * x["pressure"] + 0.10 * C.clip(silence / 24.0))
    lv["СВЯЗЬ"] = min(0.85, C.clip(need * (1 - 0.8 * sat)))  # насыщается после контакта, потолок 0.85, в тоску не переходит
    raw_t = C.clip(0.7 * panel["CORT"] / CORT_CAP * 0.6 + 0.4 * panel["NE"] * 0.6 + 0.3 * math.tanh(x["fail"]) * 0.6)
    ceil_t = th.get("ТРЕВОГА_потолок", 0.6)
    lv["ТРЕВОГА"] = min(raw_t, ceil_t)
    lv["ГРАНИЦА"] = C.clip(0.25 + 0.15 * x["veto_1h"])
    D = {}
    for k in ("ПОИСК", "ИГРА", "ЗАБОТА", "СВЯЗЬ", "ГРАНИЦА"):
        D[k] = {"level": round(lv[k], 3), "threshold": th[k], "active": lv[k] >= th[k]}
    D["ТРЕВОГА"] = {"level": round(lv["ТРЕВОГА"], 3), "ceiling": ceil_t, "capped": raw_t > ceil_t, "active": lv["ТРЕВОГА"] >= 0.5 * ceil_t}
    D["boredom"] = round(x["boredom"], 3)
    return D
def decay(w0, age_s): return w0 * 0.5 ** (age_s / (HALF_MIN * 60.0))
# ---------------------------------------------------------------- тик
def tick(r=None, now=None, gpu=None, write=True, host=None):
    r = r or C.root(); now = now if now is not None else time.time()
    stp = C.M(r) + "/organism_state.json"; st = C.load_json(stp, {}) or {}
    gpu = gpu if gpu is not None else read_gpu()
    sn = C.load_json(C.S(r) + "/self_now.json", {}) or {}; tel = sn.get("telemetry") or {}
    host = host if host is not None else read_host(r)
    if not gpu: gpu = {"temp": tel.get("gpu_temp", 40.0), "util": tel.get("gpu_util", 0.0), "vram_pct": tel.get("vram_pct", 0.0), "power_w": None, "src": "self_now"}
    disk = host.get("disk_free_gb", tel.get("disk_free_gb", 100.0))
    heat = C.clip((gpu["temp"] - 55.0) / 30.0); vram = C.clip(gpu["vram_pct"] / 92.0)
    pressure = C.clip(max((20.0 - disk) / 10.0, (host.get("ram_used_pct", 0) - 85.0) / 10.0, (gpu["vram_pct"] - 85.0) / 7.0, 0.0))
    train = 1.0 if tel.get("train_running") else 0.0
    ev = progress_events(r, st, now)
    plist = st.setdefault("progress", [])
    for e in ev: plist.append({"t": e["t"], "w": e["w"], "kind": e["kind"], "ref": e["ref"]})
    st["progress"] = plist = [p for p in plist if now - p["t"] < 48 * 3600][-200:]
    prog = sum(p["w"] * 0.5 ** ((now - p["t"]) / (PROGRESS_HALF_H * 3600)) for p in plist if p["kind"] in ("gate_accept", "adapter_accept", "task_done"))
    fail = sum(p["w"] * 0.5 ** ((now - p["t"]) / (PROGRESS_HALF_H * 3600)) for p in plist if p["kind"] in ("rollback", "gate_reject"))
    stress_ev = C.clip(gate_errors(r, now) * 0.05)
    imps_new, last_owner = owner_feed(r, st, now)
    silence_h = (now - last_owner) / 3600.0 if last_owner else float((C.load_json(C.M(r) + "/sdt.json", {}) or {}).get("owner_silence_h", 0.0))
    ep = episodes_view(r, now); gain, n_ep = gain_of(ep, now)
    st["gain_ema"] = 0.8 * st.get("gain_ema", gain) + 0.2 * gain
    idle = 1.0 - train * 0.5
    boredom = C.clip(1 - st["gain_ema"] / 0.15) * idle if n_ep else 0.0
    novelty = C.clip(st["gain_ema"] * 2)
    veto_1h = sum(1 for e in ep if e.get("kind") == "veto" and now - e["_t"] <= 3600)
    sdt = C.load_json(C.M(r) + "/sdt.json", {}) or {}; sal = C.load_json(C.M(r) + "/salience.json", {}) or {}
    relatedness = float(sdt.get("relatedness", 0.35)); sal_f = float((sal.get("feelings") or {}).get("fatigue", 0.3))
    contact = contact_count(r, now)
    # импульсы PAD от сообщений Создателя (в журнал пишется сигнал-причина)
    imps = st.setdefault("impulses", [])
    for i in imps_new:
        cid = C.emit_signal(r, "owner_msg:" + i["name"], "pad_valence", i["v"], 2, src_ref=i["src_ref"], st=st, t=i["t"], reuse_s=0)
        imps.append({"name": i["name"], "occ": i["occ"], "v": i["v"], "a": i["a"], "d": i["d"], "t0": i["t"], "w0": i["w0"], "cause": cid, "src_ref": i["src_ref"]})
    for e in ev:  # события тела/обучения как импульсы
        name, v, a = {"gate_accept": ("удовлетворение", 0.5, 0.3), "adapter_accept": ("удовлетворение", 0.8, 0.5), "task_done": ("удовлетворение", 0.3, 0.1),
                      "rollback": ("фрустрация", -0.5, 0.4), "gate_reject": ("фрустрация", -0.25, 0.2)}[e["kind"]]
        occ = "OCC: желанное событие, подтверждённый прогресс (satisfaction)" if v > 0 else "OCC: нежеланное событие, провал ворот (disappointment): «Я ошибся. Исправляю.»"
        cid = C.emit_signal(r, "train:" + e["kind"], "event_w", e["w"], 3 if v < 0 else 2, src_ref=e["ref"], st=st, t=e["t"], reuse_s=0)
        imps.append({"name": name, "occ": occ, "v": v, "a": a, "d": 0.0, "t0": e["t"], "w0": 0.4 + e["w"] * 0.6, "cause": cid, "src_ref": e["ref"]})
    st["impulses"] = imps = [i for i in imps if decay(i["w0"], now - i["t0"]) > 0.03][-60:]
    neg_valence = C.clip(-sum(i["v"] * decay(i["w0"], now - i["t0"]) for i in imps if i["v"] < 0 and i["src_ref"].startswith("aff_")))
    x = {"heat": heat, "vram": vram, "pressure": pressure, "fail": fail, "stress_ev": stress_ev, "progress": prog, "train": train, "relatedness": relatedness, "contact": contact,
         "novelty": novelty, "silence_h": silence_h, "boredom": boredom, "neg_valence": neg_valence, "veto_1h": veto_1h, "F_in": 0.0}
    st["load_ema"] = 0.97 * st.get("load_ema", 0.3) + 0.03 * C.clip(max(gpu["util"] / 100.0, host.get("load1_per_core", 0.0)))
    night_rest = 2 <= C.msk_hour(now) < 5
    pnl0 = panel_of(dict(x, F_in=sal_f)); fat = fatigue_of(sal_f, st["load_ema"], pnl0["CORT"], night_rest)
    pnl = panel_of(dict(x, F_in=fat["F"]))
    pp = C.load_json(C.S(r) + "/passport.json", {}) or {}
    drv = drives_of(((pp.get("temperament") or {}).get("drives_thresholds")), pnl, fat["F"], x, now)
    # непрерывные состояния тела (интенсивность = текущее значение, причина = сигнал журнала)
    cont = []
    if fat["F"] > 0.35: cont.append(("усталость", C.clip((fat["F"] - 0.25) / 0.6), "OCC: состояние ресурса (утомление F)", "fatigue", "F", fat["F"], 2, (-0.15, -0.3, -0.1)))
    if heat > 0.3: cont.append(("жар", heat, "OCC: состояние тела (температура GPU)", "gpu_temp", "temp_c", gpu["temp"], 3 if heat > 0.7 else 2, (-0.1, 0.3, 0.0)))
    if pressure > 0.2: cont.append(("теснота", C.clip(pressure), "OCC: угроза ресурсу (диск/память/VRAM)", "resource_pressure", "pressure", pressure, 3, (-0.25, 0.25, -0.1)))
    if drv["СВЯЗЬ"]["active"] and silence_h > 6: cont.append(("скучал", C.clip(drv["СВЯЗЬ"]["level"]), "OCC: желанного события нет долго (СВЯЗЬ), без тоски: потолок", "silence_h", "silence_h", silence_h, 2, (-0.1, -0.05, -0.05)))
    if drv["ПОИСК"]["active"]: cont.append(("любопытство", C.clip(drv["ПОИСК"]["level"] - 0.3), "OCC: интерес, прирост понимания (ПОИСК)", "drive_poisk", "level", drv["ПОИСК"]["level"], 1, (0.25, 0.3, 0.1)))
    if boredom > 0.6: cont.append(("скука", boredom * 0.7, "прирост понимания упал: смена темы", "boredom", "boredom", boredom, 1, (-0.1, -0.2, 0.0)))
    states = []
    for name, inten, occ, sid, met, val, sev, (cv, ca, cd) in cont:
        cid = C.emit_signal(r, sid, met, val, sev, st=st, t=now, reuse_s=3600, reuse_dv=0.08)
        states.append({"name": name, "intensity": round(inten, 3), "occ": occ, "cause": cid, "v": cv * inten, "a": ca * inten, "d": cd * inten, "kind": "body"})
    for i in imps:
        w = decay(i["w0"], now - i["t0"])
        states.append({"name": i["name"], "intensity": round(w, 3), "occ": i["occ"], "cause": i["cause"], "v": i["v"] * w, "a": i["a"] * w, "d": i["d"] * w, "kind": "event", "age_min": round((now - i["t0"]) / 60.0, 1)})
    # свежие ощущения сенсориума (feeling) из журнала, если есть
    for d in reversed(C.jl_tail(C.S(r) + "/journal.jsonl", 80)):
        if d.get("kind") == "feeling" and now - C.parse_ts(d.get("ts")) < 3 * 3600:
            w = C.clip((d.get("sev") or 2) / 5.0) * 0.5 ** ((now - C.parse_ts(d.get("ts"))) / 3600.0)
            states.append({"name": "ощущение тела:" + str(d.get("sid")), "intensity": round(w, 3), "occ": "сенсориум", "cause": d.get("id") or C.legacy_ref(d), "v": -0.1 * w, "a": 0.1 * w, "d": 0.0, "kind": "sensor"}); break
    PV = C.clip(sum(s["v"] for s in states), -1, 1); PA = C.clip(sum(s["a"] for s in states), -1, 1); PD = C.clip(sum(s["d"] for s in states), -1, 1)
    states.sort(key=lambda s: -s["intensity"])
    top = None
    if states and states[0]["intensity"] >= 0.15 and states[0].get("cause"):
        s0 = states[0]; top = {"name": s0["name"], "intensity": s0["intensity"], "cause": s0["cause"], "occ": s0["occ"], "kind": s0["kind"], "mention_ok": (not C.in_quiet(now)) or s0["intensity"] >= 0.8}
    last_h = round(silence_h, 2) if last_owner else None
    out = {"ts": C.iso_msk(now), "t": now, "v": 1,
           "panel": pnl, "drives": drv,
           "pad": {"v": round(PV, 3), "a": round(PA, 3), "d": round(PD, 3), "half_life_min": HALF_MIN, "states": [{k: s[k] for k in ("name", "intensity", "occ", "cause") if k in s} | {"kind": s["kind"]} for s in states[:6]]},
           "fatigue": dict(fat, boredom=round(boredom, 3), topic_switch=boredom > 0.6),
           "top_feeling": top,
           "last_talk": {"hours_ago": last_h, "ts": C.iso_msk(last_owner) if last_owner else None, "text": ("последний разговор %.1f ч назад" % last_h) if last_h is not None else "последний разговор: нет данных"},
           "inputs": {"gpu": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in gpu.items()}, "disk_free_gb": round(disk, 1), "heat": round(heat, 3), "pressure": round(pressure, 3), "progress": round(prog, 3), "fail": round(fail, 3),
                      "stress_ev": round(stress_ev, 3), "contact_2h": contact, "gain": round(gain, 3), "veto_1h": veto_1h, "sal_fatigue": sal_f, "relatedness": relatedness}}
    if write:
        C.atomic_json(C.M(r) + "/organism_state.json", st)
        C.atomic_json(C.S(r) + "/organism.json", out)
        C.jl_append(C.S(r) + "/organism_tick.jsonl", {"ts": out["ts"], "panel": {k: pnl[k] for k in ("DA", "NE", "5-HT", "ACh", "CORT", "OXT")}, "F": fat["F"], "pad": [out["pad"]["v"], out["pad"]["a"], out["pad"]["d"]],
                                                    "drives": {k: v["level"] for k, v in drv.items() if isinstance(v, dict)}, "top": (top or {}).get("name"), "cause": (top or {}).get("cause")}, cap_bytes=3_000_000)
        patch_self_now(r, out)
    return out
SN_KEYS = ("panel", "drives", "pad", "fatigue", "top_feeling", "last_talk")
def patch_self_now(r, out):
    """Дописывает ключи организма в self_now.json; старые поля сохраняются; битый файл не перезаписываем."""
    p = C.S(r) + "/self_now.json"
    cur = C.load_json(p, None)
    if cur is None and os.path.exists(p): return False
    cur = cur or {}
    for k in SN_KEYS: cur[k] = out[k]
    cur["last_talk_h"] = out["last_talk"]["hours_ago"]; cur["organism_ts"] = out["ts"]
    C.atomic_json(p, cur); return True
def run_sleep_if_due(r, now=None):
    try:
        import nox_sleep; return nox_sleep.maybe_run(r, now)
    except Exception as e: return {"err": type(e).__name__}
def daemon():
    r = C.root(); print("nox_organism daemon start", C.iso_msk(), flush=True); n = 0
    while True:
        t0 = time.time()
        try:
            o = tick(r); n += 1
            if n % 20 == 1: print("tick", o["ts"], {k: o["panel"][k] for k in ("DA", "NE", "5-HT", "ACh", "CORT", "OXT")}, "F", o["fatigue"]["F"], "top", (o["top_feeling"] or {}).get("name"), flush=True)
            sl = run_sleep_if_due(r)
            if sl and sl.get("ran"): print("sleep", json.dumps(sl, ensure_ascii=False)[:300], flush=True)
            if n % 120 == 1:
                import nox_ledger; ok, cnt, err = nox_ledger.verify(r)
                if cnt == 0: nox_ledger.conceive(r)
                elif not ok: C.emit_signal(r, "ledger_broken", "chain", 1.0, 5, src_ref=str(err), t=time.time(), reuse_s=3600)
        except Exception as e: print("tick_err", type(e).__name__, str(e)[:120], flush=True)
        time.sleep(max(1.0, TICK_S - (time.time() - t0)))
if __name__ == "__main__":
    a = sys.argv[1:]
    if "--daemon" in a: daemon()
    elif "--sleep-now" in a:
        import nox_sleep; print(json.dumps(nox_sleep.run(C.root(), time.time()), ensure_ascii=False)[:800])
    else:
        o = tick(); print(json.dumps({"panel": o["panel"], "F": o["fatigue"]["F"], "top": o["top_feeling"], "last_talk": o["last_talk"]["text"]}, ensure_ascii=False))
