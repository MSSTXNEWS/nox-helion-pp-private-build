"""Проверка 1V14-01 на сервере: реальный ответ чата. Ключ читается на сервере и не печатается."""
import json, sys, urllib.request
sys.path.insert(0, "/root/nox/scripts")
from common import read_api_key
key = read_api_key()
def call(path, body=None):
    req = urllib.request.Request("http://127.0.0.1:8080" + path,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0), str(e)[:200]
for p in ("/api/nox/status", "/v1/models"):
    c, t = call(p); print(p, c, t[:200].replace(key, "***"))
b = {"model": "nox", "stream": False, "max_tokens": 120,
     "messages": [{"role": "user", "content": "Кто ты? Ответь одной фразой."}]}
c, t = call("/v1/chat/completions", b); print("chat", c, t[:600].replace(key, "***"))
