import re,sys
p='/root/nox/web_server.py'; s=open(p,encoding='utf-8').read()
if 'NOXGZ' in s: print('already'); sys.exit(0)
old='''    def _send(self, code, body=b"", ctype="application/json", extra=None):
        self.send_response(code)'''
new='''    def _send(self, code, body=b"", ctype="application/json", extra=None):
        extra = dict(extra or {})  # NOXGZ
        if 1024 < len(body) < 8000000 and "gzip" in (self.headers.get("Accept-Encoding") or "") and (ctype.startswith("text/") or "javascript" in ctype or "json" in ctype or "svg" in ctype or "xml" in ctype):
            import gzip as _gz; body = _gz.compress(body, 5); extra["Content-Encoding"] = "gzip"; extra["Vary"] = "Accept-Encoding"
        self.send_response(code)'''
assert old in s; s=s.replace(old,new,1)
old2='{"Cache-Control": "no-cache"})\n        return self._j(404, {"error": "not found"})\n    def _body'
assert old2 in s
s=s.replace(old2,'{"Cache-Control": ("public, max-age=86400" if (rel.startswith(("vendor/","assets/","pc/vendor/","pc/assets/")) and not rel.endswith((".html",))) or rel.endswith((".woff2",".jpg",".png",".webp",".onnx",".wasm",".hdr",".mp3",".ogg")) else "no-cache")})\n        return self._j(404, {"error": "not found"})\n    def _body',1)
open(p,'w',encoding='utf-8').write(s); print('patched')
