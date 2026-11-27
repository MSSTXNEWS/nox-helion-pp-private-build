echo "K1: v1_02e"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; V=$N/venv_mem; D=$N/svc/mem; F=$N/web/pkg/server/chat_core.py; M=$D/nox_mem.py
cp -n $F $F.bak_v102; cp -n $M $M.bak_v102
rm -f $N/state/chat_v102.off
python3 - <<'PY'
F="/workspace/nox/web/pkg/server/chat_core.py"; s=open(F).read()
if "V1_02" in s: print("chat_core already")
else:
    a='def _k1_free_slot(prefer=0, avoid=()):'
    assert s.count(a)==1
    new='''# V1_02 (27.11): липкий слот чата из {0,1,2} (слот 3 = извлечение фактов), прогрев префикса во всех слотах, короткая память в ходе. Откат: touch state/chat_v102.off
_V102 = [None]
def _v102_on(): return not os.path.exists("/workspace/nox/state/chat_v102.off")
def _v102_slot(prefer, avoid):
    import urllib.request as _u
    d = json.loads(_u.urlopen("http://127.0.0.1:8104/slots", timeout=1.0).read())
    busy = {x.get("id") for x in d if x.get("is_processing")}
    ids = [x.get("id") for x in d]
    cand = [i for i in (0, 1, 2) if i in ids and i not in avoid]
    if _V102[0] in cand and _V102[0] not in busy: return _V102[0]
    for i in cand:
        if i not in busy: _V102[0] = i; return i
    for i in ids:
        if i not in busy and i not in avoid: return i
    return _V102[0] if _V102[0] in cand else prefer
def _v102_warm_loop():
    import urllib.request as _u
    time.sleep(5)
    while True:
        try:
            if _v102_on() and not os.path.exists("/workspace/nox/state/chat_fast.off"):
                d = json.loads(_u.urlopen("http://127.0.0.1:8104/slots", timeout=2).read())
                for x in d:
                    if x.get("id") in (0, 1, 2) and not x.get("is_processing"):
                        b = {"model": "x", "messages": [{"role": "system", "content": _k1_stable()}, {"role": "user", "content": "Привет"}], "max_tokens": 1, "id_slot": x.get("id"), "cache_prompt": True, "chat_template_kwargs": {"enable_thinking": False}}
                        _u.urlopen(_u.Request("http://127.0.0.1:8104/v1/chat/completions", data=json.dumps(b, ensure_ascii=False).encode(), headers={"Content-Type": "application/json"}), timeout=150).read()
        except Exception:
            pass
        time.sleep(45)
def _k1_free_slot(prefer=0, avoid=()):
    if _v102_on():
        try: return _v102_slot(prefer, avoid)
        except Exception: pass
    return _k1_free_slot0(prefer, avoid)
def _k1_free_slot0(prefer=0, avoid=()):'''
    s=s.replace(a,new)
    b='threading.Thread(target=_k1_warm_loop, daemon=True).start()\n'
    assert s.count(b)==1
    s=s.replace(b,b+'threading.Thread(target=_v102_warm_loop, daemon=True).start()\n')
    c='[:900] if _mem else ""'
    assert s.count(c)==1
    s=s.replace(c,'[:(360 if _v102_on() else 900)] if _mem else ""')
    open(F,"w").write(s); print("chat_core patched")
M="/workspace/nox/svc/mem/nox_mem.py"; s=open(M).read()
if "V1_02" in s: print("mem already")
else:
    a='        while time.time() - LAST_RECALL < 12: time.sleep(1)'
    assert s.count(a)==1
    s=s.replace(a,'        _tg = time.time()   # V1_02: извлечение фактов только в простое: >=22 с после последнего recall/хода. Откат: touch state/chat_v102.off\n        while time.time() - max(LAST_RECALL, _tg) < (12 if os.path.exists("/workspace/nox/state/chat_v102.off") else 22): time.sleep(1)')
    open(M,"w").write(s); print("mem patched")
PY
grep -q "^import os\|^import.*\bos\b" $M && echo mem_has_os
python3 -m py_compile $F && echo compiled_chat || { cp $F.bak_v102 $F; echo ROLLED_CHAT; exit 1; }
$V/bin/python -m py_compile $M && echo compiled_mem || { cp $M.bak_v102 $M; echo ROLLED_MEM; exit 1; }
pkill -f svc/mem/nox_mem.py; sleep 1
setsid nohup $V/bin/python $M >$N/svc/logs/mem.log 2>&1 < /dev/null &
for i in $(seq 1 20); do curl -s -m 2 127.0.0.1:18220/health && break; sleep 2; done; echo
curl -sfL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/owner/relaunch.py?cb=$(date +%s)" -o /tmp/relaunch.py
pid=$(ss -ltnp | grep "127.0.0.1:8091 " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo web pid $pid
python3 /tmp/relaunch.py $pid $N/web/restart_k1.log http://127.0.0.1:8091/health 2>&1 | tail -2
echo END
