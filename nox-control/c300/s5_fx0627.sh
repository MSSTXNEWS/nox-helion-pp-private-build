pkill -f s5_chain2.sh
python3 - <<'P'
import py_compile
f="/workspace/nox/qa_audit.py"; s=open(f).read()
s=s.replace('  # S5PROBE)',')  # S5PROBE')
open(f,"w").write(s); py_compile.compile(f,doraise=True); print("OUT: compiled ok")
P
grep -c S5PROBE /workspace/nox/qa_audit.py
: > /tmp/s5_chain2.log; setsid nohup bash /tmp/s5_chain2.sh >/dev/null 2>&1 < /dev/null &
sleep 40; echo "OUT: log: $(tail -c 200 /tmp/s5_chain2.log)"; ps aux | grep "qa_audit.py" | grep -v grep | wc -l
