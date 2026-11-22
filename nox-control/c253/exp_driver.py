#!/usr/bin/env python3
# B (SPD этап 2): рычаги GLM по одному с накоплением. Свой драйвер поверх ik_llama (ab_bench стартует llama.cpp на 8091 и не умеет taskset/numactl).
# Запуск: nohup setsid python3 exp_driver.py > /root/nox/logs/B_exp.out 2>&1 &   Итог: /root/nox/logs/B_exp_results.json, GLM_ARGS.best
import json, os, shlex, signal, subprocess, sys, time, urllib.request, difflib, shutil
BIN = "/root/nox/ik_llama/build/bin/llama-server"
MODEL = "/root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf"
PORT = 8081; LOG = "/root/nox/logs"; RC = "/root/nox/receipts"; OUT = LOG + "/B_exp_results.json"
os.makedirs(RC + "/bak_B", exist_ok=True)
def sh(c, t=30):
    return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=t).stdout.strip()
def pids():
    return [int(p) for p in sh("pgrep -f 'llama-server.*--port 8081'").split()]
def topo():
    rows = [l.split(",") for l in sh("lscpu -p=CPU,CORE,SOCKET,NODE").splitlines() if not l.startswith("#")]
    s0, seen = [], set()
    for c, core, sock, node in rows:
        if sock == "0" and core not in seen: seen.add(core); s0.append(int(c))
    return sorted(s0)
S0 = topo(); S0LIST = ",".join(map(str, S0[:24]))
# окружение берём у работающего GLM (LD_LIBRARY_PATH и т.д.)
ENV0 = {}
try:
    p = pids()[0]
    for kv in open("/proc/%d/environ" % p, "rb").read().split(b"\0"):
        if b"=" in kv: k, v = kv.split(b"=", 1); ENV0[k.decode()] = v.decode()
    cur_cmd = open("/proc/%d/cmdline" % p, "rb").read().replace(b"\0", b" ").decode()
    open(RC + "/bak_B/glm_cmdline_before_B.txt", "w").write(cur_cmd)
    shutil.copy("/root/nox/start_glm.sh", RC + "/bak_B/start_glm.sh.orig")
except Exception as e:
    print("env0 fail", e)
for k in ("TMUX", "SSH_CLIENT"): ENV0.pop(k, None)
def get(path, t=5):
    return json.loads(urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=t).read().decode() or "{}")
