echo "C300: ui_lk2"; id -u
for d in /proc/[0-9]*; do for f in $d/fd/*; do t=$(readlink $f 2>/dev/null); [ "$t" = /tmp/qaa.lock ] && echo "$d $f"; done; done 2>/dev/null | awk -F/ '{print $3}' | sort -u > /tmp/holders.txt
for p in $(cat /tmp/holders.txt); do ps -o pid,ppid,etimes,stat,args -p $p 2>/dev/null | tail -1 | cut -c1-170; done
echo "== log tail"; tail -5 /workspace/nox/agent/out/qa_audit.log 2>/dev/null | cut -c1-200
