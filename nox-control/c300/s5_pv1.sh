cat > /tmp/s5_pv.py <<'P'
import sys,shutil,time,py_compile
f="/workspace/nox/qa_audit.py"; s=open(f).read()
if "S5PARSE" in s: print("OUT: already"); sys.exit()
shutil.copy(f,f+".bak_s5_"+time.strftime("%H%M"))
s=s.replace('"max_tokens": 1500','"max_tokens": 3500',1)
old='    try: j = json.loads(m.group(0)) if m else {}\n    except Exception: pass\n'
new=old+'''    if not j:  # S5PARSE: JSON обрезан/невалиден — достаём числа регэкспом
        for kk in ("wow", "A", "R", "U"):
            mm = re.search(r'"%s"\\s*:\\s*([0-9.]+)' % kk, v)
            if mm: j[kk] = float(mm.group(1))
        j["handmade"] = bool(re.search(r'"handmade"\\s*:\\s*true', v)); j["neon"] = bool(re.search(r'"neon"\\s*:\\s*true', v)); j["overlap"] = bool(re.search(r'"overlap"\\s*:\\s*true', v))
        if "wow" not in j: j = {}
'''
assert old in s
open(f,"w").write(s.replace(old,new,1)); py_compile.compile(f,doraise=True); print("OUT: patched")
P
/workspace/nox/venv/bin/python /tmp/s5_pv.py
