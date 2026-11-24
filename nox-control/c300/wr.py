import shutil, time, subprocess
p="/workspace/nox/web/pkg/server/web_server.py"; s=open(p).read(); ts=time.strftime("%H%M%S")
if "/img/generate" in s: print("already"); raise SystemExit
shutil.copy(p,p+".bak_c300_img_"+ts)
helper='''
# ---- c300: Фотостудия — генерация (:8500), файлы результата, зрение (:8104 с mmproj) ----
def _c300_img_file(h, qs):
    import urllib.parse as _u, os as _o
    q = _u.parse_qs(qs.lstrip("?")); p = _o.path.realpath((q.get("p") or [""])[0])
    if not p.startswith("/workspace/nox/") or not p.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) or not _o.path.isfile(p):
        return h._j(404, {"error": "нет файла"})
    b = open(p, "rb").read(); h.send_response(200); h.send_header("Content-Type", "image/" + ("jpeg" if p.lower().endswith(("jpg", "jpeg")) else p.rsplit(".", 1)[1].lower()))
    h.send_header("Content-Length", str(len(b))); h.send_header("Cache-Control", "max-age=86400"); h.end_headers(); h.wfile.write(b)
def _c300_vision(h, raw):
    import json as _j, http.client as _hc
    try: b = _j.loads(raw or b"{}")
    except Exception: return h._j(400, {"error": "плохой JSON"})
    img, q = b.get("image") or "", (b.get("prompt") or "Опиши изображение по-русски.")[:2000]
    if not img.startswith("data:image/") or len(img) > 8_000_000: return h._j(400, {"error": "нужна картинка data:image/* до 6 МБ"})
    body = _j.dumps({"messages": [{"role": "user", "content": [{"type": "text", "text": q}, {"type": "image_url", "image_url": {"url": img}}]}], "max_tokens": 500, "temperature": 0.4, "chat_template_kwargs": {"enable_thinking": False}})
    try:
        c = _hc.HTTPConnection(os.environ.get("NOX_VISION", "127.0.0.1:8104"), timeout=240); c.request("POST", "/v1/chat/completions", body=body, headers={"Content-Type": "application/json"})
        r = c.getresponse(); d = _j.loads(r.read() or b"{}")
        t = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        return h._j(200 if t else 502, {"text": t} if t else {"error": str(d)[:300]})
    except Exception as e: return h._j(502, {"error": "зрение недоступно: %s" % e})
'''
i = s.index("\nclass "); s = s[:i] + "\n" + helper + s[i:]
g='        if p.startswith("/tts/"): return self._proxy("GET", p[4:] + qs, None, TTS, "TTS (127.0.0.1:8094)")\n'
po='        if p.startswith("/tts/"): return self._proxy("POST", p[4:] + qs, raw, TTS, "TTS (127.0.0.1:8094)", self.headers.get("Content-Type"))\n'
assert s.count(g)==1 and s.count(po)==1
s=s.replace(g, g+'        if p == "/img/file": return _c300_img_file(self, qs)\n        if p == "/img/health": return self._proxy("GET", "/health", None, os.environ.get("NOX_IMGSVC", "127.0.0.1:8500"), "генерация (:8500)")\n')
s=s.replace(po, po+'        if p == "/img/generate": return self._proxy("POST", "/generate", raw, os.environ.get("NOX_IMGSVC", "127.0.0.1:8500"), "генерация (:8500)", "application/json")\n        if p == "/vision/describe": return _c300_vision(self, raw)\n')
open(p,"w").write(s); r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-300:])
if r.returncode: shutil.copy(p+".bak_c300_img_"+ts,p); print("REVERTED")
