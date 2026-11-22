import re, shutil, subprocess
p="/root/nox/repo/nox-control/voice/textproc.py"; s=open(p).read(); shutil.copy(p,p+".bak_nox")
m=re.search(r"def clean_for_tts\(([^)]*)\):\n((?:\s+\"\"\".*?\"\"\"\n)?)", s, re.S)
arg=m.group(1).split(",")[0].split("=")[0].strip()
ins='    %s = re.sub(r"\\bNOX\\b", "Нокс", re.sub(r"\\bNOX HELION\\b", "Нокс Хелион", %s or ""))\n' % (arg, arg)
if "Нокс Хелион" not in s:
    s=s[:m.end()]+ins+s[m.end():]
    if not re.search(r"^import re|^import .*\bre\b", s, re.M): s="import re\n"+s
open(p,"w").write(s); r=subprocess.run(["python3","-m","py_compile",p],capture_output=True,text=True); print("compile",r.returncode,r.stderr[-200:])
if r.returncode: shutil.copy(p+".bak_nox",p); print("REVERTED")