def post(path, o, t):
    r = urllib.request.Request("http://127.0.0.1:%d%s" % (PORT, path), json.dumps(o).encode(), {"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(r, timeout=t).read().decode())
def stop():
    for p in pids():
        try: os.kill(p, signal.SIGTERM)
        except OSError: pass
    for _ in range(60):
        if not pids(): return
        time.sleep(2)
    for p in pids():
        try: os.kill(p, signal.SIGKILL)
        except OSError: pass
    time.sleep(3)
def start(cfg, tag):
    stop()
    args = " ".join("%s %s" % (k, v) if v != "" else k for k, v in cfg["args"].items())
    cmd = "%s %s -m %s --host 127.0.0.1 --port %d %s" % (cfg["prefix"], BIN, MODEL, PORT, args)
    env = dict(ENV0); env.update(cfg.get("env", {}))
    lf = open("%s/B_glm_%s.log" % (LOG, tag), "wb")
    pr = subprocess.Popen(cmd, shell=True, env=env, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 1500:
        time.sleep(5)
        if not pids() and pr.poll() is not None: return None, "умер при старте rc=%s" % pr.returncode
        try:
            if get("/health").get("status") == "ok": return time.time() - t0, cmd
        except Exception: pass
    return None, "health timeout"
def bench(cfg_id):
    m = {}
    def gen(prompt, n, to=600):
        t0 = time.time(); r = post("/completion", {"prompt": prompt, "n_predict": n, "temperature": 0, "cache_prompt": False}, to); tm = r["timings"]
        return {"pp_n": tm.get("prompt_n"), "pp_s": tm.get("prompt_per_second"), "tg_s": tm.get("predicted_per_second"), "ttft_ms": tm.get("prompt_ms"), "text": r.get("content", ""), "wall": time.time() - t0}
    try:
        gen("Привет", 4)  # прогрев
        sh_ = [gen("Объясни кратко, что такое RAID.", 32) for _ in range(2)]
        m["tg"] = sum(x["tg_s"] for x in sh_) / 2; m["ttft_short_ms"] = sum(x["ttft_ms"] for x in sh_) / 2
        lg = gen("Скорость генерации большой языковой модели на процессоре ограничена пропускной способностью памяти. " * 30 + "\nКратко: о чём текст?", 16)
        m["pp"] = lg["pp_s"]; m["pp_n"] = lg["pp_n"]; m["ttft_long_ms"] = lg["ttft_ms"]
        q = gen("Перечисли по порядку первые двенадцать простых чисел, через запятую, без пояснений.", 40)
        m["q_text"] = q["text"]
    except Exception as e:
        m["error"] = str(e)[:150]
    return m
def sim(a, b): return difflib.SequenceMatcher(None, a, b).ratio()
BASE_ARGS = {"-ngl": "22", "-ot": "exps=CPU", "-c": "16384", "-np": "1", "-fa": "on", "-amb": "512", "--jinja": "", "-t": "22", "-tb": "26", "-b": "2048", "-ub": "512"}
CHAMP = {"prefix": "GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c 0-17", "env": {}, "args": dict(BASE_ARGS)}
def lever(name, f):
    return (name, f)
def L01a(c): c["prefix"] = "nohup"; c["args"].update({"-t": "24", "-tb": "24"}); return c
def L01b(c): c["prefix"] = "nohup taskset -c " + S0LIST; c["args"].update({"-t": "24", "-tb": "24"}); return c
def L01c(c): c["prefix"] = "nohup numactl --interleave=all"; c["args"].update({"-t": "26", "-tb": "26"}); return c
def L02(c): c["args"].update({"-b": "2048", "-ub": "1024"}); return c
def L03(c): c["args"].update({"-b": "4096", "-ub": "2048"}); c["env"]["GGML_OP_OFFLOAD_MIN_BATCH"] = "1024"; return c
def L08(c): c["args"].update({"--cache-reuse": "256", "--slot-save-path": "/root/nox/state/soul_kv"}); os.makedirs("/root/nox/state/soul_kv", exist_ok=True); return c
def L10(c): c["args"]["--numa"] = "distribute"; return c
def L04(c): c["args"]["--moe-cache-mib"] = "1500"; return c
def L05(c): c["args"]["--spec-type"] = "mtp:n_max=1,p_min=0.0"; return c
ORDER = [("L01a_phys24_nonice", L01a), ("L01b_socket0_24", L01b), ("L01c_interleave26", L01c), ("L02_ub1024", L02), ("L03_ub2048", L03),
         ("L08_cache_reuse", L08), ("L10_numa_distribute", L10), ("L04_moe_cache_1500", L04), ("L05_mtp1", L05)]
ONLY = sys.argv[1].split(",") if len(sys.argv) > 1 else None
res = []; champ = json.loads(json.dumps(CHAMP)); champ_m = None; champ_q = None
def save(): json.dump({"results": res, "champ": champ, "champ_metrics": champ_m}, open(OUT, "w"), ensure_ascii=False, indent=1)
def run(id_, cfg):
    t, info = start(cfg, id_)
    if t is None:
        r = {"id": id_, "ok": False, "error": info}; res.append(r); save(); return None
    m = bench(id_); m["load_s"] = round(t); r = {"id": id_, "cmd": info[:400], "m": m}; res.append(r); save(); print(id_, json.dumps({k: v for k, v in m.items() if k != "q_text"}), flush=True); return m
champ_m = run("base_current", champ); champ_q = (champ_m or {}).get("q_text", "")
if not champ_m or "error" in champ_m: print("baseline fail"); sys.exit(1)
for name, f in ORDER:
    if ONLY and name.split("_")[0] not in ONLY: continue
    if name.startswith("L01") and name != "L01a_phys24_nonice" and False: pass
    cand = f(json.loads(json.dumps(champ)))
    m = run(name, cand)
    if not m or "error" in m: 
        res[-1]["verdict"] = "отказ/ошибка"; save(); continue
    tr = m["tg"] / champ_m["tg"]; pr = m["pp"] / champ_m["pp"]; fr = champ_m["ttft_long_ms"] / max(m["ttft_long_ms"], 1)
    qs = sim(m["q_text"], champ_q); score = .6 * tr + .3 * pr + .1 * fr
    acc = score >= 1.05 and tr >= 0.9 and qs >= 0.9 and (tr >= 1.05 or pr >= 1.05)
    res[-1]["verdict"] = {"tg_ratio": round(tr, 3), "pp_ratio": round(pr, 3), "ttft_ratio": round(fr, 3), "quality_sim": round(qs, 3), "score": round(score, 3), "accepted": acc}
    print(name, res[-1]["verdict"], flush=True)
    if acc: champ, champ_m = cand, m
    save()
# финал: запустить победителя
best = {"prefix": champ["prefix"], "env": champ["env"], "args": champ["args"], "metrics": {k: v for k, v in champ_m.items() if k != "q_text"}}
json.dump(best, open("/root/nox/GLM_ARGS.best", "w"), ensure_ascii=False, indent=1)
m = run("final_best", champ)
print("FINAL", json.dumps({k: v for k, v in (m or {}).items() if k != "q_text"}), flush=True)
sh("cp %s /root/nox/receipts/V7-02_exp_results.json" % OUT)
json.dump({"id": "V7-02", "ok": bool(m and "error" not in m), "best": best}, open(RC + "/V7-02.json", "w"), ensure_ascii=False, indent=1)
