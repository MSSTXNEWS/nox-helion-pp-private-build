import sys
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "_race_watch" in s: print("race already"); sys.exit(0)
def rep(a,b):
    global s
    assert s.count(a)==1,(s.count(a),a[:70]); s=s.replace(a,b,1)
rep('    levels = []; parts = []; got = [False]; tf = ThinkFilter(); info = {"path": None}\n',
    '    levels = []; parts = []; got = [False]; tf = ThinkFilter(); info = {"path": None}\n    race = {"adv": None, "local": [], "lk": threading.Lock(), "cut": False}      # C: гонка локальной модели и советника\n')
rep('        v = tf.feed(s)\n        if not v:\n            return\n        lv = stage_level(stage)',
    '        v = tf.feed(s)\n        if not v:\n            return\n        if race["adv"] is not None:\n            race["local"].append(v); return\n        lv = stage_level(stage)')
rep('        got[0] = True; parts.append(v); out({"t": "delta", "text": v, "stage": stage})',
    '        with race["lk"]:\n            if race["adv"] is not None:\n                race["local"].append(v); return\n            got[0] = True\n        parts.append(v); out({"t": "delta", "text": v, "stage": stage})')
rep('    out({"t": "meta", "turn_id": t.id, "conversation_id": cid, "mode": mode, "length": length})\n',
'''    out({"t": "meta", "turn_id": t.id, "conversation_id": cid, "mode": mode, "length": length})
    def _race_watch():
        try:
            if not _le("race") or str(text).startswith("/") or draw_request(text) is not None: return
            lim = float(body.get("race_s") or _le_num("race_s", 7.0)); end = time.time() + lim
            while time.time() < end:
                if got[0] or t.stop: return
                time.sleep(0.1)
            if got[0] or t.stop: return
            h = [{"role": m["role"], "content": str(m.get("content") or "")[:600]} for m in history if m.get("role") in ("user", "assistant")][-6:]
            t1 = time.time(); r = _living_call_t("http://127.0.0.1:18217/fast", {"q": text, "history": h}, 14.0); txt = (r or {}).get("text")
            if not txt: return
            with race["lk"]:
                if got[0] or t.stop: return
                race["adv"] = r; got[0] = True
            out({"t": "race", "winner": "советник", "model": r.get("model"), "after_s": round(t1 - (end - lim), 1), "ms": r.get("ms")})
            for i in range(0, len(txt), 40):
                parts.append(txt[i:i + 40]); out({"t": "delta", "text": txt[i:i + 40], "stage": "advisor"}); time.sleep(0.015)
            def _cut():
                race["cut"] = True
                try: stop(turn_id=t.id)
                except Exception: pass
            _tm = threading.Timer(_le_num("race_wait", 20.0), _cut); _tm.daemon = True; _tm.start(); race["tm"] = _tm
        except Exception:
            import traceback
            try: open("/workspace/nox/state/pipe_err.log", "a").write("race: " + traceback.format_exc() + "\\n")
            except Exception: pass
    threading.Thread(target=_race_watch, daemon=True).start()
''')
rep('    if t.stop and status == "done":\n        status = "stopped"\n',
'''    if race.get("tm"): race["tm"].cancel()
    if race["adv"] is not None and not parts == []:
        status = "done"; err = None
    if t.stop and status == "done" and race["adv"] is None:
        status = "stopped"
''')
rep('    final_level = (',
'''    if race["adv"] is not None:
        _m = dict(_lv.get("meta") or {}); _m["race"] = "советник"; _m["race_model"] = race["adv"].get("model"); _m["sources"] = list(dict.fromkeys(list(_m.get("sources") or []) + ["советник"]))
        _lv["meta"] = _m; _alt = "".join(race["local"]).strip()
        if _alt and not race["cut"]: _lv["alt"] = _alt
    final_level = (''')
rep('def _pipe_after(text, ans, cid, body, lv, out):',
'''def _le_num(name, d):
    try:
        with open("/workspace/nox/state/persona.json", encoding="utf-8") as f: v = (json.load(f).get("living_engines") or {}).get(name)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else d
    except Exception: return d
def _pipe_after(text, ans, cid, body, lv, out):''')
import re as _re
_n=len(_re.findall(r'"incognito": inc\}, (?:24|34)\.0\)', s)); assert _n==1,_n
s=_re.sub(r'"incognito": inc\}, (?:24|34)\.0\)', '"incognito": inc, "alt": (lv or {}).get("alt")}, 40.0)', s, count=1)
open(p,"w",encoding="utf-8").write(s); print("race patched")
