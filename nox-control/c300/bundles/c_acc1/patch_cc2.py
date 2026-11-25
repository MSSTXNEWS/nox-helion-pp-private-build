import sys
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "pipe_err.log" in s: print("cc2 already"); sys.exit(0)
a='        r = _living_call_t("http://127.0.0.1:18217/verdict", {"q": text, "answer": ans, "cid": cid, "incognito": inc}, 24.0)\n        m = (r or {}).get("meta") or {}\n        if not m: return\n'
assert a in s, "anchor a"
b='''        _t0 = time.time(); _pm = dict((lv or {}).get("meta") or {}); _pm["pending"] = True
        out({"t": "meta2", "meta": _pm})
        r = _living_call_t("http://127.0.0.1:18217/verdict", {"q": text, "answer": ans, "cid": cid, "incognito": inc}, 34.0)
        m = (r or {}).get("meta") or {}
        try: open("/workspace/nox/state/pipe_err.log", "a").write("%s cid=%s ms=%d ok=%s err=%s\\n" % (time.strftime("%H:%M:%S"), cid, int((time.time() - _t0) * 1000), bool(m), (r or {}).get("err")))
        except Exception: pass
        if not m:
            _pm["pending"] = False; out({"t": "meta2", "meta": _pm}); return
'''
s=s.replace(a,b,1)
c='    except Exception: pass\ndef _living_call_t'
assert c in s, "anchor c"
s=s.replace(c,'''    except Exception:
        import traceback
        try: open("/workspace/nox/state/pipe_err.log", "a").write(traceback.format_exc() + "\\n")
        except Exception: pass
def _living_call_t''',1)
open(p,"w",encoding="utf-8").write(s); print("cc2 patched")
