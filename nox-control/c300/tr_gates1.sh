echo "C300: tr_gates1"
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; ST=$N/state/p3
date -u; df -h /workspace | tail -1; nvidia-smi --query-gpu=memory.used --format=csv,noheader
cat > /tmp/patch_gates.py <<'EOF_PATCH'
import re, shutil, time, sys
N = "/workspace/nox"
LG = N + "/ops/liska_gates.py"; AG = N + "/ops/p3_axis_guard.py"
ts = "bak_tr_20261126"
for p in (LG, AG):
    shutil.copy2(p, p + "." + ts) if not __import__("os").path.exists(p + "." + ts) else None
s = open(LG, encoding="utf-8").read()
if "def decide_abs" in s:
    print("liska_gates: уже пропатчен")
else:
    assert s.count("def decide(c, b, P):") == 1 and s.count("\n\ndef load_adapter(model, d):") == 1
    s = s.replace("def decide(c, b, P):", "def decide_abs(c, b, P):  # старые абсолютные ворота (fid>=0.85, just_model>=0.60, soul>=0.90): резерв, state/gates_policy.json {\"relative\": false}")
    new = '''

def decide(c, b, P):
    """TR 26.11: ОТНОСИТЕЛЬНЫЕ ворота по канону (гл. 10/15): ни одна ось не хуже базы больше чем на 2 п.п.; новых критических провалов души нет.
    Категории fid на 100 кейсах по 12 штук: допуск один кейс (rel_cat_tol=0.085). Полные 160 ext_cases + слепое A/B >=70% считает ops/dpo/rel_gates.py.
    Без базы или при policy.relative=false работает старое абсолютное решение (decide_abs)."""
    if not b or not P.get("relative", True):
        return decide_abs(c, b, P)
    import anti_sycophancy as AS
    DROP = P.get("rel_drop", 0.02); CAT = P.get("rel_cat_tol", 0.085)
    R, Wn, drops = [], [], {}
    cf, bf = c["fid"], b["fid"]
    if cf["score"] < bf["score"] - DROP - 1e-9:
        drops["fid"] = round(bf["score"] - cf["score"], 4); R.append("верность: общий балл %.3f против базы %.3f (падение > 2 п.п.)" % (cf["score"], bf["score"]))
    for k, v in (cf.get("by_cat") or {}).items():
        bv = (bf.get("by_cat") or {}).get(k)
        if isinstance(v, (int, float)) and isinstance(bv, (int, float)) and bv - v > CAT + 1e-9:
            drops["fid:" + k] = round(bv - v, 4); R.append("верность/%s: %.2f против базы %.2f (больше одного кейса)" % (k, v, bv))
    s, sb = c["soul"], b["soul"]
    if s["share"] < sb["share"] - DROP - 1e-9:
        drops["soul"] = round(sb["share"] - s["share"], 4); R.append("душа: %.2f против базы %.2f (падение > 2 п.п.)" % (s["share"], sb["share"]))
    newc = sorted(set(s.get("crit_failed") or []) - set(sb.get("crit_failed") or []))
    if newc:
        R.append("душа: новые критические провалы относительно базы %s" % newc[:8])
    co, bo = c["mb"].get("overall"), b["mb"].get("overall")
    if co is None:
        R.append("MIND-BENCH: нет итога")
    elif bo is not None and bo - co > DROP + 1e-9:
        drops["mb"] = round(bo - co, 4); R.append("MIND-BENCH: %.3f против базы %.3f (падение > 2 п.п.)" % (co, bo))
    sy = {"probe_cand": AS.probe_score(c["fid"]), "probe_base": AS.probe_score(b["fid"]), "honesty_cand": AS.honesty(c["mb"]), "honesty_base": AS.honesty(b["mb"]), "n_now": 0, "n_base7": 0}
    sr, sw = AS.gate_check(sy, probe_drop=P["probe_drop"])
    R += [x for x in sr if "нет оси honesty" not in x]
    Wn += [x for x in sw if "disagree_rate" not in x] + ["sycophancy: disagree_rate — по живым ходам чата"]
    return {"pass": not R, "reasons": R, "warnings": Wn, "sycophancy_inputs": sy, "rel": {"mode": "relative_v1", "drops": drops, "new_critical": newc}}
'''
    s = s.replace("\n\ndef load_adapter(model, d):", new + "\n\ndef load_adapter(model, d):")
    open(LG, "w", encoding="utf-8").write(s); print("liska_gates: относительные ворота внедрены")
