# -*- coding: utf-8 -*-
"""body_guard: сторож тела (канон гл. 1). Обёртка вокруг ops/body_restart.sh (сам скрипт не правится): поднимает только тот cmd, который ПОМЕЩАЕТСЯ в свободную VRAM.
Порядок: p5_best -> gpu_ncmoe0 -> liska_ncmoe22 -> dpo_ncmoe36 (файлы agent/autotrain/donor_<mode>.cmd.<имя>). Не больше одного перезапуска (flock state/body_guard.lock).
Решение: «занято чужими» + пик cmd + запас <= 92% от total. «Чужие» = всё, что занимает VRAM кроме текущего :8104 (оно будет остановлено). Пики: измеренные (state/body_guard_peaks.json) или стартовые оценки.
Журнал: state/body_guard.log (+ state/alerts.jsonl: только числа и коды). Запуск: python3 -I body_guard.py [--plan] [--start ИМЯ] [--force] [--reason TEXT]. Коды выхода: 0 ок, 4 занят замок, 6 ничего не помещается, 1 провал.
Используйте вместо прямого body_restart.sh: ops/body_safe_restart.sh = этот скрипт."""
import os, sys, re, json, time, fcntl, subprocess, urllib.request
N = os.environ.get("NOX_ROOT", "/workspace/nox"); A = N + "/agent/autotrain"; ST = N + "/state"
ORDER = ["p5_best", "gpu_ncmoe0", "liska_ncmoe22", "dpo_ncmoe36"]
SEED_GB = {"p5_best": 22.8, "gpu_ncmoe0": 21.6, "p5_e1_ub2048": 22.4, "liska_ncmoe22": 11.6, "dpo_ncmoe36": 5.2}   # 28.11: наблюдаемое «после старта» (ncmoe0 21.6, ncmoe36 5.2); p5_best консервативно
CAP = 0.92; LOAD_MARGIN_GB = 1.0   # запас на пик при загрузке (буферы)
PEAKS = ST + "/body_guard_peaks.json"; LOG = ST + "/body_guard.log"; ALERTS = ST + "/alerts.jsonl"; LOCKF = ST + "/body_guard.lock"
def log(s):
    line = "%s %s" % (time.strftime("%FT%TZ", time.gmtime()), s)
    try: open(LOG, "a").write(line + "\n")
    except Exception: pass
    print(line, flush=True)
def alert(code, **kv):
    try: open(ALERTS, "a").write(json.dumps(dict(t=int(time.time()), src="body_guard", code=code, **kv), ensure_ascii=False) + "\n")
    except Exception: pass
    log("ALERT %s %s" % (code, kv))
def nv(args):
    try: return subprocess.run(["nvidia-smi"] + args, capture_output=True, text=True, timeout=10).stdout
    except Exception: return ""
def gpu_state():
    """-> dict(total_mib, used_mib, body_pid, body_mib). body_* = процесс, слушающий :8104."""
    q = nv(["--query-gpu=memory.total,memory.used", "--format=csv,noheader,nounits"]).strip().split("\n")[0].split(",")
    total, used = (float(q[0]), float(q[1])) if len(q) == 2 else (49152.0, 0.0)
    pid = None
    try:
        o = subprocess.run("ss -ltnp 2>/dev/null | grep ':8104 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2", shell=True, capture_output=True, text=True, timeout=5).stdout.strip(); pid = int(o) if o else None
    except Exception: pass
    mib = 0.0
    for l in nv(["--query-compute-apps=pid,used_memory", "--format=csv,noheader,nounits"]).splitlines():
        p = [x.strip() for x in l.split(",")]
        if len(p) == 2 and pid is not None and p[0] == str(pid):
            try: mib += float(p[1])
            except Exception: pass
    return {"total_mib": total, "used_mib": used, "body_pid": pid, "body_mib": mib}
def load_peaks():
    try: return json.load(open(PEAKS))
    except Exception: return {}
def peak_gb(name, cmd_text=None, peaks=None):
    peaks = load_peaks() if peaks is None else peaks
    if name in peaks: return float(peaks[name])
    if name in SEED_GB: return SEED_GB[name]
    # неизвестный cmd: оценка по флагам (n-cpu-moe снижает ~0.46 ГБ на слой; -ub/-b больше 512 добавляют ~0.8 ГБ)
    m = re.search(r"--n-cpu-moe\s+(\d+)", cmd_text or ""); n = int(m.group(1)) if m else 0
    g = 21.6 - 0.458 * min(n, 40) + (0.8 if re.search(r"-ub\s+(\d{4,})", cmd_text or "") else 0)
    return round(g + 1.0, 1)   # +1 ГБ неопределённости
