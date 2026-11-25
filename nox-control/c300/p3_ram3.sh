#!/bin/bash
echo "== serve_stack 8104"; grep -n -B3 -A6 -- "8104" /workspace/nox/serve/serve_stack.sh | cut -c1-300 | head -40
echo "== restart.sh 8104"; grep -n -- "8104" /workspace/nox/serve/restart.sh | cut -c1-260 | head
echo "== nox_agents refs to 8104"; grep -rn --include=*.py --include=*.yaml --include=*.json --include=*.env -E "8104" /workspace/nox/agents /workspace/nox/agent/nox_agents 2>/dev/null | cut -c1-200 | head -12
grep -rn -E "8104" /workspace/nox/state/*.json 2>/dev/null | cut -c1-160 | head -5
echo "== t17 client"; ps -o pid,etimes,args -p 1415768 | cut -c1-200
echo "== mlock test"; python3 - <<'PY'
import mmap,ctypes,os
libc=ctypes.CDLL("libc.so.6",use_errno=True)
m=mmap.mmap(-1,2<<30); a=ctypes.c_void_p.from_buffer(m)
r=libc.mlock(ctypes.c_void_p(ctypes.addressof(ctypes.c_char.from_buffer(m))),ctypes.c_size_t(2<<30)); print("mlock 2GB rc",r,os.strerror(ctypes.get_errno()) if r else "ok")
PY
grep -E "Cap(Eff|Bnd)" /proc/self/status; ulimit -l
echo "== 8104 log tail"; tail -n 8 /workspace/nox/agent/out/nox_8104.log | cut -c1-200
echo "== vmtouch/numactl"; which vmtouch numactl pidstat perf 2>&1 | head
echo "== disk read device"; cat /proc/pressure/io | head -1; lsblk -d -o NAME,ROTA,SIZE 2>/dev/null | head -5; df -h /workspace | tail -1