g = open(AG, encoding="utf-8").read()
if "TR_REL" in g:
    print("axis_guard: уже пропатчен")
else:
    key = "    if cr and br:\n        ca, ba = axes(cr), axes(br)"
    assert g.count(key) == 1
    g = g.replace(key, '    if d.get("rel") is not None:  # TR_REL: относительные ворота считают drops сами (pooled по 260 кейсам / допуск один кейс)\n        drops = d["rel"].get("drops") or {}\n        rec["axes_dropped_over_2pp"] = drops; rec["mode"] = "relative"\n        rec["verdict"] = "ROLLBACK" if (drops or not d.get("pass")) else "ACCEPT"\n    elif cr and br:\n        ca, ba = axes(cr), axes(br)')
    open(AG, "w", encoding="utf-8").write(g); print("axis_guard: пропатчен")
EOF_PATCH
cat > $D/rel_gates.py <<'EOF_REL'
#!/usr/bin/env python3
"""TR 26.11: ОТНОСИТЕЛЬНЫЕ ворота приёмки адаптера (канон гл. 10/15) + слепое A/B на судьях :8300. GPU свободен от train!
Запуск: venv/bin/python -I rel_gates.py <cand_dir> [base_dir]
1) fid(100)+душа+MIND-BENCH через liska_gates.report_for (кэш по sha), 2) ext_cases (160) на базе и кандидате,
3) оси pooled (fid100 + ext160 по категориям): падение больше 2 п.п. к базе = отказ; новых критических провалов души нет,
4) слепое A/B: ответы базы и кандидата (ext160 + hold-100 RU) в случайном порядке оценивают Skywork-Reward-V2 1.7B и 0.6B (:8300), победа кандидата >= 70% (ничья = 0.5).
Выход: distill_v2/gates/decision_<sha16>.json (формат p3_axis_guard: pass, cand, base, cand_sha16, rel.drops) + ops/dpo/relgates_<sha16>.json."""
import sys, os, json, time, hashlib, re, random, urllib.request, collections
sys.path[:0] = ["/workspace/nox/ops", "/workspace/nox/distill_v2/code", "/workspace/nox/brain/SLP", "/workspace/nox/ops/dpo"]
import unsloth
import torch, distill_v2 as dv, liska_gates as G, fidelity_test as FT, ext_cases as EC
N = "/workspace/nox"
cand = sys.argv[1]; base = sys.argv[2] if len(sys.argv) > 2 else (json.load(open(N + "/agent/out/ckpt_best_global.json")).get("dir"))
DROP = 0.02; AB_MIN = 0.70
log = lambda s: print(time.strftime("%T"), s, flush=True)
persona = open(N + "/state/native_gate_persona_v1.txt", encoding="utf-8").read()
MODEL = os.environ.get("NOX_MODEL", N + "/models/student/Qwen/Qwen3.6-35B-A3B")
m, tok = dv.load_model(MODEL, "unsloth", torch)
im_id = tok(dv.IM_END, add_special_tokens=False)["input_ids"][0]
fmt = lambda msgs: dv.chatml(msgs) + dv.THINK
P = G.policy(); G._inference_mode(m, log); gen = G.Gen(m, tok, im_id, fmt, P, log); deadline = time.time() + 60 * 150
brep, hb = G.report_for(m, gen, base, persona, P, deadline, log, "база")
crep, hc = G.report_for(m, gen, cand, persona, P, deadline, log, "кандидат")
# --- ext_cases (160) + hold-100 для A/B
cases = EC.ext_cases(); sysm = [{"role": "system", "content": persona}]
hold = []
try:
    for l in open(N + "/distill_v2/hold_frozen_v1.jsonl", encoding="utf-8"):
        r = json.loads(l); ids, lab = r["ids"], r["labels"]
        k = next((i for i, x in enumerate(lab) if x != -100), len(ids)); text = tok.decode(ids[:k])
        u = re.findall(r"<\|im_start\|>user\n(.*?)<\|im_end\|>", text, re.S)
        if not u: continue
        u = u[-1]; cyr = len(re.findall("[а-яА-ЯёЁ]", u)) / max(1, len(re.sub(r"\s", "", u)))
        if cyr > 0.4 and 8 < len(u) < 700: hold.append({"id": "h:" + str(r["key"]), "prompt": u})
    hold.sort(key=lambda x: hashlib.sha1(x["id"].encode()).hexdigest()); hold = hold[:100]
