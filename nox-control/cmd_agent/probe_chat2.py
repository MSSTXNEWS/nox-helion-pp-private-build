"""1V14-01: разные формы запроса к чату. Ключ не печатается."""
import json, sys, urllib.request, subprocess
sys.path.insert(0, "/root/nox/scripts")
from common import read_api_key
key = read_api_key()
def call(body):
    req = urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=150) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return getattr(e, "code", 0), str(e)[:200]
m = [{"role": "user", "content": "Скажи привет одним словом."}]
for name, b in (("nostream", {"messages": m, "max_tokens": 60}),
                ("stream", {"messages": m, "max_tokens": 60, "stream": True})):
    c, t = call(b)
    print(name, c, len(t), t[:350].replace("\n", " ").encode("ascii", "replace").decode())
print("--- proxy.log tail")
print(subprocess.run("tail -8 /root/nox/logs/proxy.log | cut -c1-200 | iconv -f utf-8 -t ascii//TRANSLIT -c", shell=True, capture_output=True, text=True).stdout)
