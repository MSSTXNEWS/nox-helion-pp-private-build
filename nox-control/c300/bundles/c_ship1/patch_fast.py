p="/workspace/nox/svc/pipeline/pipeline_svc.py"; s=open(p,encoding="utf-8").read()
a='L.sort(key=lambda m: m.get("latency_ms") or 9999)'
assert a in s
s=s.replace(a,'import re as _re; L.sort(key=lambda m: (1 if _re.search(r"coder|code|embed|tiny|vision|tts|image|guard|1b|0\\.5b", m["id"], _re.I) else 0, m.get("latency_ms") or 9999))',1)
a2='SYS_FAST = "Ты NOX'
assert a2 in s
s=s.replace(a2,'SYS_FAST = "Всегда отвечай только по-русски, без иероглифов. Ты NOX',1)
open(p,"w",encoding="utf-8").write(s); print("fast patched")