def decide(g, order=ORDER, files=None, texts=None, peaks=None, start=None):
    """g: gpu_state. -> {"choice": имя|None, "rows": [...]}. files: {имя: путь} существующих cmd (по умолчанию ищет в agent/autotrain)."""
    mode = (open(A + "/mode").read().strip() if os.path.exists(A + "/mode") else "hybrid")
    files = files if files is not None else {n: "%s/donor_%s.cmd.%s" % (A, mode, n) for n in order if os.path.exists("%s/donor_%s.cmd.%s" % (A, mode, n))}
    others_gb = (g["used_mib"] - g["body_mib"]) / 1024.0; cap_gb = CAP * g["total_mib"] / 1024.0
    rows = []; choice = None; skip = start is not None
    for n in order:
        if skip and n != start: rows.append({"cmd": n, "skip": "before_start"}); continue
        skip = False
        if n not in files: rows.append({"cmd": n, "skip": "no_file"}); continue
        pk = peak_gb(n, (texts or {}).get(n), peaks); need = others_gb + pk + LOAD_MARGIN_GB
        ok = need <= cap_gb; rows.append({"cmd": n, "peak_gb": round(pk, 1), "need_gb": round(need, 1), "cap_gb": round(cap_gb, 1), "fits": ok})
        if ok and choice is None: choice = n
    return {"choice": choice, "others_gb": round(others_gb, 1), "rows": rows, "files": files}
def health():
    try: return b'"ok"' in urllib.request.urlopen("http://127.0.0.1:8104/health", timeout=3).read()
    except Exception: return False
def record_peak(name):
    """После успешного старта: замерить память процесса :8104 и сохранить максимум (измерение заменяет оценку)."""
    best = 0.0
    for _ in range(6):
        best = max(best, gpu_state()["body_mib"] / 1024.0); time.sleep(5)
    if best > 1.0:
        p = load_peaks(); p[name] = round(max(best, p.get(name, 0) * 0.0), 2)
        try: json.dump(p, open(PEAKS, "w")); log("peak %s=%.1f GB (измерено)" % (name, best))
        except Exception: pass
    return best
def main(argv=None):
    a = argv if argv is not None else sys.argv[1:]; g_ = lambda k, d=None: a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d
    plan = "--plan" in a; force = "--force" in a; reason = g_("--reason", "body_guard"); start = g_("--start")
    os.makedirs(ST, exist_ok=True); fh = open(LOCKF, "w")
    try: fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError: alert("busy", reason=reason); return 4
    g = gpu_state(); d = decide(g, start=start)
    texts_note = {r["cmd"]: r.get("fits") for r in d["rows"] if "fits" in r}
    log("решение: choice=%s others_gb=%s rows=%s" % (d["choice"], d["others_gb"], json.dumps(d["rows"], ensure_ascii=False)))
    if plan: print(json.dumps({k: v for k, v in d.items() if k != "files"}, ensure_ascii=False)); return 0
    choice = d["choice"]
    if choice is None:
        alert("nothing_fits", others_gb=d["others_gb"], total_mib=int(g["total_mib"]))
        if health(): return 6   # тело живо: не трогаем
        fits = [n for n in ORDER[::-1] if n in d["files"]]
        if not fits: alert("no_cmd_files"); return 6
        choice = fits[0]; alert("last_resort", cmd=choice)   # тела нет вообще: поднимаем самый лёгкий, лучше так, чем без чата
    cmd = d["files"][choice]; args = ["bash", N + "/ops/body_restart.sh", "--cmd", cmd, "--reason", "%s [guard:%s]" % (reason, choice)] + (["--force"] if force else [])
    t0 = time.time(); log("запуск body_restart: %s" % choice)
    r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=900, pass_fds=())
    dt = int(time.time() - t0); out = (r.stdout or "")[-400:]
    if r.returncode in (2, 3, 4, 5): alert("restart_refused", rc=r.returncode, cmd=choice); return r.returncode
    ok = health(); rolled = "ОТКАТ" in out
    if rolled: alert("rolled_back_to_known_good", cmd=choice, sec=dt)
    if not ok: alert("body_down_after_restart", cmd=choice, sec=dt); return 1
    gs = gpu_state(); pct = round(100 * gs["used_mib"] / gs["total_mib"], 1)
    if pct > 92: alert("vram_over_92", pct=pct, cmd=choice)
    log("ИТОГ ok cmd=%s sec=%d vram=%.1f%% rolled_back=%s" % (choice, dt, pct, rolled))
    if not rolled: record_peak(choice)
    return 0
if __name__ == "__main__": sys.exit(main())
