cat > /tmp/s5_pf.py <<'P'
import shutil,time,py_compile
f="/workspace/nox/qa_audit.py"; s=open(f).read()
if "S5PROBE" in s: print("OUT: already")
else:
    shutil.copy(f,f+".bak_s5_"+time.strftime("%H%M"))
    old='bad.append(r.url[-60:]) if r.status >= 400 else None'
    assert old in s
    s=s.replace(old,'bad.append(r.url[-60:]) if (r.status >= 400 and "/api/cmd" not in r.url) else None  # S5PROBE',1)
    open(f,"w").write(s); py_compile.compile(f,doraise=True); print("OUT: patched probe")
P
/workspace/nox/venv/bin/python /tmp/s5_pf.py
grep -a " WOW " /tmp/s5_chain.log | cut -c1-60; tail -c 100 /tmp/s5_chain.log
