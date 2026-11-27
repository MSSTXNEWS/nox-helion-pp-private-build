echo "K1: l1_oa2"
F=/workspace/nox/stewards/owner_active.py
[ -f $F.bak_l1_1 ] || cp $F $F.bak_l1_1
python3 - <<'P'
F="/workspace/nox/stewards/owner_active.py"
s=open(F).read()
if "L1_NICE" in s: print("already"); raise SystemExit
a="S = {}\n"
assert a in s
add=a+'''# L1_NICE 27.11: судьи и сборка DPO-пар не стопорятся (раунд идёт), но на время хода владельца получают nice 19
NRX = [("judge", r"llama-server .*--port (8300|8144|8151|8152|8141|8142) "), ("judge_py", r"(judge|gates).*\\.py"), ("build_dpo", r"build_dpo\\d*\\.py")]
NI = {}
def nice_down():
    done = []
    for name, rx in NRX:
        for pid in find(rx):
            if pid in NI or str(pid) in S: continue
            try: NI[pid] = os.getpriority(os.PRIO_PROCESS, pid); os.setpriority(os.PRIO_PROCESS, pid, 19); done.append("%s:%d" % (name, pid))
            except OSError: pass
    try:   # судья :8300 по порту
        import subprocess
        out = subprocess.run(["ss", "-ltnp"], capture_output=True, text=True).stdout
        for ln in out.splitlines():
            if ":8300 " in ln and "pid=" in ln:
                pid = int(ln.split("pid=")[1].split(",")[0])
                if pid not in NI:
                    NI[pid] = os.getpriority(os.PRIO_PROCESS, pid); os.setpriority(os.PRIO_PROCESS, pid, 19); done.append("judge8300:%d" % pid)
    except Exception: pass
    if done: log("NICE19 " + ", ".join(done))
def nice_up():
    for pid, v in list(NI.items()):
        try: os.setpriority(os.PRIO_PROCESS, pid, max(0, v))
        except OSError: pass
    if NI: log("NICE restore %d" % len(NI))
    NI.clear()
'''
s=s.replace(a,add,1)
b="        if holding: pause()\n        elif S: release("
assert b in s
s=s.replace(b,"        if holding: pause(); nice_down()\n        elif NI and not holding: nice_up()\n        if (not holding) and S: release(",1) if False else s
# проще: вставки в pause/release
s=s.replace("    if done: save(); log(\"PAUSE \" + \", \".join(done))\n","    if done: save(); log(\"PAUSE \" + \", \".join(done))\n    nice_down()\n",1)
s=s.replace("def release(why):\n","def release(why):\n    nice_up()\n",1)
open(F,"w").write(s); print("patched")
P
python3 -m py_compile $F && echo compile_ok || { cp $F.bak_l1_1 $F; echo ROLLBACK; exit 0; }
cd /workspace/nox/stewards && python3 - <<'P'
import sys,os
sys.path.insert(0,"/workspace/nox/stewards")
import owner_active as A
for n,rx in A.RX+A.NRX: print("match",n,len(A.find(rx)))
before={p:os.getpriority(os.PRIO_PROCESS,p) for n,rx in A.NRX for p in A.find(rx)}
A.nice_down(); mid=sorted(set(os.getpriority(os.PRIO_PROCESS,p) for p in before)); A.nice_up()
after=sorted(set(os.getpriority(os.PRIO_PROCESS,p) for p in before if os.path.exists("/proc/%d"%p)))
print("nice_before",sorted(set(before.values())),"during",mid,"after",after)
P
supervisorctl restart nox_owner_active | head -2; sleep 3; supervisorctl status nox_owner_active | awk '{print $2}'
