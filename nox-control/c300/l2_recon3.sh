echo "K1: l2_recon3"
N=/workspace/nox
ss -ltnp | grep -E ":18215|:18217|:8082|:8104|:8105" | awk '{print $4,$6}' | cut -c1-120
python3 -c "import json;d=json.load(open('$N/state/persona.json'));print({k:v for k,v in d.items() if k!='system_hint'})"
ls $N/state | head -60; ls -la $N/state/chat_fast.off 2>&1|head -1
pid=$(ss -ltnp | grep ":18215 " | sed 's/.*pid=\([0-9]*\).*/\1/'); echo pid=$pid; tr '\0' ' ' </proc/$pid/cmdline; echo; ls -l /proc/$pid/cwd
d=$(readlink /proc/$pid/cwd); f=$(tr '\0' '\n' </proc/$pid/cmdline | grep '\.py$' | head -1); echo "file=$f"
wc -l $f 2>/dev/null; grep -n -i -E "mem0|def |sqlite|embed|8082|s03|\.db|recall" $f | head -90
