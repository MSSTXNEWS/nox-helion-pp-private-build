set -x
N=/workspace/nox; W=$N/web/pkg/server; S=$N/web/site; P=$N/svc/pipeline; B=$P/acc1; O=$N/state/c_acc1.out; : > $O
exec >> $O 2>&1
echo "== pipeline_svc tune"; cp -n $P/pipeline_svc.py $P/pipeline_svc.py.bak_c_2
sed -i 's/^BUDGET = 18.0/BUDGET = 30.0/; s/def judge(text, ctx=None, source=None, t=9):/def judge(text, ctx=None, source=None, t=22):/; s/return {"meta": {}, "ms": int((time.time() - t0) \* 1000)}\n    hard/&/' $P/pipeline_svc.py
python3 - <<'PY'
p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
k='if s["err"] or s["n"] == 0: return {"meta": {}, "ms"'
if k in s and '"err": str(' not in s:
    s=s.replace(k,'if s["err"] or s["n"] == 0: return {"meta": {}, "err": str(s["err"] or "judges=0"), "ms"',1); open(p,"w",encoding="utf-8").write(s); print("err field added")
PY
python3 -m py_compile $P/pipeline_svc.py && echo pc_ok
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 2; curl -s -m4 localhost:18217/health
echo "== chat_core pipe_err + pending"; cp -n $W/chat_core.py $W/chat_core.py.bak_c_2
python3 $B/patch_cc2.py && python3 -m py_compile $W/chat_core.py && echo cc_ok || { cp $W/chat_core.py.bak_c_2 $W/chat_core.py; echo cc_rollback; }
echo "== rq.js pending"; cp -n $S/nox-chat-rq.js $S/nox-chat-rq.js.bak_c_2; python3 $B/patch_rq.py || cp $S/nox-chat-rq.js.bak_c_2 $S/nox-chat-rq.js
sed -i 's#nox-chat-rq.js?v=[0-9a-z]*#nox-chat-rq.js?v=c2#' $S/chat.html; grep -o "nox-chat-rq.js?v=[0-9a-z]*" $S/chat.html
( $W/run_web.sh restart </dev/null >/tmp/c_web_restart.log 2>&1 ); sleep 6
echo "== ddgs"; cat $P/pip.log | tail -3; $N/venv_living/bin/pip list 2>/dev/null | grep -i ddgs
timeout 40 $N/venv_living/bin/python -c "
from ddgs import DDGS
r=DDGS().text('столица Австралии',max_results=2,timeout=10); print('DDGS',len(r),str(r)[:300])" 2>&1 | tail -3
curl -sI -m8 https://duckduckgo.com | head -1; curl -sI -m8 https://html.duckduckgo.com | head -1; curl -sI -m8 https://api.duckduckgo.com | head -1
echo "== low-confidence verdict"
timeout 60 curl -s -m55 localhost:18217/verdict -H 'Content-Type: application/json' -d '{"q":"Какая столица Австралии?","answer":"Столица Австралии — Сидней, самый крупный город страны.","cid":"clow1"}'; echo
timeout 60 curl -s -m55 localhost:18217/verdict -H 'Content-Type: application/json' -d '{"q":"Кто выиграл чемпионат мира по шахматам в 2086 году?","answer":"Его выиграл Иван Петров.","cid":"clow2"}'; echo
echo "== probes :8810"; ss -ltnp | grep -E ':8810|:8130|:8400' | cut -c1-160
curl -s -m4 localhost:8810/board | head -c 700; echo; curl -s -m4 localhost:8810/health | head -c 200; echo
grep -n "8810" $N/svc/svc_registry* $N/web/pkg/server/*.py 2>/dev/null | head -5; ls $N/svc | head -30
echo "== qa_audit"; find $N -maxdepth 3 -name "qa_audit*.py" 2>/dev/null | head; ls -t $S/qa 2>/dev/null | head -12
echo "== chat.html scripts check"; grep -c "nox-ghost-all" $S/chat.html
echo FINISHED
