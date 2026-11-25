import sys
p="/workspace/nox/web/pkg/server/chat_core.py"; s=open(p,encoding="utf-8").read()
if "advisors_unavailable" in s: print("race2 already"); sys.exit(0)
a='            t1 = time.time(); r = _living_call_t('
assert s.count(a)==1
s=s.replace(a,'            out({"t": "stage", "text": "локальная модель думает долго, спрашиваю советника…"})\n'+a,1)
b='            if not txt: return\n'
assert s.count(b)==1
s=s.replace(b,'            if not txt:\n                out({"t": "stage", "text": "советники сейчас недоступны (лимит/сбой), жду локальную модель…", "code": "advisors_unavailable"}); return\n',1)
open(p,"w",encoding="utf-8").write(s); print("race2 patched")
