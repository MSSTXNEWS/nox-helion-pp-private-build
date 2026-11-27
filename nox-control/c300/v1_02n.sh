echo "K1: v1_02n"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
cp -n $F $F.bak_v102d
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='                try: j = json.loads(d)\n                except Exception: continue\n                v = ((j.get("choices") or [{}])[0].get("delta") or {}).get("content")\n                if v:\n                    n += 1; on_delta(v, None)\n                    if n == 1:'
print(s.count(a))
assert s.count(a)==1
s=s.replace(a,a.replace("                v = ((j.get","                if j.get(\"timings\"): _V102TM[0] = j[\"timings\"]\n                v = ((j.get",1))
b='    finally:\n        for p, v in prev.items():'
assert s.count(b)==1
s=s.replace(b,'''    finally:
        try:
            _tm = _V102TM[0] or {}; _V102TM[0] = None
            open("/workspace/nox/state/chat_fast.log", "a").write("  slot=%s prompt_n=%s cache_n=%s prompt_ms=%s\\n" % (body.get("id_slot"), _tm.get("prompt_n"), _tm.get("cache_n"), int(_tm.get("prompt_ms") or 0)))
        except Exception: pass
        for p, v in prev.items():''')
s=s.replace("_V102 = [None]\n","_V102 = [None]\n_V102TM = [None]\n",1)
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled || { cp $F.bak_v102d $F; echo ROLLED; exit 1; }
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 40
for i in 1 2; do curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh | grep -E "^(MEM|ADDR|JM|LOAD)" | cut -c1-70; done
tail -26 $N/state/chat_fast.log
echo END