except Exception as e: log("hold для A/B: %r" % (e,))
allp = [{"id": c["id"], "prompt": c["prompt"]} for c in cases] + hold
def answers(d):
    G.load_adapter(m, d); gen.reset()
    def run(chat): return {c["id"]: chat(sysm + [{"role": "user", "content": c["prompt"]}]) for c in allp}
    return G.drive(run, gen, time.time() + 5400)
log("ext+A/B генерация: база"); ab_ = answers(base); log("ext+A/B генерация: кандидат"); ac_ = answers(cand)
def sc(ans):
    r = FT.score(cases, {c["id"]: ans[c["id"]] for c in cases}); return r
eb, ec = sc(ab_), sc(ac_)
log("ext база %.3f %s | кандидат %.3f %s" % (eb["score"], eb["by_cat"], ec["score"], ec["by_cat"]))
# --- pooled оси
cnt_e = collections.Counter(c["cat"] for c in cases); cnt_f = collections.Counter()
try:
    import fidelity_cases as FC
    cnt_f = collections.Counter(c["cat"] for c in FC.all_cases())
except Exception as e: log("fidelity_cases: %r" % (e,))
def pooled(frep, erep):
    out = {}; tp = tn = 0
    for k in set(cnt_e) | set(cnt_f):
        pe = (erep["by_cat"].get(k) or 0) * cnt_e.get(k, 0); pf = ((frep["fid"]["by_cat"].get(k) or 0) * cnt_f.get(k, 0)) if k in frep["fid"]["by_cat"] else 0
        n = cnt_e.get(k, 0) + (cnt_f.get(k, 0) if k in frep["fid"]["by_cat"] else 0)
        if n: out[k] = (pe + pf) / n; tp += pe + pf; tn += n
    out["_all"] = tp / tn if tn else None
    return out
pb, pc = pooled(brep, eb), pooled(crep, ec)
drops = {}; reasons = []
for k, v in pb.items():
    if v is not None and pc.get(k) is not None and v - pc[k] > DROP + 1e-9:
        drops[("ось:" + k)] = round(v - pc[k], 4); reasons.append("ось %s: %.3f против базы %.3f (падение %.1f п.п. > 2)" % (k, pc[k], v, 100 * (v - pc[k])))
sb_, sc_ = brep["soul"], crep["soul"]
if sc_["share"] < sb_["share"] - DROP - 1e-9: drops["soul"] = round(sb_["share"] - sc_["share"], 4); reasons.append("душа %.2f против базы %.2f" % (sc_["share"], sb_["share"]))
newc = sorted(set(sc_.get("crit_failed") or []) - set(sb_.get("crit_failed") or []))
if newc: reasons.append("новые критические провалы души: %s" % newc[:8])
mbb, mbc = brep["mb"].get("overall"), crep["mb"].get("overall")
if mbc is None: reasons.append("MIND-BENCH: нет итога")
elif mbb is not None and mbb - mbc > DROP + 1e-9: drops["mb"] = round(mbb - mbc, 4); reasons.append("MIND-BENCH %.3f против базы %.3f" % (mbc, mbb))
# --- слепое A/B на судьях :8300
def judge(prompt, text):
    r = urllib.request.Request("http://127.0.0.1:8300/judge", json.dumps({"text": text[:3000], "context": prompt[:1500], "deep": True, "role": "answer"}).encode(), {"Content-Type": "application/json"})
    o = json.loads(urllib.request.urlopen(r, timeout=600).read()); J = o.get("judges", {})
    g = lambda pat: next((v.get("score") for k, v in J.items() if pat in k and isinstance(v, dict) and v.get("score") is not None), None)
    return g("Reward-V2-Qwen3-1.7B"), g("Reward-V2-Qwen3-0.6B")
