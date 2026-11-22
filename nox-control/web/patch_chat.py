import re,sys
p='/root/nox/web_server.py'; s=open(p,encoding='utf-8').read()
if 'NOXFB' in s: print('already'); sys.exit(0)
# 1. метод-запасной быстрый слой
helper='''    def _fast_text(self, req):  # NOXFB
        import re as _re
        def cl(t): return _re.sub(r"<think>.*?</think>", "", t or "", flags=_re.S).replace("</think>", "").strip()
        try:
            c2 = http.client.HTTPConnection("127.0.0.1:8083", timeout=120)
            c2.request("POST", "/v1/chat/completions", body=json.dumps({"messages": req["messages"], "max_tokens": int(req.get("max_tokens") or 400), "stream": False}), headers={"Content-Type": "application/json"})
            m = ((json.loads(c2.getresponse().read()).get("choices") or [{}])[0].get("message") or {})
            return cl(m.get("content")) or cl(m.get("reasoning_content")) or cl(m.get("reasoning"))
        except Exception:
            return ""
    def _clean(self, t):  # NOXFB: служебное - не в текст (фазы идут полем nox_phase)
        import re as _re
        keep = [l for l in (t or "").split("\\n") if not _re.search(r"Глубокий ответ|готовлю в фоне|\\(задача\\s*t?\\d+|результат появится|Быстрый слой|быстрым слоем|повтори(те)? запрос|GLM\\s*занят|</?think>|⏳", l)]
        return "\\n".join(keep).strip()
    def _fb(self, req, mode, why):
        txt = self._clean(self._fast_text(req)) or "Мессир, ответ сейчас не сложился; запись в журнале."
        phase = "deep_busy" if mode in ("deep", "max") else "fast_fallback"
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.send_header("Cache-Control", "no-cache"); self.send_header("Connection", "close"); self.end_headers()
        for o in ({"model": TAG, "message": {"role": "assistant", "content": txt}, "done": False, "nox_phase": {"phase": phase, "why": why[:80]}}, {"model": TAG, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"}):
            self.wfile.write((json.dumps(o, ensure_ascii=False) + "\\n").encode())
        self.wfile.flush()
    def _body(self):'''
assert '    def _body(self):' in s; s=s.replace('    def _body(self):',helper,1)
a='return self._j(502, {"error": "шлюз GLM недоступен: %s" % e})'; assert a in s
s=s.replace(a,'return self._fb(req, _mode, str(e))',1)
b=re.search(r'return self\._j\(502, \{"error": "шлюз GLM ответил %s: %s" % \(r\.status, r\.read\(\)\[:200\]\.decode\("utf-8", "replace"\)\)\}\)',s); assert b
s=s.replace(b.group(0),'return self._fb(req, _mode, "gw %s" % r.status)',1)
# 2. пустой поток -> запасной
c='            if ok: out({"model": TAG, "message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop"})'
assert c in s
s=s.replace(c,'''            if not "".join(_acc).strip():
                _t = self._clean(self._fast_text(req)) or "Мессир, ответ сейчас не сложился; запись в журнале."
                out({"model": TAG, "message": {"role": "assistant", "content": _t}, "done": False, "nox_phase": {"phase": "deep_busy" if _mode in ("deep", "max") else "empty_retry"}}); ok = True
'''+c,1)
# 3. честная ошибка фоновой задачи
d='j["status"] = "error"; j["text"] = str(e)'; assert d in s
s=s.replace(d,'j["status"] = "error"; j["text"] = ""; j["phase"] = "deep_failed"',1)
open(p,'w',encoding='utf-8').write(s); print('patched web_server')
# 4. Максимум
m='/root/nox/web/nox_mode.js'; t=open(m,encoding='utf-8').read()
if "'max'" not in t.split("function get")[0]:
    t2=re.sub(r"(\['deep','Глубоко','[^']*'\])",r"\1,['max','Максимум','GLM-5.3 на полную глубину, дольше всего']",t,1)
    t2=t2.replace("return v==='max'?'deep':v","return v"); open(m,'w',encoding='utf-8').write(t2); print('max restored', t2!=t)
