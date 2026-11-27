echo "K1: l1_oa1"
pid=$(supervisorctl pid nox_owner_active); echo "pid=$pid"
f=$(tr '\0' ' ' </proc/$pid/cmdline | grep -oE '[A-Za-z0-9_/.-]+\.(py|sh)' | head -1); echo "script=$f"
[ -f "$f" ] || f=$(find /workspace/nox -name "$(basename $f)" 2>/dev/null | head -1); echo "path=$f lines=$(wc -l <$f)"
cut -c1-200 $f | head -150