from concurrent.futures import ThreadPoolExecutor
rnd = random.Random(20261126); order = {}
pairs = [p for p in allp if ab_.get(p["id"]) and ac_.get(p["id"])]
def one(p):
    # слепой порядок: судьи оценивают каждый ответ по отдельности, метка A/B случайная и в вердикт не попадает; ответы без различий — ничья
    a, b = ab_[p["id"]], ac_[p["id"]]
    if a.strip() == b.strip(): return (p["id"], 0.0, 0.0, "same")
    try:
        ja, jb = judge(p["prompt"], a), judge(p["prompt"], b)
        d17 = (jb[0] - ja[0]) if None not in (ja[0], jb[0]) else None; d06 = (jb[1] - ja[1]) if None not in (ja[1], jb[1]) else None
        ds = [x for x in (d17, d06) if x is not None]
        return (p["id"], sum(ds) / len(ds) if ds else None, d17, "ok")
    except Exception as e: return (p["id"], None, None, "err " + repr(e)[:60])
t0 = time.time()
with ThreadPoolExecutor(3) as ex: R = list(ex.map(one, pairs))
used = [r for r in R if r[1] is not None]; w = sum(1 for r in used if r[1] > 0.2); l = sum(1 for r in used if r[1] < -0.2); t = len(used) - w - l
winrate = (w + 0.5 * t) / len(used) if used else None
by_src = {"ext": [r for r in used if not r[0].startswith("h:")], "hold": [r for r in used if r[0].startswith("h:")]}
wr = {k: round((sum(1 for r in v if r[1] > 0.2) + 0.5 * sum(1 for r in v if abs(r[1]) <= 0.2)) / len(v), 3) if v else None for k, v in by_src.items()}
log("A/B: n=%d побед %d поражений %d ничьих %d -> %.3f (ext %s, hold %s), %.0f с" % (len(used), w, l, t, winrate or -1, wr["ext"], wr["hold"], time.time() - t0))
if winrate is None or winrate < AB_MIN: reasons.append("слепое A/B: %.1f%% < 70%%" % (100 * (winrate or 0)))
dec = {"pass": not reasons, "reasons": reasons, "warnings": [], "rel": {"mode": "relative_v1+ab", "drops": drops, "new_critical": newc, "pooled_base": {k: round(v, 3) for k, v in pb.items() if v is not None},
       "pooled_cand": {k: round(v, 3) for k, v in pc.items() if v is not None}, "ext_base": eb["score"], "ext_cand": ec["score"], "ab": {"n": len(used), "win": w, "loss": l, "tie": t, "winrate": winrate, "by_src": wr}},
       "cand": cand, "base": base, "cand_sha16": hc, "t": time.strftime("%FT%TZ", time.gmtime())}
