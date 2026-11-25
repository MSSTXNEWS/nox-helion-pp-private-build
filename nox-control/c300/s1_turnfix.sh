cd /workspace/nox/web/pkg/server
[ -f chat_core.py.bak_s1_1 ] || cp -p chat_core.py chat_core.py.bak_s1_1
[ -f web_server.py.bak_s1_1 ] || cp -p web_server.py web_server.py.bak_s1_1
python3 - <<'P'
import re
s=open('chat_core.py',encoding='utf-8').read()
if 'S1_REAPER' not in s:
    s=s.replace("self.stop = False; self.backend = None;","self.t0 = time.time(); self.last = self.t0; self.stop = False; self.backend = None;",1)
    s=s.replace("""def running_turn(cid):
    with LOCK:
        for t in ACTIVE.values():
            if t.cid == cid:
                return t
    return None
""","""S1_REAPER = 1  # S1 25.11: зависший ход снимается сам
STALE_S = float(os.environ.get("NOX_TURN_STALE_S", "180"))   # без единого токена столько секунд
HARD_S = float(os.environ.get("NOX_TURN_HARD_S", "900"))     # потолок на весь ход


def _remote_stop(t):
    try:
        if t.rte_tid:
            _call(RTE, "POST", "/v1/turns/%s/stop" % urllib.parse.quote(t.rte_tid), {}, 4.0)
    except Exception:
        pass
    try:
        _call(CORE, "POST", "/v1/stop", {"turn_id": t.id, "conversation_id": t.cid}, 4.0)
    except Exception:
        pass


def reap(cid=None):
    \"\"\"Снять зависшие ходы: нет токенов > STALE_S или ход старше HARD_S. Возвращает число снятых.\"\"\"
    now = time.time(); dead = []
    with LOCK:
        for t in list(ACTIVE.values()):
            if cid is not None and t.cid != cid:
                continue
            if now - max(getattr(t, "last", 0), getattr(t, "t0", now)) > STALE_S or now - getattr(t, "t0", now) > HARD_S:
                dead.append(t); ACTIVE.pop(t.id, None)
    for t in dead:
        t.stop = True
        c = t.conn
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        threading.Thread(target=_remote_stop, args=(t,), daemon=True).start()
    return len(dead)


def _reaper_loop():
    while True:
        time.sleep(15)
        try:
            reap()
        except Exception:
            pass


threading.Thread(target=_reaper_loop, daemon=True).start()


def running_turn(cid):
    reap(cid)
    with LOCK:
        for t in ACTIVE.values():
            if t.cid == cid:
                return t
    return None
""",1)
    s=s.replace('def stop(turn_id=None, cid=None):','def stop(turn_id=None, cid=None, all_=False):',1)
    s=s.replace("ts = [ACTIVE[turn_id]] if turn_id in ACTIVE else [t for t in ACTIVE.values() if cid and t.cid == cid]","ts = [ACTIVE[turn_id]] if turn_id in ACTIVE else [t for t in ACTIVE.values() if all_ or (cid and t.cid == cid)]",1)
    s=s.replace("""        c = t.conn
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        res.append(rec)""","""        c = t.conn
        if c is not None:
            try:
                c.close()
            except Exception:
                pass
        t.drop()
        res.append(rec)""",1)
    s=s.replace("""    def on_delta(s, stage=None):
        v = tf.feed(s)""","""    def on_delta(s, stage=None):
        t.last = time.time()
        v = tf.feed(s)""",1)
    open('chat_core.py','w',encoding='utf-8').write(s)
w=open('web_server.py',encoding='utf-8').read()
w=w.replace('CC.stop(b.get("turn_id"), b.get("conversation_id"))','CC.stop(b.get("turn_id"), b.get("conversation_id"), bool(b.get("all")))',1)
open('web_server.py','w',encoding='utf-8').write(w)
P
grep -c "S1_REAPER" chat_core.py; grep -n 'CC.stop(' web_server.py | cut -c1-160; grep -n "t.last = time.time()" chat_core.py
/workspace/nox/venv/bin/python -m py_compile chat_core.py web_server.py && echo COMPILED
echo ==BEFORE; curl -s -m 10 http://127.0.0.1:8091/glm/v1/nox/stats | head -c 700; echo
curl -s -m 10 http://127.0.0.1:8090/health | head -c 500; echo
cat run_web.sh | head -20
