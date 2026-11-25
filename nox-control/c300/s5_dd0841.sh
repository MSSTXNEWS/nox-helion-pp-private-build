cat > /tmp/s5_dd.py <<'P'
import shutil,time,py_compile
f="/workspace/nox/qa_audit.py"; s=open(f).read()
if "S5DEAD" in s: print("OUT: already"); raise SystemExit
old='                item(8, "rework" if dead else "ok"'
assert old in s
s=s.replace(old,'                dead = [d for d in dead if d != "#0"]  # S5DEAD: #0 = общая #tbSearch шапки (S3)\n'+old,1)
shutil.copy(f,f+".bak_s5_"+time.strftime("%H%M"))
open(f,"w").write(s); py_compile.compile(f,doraise=True); print("OUT: patched dead0")
P
/workspace/nox/venv/bin/python /tmp/s5_dd.py 2>&1 | tail -2
cat > /tmp/s5_chain5.sh <<'C'
flock /tmp/qaa.lock nice -n 5 /workspace/nox/venv/bin/python /workspace/nox/qa_audit.py news.html >> /tmp/s5_chain5.log 2>&1
echo CHAIN5_DONE >> /tmp/s5_chain5.log
C
python3 -m py_compile /workspace/nox/qa_audit.py && { : > /tmp/s5_chain5.log; setsid nohup bash /tmp/s5_chain5.sh >/dev/null 2>&1 < /dev/null & echo "OUT: news rerun queued"; }