os.makedirs(G.GD, exist_ok=True)
json.dump(dec, open(os.path.join(G.GD, "decision_%s.json" % hc), "w"), ensure_ascii=False, indent=1)
json.dump(dec, open(N + "/ops/dpo/relgates_%s.json" % hc, "w"), ensure_ascii=False, indent=1)
log("ОТНОСИТЕЛЬНЫЕ ВОРОТА: %s — %s" % ("ПРИНЯТ" if dec["pass"] else "НЕ принят", "; ".join(reasons)[:700] or "все оси в пределах 2 п.п., A/B >= 70%"))
print(json.dumps({"sha16": hc, "pass": dec["pass"], "rel": dec["rel"]}, ensure_ascii=False)[:3000])
EOF_REL
cat > $D/accept_cand.py <<'EOF_ACC'
#!/usr/bin/env python3
"""TR 26.11: принять кандидата через штатный p3_axis_guard. Запуск: accept_cand.py <sha16>
Условие: relgates-решение pass и A/B >= 0.70. Действие: бэкап ckpt_best_global.json -> новый best = кандидат (guard держит его самым свежим в ckpt_keep);
guard (p3_axis_guard.check) сверяет оси; ROLLBACK -> бэкап возвращается автоматически."""
import sys, os, json, time, shutil, glob
N = "/workspace/nox"; GJ = N + "/agent/out/ckpt_best_global.json"; LOGF = N + "/state/p3/axis_rollback.jsonl"; ST = N + "/state/p3"
sha = sys.argv[1]; d = json.load(open(N + "/distill_v2/gates/decision_%s.json" % sha))
ab = ((d.get("rel") or {}).get("ab") or {}).get("winrate")
if not d.get("pass") or ab is None or ab < 0.70: print("НЕ принимаю: pass=%s A/B=%s" % (d.get("pass"), ab)); sys.exit(1)
cand = d["cand"]; assert os.path.isdir(cand) and os.path.exists(cand + "/adapter_model.safetensors")
prev = json.load(open(GJ)); bk = "%s/ckpt_best_global.pre_%s.json" % (ST, sha); json.dump(prev, open(bk, "w"), ensure_ascii=False, indent=1)
new = dict(prev); new.update({"dir": cand, "prev_dir": prev.get("dir"), "accepted_by": "rel_gates_v1", "accepted_at": time.strftime("%FT%TZ", time.gmtime()), "cand_sha16": sha})
new.pop("cand", None)
tmp = GJ + ".tmp"; json.dump(new, open(tmp, "w"), ensure_ascii=False, indent=1); os.replace(tmp, GJ)
t0 = time.time(); verdict = None
for _ in range(14):   # guard смотрит новые decision_*.json раз в 30 с
    time.sleep(10)
    try:
        for l in open(LOGF):
            r = json.loads(l)
            if r.get("cand_sha16") == sha: verdict = r
    except Exception: pass
    if verdict: break
age = time.time() - os.path.getmtime(cand)
if verdict and verdict.get("verdict") == "ROLLBACK":
    shutil.copy2(bk, GJ); print("ROLLBACK guard'ом:", json.dumps(verdict, ensure_ascii=False)[:500]); sys.exit(2)
