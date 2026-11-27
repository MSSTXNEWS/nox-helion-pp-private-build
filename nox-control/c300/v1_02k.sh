echo "K1: v1_02k"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; V=$N/venv_mem; M=$N/svc/mem/nox_mem.py
cp -n $M $M.bak_v102b
python3 - <<'PY'
M="/workspace/nox/svc/mem/nox_mem.py"; s=open(M).read()
if "_pend_add" in s: print("already")
else:
    helper='''# V1_02b: недавние реплики владельца, ещё не извлечённые (извлечение отложено до простоя), попадают в recall. Откат: touch state/chat_v102.off
PEND = {}
def _pend_add(user, t):
    if os.path.exists("/workspace/nox/state/chat_v102.off"): return
    L = PEND.setdefault(user, []); L.append((time.time(), t[:300])); del L[:-4]
def _pend_drop(user, t):
    L = PEND.get(user) or []; PEND[user] = [x for x in L if x[1] != t[:300]]
def _pend_ctx(user, ctx):
    L = [x[1] for x in (PEND.get(user) or []) if time.time() - x[0] < 600]
    if not L: return ctx
    add = "Недавно собеседник сказал (ещё не сохранено): " + " | ".join(L)
    return (ctx + "\\n" + add) if ctx else ("Из твоей долговременной памяти (недавно, ещё не сохранено): " + add)
class H('''
    assert s.count("class H(")==1; s=s.replace("class H(",helper,1)
    a='return self._j({"context": ctx, "hits": len(hits),'; assert s.count(a)==1
    s=s.replace(a,'ctx = _pend_ctx(user, ctx)\n                return self._j({"context": ctx, "hits": len(hits),')
    a='try: Q.put_nowait((t,'; assert s.count(a)==1
    s=s.replace(a,'_pend_add(user, t)\n                try: Q.put_nowait((t,')
    a='for f in extract(text, ans): add_fact(f, user, cid)'; assert s.count(a)==1
    s=s.replace(a,a+'\n            _pend_drop(user, text)')
    open(M,"w").write(s); print("patched")
PY
$V/bin/python -m py_compile $M && echo compiled || { cp $M.bak_v102b $M; echo ROLLED; exit 1; }
pkill -f svc/mem/nox_mem.py; sleep 1
setsid nohup $V/bin/python $M >$N/svc/logs/mem.log 2>&1 < /dev/null &
for i in $(seq 1 20); do curl -s -m 2 127.0.0.1:18220/health && break; sleep 2; done; echo
sleep 20
for i in 1 2; do curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/rv_turn.sh?cb=$(date +%s)" -o /tmp/rv_turn_v102.sh && bash /tmp/rv_turn_v102.sh | grep -E "^(MEM|ADDR|JM|LOAD)"; done
echo END
