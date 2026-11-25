echo S4RUN:s4_mem4
grep -n "NOX_MEMORY_DB\|NOX_WOW7_MEM\|NOX_RECALL\|NOX_MEMORY_API" /workspace/nox/integration/web_core.env 2>/dev/null | cut -c1-200 | head
timeout 20 grep -ln "recall_server" /workspace/nox/integration/*.sh /workspace/nox/ops/*.sh /workspace/nox/*.sh /root/nox/*.sh 2>/dev/null | head
for f in $(timeout 20 grep -ln "recall_server" /workspace/nox/integration/*.sh /root/nox/*.sh /workspace/nox/*.sh 2>/dev/null | head -2); do grep -n "recall_server" $f | cut -c1-260; done
ls /workspace/nox/state | grep -i "mem\|s03\|recall" | head
timeout 20 find /workspace/nox/wow7 /workspace/nox/state -maxdepth 3 \( -name "*.db" -o -name "*.sqlite*" \) 2>/dev/null | head -8
sed -n 1,45p /workspace/nox/brain/DEPLOY/staged/nox-control/qs6/recall_server.py | cut -c1-200
