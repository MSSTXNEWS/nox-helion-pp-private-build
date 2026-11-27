echo "K1: v1_02p"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; F=$N/web/pkg/server/chat_core.py
cp -n $F $F.bak_v102e
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
a='        sysm = [{"role": "system", "content": _k1_stable()}]\n'
assert s.count(a)==1
s=s.replace(a,a+'''        if _v102_on():   # V1_02: подсказка длины -> в конец системного сообщения (кэшируется и греется), хвост хода короткий
            _i = up_text.rfind("\\n\\n(")
            if _i > 0 and up_text.endswith(")") and len(up_text) - _i < 700:
                sysm = [{"role": "system", "content": _k1_stable() + "\\n" + up_text[_i + 2:]}]; up_text = up_text[:_i]
''')
b='''b = {"model": "x", "messages": [{"role": "system", "content": _k1_stable()}, {"role": "user", "content": "Привет"}], "max_tokens": 1, "id_slot": x.get("id"),'''
assert s.count(b)==1
s=s.replace(b,'''_h = (LENGTH.get("normal") or [""])[0]
                        b = {"model": "x", "messages": [{"role": "system", "content": _k1_stable() + (("\\n(" + _h + ")") if _h else "")}, {"role": "user", "content": "Привет"}], "max_tokens": 1, "id_slot": x.get("id"),''')
open(F,"w").write(s); print("patched")
PY
python3 -m py_compile $F && echo compiled || { cp $F.bak_v102e $F; echo ROLLED; exit 1; }
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -1
sleep 75
for i in 1 2 3; do curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh | grep -E "^(MEM|ADDR|JM|LOAD)" | cut -c1-62; done
tail -12 $N/state/chat_fast.log | grep slot=
echo END
