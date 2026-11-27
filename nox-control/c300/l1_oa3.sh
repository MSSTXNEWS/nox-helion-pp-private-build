echo "K1: l1_oa3"
F=/workspace/nox/stewards/owner_active.py
cp $F $F.bak_l1_2
python3 - <<'P'
F="/workspace/nox/stewards/owner_active.py"
s=open(F).read()
s=s.replace("NI = {}\n",'''NI = {}
def setnice(pid, v):   # nice в Linux потоковый: ставим на все потоки процесса
    for t in os.listdir("/proc/%d/task" % pid):
        try: os.setpriority(os.PRIO_PROCESS, int(t), v)
        except OSError: pass
''',1)
s=s.replace("os.setpriority(os.PRIO_PROCESS, pid, 19)","setnice(pid, 19)")
s=s.replace("os.setpriority(os.PRIO_PROCESS, pid, max(0, v))","setnice(pid, max(0, v))")
open(F,"w").write(s)
P
python3 -m py_compile $F && echo compile_ok || { cp $F.bak_l1_2 $F; echo ROLLBACK; exit 0; }
python3 - <<'P'
import sys,os
sys.path.insert(0,"/workspace/nox/stewards")
import owner_active as A
pids=sorted({p for n,rx in A.NRX for p in A.find(rx)})
def nices(): return sorted({os.getpriority(os.PRIO_PROCESS,int(t)) for p in pids if os.path.exists("/proc/%d"%p) for t in os.listdir("/proc/%d/task"%p)})
b=nices(); A.nice_down(); m=nices(); A.nice_up(); a=nices()
print("threads_nice before",b,"during",m,"after",a)
P
supervisorctl restart nox_owner_active | tail -1; sleep 3; supervisorctl status nox_owner_active | awk '{print $2}'
