#!/usr/bin/env bash
# S1_01 РАЗВЕДКА (SPD-01 + OPT-06 dry-run) и БАЗОВЫЙ ЗАМЕР. Ничего не меняет в работе, кроме файлов пакета. Метка #S1. Идёт в фон (замер GLM долгий).
# Выход: /root/nox/receipts/{SPD-01,OPT-06,V7-01}.json, /root/nox/state/v7/BASELINE.json (скорости GLM/быстрой модели/шлюза) и baseline_flags.json (текущие флаги, версии).
# Флаги: --dry-run --fg --status ; --no-bench (без замера скоростей)
SID=V7-01; STAGE_NO=1; TITLE="Разведка и baseline"; LONG=1
stage_plan() {
  echo "1. набор deploy,spd,opt,common из main; ссылки wow7"
  echo "2. recon_s1.sh -> SPD-01.json (CPU/NUMA/cgroup/THP/PCIe/RAM BW/поддержка флагов llama.cpp)"
  echo "3. numa_tune.sh --dry-run -> OPT-06.json (только чтение)"
  echo "4. снимок флагов: cmdline llama-server, glm.args, GLM_ARGS (репо, свип), winner.json, env шлюза, версии -> state/v7/baseline_flags.json"
  echo "5. baseline: ab_bench --attach на :8081 (GLM) и :8083 (быстрая) + проба чата через шлюз -> state/v7/BASELINE.json"
}
stage_apply() {
  local s; for s in spd opt common; do v7_sync_set "$s" || return 1; done
  v7_links; mkdir -p "$V7_RUN"
  RECEIPTS="$V7_RC" bash "$V7_W/spd/recon_s1.sh" >"$V7_RUN/recon.out" 2>&1 || say "recon_s1 rc!=0 (см. $V7_RUN/recon.out)"; tail -3 "$V7_RUN/recon.out" | cut -c1-200
  bash "$V7_W/opt/numa_tune.sh" --dry-run --receipts-dir "$V7_RC" >"$V7_RUN/numa.out" 2>&1 || say "numa_tune rc!=0"
  python3 -I - "$V7_RUN/baseline_flags.json" "$V7_HOME" "$V7_CTL" <<'PY'
import glob, json, os, subprocess, sys, time
out, home, ctl = sys.argv[1:4]
def rd(p):
    try: return open(p, errors="replace").read().strip()
    except OSError: return None
procs = []
for d in os.listdir("/proc"):
    if d.isdigit():
        c = (rd("/proc/%s/cmdline" % d) or "").replace("\0", " ").strip()
        if "llama-server" in c or "gateway.py" in c or "web_server.py" in c or "nox_dispatcher" in c or "nox_core" in c:
            procs.append({"pid": int(d), "cmd": c[:600]})
gw_env = {}
for p in procs:
    if "gateway.py" in p["cmd"]:
        for kv in (rd("/proc/%d/environ" % p["pid"]) or "").split("\0"):
            if kv.startswith("NOX_") and "=" in kv: gw_env[kv.split("=", 1)[0]] = kv.split("=", 1)[1][:120]
def git(*a):
    try: return subprocess.run(["git", "-C", os.path.join(home, "repo")] + list(a), capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception: return None
d = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "procs": procs, "gateway_env_NOX": gw_env,
     "glm_args_live": rd(os.path.join(home, "gpu_tier/glm.args")), "GLM_ARGS_repo": rd(os.path.join(ctl, "gpu_tier/GLM_ARGS")),
     "GLM_ARGS_best": rd(os.path.join(home, "gpu_tier/GLM_ARGS.best")), "winner_json": rd(os.path.join(home, "logs/spd_ab/winner.json")),
     "repo_head": git("rev-parse", "--short", "HEAD"), "repo_dirty_files": (git("status", "--porcelain") or "").count("\n") + (1 if git("status", "--porcelain") else 0),
     "dsp_installed": os.path.isdir(os.path.join(home, "dsp/current")), "v7_flags": rd(os.path.join(home, "state/v7_flags.json"))}
json.dump(d, open(out, "w"), ensure_ascii=False, indent=1)
print("снимок флагов: процессов %d, repo=%s dirty=%s" % (len(procs), d["repo_head"], d["repo_dirty_files"]))
PY
  has_extra --no-bench && { say "замер пропущен (--no-bench)"; return 0; }
  v7_ld; local B="$V7_RUN/baseline" ; mkdir -p "$B"
  if v7_http http://127.0.0.1:8081/health 5; then python3 "$V7_W/spd/ab_bench.py" --attach http://127.0.0.1:8081 --matrix "$V7_W/spd/matrix.json" --out "$B/glm" || say "замер GLM не удался"; else say "GLM :8081 не отвечает - baseline GLM пуст"; fi
  if v7_http http://127.0.0.1:8083/health 5; then python3 "$V7_W/spd/ab_bench.py" --attach http://127.0.0.1:8083 --matrix "$V7_W/spd/matrix.json" --out "$B/fast" || say "замер fast не удался"; fi
  v7_chat_probe fast 24 90 > "$B/gateway_fast.json" 2>/dev/null || true
  python3 -I - "$B" "$V7_RUN/BASELINE.json" <<'PY'
import json, os, sys
b, out = sys.argv[1:3]
def m(p):
    try: return json.load(open(p))["winner"]["metrics"]
    except Exception: return None
def line(p):
    try: return json.loads(open(p).read().strip().splitlines()[-1])
    except Exception: return None
d = {"glm": m(os.path.join(b, "glm/results.json")), "fast": m(os.path.join(b, "fast/results.json")), "gateway_fast": line(os.path.join(b, "gateway_fast.json"))}
for k in ("glm", "fast"):
    if d[k]: d[k].pop("quality_text", None)
json.dump(d, open(out, "w"), ensure_ascii=False, indent=1); print(json.dumps(d, ensure_ascii=False)[:500])
PY
  V7_RESULT=$(cat "$V7_RUN/BASELINE.json" | tr -d '\n ')
}
stage_health() { v7_health_regress; }
stage_rollback() { return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
