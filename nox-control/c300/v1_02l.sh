echo "K1: v1_02l"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
cp -n $F $F.bak_v102c
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='if "llama-server" in cl and ("Qwen3-30B-A3B" in cl or "Thinking-2507" in cl): r.append(int(d))'
assert s.count(a)==1
s=s.replace(a,'if ("llama-server" in cl and ("Qwen3-30B-A3B" in cl or "Thinking-2507" in cl)) or (_v102_on() and any(k in cl for k in ("judge_service", "chrome-headless-shell", "--port 8144", "--port 8141", "train_dpo", "distill_v2"))): r.append(int(d))   # V1_02: фон в nice 19 на время хода')
b='    t0 = time.time(); n = 0; status = "done"; err = None\n    try:\n        sysm = [{"role": "system"'
assert s.count(b)==1
s=s.replace(b,'    _v102_boost(prev)\n'+b)
c='def _v102_warm_loop():'
s=s.replace(c,'''def _v102_boost(prev):   # llama :8104 получает nice -10 на время хода (вернётся в finally)
    if not _v102_on(): return
    try:
        for d in os.listdir("/proc"):
            if d.isdigit():
                try: cl = open("/proc/%s/cmdline" % d, "rb").read().decode("utf-8", "replace")
                except Exception: continue
                if "llama-server" in cl and "--port 8104" in cl:
                    p = int(d); prev[p] = os.getpriority(os.PRIO_PROCESS, p); os.setpriority(os.PRIO_PROCESS, p, -10)
    except Exception: pass
'''+c,1)
assert s.count("[:(360 if _v102_on() else 900)]")==1
s=s.replace("[:(360 if _v102_on() else 900)]","[:(300 if _v102_on() else 900)]")
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled || { cp $F.bak_v102c $F; echo ROLLED; exit 1; }
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -2
sleep 40
for i in 1 2; do curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh | grep -E "^(MEM|ADDR|JM|LOAD)"; done
echo END
