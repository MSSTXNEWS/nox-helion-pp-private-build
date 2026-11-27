echo "K1: l1_slot3"
for p in 8510 8090 8793 18217; do pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$pid" ] && echo "port $p script=$(tr '\0' ' ' </proc/$pid/cmdline | grep -oE '[A-Za-z0-9_/.-]+\.py' | head -1)"; done
cd /workspace/nox
for f in $(for p in 8510 8090 8793 18217; do pid=$(ss -ltnp | grep ":$p " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); [ -n "$pid" ] && tr '\0' ' ' </proc/$pid/cmdline | grep -oE '[A-Za-z0-9_/.-]+\.py' | head -1; done | sort -u); do [ -f "$f" ] || f=$(find /workspace/nox -name "$(basename $f)" -not -path "*/node_modules/*" 2>/dev/null | head -1); echo "$f id_slot=$(grep -c id_slot $f) refs8104=$(grep -c 8104 $f)"; grep -n "8104" $f | grep -v "^.*#" | cut -c1-170 | head -4; done
