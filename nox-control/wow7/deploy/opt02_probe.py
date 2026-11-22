#!/usr/bin/env python3
"""opt02_probe.py (OPT-02): зонд стоимости проверки n токенов за один проход GLM (объединение экспертов MoE) ДО драфтеров MTP/DFlash2.
llama-bench -p 1,2,4,8,16 -n 0 с реальными флагами; t(n)=n/avg_ts, ratio(n)=t(n)/t(1); выигрыш спекуляции ~ a/ratio(n) при средней длине приёма a,
значит break_even_accept(n)=ratio(n). Решение worth_draft: ratio(8)<4 (или ratio(4)<3, если n=8 нет) - порог карточки OPT-02 (~4), ГИПОТЕЗА, подтверждает A/B L05/L06.
Требует остановленный GLM (одна главная модель за раз). Использование: opt02_probe.py --bench BIN --model GGUF --args "флаги llama-server" --out OPT-02.json [--dry-run]"""
import argparse
import json
import shlex
import subprocess
import sys
import time

# флаги llama-server -> llama-bench (имя, число значений); остальное отбрасывается и записывается в dropped
MAP = {"-ngl": ("-ngl", 1), "--n-gpu-layers": ("-ngl", 1), "-t": ("-t", 1), "--threads": ("-t", 1), "-b": ("-b", 1), "--batch-size": ("-b", 1),
       "-ub": ("-ub", 1), "--ubatch-size": ("-ub", 1), "-ot": ("-ot", 1), "--override-tensor": ("-ot", 1), "--numa": ("--numa", 1),
       "--no-op-offload": ("--no-op-offload", 0)}


def translate(args_text):
    toks, out, dropped, i = shlex.split(args_text), [], [], 0
    while i < len(toks):
        t = toks[i]
        if t in ("-fa", "--flash-attn"):
            v = toks[i + 1] if i + 1 < len(toks) else "on"
            out += ["-fa", "0" if v in ("off", "0") else "1"]; i += 2; continue
        if t in MAP:
            name, n = MAP[t]
            out += [name] + toks[i + 1:i + 1 + n]; i += 1 + n; continue
        dropped.append(t); i += 1
    return out, dropped


def analyze(rows):
    """rows: [{n_prompt, avg_ts}] -> {n, t_s, ratio, break_even_accept, worth_draft, why}"""
    pts = sorted((int(r["n_prompt"]), float(r["avg_ts"])) for r in rows if int(r.get("n_prompt", 0)) > 0 and r.get("avg_ts"))
    if not pts or pts[0][0] != 1:
        raise ValueError("нет замера n=1")
    t = {n: n / ts for n, ts in pts}
    ratio = {n: t[n] / t[1] for n in t}
    ns = sorted(t)
    worth, why = False, "нет n=4 и n=8"
    if 8 in ratio:
        worth, why = ratio[8] < 4.0, "ratio(8)=%.2f %s 4.0" % (ratio[8], "<" if ratio[8] < 4.0 else ">=")
    elif 4 in ratio:
        worth, why = ratio[4] < 3.0, "ratio(4)=%.2f %s 3.0" % (ratio[4], "<" if ratio[4] < 3.0 else ">=")
    return {"n": ns, "t_s": [round(t[n], 5) for n in ns], "ratio": [round(ratio[n], 3) for n in ns],
            "break_even_accept": [round(ratio[n], 3) for n in ns], "worth_draft": worth, "why": why}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bench", default="/root/nox/llama.cpp/build/bin/llama-bench")
    ap.add_argument("--model", default="/root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf")
    ap.add_argument("--args", default=""); ap.add_argument("--out", default="/root/nox/receipts/OPT-02.json")
    ap.add_argument("--reps", type=int, default=2); ap.add_argument("--timeout", type=int, default=3000); ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    bargs, dropped = translate(a.args)
    cmd = [a.bench, "-m", a.model] + bargs + ["-p", "1,2,4,8,16", "-n", "0", "-r", str(a.reps), "-o", "json"]
    if a.dry_run:
        print("DRY:", " ".join(shlex.quote(c) for c in cmd), "| отброшено:", " ".join(dropped) or "-", "| квитанция", a.out)
        return 0
    rec = {"id": "OPT-02", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "cmd": " ".join(cmd), "dropped": dropped}
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=a.timeout)
        if p.returncode != 0:
            raise RuntimeError("llama-bench rc=%d: %s" % (p.returncode, (p.stderr or p.stdout)[-300:]))
        txt = p.stdout
        rows = json.loads(txt[txt.index("["):txt.rindex("]") + 1])
        rec.update(analyze(rows)); rec["ok"] = True
    except Exception as e:
        rec.update({"ok": False, "worth_draft": False, "error": "%s: %s" % (type(e).__name__, e)})
    json.dump(rec, open(a.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({k: rec.get(k) for k in ("ok", "ratio", "worth_draft", "why", "error")}, ensure_ascii=False))
    return 0 if rec["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