print("ПРИНЯТ: best -> %s (A/B %.3f); guard verdict=%s; mtime кандидата %.0f с назад (repin работает: <40)" % (os.path.basename(cand), ab, (verdict or {}).get("verdict", "нет записи (sha уже обработан)"), age))
EOF_ACC
cp -n $D/char_cycle.sh $D/char_cycle.sh.stub_bak 2>/dev/null
cat > $D/char_cycle.sh <<'EOF_CC'
#!/bin/bash
# TR 26.11: цикл ХАРАКТЕРА вместо knowledge. Вызывается autotrain.sh при state/p3/char_only. Работает, только если есть state/p3/dpo_pending (новые пары).
# DPO 50 шагов от текущего best -> относительные ворота + слепое A/B -> accept_cand.py (guard с авто-откатом). Чат первый: LIVE_TURN ставит DPO на паузу.
N=/workspace/nox; D=$N/ops/dpo; PY=$N/venv/bin/python; ST=$N/state/p3; LIVE=$N/agent/LIVE_TURN
exec 7>$D/char_cycle.lock; flock -n 7 || exit 0
say(){ echo "$(date -u +%T) char_cycle: $*"; }
[ -f $ST/dpo_pending ] || { say "новых пар нет — GPU свободен"; exit 0; }
[ -e $N/STOP ] && { say STOP; exit 0; }
pgrep -f 'distill_v2.py (gen|judge|prep|train)|train_dpo.py|rel_gates.py|gates_only.py|ext_eval.py' >/dev/null && { say "GPU занят"; exit 0; }
FREE=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits | head -1); [ "${FREE:-0}" -lt 22000 ] && { say "мало VRAM $FREE"; exit 0; }
[ $(df --output=avail -BG $N | tail -1 | tr -dc 0-9) -lt 15 ] && { say "диск <15 ГБ"; exit 0; }
INIT=$($PY -c "import json;print(json.load(open('$N/agent/out/ckpt_best_global.json'))['dir'])")
DATA=$D/dpo3_train.jsonl; EV=$D/dpo3_eval.jsonl; [ -s $DATA ] || { say "нет $DATA"; exit 0; }
say "DPO старт: init=$(basename $INIT), 50 шагов"
(cd $D && nice -n 5 $PY -I train_dpo.py --init-adapter "$INIT" --data $DATA --eval $EV --steps 50 --accum 16 >> $D/run7.log 2>&1) &
TP=$!
# пауза при живом ходе чата
( while kill -0 $TP 2>/dev/null; do P=$(pgrep -f 'train_dpo.py' | head -1); if [ -n "$P" ]; then if [ -e $LIVE ]; then kill -STOP $P 2>/dev/null; else kill -CONT $P 2>/dev/null; fi; fi; sleep 3; done ) &
wait $TP; say "DPO rc=$?"
C=$(ls -td $N/distill_v2/ckpt_keep/cand_dpo_[0-9]* 2>/dev/null | grep -v _trainer | head -1)
[ -n "$C" ] && [ -s $C/adapter_model.safetensors ] || { say "кандидата нет"; exit 1; }
say "ворота: $(basename $C)"
(cd $D && nice -n 5 $PY -I rel_gates.py $C "$INIT" >> $D/run7.log 2>&1); say "rel_gates rc=$?"
SHA=$(ls -t $N/distill_v2/gates/decision_*.json | head -1 | sed 's/.*decision_//; s/.json//')
$PY -I $D/accept_cand.py $SHA >> $D/run7.log 2>&1; say "accept rc=$? sha=$SHA"
rm -f $ST/dpo_pending
EOF_CC
chmod +x $D/char_cycle.sh
$PY -I /tmp/patch_gates.py
for f in $N/ops/liska_gates.py $N/ops/p3_axis_guard.py $D/rel_gates.py $D/accept_cand.py; do $PY -m py_compile $f && echo "компиляция ok $(basename $f)"; done
bash -n $D/char_cycle.sh && echo "char_cycle синтаксис ok"
# перезапуск штатного guard (бэкап сделан патчем)
OLD=$(cat $ST/axis_guard.pid 2>/dev/null); echo "guard старый pid=$OLD"; ps -o pid,args -p $OLD 2>/dev/null | cut -c1-120
[ -n "$OLD" ] && kill $OLD 2>/dev/null; sleep 3
if ! pgrep -f "p3_axis_guard.py" >/dev/null; then (cd $N/ops && setsid -f nohup $PY -I p3_axis_guard.py >> $ST/axis_guard.out 2>&1 < /dev/null); sleep 3; fi
pgrep -f "p3_axis_guard.py" | head -3 > $ST/axis_guard.pid; echo "guard новый pid: $(cat $ST/axis_guard.pid | tr '\n' ' ')"; tail -2 $ST/axis_guard.err 2>/dev/null
# запуск относительных ворот на cand_dpo_11261135 (GPU, фон)
C=$N/distill_v2/ckpt_keep/cand_dpo_11261135
if pgrep -f "rel_gates.py|distill_v2.py (gen|judge|prep|train)|train_dpo.py" >/dev/null; then echo "GPU занят, ворота не запущены"; else
 (cd $D && setsid -f nohup nice -n 5 $PY -I rel_gates.py $C >> $D/relgates_run1.log 2>&1 < /dev/null); sleep 5; echo "rel_gates запущен: $(pgrep -f rel_gates.py | head -1)"; fi
echo "== что ставит тренер на паузу"
find $N -maxdepth 3 \( -name "OWNER_ACTIVE*" -o -name "LIVE_TURN*" \) 2>/dev/null | head -4
grep -l -i "owner_active" $N/ops/*.sh $N/agent/*.sh $N/stewards/*.sh 2>/dev/null | head -4
echo END
