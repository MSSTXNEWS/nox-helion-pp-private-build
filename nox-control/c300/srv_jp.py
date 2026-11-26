import sys,shutil,time,py_compile
F="/workspace/nox/judges/judge_service.py"; s=open(F,encoding="utf-8").read()
if "FAST_P3" in s: print("already"); sys.exit(0)
shutil.copy(F,F+".bak_fast_%d"%int(time.time()))
a="class JudgeIn(BaseModel):\n    text: str\n"; assert s.count(a)==1
s=s.replace(a,a+"    fast: Optional[bool] = False  # FAST_P3: лёгкий набор судей (verdict чата <=8 с); автоматически в фазе train для приоритетных запросов\n",1)
b="    todo = [(r, j) for r, j in LOADED.items() if j[\"kind\"] != \"emb\" and (req.deep or not j[\"deep\"])\n            and not (j[\"kind\"] == \"minicheck\" and not req.source)]\n"
assert s.count(b)==1
c=b+'''    if (req.fast or (prio and _train_phase())) and not req.deep:   # FAST_P3: нужные для p_good и флагов: reward-0.6B, rejection, rucola, formal, MI, токсичность x2, Qwen3Guard
        _FAST = re.compile(r"Skywork-Reward-V2-Qwen3-0\\.6B|rejection|rucola|formality|motivational|rubert-tiny-toxicity|russian_toxicity|Qwen3Guard", re.I)
        todo = [(r, j) for r, j in todo if _FAST.search(r)]
'''
s=s.replace(b,c,1)
if "\nimport re" not in s and "import re," not in s and ", re" not in s.split("\n",30)[-1][:0]:
    s=s.replace("from fastapi import","import re\nfrom fastapi import",1)
open(F,"w",encoding="utf-8").write(s); py_compile.compile(F,doraise=True); print("patched")
